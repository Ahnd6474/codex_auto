import { memo, useId, useMemo } from "react";
import { displayStatus } from "../../locale";
import { effectiveStepStatus, statusTone } from "../../utils";

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
  neutral: { fill: "#1f2937", stroke: "#475569", text: "#e5e7eb", meta: "#94a3b8" },
  info: { fill: "#172554", stroke: "#3b82f6", text: "#dbeafe", meta: "#93c5fd" },
  success: { fill: "#052e2b", stroke: "#14b8a6", text: "#ccfbf1", meta: "#5eead4" },
  warning: { fill: "#422006", stroke: "#f59e0b", text: "#fef3c7", meta: "#fcd34d" },
  danger: { fill: "#450a0a", stroke: "#ef4444", text: "#fee2e2", meta: "#fca5a5" },
};

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

function buildChartData(steps = [], projectStatus = "", language = "en") {
  const levels = buildChartLevels(steps);
  const positions = new Map();
  const maxRows = Math.max(1, ...levels.map((level) => level.length));
  const width = Math.max(960, MARGIN_X * 2 + levels.length * BOX_WIDTH + Math.max(0, levels.length - 1) * GAP_X);
  const height = Math.max(320, MARGIN_Y * 2 + maxRows * BOX_HEIGHT + Math.max(0, maxRows - 1) * GAP_Y);

  levels.forEach((level, levelIndex) => {
    const x = MARGIN_X + levelIndex * (BOX_WIDTH + GAP_X);
    level.forEach((step, rowIndex) => {
      const y = MARGIN_Y + rowIndex * (BOX_HEIGHT + GAP_Y);
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
      const stepStatus = effectiveStepStatus(step, projectStatus);
      const tone = statusTone(stepStatus);
      const palette = PALETTE[tone] || PALETTE.neutral;
      const detailSource =
        step.display_description ||
        step.success_criteria ||
        ((step.depends_on || []).length ? (step.depends_on || []).join(", ") : "") ||
        ((step.owned_paths || []).length ? `${step.owned_paths.length} owned path(s)` : "No summary");
      return {
        step,
        x,
        y,
        stepStatus,
        tone,
        palette,
        titleLines: wrapChartText(step.title, 24, 2),
        detailLines: wrapChartText(detailSource, 28, 2),
        statusLabel: displayStatus(stepStatus, language),
      };
    });

  const splitJunctions = [];
  const mergeJunctions = [];
  const nodeToSplitSegments = [];
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
      const endPoint = mergePoint || targetCenter;
      edgeSegments.push({
        key: `${step.step_id}-${targetId}`,
        d: orthogonalPath(startPoint.x, startPoint.y, endPoint.x, endPoint.y),
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
    mergeToNodeSegments,
    splitJunctions,
    mergeJunctions,
  };
}

function ExecutionFlowChartComponent({ steps = [], projectStatus = "", language = "en", selectedStepId = "", onSelectStep = null }) {
  const arrowId = useId().replace(/:/g, "-");
  const chart = useMemo(() => buildChartData(steps, projectStatus, language), [steps, projectStatus, language]);

  if (!steps.length) {
    return null;
  }

  return (
    <div className="history-flow">
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
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b" />
            </marker>
          </defs>

          {chart.nodeToSplitSegments.map((segment) => (
            <path key={segment.key} d={segment.d} stroke="#64748b" strokeWidth="3" fill="none" strokeLinecap="round" />
          ))}
          {chart.edgeSegments.map((segment) => (
            <path
              key={segment.key}
              d={segment.d}
              stroke="#64748b"
              strokeWidth="3"
              fill="none"
              strokeLinecap="round"
              strokeLinejoin="round"
              markerEnd={segment.arrow ? `url(#${arrowId})` : undefined}
            />
          ))}
          {chart.mergeToNodeSegments.map((segment) => (
            <path
              key={segment.key}
              d={segment.d}
              stroke="#64748b"
              strokeWidth="3"
              fill="none"
              strokeLinecap="round"
              markerEnd={`url(#${arrowId})`}
            />
          ))}
          {chart.splitJunctions.map((junction, index) => (
            <circle key={`split-${index}`} cx={junction.x} cy={junction.y} r="5" fill="#0f172a" stroke="#64748b" strokeWidth="2" />
          ))}
          {chart.mergeJunctions.map((junction, index) => (
            <circle key={`merge-${index}`} cx={junction.x} cy={junction.y} r="5" fill="#0f172a" stroke="#64748b" strokeWidth="2" />
          ))}

          {chart.nodes.map((node) => {
            const selected = node.step.step_id === selectedStepId;
            const stroke = selected ? "#f8fafc" : node.palette.stroke;
            const strokeWidth = selected ? 3 : 2;
            return (
              <g
                key={node.step.step_id}
                className={`execution-flow-chart__node execution-flow-chart__node--${node.tone} ${selected ? "selected" : ""}`}
                onClick={() => onSelectStep?.(node.step.step_id)}
                style={{ cursor: onSelectStep ? "pointer" : "default" }}
              >
                <title>{`${node.step.step_id}: ${node.step.title}`}</title>
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
    </div>
  );
}

export const ExecutionFlowChart = memo(ExecutionFlowChartComponent);
