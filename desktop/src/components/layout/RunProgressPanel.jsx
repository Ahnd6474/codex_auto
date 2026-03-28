import { useEffect, useState } from "react";
import { useI18n } from "../../i18n";
import { displayStatus } from "../../locale";
import {
  commandLabel,
  deriveExecutionProgress,
  executionProgressCaptionDisplay,
  formatDurationCompact,
  formatUsd,
  planningProgressCaptionDisplay,
  shouldShowEstimatedCost,
} from "../../utils";

function stepLabel(step) {
  return [step?.step_id, step?.title].filter(Boolean).join(" – ");
}

function runningStepLabels(steps = [], maxVisible = 3) {
  const labels = steps.map((step) => stepLabel(step)).filter(Boolean);
  if (!labels.length) return "";
  if (labels.length <= maxVisible) return labels.join(", ");
  return `${labels.slice(0, maxVisible).join(", ")} +${labels.length - maxVisible}`;
}

function LiveDot() {
  return (
    <span
      aria-hidden="true"
      style={{
        display: "inline-block",
        width: "8px",
        height: "8px",
        borderRadius: "50%",
        background: "var(--info)",
        boxShadow: "0 0 0 0 rgba(95,151,214,0.6)",
        animation: "live-dot-pulse 1.4s ease-in-out infinite",
        flexShrink: 0,
      }}
    />
  );
}

export function RunProgressPanel({ detail, planDraft, activeJob }) {
  const { language, t } = useI18n();
  const progress = deriveExecutionProgress(detail, planDraft, activeJob);
  const runtimeInsights = detail?.runtime_insights || {};
  const executionEstimate = runtimeInsights?.execution || {};
  const costEstimate = runtimeInsights?.cost || {};
  const showEstimatedCost = shouldShowEstimatedCost(detail?.runtime || {}, costEstimate);
  const [nowTick, setNowTick] = useState(Date.now());

  useEffect(() => {
    if (!progress.isActive) return undefined;
    const timer = window.setInterval(() => setNowTick(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [progress.isActive]);

  if (!progress.isActive) return null;

  let currentWork = commandLabel(progress.command, language);
  if (progress.phase === "planning") {
    currentWork = progress.planningCurrentStage?.label || t("run.planGeneration");
  } else if (progress.phase === "closeout") {
    currentWork = t("run.closeoutRunning");
  } else if (progress.phase === "debugging") {
    currentWork = t("run.debugging");
  } else if (String(progress.status || "").trim().toLowerCase() === "running:merging") {
    currentWork = displayStatus(progress.status, language);
  } else if (String(progress.runningStep?.status || "").trim().toLowerCase() === "integrating") {
    currentWork = `${displayStatus("integrating", language)} ${stepLabel(progress.runningStep)}`.trim();
  } else if ((progress.runningStepList || []).length > 1) {
    currentWork = t("run.workingOnSteps", { steps: runningStepLabels(progress.runningStepList) });
  } else if (progress.runningStep) {
    currentWork = t("run.workingOnStep", { step: stepLabel(progress.runningStep) });
  } else if (progress.nextStep) {
    currentWork = t("run.preparingStep", { step: stepLabel(progress.nextStep) });
  }

  const progressSummary =
    progress.phase === "planning" && progress.planningStageCount
      ? planningProgressCaptionDisplay(progress, language)
      : executionProgressCaptionDisplay(progress.plan, language);

  const runningStartTimes = (progress.runningStepList || [])
    .map((step) => Date.parse(String(step?.started_at || "")))
    .filter((value) => Number.isFinite(value));

  const runningStepElapsedSeconds = runningStartTimes.length
    ? Math.max(0, Math.round((nowTick - Math.min(...runningStartTimes)) / 1000))
    : 0;

  const badgeLabel =
    progress.phase === "planning"
      ? displayStatus(progress.planningCurrentStage?.status || "running", language)
      : progress.phase === "debugging"
        ? displayStatus(progress.status || "running:debugging", language)
        : String(progress.status || "").trim().toLowerCase() === "running:merging"
          ? displayStatus(progress.status, language)
          : String(progress.runningStep?.status || "").trim().toLowerCase() === "integrating"
            ? displayStatus("integrating", language)
            : commandLabel(progress.command, language) || t("action.backgroundJob");

  return (
    <>
      <style>{`
        @keyframes live-dot-pulse {
          0%, 100% { box-shadow: 0 0 0 0 rgba(95,151,214,0.55); }
          50% { box-shadow: 0 0 0 6px rgba(95,151,214,0); }
        }
      `}</style>

      <section className="run-progress-banner">
        {/* Header row */}
        <div className="run-progress-banner__header">
          <div style={{ display: "flex", alignItems: "center", gap: "8px", minWidth: 0 }}>
            <LiveDot />
            <div style={{ minWidth: 0 }}>
              <span className="eyebrow">{t("run.liveRun")}</span>
              <strong style={{ display: "block", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {currentWork || t("action.backgroundJob")}
              </strong>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "8px", flexShrink: 0 }}>
            {!progress.indeterminate && progress.percent != null ? (
              <span style={{ fontSize: "13px", fontWeight: "700", color: "var(--info)", fontVariantNumeric: "tabular-nums" }}>
                {progress.percent}%
              </span>
            ) : null}
            <span className="status-badge status-badge--info">{badgeLabel}</span>
          </div>
        </div>

        {/* Progress track */}
        <div
          className="run-progress-banner__track"
          role="progressbar"
          aria-label={t("run.stepProgress")}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={progress.indeterminate ? undefined : progress.percent ?? 0}
        >
          <div
            className={`run-progress-banner__fill ${progress.indeterminate ? "run-progress-banner__fill--indeterminate" : ""}`}
            style={progress.indeterminate ? undefined : { width: `${progress.visualPercent}%` }}
          />
        </div>

        {/* Meta info row */}
        <div className="run-progress-banner__meta">
          {progressSummary ? <span>{progressSummary}</span> : null}
          {progress.phase === "planning" && progress.planningCurrentAgentLabel ? (
            <span>{progress.planningCurrentAgentLabel}</span>
          ) : null}
          {progress.totalProgressUnits ? (
            <span>
              {t("run.completedStepsSummary", {
                completed: progress.completedProgressUnits,
                total: progress.totalProgressUnits,
              })}
            </span>
          ) : null}
          {progress.runningStepList?.length > 1 ? (
            <span>{t("run.runningNodeSummary", { count: progress.runningStepList.length })}</span>
          ) : null}
          {(!progress.runningStepList || progress.runningStepList.length <= 1) && progress.readyIds.length > 1 ? (
            <span>{t("run.readyNodeSummary", { count: progress.readyIds.length })}</span>
          ) : null}
          {progress.phase !== "planning" ? (
            <span>
              {t("run.currentElapsed")}: {formatDurationCompact(runningStepElapsedSeconds, language)}
            </span>
          ) : null}
          {progress.phase !== "planning" ? (
            <span>
              {t("run.currentRemaining")}: {formatDurationCompact(executionEstimate.remaining_seconds ?? 0, language)}
            </span>
          ) : null}
          {progress.phase !== "planning" && showEstimatedCost ? (
            <span>
              {t("run.estimatedCost")}: {formatUsd(costEstimate.estimated_total_cost_usd ?? 0, language)}
            </span>
          ) : null}
        </div>

        {/* Planning stages */}
        {progress.phase === "planning" && progress.planningStages.length ? (
          <div className="run-progress-banner__stages" aria-label="Planning stages">
            {progress.planningStages.map((stage) => (
              <span
                key={`${stage.key || "stage"}-${stage.index}`}
                className={`run-progress-stage run-progress-stage--${stage.status || "pending"}`}
              >
                <strong>{stage.index}.</strong> {stage.label || stage.key}
                <span className="run-progress-stage__status">{displayStatus(stage.status || "pending", language)}</span>
              </span>
            ))}
          </div>
        ) : null}

        {/* Headline activity */}
        {progress.headlineActivity ? (
          <div className="run-progress-banner__activity">
            <span>{t("history.recentActivity")}</span>
            <strong>{progress.headlineActivity}</strong>
          </div>
        ) : null}
      </section>
    </>
  );
}
