import {
  resolveCheckpointExecutionState,
  visibleExecutionJob,
} from "../utils.js";
import { reduceProjectDetailState } from "./projectStateReducer.js";

const DEFAULT_PLANNING_STAGE_LABELS = Object.freeze({
  context_scan: "Scan repository context",
  planner_a: "Planner Agent A",
  planner_b: "Planner Agent B",
  finalize: "Validate and save plan",
});

const REFRESH_EVENT_TYPES = new Set([
  "step-started",
  "step-finished",
  "batch-finished",
  "closeout-finished",
  "run-paused",
  "ml-cycle-stopped",
]);

function normalizedText(value = "") {
  return String(value || "").trim();
}

function normalizedRepoId(detail = null) {
  return normalizedText(detail?.project?.repo_id);
}

function parsePositiveInt(value, fallback = 0) {
  const parsed = Number.parseInt(String(value || "").trim(), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function parseTimestampMs(value = "") {
  const timestampMs = Date.parse(String(value || "").trim());
  return Number.isFinite(timestampMs) ? timestampMs : null;
}

function normalizePlanningStatus(value = "") {
  const normalized = normalizedText(value).toLowerCase();
  if (["completed", "failed", "running"].includes(normalized)) {
    return normalized;
  }
  return "running";
}

function isTerminalPlanningEvent(record = null) {
  if (!record) {
    return false;
  }
  const eventType = normalizedText(record.eventType).toLowerCase();
  const status = normalizedText(record.details?.status).toLowerCase();
  return eventType === "plan-stopped" || ["stopped", "cancelled", "canceled"].includes(status);
}

function planningStageLabel(stageKey = "", fallbackLabel = "") {
  const explicit = normalizedText(fallbackLabel);
  if (explicit) {
    return explicit;
  }
  const known = DEFAULT_PLANNING_STAGE_LABELS[normalizedText(stageKey).toLowerCase()];
  if (known) {
    return known;
  }
  const derived = normalizedText(stageKey).replaceAll("_", " ");
  if (!derived) {
    return "";
  }
  return derived.charAt(0).toUpperCase() + derived.slice(1);
}

function uniquePrepend(items = [], nextItem, limit = 8) {
  const nextItems = Array.isArray(items) ? items.filter(Boolean) : [];
  if (!nextItem) {
    return nextItems.slice(0, limit);
  }
  const serialized = JSON.stringify(nextItem);
  const filtered = nextItems.filter((item) => JSON.stringify(item) !== serialized);
  return [nextItem, ...filtered].slice(0, limit);
}

function normalizedExecutionMode(plan = null, record = null) {
  const eventMode = normalizedText(record?.details?.execution_mode).toLowerCase();
  if (eventMode) {
    return eventMode;
  }
  return normalizedText(plan?.execution_mode).toLowerCase();
}

function terminalStepStatus(status = "") {
  return ["completed", "failed"].includes(normalizedText(status).toLowerCase());
}

function patchCheckpointsFromRunEvent(checkpoints = null, record = null, loopState = null, activeJob = null) {
  if (!checkpoints || typeof checkpoints !== "object" || !record) {
    return checkpoints;
  }
  if (!["project-state-synced", "checkpoint-approved"].includes(record.eventType)) {
    return checkpoints;
  }

  if (record.eventType === "checkpoint-approved") {
    const nextItems = (Array.isArray(checkpoints.items) ? checkpoints.items : []).map((item) => {
      if (!item || typeof item !== "object") {
        return item;
      }
      const status = normalizedText(item.status).toLowerCase();
      if (status === "awaiting_review") {
        return {
          ...item,
          status: "approved",
        };
      }
      return item;
    });
    return {
      ...checkpoints,
      current_checkpoint_id: null,
      current_checkpoint_lineage_id: null,
      items: nextItems,
      pending: null,
    };
  }

  const checkpointState = resolveCheckpointExecutionState(
    {
      project: {
        current_status: normalizedText(record.projectStatus || ""),
      },
      loop_state: {
        ...(loopState && typeof loopState === "object" ? loopState : {}),
        current_checkpoint_id: record.eventType === "project-state-synced"
          ? normalizedText(record.details?.current_checkpoint_id)
          : normalizedText(loopState?.current_checkpoint_id),
        current_checkpoint_lineage_id: record.eventType === "project-state-synced"
          ? normalizedText(record.details?.current_checkpoint_lineage_id)
          : normalizedText(loopState?.current_checkpoint_lineage_id),
        pending_checkpoint_approval:
          record.eventType === "checkpoint-approved"
            ? false
            : record.eventType === "project-state-synced" && record.details?.pending_checkpoint_approval !== undefined
              ? Boolean(record.details.pending_checkpoint_approval)
              : Boolean(loopState?.pending_checkpoint_approval),
      },
      checkpoints,
    },
    activeJob,
  );

  const nextPending = checkpointState.waitingForApproval
    ? (checkpointState.pending ? { ...checkpointState.pending } : null)
    : null;
  const nextCurrentCheckpointId = checkpointState.processActive ? checkpointState.currentCheckpointId : null;
  const nextCurrentCheckpointLineageId = checkpointState.processActive ? checkpointState.currentCheckpointLineageId : null;
  const items = Array.isArray(checkpointState.items) ? checkpointState.items : [];
  const changed =
    normalizedText(nextPending?.checkpoint_id) !== normalizedText(checkpoints?.pending?.checkpoint_id)
    || normalizedText(nextPending?.status) !== normalizedText(checkpoints?.pending?.status)
    || normalizedText(nextCurrentCheckpointId) !== normalizedText(checkpoints?.current_checkpoint_id)
    || normalizedText(nextCurrentCheckpointLineageId) !== normalizedText(checkpoints?.current_checkpoint_lineage_id)
    || items !== checkpoints.items;

  if (!changed) {
    return checkpoints;
  }
  return {
    ...checkpoints,
    current_checkpoint_id: nextCurrentCheckpointId,
    current_checkpoint_lineage_id: nextCurrentCheckpointLineageId,
    items,
    pending: nextPending,
  };
}

function patchPlanFromRunEvent(plan = null, record = null) {
  if (!plan || typeof plan !== "object" || !record) {
    return plan;
  }
  const steps = Array.isArray(plan.steps) ? plan.steps : [];
  const eventType = record.eventType;
  const executionMode = normalizedExecutionMode(plan, record);
  const isParallel = executionMode === "parallel";
  const detailStepId = normalizedText(record.details?.step_id);
  const detailStepIds = Array.isArray(record.details?.step_ids)
    ? record.details.step_ids.map((value) => normalizedText(value)).filter(Boolean)
    : [];
  const detailStatuses = record.details?.statuses && typeof record.details.statuses === "object"
    ? record.details.statuses
    : null;
  let changed = false;
  const nextSteps = steps.map((step) => {
    if (!step || typeof step !== "object") {
      return step;
    }
    const stepId = normalizedText(step.step_id);
    const stepStatus = normalizedText(step.status).toLowerCase();
    if (!stepId) {
      return step;
    }
    if (eventType === "step-started") {
      if (stepId === detailStepId) {
        changed = true;
        return {
          ...step,
          status: "running",
          started_at: normalizedText(step.started_at) || record.timestamp || step.started_at,
          notes: "",
        };
      }
      if (!isParallel && stepStatus === "running") {
        changed = true;
        return {
          ...step,
          status: "paused",
        };
      }
      return step;
    }
    if (eventType === "step-finished" && stepId === detailStepId) {
      const nextStatus = normalizedText(record.details?.status) || step.status || "completed";
      changed = true;
      return {
        ...step,
        status: nextStatus,
        completed_at: terminalStepStatus(nextStatus) ? (record.timestamp || step.completed_at) : step.completed_at,
        commit_hash: normalizedText(record.details?.commit_hash) || step.commit_hash,
      };
    }
    if (eventType === "batch-finished" && detailStatuses && Object.hasOwn(detailStatuses, stepId)) {
      const nextStatus = normalizedText(detailStatuses[stepId]) || step.status;
      changed = true;
      return {
        ...step,
        status: nextStatus,
        completed_at: terminalStepStatus(nextStatus) ? (record.timestamp || step.completed_at) : step.completed_at,
      };
    }
    if (eventType === "run-paused" && ["running", "integrating"].includes(stepStatus)) {
      changed = true;
      return {
        ...step,
        status: "paused",
      };
    }
    if (eventType === "batch-started" && detailStepIds.includes(stepId)) {
      changed = true;
      return {
        ...step,
        status: "running",
        started_at: normalizedText(step.started_at) || record.timestamp || step.started_at,
        notes: "",
      };
    }
    return step;
  });

  let nextCloseoutStatus = plan.closeout_status;
  if (eventType === "closeout-started" && normalizedText(nextCloseoutStatus).toLowerCase() !== "running") {
    nextCloseoutStatus = "running";
    changed = true;
  }
  if (eventType === "closeout-finished") {
    const finalStatus = normalizedText(record.details?.status);
    if (finalStatus && finalStatus !== normalizedText(nextCloseoutStatus)) {
      nextCloseoutStatus = finalStatus;
      changed = true;
    }
  }

  if (!changed) {
    return plan;
  }
  return {
    ...plan,
    steps: nextSteps,
    closeout_status: nextCloseoutStatus,
  };
}

export function projectUiEventRecord(eventPayload) {
  const payload = eventPayload?.payload;
  const event = payload?.event;
  if (!payload || typeof payload !== "object" || !event || typeof event !== "object") {
    return null;
  }
  return {
    repoId: normalizedText(payload.repo_id),
    projectDir: normalizedText(payload.project_dir),
    projectStatus: normalizedText(payload.project_status || payload.status),
    timestamp: normalizedText(event.timestamp),
    eventType: normalizedText(event.event_type),
    message: normalizedText(event.message),
    details: event.details && typeof event.details === "object" ? event.details : {},
    rawEvent: {
      timestamp: normalizedText(event.timestamp),
      event_type: normalizedText(event.event_type),
      message: normalizedText(event.message),
      details: event.details && typeof event.details === "object" ? event.details : {},
    },
  };
}

export function projectUiEventActivityLine(record) {
  if (!record) {
    return "";
  }
  const stepId = normalizedText(record.details?.step_id);
  const detailSuffix = stepId ? ` [${stepId}]` : "";
  return `${record.timestamp} | ${record.eventType}${detailSuffix} | ${record.message}`.trim();
}

function updatePlanningProgress(progress = null, record = null) {
  if (!record || normalizedText(record.details?.flow).toLowerCase() !== "planning") {
    return progress;
  }
  if (isTerminalPlanningEvent(record)) {
    return null;
  }
  const stageIndex = parsePositiveInt(record.details?.stage_index, 0);
  const stageCount = Math.max(parsePositiveInt(record.details?.stage_count, 0), stageIndex);
  if (!stageIndex || !stageCount) {
    return progress;
  }
  const currentStatus = normalizePlanningStatus(record.details?.status);
  const currentStageKey = normalizedText(record.details?.stage_key).toLowerCase();
  const currentStageLabel = planningStageLabel(currentStageKey, record.details?.stage_label);
  const currentAgentLabel = normalizedText(record.details?.agent_label);
  const existingStages = Array.isArray(progress?.stages) ? progress.stages : [];
  const stageMap = new Map(
    existingStages
      .filter((stage) => stage && typeof stage === "object")
      .map((stage) => [parsePositiveInt(stage.index, 0), stage]),
  );
  const stages = Array.from({ length: stageCount }, (_, offset) => {
    const index = offset + 1;
    const existing = stageMap.get(index) || {};
    const existingKey = normalizedText(existing.key).toLowerCase();
    const stageKey = index === stageIndex ? currentStageKey || existingKey : existingKey;
    const stageLabel = planningStageLabel(stageKey, index === stageIndex ? currentStageLabel : existing.label);
    const stageStatus =
      index < stageIndex
        ? "completed"
        : index === stageIndex
          ? currentStatus
          : "pending";
    return {
      key: stageKey,
      index,
      label: stageLabel,
      status: stageStatus,
      agent_label: index === stageIndex ? currentAgentLabel || normalizedText(existing.agent_label) : normalizedText(existing.agent_label),
    };
  });

  const progressUnits =
    currentStatus === "completed"
      ? stageIndex
      : currentStatus === "failed"
        ? Math.max(0, stageIndex - 0.5)
        : Math.max(0, stageIndex - 0.5);
  const percent = stageCount ? Math.max(0, Math.min(100, Math.round((progressUnits / stageCount) * 100))) : 0;
  const completedStages = currentStatus === "completed" ? stageIndex : Math.max(0, stageIndex - 1);

  return {
    stage_count: stageCount,
    completed_stages: completedStages,
    percent,
    current_stage_key: currentStageKey,
    current_stage_index: stageIndex,
    current_stage_label: currentStageLabel,
    current_stage_status: currentStatus,
    current_agent_label: currentAgentLabel,
    message: record.message,
    event_type: record.eventType,
    stages,
  };
}

export function shouldRefreshProjectDetailForUiEvent(eventPayload) {
  const record = projectUiEventRecord(eventPayload);
  if (!record) {
    return false;
  }
  if (normalizedText(record.details?.flow).toLowerCase() === "planning") {
    return false;
  }
  return REFRESH_EVENT_TYPES.has(record.eventType);
}

export function applyProjectUiEvent(detail, eventPayload, options = {}) {
  const record = projectUiEventRecord(eventPayload);
  if (!detail || !record || normalizedRepoId(detail) !== record.repoId) {
    return detail;
  }

  const activityLimit = Math.max(1, parsePositiveInt(options.activityLimit, 8));
  const historyLimit = Math.max(1, parsePositiveInt(options.historyLimit, 40));
  const activityLine = projectUiEventActivityLine(record);
  const nextPlan = patchPlanFromRunEvent(detail.plan, record);
  const activeExecutionJob = visibleExecutionJob(options.activeJob ?? options.runningJob ?? null);
  const processStatus = normalizedText(activeExecutionJob?.status).toLowerCase();
  const processActive = Boolean(activeExecutionJob) && (processStatus === "running" || processStatus === "queued");

  const nextProject = detail.project
    ? {
        ...detail.project,
        current_status: record.projectStatus || detail.project.current_status,
        last_run_at:
          record.eventType === "project-state-synced"
            ? normalizedText(record.details?.last_run_at) || detail.project.last_run_at
            : detail.project.last_run_at,
      }
    : detail.project;

  const nextLoopState = detail.loop_state
    ? {
        ...detail.loop_state,
        current_task:
          record.eventType === "project-state-synced"
            ? (processActive ? normalizedText(record.details?.current_task) : "")
            : detail.loop_state.current_task,
        current_checkpoint_id:
          record.eventType === "project-state-synced"
            ? (processActive ? normalizedText(record.details?.current_checkpoint_id) : "")
            : detail.loop_state.current_checkpoint_id,
        current_checkpoint_lineage_id:
          record.eventType === "project-state-synced"
            ? (processActive ? normalizedText(record.details?.current_checkpoint_lineage_id) : "")
            : detail.loop_state.current_checkpoint_lineage_id,
        pending_checkpoint_approval:
          record.eventType === "project-state-synced"
            ? (processActive && record.details?.pending_checkpoint_approval !== undefined
              ? Boolean(record.details.pending_checkpoint_approval)
              : false)
            : detail.loop_state.pending_checkpoint_approval,
      }
    : detail.loop_state;
  const nextCheckpoints = patchCheckpointsFromRunEvent(detail.checkpoints, record, nextLoopState, activeExecutionJob);

  const nextActivity = activityLine
    ? uniquePrepend(detail.activity, activityLine, activityLimit)
    : Array.isArray(detail.activity) ? detail.activity : [];

  const nextHistory = detail.history && typeof detail.history === "object"
    ? {
        ...detail.history,
        ui_events: uniquePrepend(detail.history.ui_events, record.rawEvent, historyLimit),
      }
    : detail.history;

  const nextBottomPanels = detail.bottom_panels && typeof detail.bottom_panels === "object"
    ? {
        ...detail.bottom_panels,
        execution_log_lines: activityLine
          ? uniquePrepend(detail.bottom_panels.execution_log_lines, activityLine, activityLimit)
          : detail.bottom_panels.execution_log_lines,
      }
    : detail.bottom_panels;

  const nextSnapshot = detail.snapshot && typeof detail.snapshot === "object"
    ? (() => {
        const snapshot = {
          ...detail.snapshot,
          project: detail.snapshot.project && typeof detail.snapshot.project === "object"
            ? {
                ...detail.snapshot.project,
                current_status: record.projectStatus || detail.snapshot.project.current_status,
                last_run_at:
                  record.eventType === "project-state-synced"
                    ? normalizedText(record.details?.last_run_at) || detail.snapshot.project.last_run_at
                    : detail.snapshot.project.last_run_at,
              }
            : detail.snapshot.project,
          loop_state: detail.snapshot.loop_state && typeof detail.snapshot.loop_state === "object"
            ? {
                ...detail.snapshot.loop_state,
                current_task:
                  record.eventType === "project-state-synced"
                    ? (processActive ? normalizedText(record.details?.current_task) : "")
                    : detail.snapshot.loop_state.current_task,
                current_checkpoint_id:
                  record.eventType === "project-state-synced"
                    ? (processActive ? normalizedText(record.details?.current_checkpoint_id) : "")
                    : detail.snapshot.loop_state.current_checkpoint_id,
                current_checkpoint_lineage_id:
                  record.eventType === "project-state-synced"
                    ? (processActive ? normalizedText(record.details?.current_checkpoint_lineage_id) : "")
                    : detail.snapshot.loop_state.current_checkpoint_lineage_id,
                pending_checkpoint_approval:
                  record.eventType === "project-state-synced"
                    ? (processActive && record.details?.pending_checkpoint_approval !== undefined
                      ? Boolean(record.details.pending_checkpoint_approval)
                      : false)
                    : detail.snapshot.loop_state.pending_checkpoint_approval,
              }
            : detail.snapshot.loop_state,
        };
        if (detail.snapshot.plan && typeof detail.snapshot.plan === "object") {
          snapshot.plan = nextPlan;
        }
        return snapshot;
      })()
    : detail.snapshot;

  return reduceProjectDetailState({
    detail: {
      ...detail,
      project: nextProject,
      loop_state: nextLoopState,
      checkpoints: nextCheckpoints,
      activity: nextActivity,
      history: nextHistory,
      bottom_panels: nextBottomPanels,
      snapshot: nextSnapshot,
      plan: nextPlan,
      planning_progress: updatePlanningProgress(detail.planning_progress, record),
    },
    activeJob: activeExecutionJob,
    detailOptions: {
      nowMs: Number.isFinite(options?.nowMs) ? options.nowMs : (parseTimestampMs(record.timestamp) ?? undefined),
    },
  }).detail;
}
