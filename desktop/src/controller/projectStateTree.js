import {
  isChatJob,
  projectChatJobFromJobs,
  projectJobFromJobs,
  visibleExecutionJob,
} from "../domain/projectExecution.js";
import {
  deriveExecutionUiState,
  isActiveExecutionStatus,
  isPlanningProgressRunning,
  sanitizeProjectDetailForJobState,
  sanitizeProjectListForJobState,
  workspaceStatsFromProjects,
} from "../utils.js";

function normalizedText(value = "") {
  return String(value || "").trim();
}

function normalizedStatus(value = "") {
  return normalizedText(value).toLowerCase();
}

function normalizedProject(value = null) {
  return value && typeof value === "object" ? value : {};
}

function normalizedPlan(value = null) {
  return value && typeof value === "object" ? value : {};
}

function normalizedJobItems(value = null) {
  if (Array.isArray(value)) {
    return value.filter(Boolean);
  }
  return value ? [value] : [];
}

function resolveJobSource(input = {}) {
  if (Object.prototype.hasOwnProperty.call(input, "jobSource")) {
    return input.jobSource;
  }
  if (Array.isArray(input.jobs)) {
    return input.jobs;
  }
  if (Array.isArray(input.activeJob)) {
    return input.activeJob;
  }
  if (Array.isArray(input.runningJob)) {
    return input.runningJob;
  }
  return input.activeJob ?? input.runningJob ?? null;
}

export function queuedExecutionJobs(jobs = []) {
  return normalizedJobItems(jobs)
    .filter((job) => normalizedStatus(job?.status) === "queued" && !isChatJob(job))
    .sort((left, right) => {
      const leftPosition = Number.parseInt(String(left?.queue_position || 0), 10) || Number.MAX_SAFE_INTEGER;
      const rightPosition = Number.parseInt(String(right?.queue_position || 0), 10) || Number.MAX_SAFE_INTEGER;
      if (leftPosition !== rightPosition) {
        return leftPosition - rightPosition;
      }
      return (Number(left?.updated_at_ms || 0) || 0) - (Number(right?.updated_at_ms || 0) || 0);
    });
}

export function projectStateIdentity(input = {}) {
  const explicitProject = normalizedProject(input.project);
  const detailProject = normalizedProject(input.projectDetail?.project ?? input.detail?.project);
  const explicitProjectDir = normalizedText(
    input.projectDir
    || explicitProject.project_dir
    || explicitProject.repo_path
    || detailProject.repo_path,
  );
  const canUseFormProjectDir = Boolean(
    input.allowFormIdentity
    || normalizedText(input.selectedProjectId || input.repoId)
    || normalizedText(explicitProject.repo_id || detailProject.repo_id)
    || explicitProjectDir,
  );
  return {
    repo_id: normalizedText(input.selectedProjectId || input.repoId || explicitProject.repo_id || detailProject.repo_id),
    project_dir: explicitProjectDir || (canUseFormProjectDir ? normalizedText(input.projectForm?.project_dir) : ""),
    current_status: normalizedText(
      input.currentStatus
      || explicitProject.current_status
      || detailProject.current_status,
    ),
    last_run_at: normalizedText(
      input.lastRunAt
      || explicitProject.last_run_at
      || detailProject.last_run_at,
    ),
  };
}

export function buildProjectExecutionBranch(input = {}) {
  const identity = input.identity || projectStateIdentity(input);
  const jobSource = resolveJobSource(input);
  const jobs = normalizedJobItems(jobSource);
  const selectedJob = projectJobFromJobs(jobs, identity);
  const activeJob = visibleExecutionJob(selectedJob);
  const chatJob = projectChatJobFromJobs(jobs, identity);
  const queuedJobs = queuedExecutionJobs(jobs);
  return {
    identity,
    jobSource,
    jobs,
    selectedJob,
    activeJob,
    chatJob,
    queuedJobs,
    stoppableJob: activeJob || null,
    chatStoppableJob: chatJob || null,
  };
}

export function buildProjectUiBranch(input = {}) {
  const execution = input.execution || buildProjectExecutionBranch(input);
  const detail = input.detail ?? input.projectDetail ?? null;
  const planDraft = normalizedPlan(input.planDraft);
  const executionState = deriveExecutionUiState(detail, planDraft, execution.activeJob);
  const displayStatus = normalizedStatus(executionState.displayStatusValue);
  const hasProjectTarget = Boolean(
    normalizedText(input.identity?.project_dir || detail?.project?.repo_path || input.projectForm?.project_dir),
  );
  const hasRunnablePlan = Array.isArray(executionState.livePlan?.steps) && executionState.livePlan.steps.length > 0;
  const runActionRunning = displayStatus === "running" || displayStatus.startsWith("running:");
  const runActionDisabled = Boolean(
    input.pendingAction
    || input.startingJobCount > 0
    || !hasProjectTarget
    || !hasRunnablePlan
    || !executionState.consistent
    || isActiveExecutionStatus(displayStatus)
    || isPlanningProgressRunning(detail?.planning_progress)
    || executionState.checkpointFamily === "checkpoint",
  );
  return {
    busy: Boolean(
      input.pendingAction
      || input.startingJobCount > 0
      || ["queued", "running"].includes(normalizedStatus(execution.activeJob?.status))
    ),
    canRequestStop: runActionRunning || normalizedStatus(execution.stoppableJob?.status) === "running",
    canRequestChatStop: ["queued", "running"].includes(normalizedStatus(execution.chatStoppableJob?.status)),
    canCancelReservation: normalizedStatus(execution.activeJob?.status) === "queued",
    hasRunnablePlan,
    runActionDisabled,
    runActionRunning,
    canRunPlan: !runActionDisabled,
  };
}

export function buildProjectDetailBranch(input = {}) {
  const detail = input.detail ?? input.projectDetail ?? null;
  if (!detail) {
    return {
      raw: detail,
      normalized: detail,
    };
  }
  const jobSource = input.execution?.jobSource ?? resolveJobSource(input);
  return {
    raw: detail,
    normalized: sanitizeProjectDetailForJobState(detail, jobSource, input.detailOptions || {}),
  };
}

export function buildProjectListingBranch(input = {}) {
  const projects = Array.isArray(input.projects) ? input.projects : [];
  const jobSource = input.execution?.jobSource ?? resolveJobSource(input);
  const normalized = sanitizeProjectListForJobState(projects, jobSource, input.listingOptions || {});
  return {
    raw: projects,
    normalized,
    workspaceStats: workspaceStatsFromProjects(normalized),
  };
}

export function buildProjectStateTree(input = {}) {
  const identity = projectStateIdentity(input);
  const execution = buildProjectExecutionBranch({
    ...input,
    identity,
  });
  const tree = {
    identity,
    execution,
    ui: buildProjectUiBranch({
      ...input,
      execution,
    }),
  };
  if (Object.prototype.hasOwnProperty.call(input, "detail") || Object.prototype.hasOwnProperty.call(input, "projectDetail")) {
    tree.detail = buildProjectDetailBranch({
      ...input,
      execution,
    });
  }
  if (Object.prototype.hasOwnProperty.call(input, "projects")) {
    tree.listing = buildProjectListingBranch({
      ...input,
      execution,
    });
  }
  return tree;
}
