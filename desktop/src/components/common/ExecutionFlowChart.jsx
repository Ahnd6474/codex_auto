import { memo, useId, useMemo, useState } from "react";
import { displayStatus } from "../../locale";
import { deriveExecutionUiState, effectiveStepStatus, failureReasonLabel, isDebuggingStatus, statusTone } from "../../utils";

const FONT_FAMILY = '"Segoe UI", "Malgun Gothic", sans-serif';
const BOX_WIDTH = 220;
const BOX_HEIGHT = 136;
const MARGIN_X = 48;
const MARGIN_Y = 72;
const GAP_X = 120;
const GAP_Y = 30;
const SPLIT_GAP = 44;
const MERGE_GAP = 38;

const PALETTE = {
  neutral: { fill: "var(--bg-panel-alt)", stroke: "var(--border)", text: "var(--text)", meta: "var(--text-muted)" },
  info: { fill: "#e0f2fe", stroke: "#0284c7", text: "#082f49", meta: "#0369a1" },
  success: { fill: "#dcfce7", stroke: "#16a34a", text: "#14532d", meta: "#15803d" },
  warning: { fill: "#fef3c7", stroke: "#d97706", text: "#78350f", meta: "#b45309" },
  danger: { fill: "#fee2e2", stroke: "#dc2626", text: "#7f1d1d", meta: "#b91c1c" },
};
const EDGE_STROKE = "#94a3b8";
const EDGE_FILL = "#ffffff";
const SELECTED_STROKE = "#0f172a";
const TOPOLOGY_CACHE_LIMIT = 24;
const chartTopologyCache = new Map();

function compactChartText(value, maxChars) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text) {
    return "";
  }
  if (text.length <= maxChars) {
    return text;
  }
  return `${text.slice(0, Math.max(0, maxChars - 3)).trimEnd()}...`;
}

function wrapChartText(value, maxCharsPerLine, maxLines = 2) {
  const text = compactChartText(value, maxCharsPerLine * maxLines + 8);
  if (!text) {
    return [];
  }
  const words = text.split(/\s+/).filter(Boolean);
  const lines = [];
  let current = "";
  for (const word of words) {
    const candidate = current ? `${current} ${word}` : word;
    if (candidate.length <= maxCharsPerLine) {
      current = candidate;
      continue;
    }
    if (current) {
      lines.push(current);
    }
    current = word;
    if (lines.length >= maxLines - 1) {
      break;
    }
  }
  if (current && lines.length < maxLines) {
    lines.push(current);
  }
  if (!lines.length) {
    lines.push(text.slice(0, maxCharsPerLine));
  }
  const trimmed = lines.slice(0, maxLines);
  const usedText = trimmed.join(" ");
  if (text.length > usedText.length && trimmed.length) {
    trimmed[trimmed.length - 1] = compactChartText(trimmed[trimmed.length - 1], maxCharsPerLine);
  }
  return trimmed;
}

function SvgTextBlock({ x, y, lines, fill, fontSize, fontWeight = "400", lineHeight = 16 }) {
  const safeLines = Array.isArray(lines) ? lines.filter(Boolean) : [];
  if (!safeLines.length) {
    return null;
  }
  return (
    <text x={x} y={y} fill={fill} fontFamily={FONT_FAMILY} fontSize={fontSize} fontWeight={fontWeight}>
      {safeLines.map((line, index) => (
        <tspan key={`${x}-${y}-${index}`} x={x} dy={index === 0 ? 0 : lineHeight}>
          {line}
        </tspan>
      ))}
    </text>
  );
}

function buildChartLevels(steps = []) {
  const orderedSteps = Array.isArray(steps) ? steps : [];
  if (!orderedSteps.length) {
    return [];
  }
  const usesDag = orderedSteps.some((step) => (step.depends_on || []).length || (step.owned_paths || []).length);
  if (!usesDag) {
    return orderedSteps.map((step) => [step]);
  }
  const stepById = new Map(orderedSteps.map((step) => [step.step_id, step]));
  const visited = new Set();
  const levels = [];
  while (visited.size < orderedSteps.length) {
    const ready = orderedSteps.filter(
      (step) =>
        !visited.has(step.step_id) &&
        (step.depends_on || []).every((dependency) => visited.has(dependency) || !stepById.has(dependency)),
    );
    const layer = ready.length ? ready : orderedSteps.filter((step) => !visited.has(step.step_id)).slice(0, 1);
    levels.push(layer);
    layer.forEach((step) => visited.add(step.step_id));
  }
  return levels;
}

function levelRowOrderSignature(level = []) {
  return level.map((step) => String(step?.step_id || "")).join("|");
}

function averageIndex(values = []) {
  if (!values.length) {
    return null;
  }
  return values.reduce((total, value) => total + value, 0) / values.length;
}

function orderChartLevels(levels = []) {
  const normalizedLevels = (levels || []).map((level) => [...level]);
  if (normalizedLevels.length <= 2) {
    return normalizedLevels;
  }
  let changed = true;
  let guard = 0;
  while (changed && guard < 6) {
    changed = false;
    guard += 1;
    for (let levelIndex = 1; levelIndex < normalizedLevels.length; levelIndex += 1) {
      const previousLevel = normalizedLevels[levelIndex - 1] || [];
      const indexByStepId = new Map(previousLevel.map((step, index) => [step.step_id, index]));
      const nextOrder = [...normalizedLevels[levelIndex]].sort((left, right) => {
        const leftParents = (left.depends_on || []).map((dependency) => indexByStepId.get(dependency)).filter((value) => Number.isFinite(value));
        const rightParents = (right.depends_on || []).map((dependency) => indexByStepId.get(dependency)).filter((value) => Number.isFinite(value));
        const leftScore = averageIndex(leftParents);
        const rightScore = averageIndex(rightParents);
        if (leftScore == null && rightScore == null) {
          return String(left.step_id || "").localeCompare(String(right.step_id || ""));
        }
        if (leftScore == null) {
          return 1;
        }
        if (rightScore == null) {
          return -1;
        }
        if (leftScore !== rightScore) {
          return leftScore - rightScore;
        }
        return String(left.step_id || "").localeCompare(String(right.step_id || ""));
      });
      if (levelRowOrderSignature(nextOrder) !== levelRowOrderSignature(normalizedLevels[levelIndex])) {
        normalizedLevels[levelIndex] = nextOrder;
        changed = true;
      }
    }
    for (let levelIndex = normalizedLevels.length - 2; levelIndex >= 0; levelIndex -= 1) {
      const nextLevel = normalizedLevels[levelIndex + 1] || [];
      const childIndexById = new Map(nextLevel.map((step, index) => [step.step_id, index]));
      const nextOrder = [...normalizedLevels[levelIndex]].sort((left, right) => {
        const leftChildren = nextLevel
          .filter((step) => (step.depends_on || []).includes(left.step_id))
          .map((step) => childIndexById.get(step.step_id))
          .filter((value) => Number.isFinite(value));
        const rightChildren = nextLevel
          .filter((step) => (step.depends_on || []).includes(right.step_id))
          .map((step) => childIndexById.get(step.step_id))
          .filter((value) => Number.isFinite(value));
        const leftScore = averageIndex(leftChildren);
        const rightScore = averageIndex(rightChildren);
        if (leftScore == null && rightScore == null) {
          return String(left.step_id || "").localeCompare(String(right.step_id || ""));
        }
        if (leftScore == null) {
          return 1;
        }
        if (rightScore == null) {
          return -1;
        }
        if (leftScore !== rightScore) {
          return leftScore - rightScore;
        }
        return String(left.step_id || "").localeCompare(String(right.step_id || ""));
      });
      if (levelRowOrderSignature(nextOrder) !== levelRowOrderSignature(normalizedLevels[levelIndex])) {
        normalizedLevels[levelIndex] = nextOrder;
        changed = true;
      }
    }
  }
  return normalizedLevels;
}

function orthogonalPath(startX, startY, endX, endY) {
  if (startX === endX && startY === endY) {
    return `M ${startX} ${startY}`;
  }
  if (startY === endY) {
    return `M ${startX} ${startY} H ${endX}`;
  }
  const middleX = Math.round(startX + (endX - startX) / 2);
  return `M ${startX} ${startY} H ${middleX} V ${endY} H ${endX}`;
}

function chartTopologySignature(steps = []) {
  return (steps || [])
    .map((step) => [
      step?.step_id || "",
      (step?.depends_on || []).join(","),
      (step?.owned_paths || []).length,
    ].join("|"))
    .join("::");
}

function resolveChartNodeVisuals(status = "", fallbackStatus = "") {
  const resolvedStatus = String(status || "").trim().toLowerCase() || String(fallbackStatus || "").trim().toLowerCase();
  const tone = statusTone(resolvedStatus);
  return {
    tone,
    palette: PALETTE[tone] || PALETTE.warning,
  };
}

function buildChartTopology(steps = []) {
  const levels = orderChartLevels(buildChartLevels(steps));
  const positions = new Map();
  const maxRows = Math.max(1, ...levels.map((level) => level.length));
  const contentHeight = maxRows * BOX_HEIGHT + Math.max(0, maxRows - 1) * GAP_Y;
  const width = Math.max(960, MARGIN_X * 2 + levels.length * BOX_WIDTH + Math.max(0, levels.length - 1) * GAP_X);
  const height = Math.max(320, MARGIN_Y * 2 + contentHeight);

  levels.forEach((level, levelIndex) => {
    const x = MARGIN_X + levelIndex * (BOX_WIDTH + GAP_X);
    const levelHeight = level.length * BOX_HEIGHT + Math.max(0, level.length - 1) * GAP_Y;
    const offsetY = MARGIN_Y + Math.max(0, (contentHeight - levelHeight) / 2);
    level.forEach((step, rowIndex) => {
      const y = offsetY + rowIndex * (BOX_HEIGHT + GAP_Y);
      positions.set(step.step_id, { x, y });
    });
  });

  const incoming = new Map(steps.map((step) => [step.step_id, []]));
  const outgoing = new Map(steps.map((step) => [step.step_id, []]));
  steps.forEach((step) => {
    (step.depends_on || []).forEach((dependency) => {
      if (!positions.has(dependency)) {
        return;
      }
      incoming.get(step.step_id)?.push(dependency);
      outgoing.get(dependency)?.push(step.step_id);
    });
  });

  const nodes = steps
    .filter((step) => positions.has(step.step_id))
    .map((step) => {
      const { x, y } = positions.get(step.step_id);
      const failureReason = failureReasonLabel(step, "en");
      return {
        step,
        x,
        y,
        titleLines: wrapChartText(step.title, 24, 2),
        detailSource:
          failureReason ||
          step.display_description ||
          step.success_criteria ||
          ((step.depends_on || []).length ? (step.depends_on || []).join(", ") : "") ||
          ((step.owned_paths || []).length ? `${step.owned_paths.length} owned path(s)` : "No summary"),
      };
    });

  const splitJunctions = [];
  const mergeJunctions = [];
  const nodeToSplitSegments = [];
  const mergeBusSegments = [];
  const mergeToNodeSegments = [];
  const edgeSegments = [];

  const splitById = new Map();
  const mergeById = new Map();

  steps.forEach((step) => {
    if (!positions.has(step.step_id)) {
      return;
    }
    const { x, y } = positions.get(step.step_id);
    const targets = outgoing.get(step.step_id) || [];
    const parents = incoming.get(step.step_id) || [];
    const centerY = y + BOX_HEIGHT / 2;
    if (targets.length > 1) {
      const junction = { x: x + BOX_WIDTH + SPLIT_GAP, y: centerY };
      splitById.set(step.step_id, junction);
      splitJunctions.push(junction);
      nodeToSplitSegments.push({
        key: `${step.step_id}-split`,
        d: `M ${x + BOX_WIDTH} ${centerY} H ${junction.x}`,
      });
    }
    if (parents.length > 1) {
      const junction = { x: x - MERGE_GAP, y: centerY };
      mergeById.set(step.step_id, junction);
      mergeJunctions.push(junction);
      const parentCenterYs = parents
        .map((parentId) => positions.get(parentId))
        .filter(Boolean)
        .map((position) => position.y + BOX_HEIGHT / 2);
      const mergeSpanYs = [...parentCenterYs, centerY];
      const minY = Math.min(...mergeSpanYs);
      const maxY = Math.max(...mergeSpanYs);
      if (Number.isFinite(minY) && Number.isFinite(maxY) && minY !== maxY) {
        mergeBusSegments.push({
          key: `${step.step_id}-merge-bus`,
          d: `M ${junction.x} ${minY} V ${maxY}`,
        });
      }
      mergeToNodeSegments.push({
        key: `${step.step_id}-merge`,
        d: `M ${junction.x} ${junction.y} H ${x}`,
      });
    }
  });

  steps.forEach((step) => {
    if (!positions.has(step.step_id)) {
      return;
    }
    const targets = outgoing.get(step.step_id) || [];
    const sourcePosition = positions.get(step.step_id);
    const sourceCenter = {
      x: sourcePosition.x + BOX_WIDTH,
      y: sourcePosition.y + BOX_HEIGHT / 2,
    };
    const startPoint = splitById.get(step.step_id) || sourceCenter;
    targets.forEach((targetId) => {
      const targetPosition = positions.get(targetId);
      if (!targetPosition) {
        return;
      }
      const targetCenter = {
        x: targetPosition.x,
        y: targetPosition.y + BOX_HEIGHT / 2,
      };
      const mergePoint = mergeById.get(targetId);
      edgeSegments.push({
        key: `${step.step_id}-${targetId}`,
        d: mergePoint
          ? `M ${startPoint.x} ${startPoint.y} H ${mergePoint.x}`
          : orthogonalPath(startPoint.x, startPoint.y, targetCenter.x, targetCenter.y),
        arrow: !mergePoint,
      });
    });
  });

  return {
    width,
    height,
    nodes,
    edgeSegments,
    nodeToSplitSegments,
    mergeBusSegments,
    mergeToNodeSegments,
    splitJunctions,
    mergeJunctions,
  };
}

function getChartTopology(steps = []) {
  const signature = chartTopologySignature(steps);
  const cached = chartTopologyCache.get(signature);
  if (cached) {
    return cached;
  }
  const topology = buildChartTopology(steps);
  if (chartTopologyCache.size >= TOPOLOGY_CACHE_LIMIT) {
    const oldestKey = chartTopologyCache.keys().next().value;
    chartTopologyCache.delete(oldestKey);
  }
  chartTopologyCache.set(signature, topology);
  return topology;
}

function effectiveChartStepStatus(step = null, projectStatus = "", activeLineageId = "", checkpointState = null, checkpointFamily = "") {
  const currentStatus = effectiveStepStatus(step, projectStatus);
  const normalizedStepStatus = String(step?.status || "").trim().toLowerCase();
  const normalizedProjectStatus = String(projectStatus || "").trim().toLowerCase();
  const stepLineageId = String(step?.metadata?.lineage_id || "").trim();
  const activeLineage = String(checkpointState?.currentCheckpointLineageId || activeLineageId || "").trim();
  const statusByStepId = checkpointState?.statusByStepId instanceof Map ? checkpointState.statusByStepId : null;
  const statusByLineageId = checkpointState?.statusByLineageId instanceof Map ? checkpointState.statusByLineageId : null;
  const checkpointStatus =
    (statusByStepId && statusByStepId.get(String(step?.step_id || "").trim()))
    || (statusByLineageId && statusByLineageId.get(stepLineageId))
    || "";
  if (checkpointStatus) {
    return checkpointStatus;
  }
  const lineageIsActive =
    Boolean(activeLineage)
    && Boolean(stepLineageId)
    && stepLineageId === activeLineage
    && (checkpointState?.hasActiveCheckpoint
      || checkpointFamily === "checkpoint"
      || checkpointFamily === "failed"
      || checkpointFamily === "completed"
      || normalizedProjectStatus.startsWith("running:")
      || normalizedProjectStatus === "running"
      || normalizedProjectStatus.startsWith("queued:")
      || normalizedProjectStatus === "queued"
      || normalizedProjectStatus === "awaiting_checkpoint_approval"
      || normalizedProjectStatus === "awaiting_review"
      || isDebuggingStatus(projectStatus));
  if (lineageIsActive) {
    if (checkpointState?.waitingForApproval || checkpointFamily === "checkpoint" || normalizedProjectStatus === "awaiting_checkpoint_approval" || normalizedProjectStatus === "awaiting_review") {
      return String(checkpointState?.pending?.status || "awaiting_review").trim().toLowerCase() || "awaiting_review";
    }
    if (checkpointFamily === "failed" || normalizedProjectStatus.endsWith("failed")) {
      return "failed";
    }
    if (checkpointFamily === "completed" || normalizedProjectStatus === "completed") {
      return "completed";
    }
    if (normalizedProjectStatus.startsWith("queued:") || normalizedProjectStatus === "queued") {
      return "queued";
    }
    if (isDebuggingStatus(projectStatus)) {
      return "running:debugging";
    }
    if (checkpointState?.processActive || normalizedProjectStatus.startsWith("running:") || normalizedProjectStatus === "running") {
      return "running";
    }
    return normalizedStepStatus || currentStatus || "pending";
  }
  return currentStatus;
}

function buildChartData(steps = [], projectStatus = "", language = "en", activeLineageId = "", checkpointState = null, checkpointFamily = "", statusSteps = []) {
  const statusByStepId = new Map();
  const statusByLineageId = new Map();
  const liveStatusByStepId = new Map();
  const liveStatusByLineageId = new Map();
  const registerStatus = (key, status) => {
    const normalizedKey = String(key || "").trim();
    const normalizedStatus = String(status || "").trim().toLowerCase();
    if (!normalizedKey || !normalizedStatus) {
      return;
    }
    statusByStepId.set(normalizedKey, normalizedStatus);
  };
  const registerLineageStatus = (key, status) => {
    const normalizedKey = String(key || "").trim();
    const normalizedStatus = String(status || "").trim().toLowerCase();
    if (!normalizedKey || !normalizedStatus) {
      return;
    }
    statusByLineageId.set(normalizedKey, normalizedStatus);
  };
  const registerLiveStatus = (key, status) => {
    const normalizedKey = String(key || "").trim();
    const normalizedStatus = String(status || "").trim().toLowerCase();
    if (!normalizedKey || !normalizedStatus) {
      return;
    }
    liveStatusByStepId.set(normalizedKey, normalizedStatus);
  };
  const registerLiveLineageStatus = (key, status) => {
    const normalizedKey = String(key || "").trim();
    const normalizedStatus = String(status || "").trim().toLowerCase();
    if (!normalizedKey || !normalizedStatus) {
      return;
    }
    liveStatusByLineageId.set(normalizedKey, normalizedStatus);
  };
  const liveSteps = Array.isArray(statusSteps) ? statusSteps : [];
  for (const item of liveSteps) {
    const itemStatus = String(item?.status || "").trim().toLowerCase();
    const stepId = String(item?.step_id || "").trim();
    const lineageId = String(item?.metadata?.lineage_id || item?.lineage_id || "").trim();
    if (stepId) {
      registerLiveStatus(stepId, itemStatus);
    }
    if (lineageId) {
      registerLiveLineageStatus(lineageId, itemStatus);
    }
  }
  const checkpointItems = Array.isArray(checkpointState?.items) ? checkpointState.items : [];
  for (const item of checkpointItems) {
    const itemStatus = String(item?.status || "").trim().toLowerCase();
    const lineageId = String(item?.lineage_id || "").trim();
    const planRefs = Array.isArray(item?.plan_refs) ? item.plan_refs : [];
    for (const ref of planRefs) {
      registerStatus(ref, itemStatus);
      if (lineageId) {
        registerLineageStatus(lineageId, itemStatus);
      }
    }
  }
  if (checkpointState?.pending && typeof checkpointState.pending === "object") {
    const pendingStatus = String(checkpointState.pending.status || "awaiting_review").trim().toLowerCase() || "awaiting_review";
    const pendingLineageId = String(checkpointState.pending.lineage_id || checkpointState.currentCheckpointLineageId || "").trim();
    const pendingRefs = Array.isArray(checkpointState.pending.plan_refs) ? checkpointState.pending.plan_refs : [];
    for (const ref of pendingRefs) {
      registerStatus(ref, pendingStatus);
      if (pendingLineageId) {
        registerLineageStatus(pendingLineageId, pendingStatus);
      }
    }
  }
  const checkpointLookup = {
    ...checkpointState,
    statusByStepId,
    statusByLineageId,
  };
  const topology = getChartTopology(steps);
  return {
    ...topology,
    nodes: topology.nodes.map((node) => {
      const liveStatus =
        liveStatusByStepId.get(String(node.step?.step_id || "").trim())
        || liveStatusByLineageId.get(String(node.step?.metadata?.lineage_id || "").trim())
        || "";
      const renderedStep = liveStatus ? { ...node.step, status: liveStatus } : node.step;
      const stepStatus = effectiveChartStepStatus(renderedStep, projectStatus, activeLineageId, checkpointLookup, checkpointFamily);
      const persistedStatus = String(node.step?.status || "").trim().toLowerCase() || "pending";
      const { tone, palette } = resolveChartNodeVisuals(stepStatus, persistedStatus);
      const failureReason = failureReasonLabel(renderedStep, language);
      return {
        ...node,
        stepStatus,
        tone,
        palette,
        detailLines: wrapChartText(
          String(stepStatus || "").trim().toLowerCase().includes("failed")
            ? failureReason || renderedStep.notes || node.detailSource
            : node.detailSource,
          28,
          2,
        ),
        statusLabel: displayStatus(stepStatus, language),
        failureReason,
      };
    }),
  };
}

function chartStepRenderSignature(steps = []) {
  return (steps || []).map((step) => [
    step?.step_id || "",
    step?.title || "",
    step?.display_description || "",
    step?.success_criteria || "",
    step?.status || "",
    Array.isArray(step?.depends_on) ? step.depends_on.join(",") : "",
    Array.isArray(step?.owned_paths) ? step.owned_paths.join(",") : "",
  ].join("|")).join("::");
}

function chartDetailStatusSignature(detail = null, activeJob = null) {
  const liveSteps = Array.isArray(detail?.plan?.steps) ? detail.plan.steps : [];
  const checkpointPending = detail?.checkpoints?.pending || null;
  const checkpointItems = Array.isArray(detail?.checkpoints?.items) ? detail.checkpoints.items : [];
  return [
    detail?.project?.current_status || "",
    activeJob?.id || "",
    activeJob?.status || "",
    activeJob?.started_at || "",
    liveSteps.map((step) => [
      step?.step_id || "",
      step?.status || "",
      step?.metadata?.lineage_id || "",
    ].join(":")).join("|"),
    checkpointItems.map((item) => [
      item?.lineage_id || "",
      item?.status || "",
      Array.isArray(item?.plan_refs) ? item.plan_refs.join(",") : "",
    ].join(":")).join("|"),
    checkpointPending
      ? [
        checkpointPending?.lineage_id || "",
        checkpointPending?.status || "",
        Array.isArray(checkpointPending?.plan_refs) ? checkpointPending.plan_refs.join(",") : "",
      ].join(":")
      : "",
  ].join("||");
}

function executionFlowChartPropsEqual(previousProps, nextProps) {
  return (
    previousProps.language === nextProps.language
    && previousProps.selectedStepId === nextProps.selectedStepId
    && previousProps.onSelectStep === nextProps.onSelectStep
    && chartStepRenderSignature(previousProps.steps) === chartStepRenderSignature(nextProps.steps)
    && chartDetailStatusSignature(previousProps.detail, previousProps.activeJob) === chartDetailStatusSignature(nextProps.detail, nextProps.activeJob)
  );
}

/* ── Stepper icons ── */
function StepperCheckIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none">
      <polyline points="3 8 6.5 11.5 13 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function StepperXIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none">
      <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function StepperViewIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none">
      <rect x="1" y="6" width="4" height="4" rx="1" stroke="currentColor" strokeWidth="1.2" />
      <rect x="6" y="6" width="4" height="4" rx="1" stroke="currentColor" strokeWidth="1.2" />
      <rect x="11" y="6" width="4" height="4" rx="1" stroke="currentColor" strokeWidth="1.2" />
      <path d="M5 8h1M10 8h1" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  );
}

function GraphViewIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none">
      <rect x="1" y="5" width="4" height="3" rx="0.8" stroke="currentColor" strokeWidth="1.2" />
      <rect x="9" y="2" width="4" height="3" rx="0.8" stroke="currentColor" strokeWidth="1.2" />
      <rect x="9" y="11" width="4" height="3" rx="0.8" stroke="currentColor" strokeWidth="1.2" />
      <path d="M5 6.5h2m0 0V3.5h2M7 6.5v6h2" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  );
}

function stepStatusCategory(status) {
  const s = String(status || "").trim().toLowerCase();
  if (s === "completed" || s === "merged") return "completed";
  if (s.startsWith("running") || s === "integrating") return "running";
  if (s.includes("fail") || s === "error") return "failed";
  if (s === "queued") return "queued";
  return "pending";
}

function HorizontalStepper({ steps = [], projectStatus = "", language = "en", selectedStepId = "", onSelectStep = null, detail = null, activeJob = null }) {
  const executionState = useMemo(() => deriveExecutionUiState(detail, null, activeJob), [detail, activeJob]);
  const completedCount = steps.filter((s) => stepStatusCategory(effectiveStepStatus(s, projectStatus)) === "completed").length;
  const progressPercent = steps.length > 0 ? Math.round((completedCount / steps.length) * 100) : 0;

  return (
    <div>
      <div className="execution-stepper__summary">
        <span>{completedCount}/{steps.length} {language === "ko" ? "완료" : "Done"}</span>
        <div className="execution-stepper__summary-progress">
          <div className="execution-stepper__summary-fill" style={{ width: `${progressPercent}%` }} />
        </div>
        <span>{progressPercent}%</span>
      </div>
      <div className="execution-stepper">
        {steps.map((step, index) => {
          const resolvedStatus = effectiveStepStatus(step, projectStatus);
          const category = stepStatusCategory(resolvedStatus);
          const selected = step.step_id === selectedStepId;
          return (
            <div key={step.step_id} style={{ display: "flex", alignItems: "flex-start" }}>
              {index > 0 ? (
                <div className="execution-stepper__connector">
                  <div className={`execution-stepper__connector-line${category === "completed" || stepStatusCategory(effectiveStepStatus(steps[index - 1], projectStatus)) === "completed" ? " execution-stepper__connector-line--done" : ""}`} />
                  <div className={`execution-stepper__connector-arrow${stepStatusCategory(effectiveStepStatus(steps[index - 1], projectStatus)) === "completed" ? " execution-stepper__connector-arrow--done" : ""}`} />
                </div>
              ) : null}
              <div className="execution-stepper__step">
                <div
                  className={`execution-stepper__node execution-stepper__node--${category}${selected ? " execution-stepper__node--selected" : ""}`}
                  onClick={() => onSelectStep?.(step.step_id)}
                  title={`${step.step_id}: ${step.title || ""}\n${displayStatus(resolvedStatus, language)}`}
                >
                  <div className={`execution-stepper__icon execution-stepper__icon--${category}`}>
                    {category === "completed" ? <StepperCheckIcon /> : null}
                    {category === "failed" ? <StepperXIcon /> : null}
                    {category === "running" ? <span className="stepper-dot" /> : null}
                  </div>
                  <span className="execution-stepper__id">{step.step_id}</span>
                  <span className="execution-stepper__title">{step.title || ""}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ExecutionFlowChartComponent({ steps = [], detail = null, activeJob = null, language = "en", selectedStepId = "", onSelectStep = null }) {
  const [viewMode, setViewMode] = useState("stepper");
  const arrowId = useId().replace(/:/g, "-");
  const executionState = useMemo(() => deriveExecutionUiState(detail, null, activeJob), [detail, activeJob]);
  const chart = useMemo(
    () => buildChartData(
      steps,
      executionState.displayStatusValue,
      language,
      String(executionState.checkpointExecutionState?.currentCheckpointLineageId || executionState.checkpointPending?.lineage_id || "").trim(),
      executionState.checkpointExecutionState,
      executionState.checkpointFamily,
      Array.isArray(detail?.plan?.steps) ? detail.plan.steps : [],
    ),
    [steps, detail?.plan?.steps, executionState.displayStatusValue, language, executionState.checkpointExecutionState, executionState.checkpointFamily, executionState.checkpointPending?.lineage_id],
  );

  if (!steps.length) {
    return null;
  }

  return (
    <div className="history-flow">
      {/* View toggle */}
      <div style={{ display: "flex", justifyContent: "flex-end", padding: "4px 8px 0" }}>
        <div className="flow-view-toggle">
          <button
            className={`flow-view-toggle__btn${viewMode === "stepper" ? " flow-view-toggle__btn--active" : ""}`}
            onClick={() => setViewMode("stepper")}
            type="button"
            title={language === "ko" ? "스텝퍼 뷰" : "Stepper view"}
          >
            <StepperViewIcon />
          </button>
          <button
            className={`flow-view-toggle__btn${viewMode === "graph" ? " flow-view-toggle__btn--active" : ""}`}
            onClick={() => setViewMode("graph")}
            type="button"
            title={language === "ko" ? "그래프 뷰" : "Graph view"}
          >
            <GraphViewIcon />
          </button>
        </div>
      </div>

      {viewMode === "stepper" ? (
        <HorizontalStepper
          steps={steps}
          projectStatus={executionState.displayStatusValue}
          language={language}
          selectedStepId={selectedStepId}
          onSelectStep={onSelectStep}
          detail={detail}
          activeJob={activeJob}
        />
      ) : (
      <div className="history-flow__canvas">
        <svg
          aria-label="Execution flow chart"
          role="img"
          viewBox={`0 0 ${chart.width} ${chart.height}`}
          width={chart.width}
          height={chart.height}
        >
          <defs>
            <marker
              id={arrowId}
              markerWidth="10"
              markerHeight="10"
              refX="8"
              refY="5"
              orient="auto"
              markerUnits="strokeWidth"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill={EDGE_STROKE} />
            </marker>
          </defs>

          {chart.nodeToSplitSegments.map((segment) => (
            <path key={segment.key} d={segment.d} stroke={EDGE_STROKE} strokeWidth="3" fill="none" strokeLinecap="round" />
          ))}
          {chart.edgeSegments.map((segment) => (
            <path
              key={segment.key}
              d={segment.d}
              stroke={EDGE_STROKE}
              strokeWidth="3"
              fill="none"
              strokeLinecap="round"
              strokeLinejoin="round"
              markerEnd={segment.arrow ? `url(#${arrowId})` : undefined}
            />
          ))}
          {chart.mergeBusSegments.map((segment) => (
            <path key={segment.key} d={segment.d} stroke={EDGE_STROKE} strokeWidth="3" fill="none" strokeLinecap="round" />
          ))}
          {chart.mergeToNodeSegments.map((segment) => (
            <path
              key={segment.key}
              d={segment.d}
              stroke={EDGE_STROKE}
              strokeWidth="3"
              fill="none"
              strokeLinecap="round"
              markerEnd={`url(#${arrowId})`}
            />
          ))}
          {chart.splitJunctions.map((junction, index) => (
            <circle key={`split-${index}`} cx={junction.x} cy={junction.y} r="5" fill={EDGE_FILL} stroke={EDGE_STROKE} strokeWidth="2" />
          ))}
          {chart.mergeJunctions.map((junction, index) => (
            <circle key={`merge-${index}`} cx={junction.x} cy={junction.y} r="5" fill={EDGE_FILL} stroke={EDGE_STROKE} strokeWidth="2" />
          ))}

          {chart.nodes.map((node) => {
            const selected = node.step.step_id === selectedStepId;
            const stroke = selected ? SELECTED_STROKE : node.palette.stroke;
            const strokeWidth = selected ? 3.25 : 2;
            return (
              <g
                key={node.step.step_id}
                className={`execution-flow-chart__node execution-flow-chart__node--${node.tone} ${selected ? "selected" : ""}`}
                onClick={() => onSelectStep?.(node.step.step_id)}
                style={{ cursor: onSelectStep ? "pointer" : "default" }}
              >
                <title>{`${node.step.step_id}: ${node.step.title}${node.failureReason ? `\nFailure: ${node.failureReason}` : ""}`}</title>
                <rect
                  x={node.x}
                  y={node.y}
                  rx="22"
                  ry="22"
                  width={BOX_WIDTH}
                  height={BOX_HEIGHT}
                  fill={node.palette.fill}
                  stroke={stroke}
                  strokeWidth={strokeWidth}
                />
                <SvgTextBlock x={node.x + 18} y={node.y + 26} lines={[node.step.step_id]} fill={node.palette.meta} fontSize="13" fontWeight="700" />
                <SvgTextBlock x={node.x + 18} y={node.y + 50} lines={node.titleLines} fill={node.palette.text} fontSize="13" fontWeight="700" lineHeight={16} />
                <SvgTextBlock x={node.x + 18} y={node.y + 86} lines={node.detailLines} fill={node.palette.meta} fontSize="11" lineHeight={14} />
                <SvgTextBlock x={node.x + 18} y={node.y + 120} lines={[node.statusLabel]} fill={node.palette.text} fontSize="11" />
              </g>
            );
          })}
        </svg>
      </div>
      )}
    </div>
  );
}

export const ExecutionFlowChart = memo(ExecutionFlowChartComponent, executionFlowChartPropsEqual);
export const __executionFlowChartTestables = {
  buildChartLevels,
  orderChartLevels,
  buildChartTopology,
  resolveChartNodeVisuals,
};
