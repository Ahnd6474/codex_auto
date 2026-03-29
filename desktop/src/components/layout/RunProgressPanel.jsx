import { useEffect, useMemo, useState } from "react";
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

/* ── Icons ── */
function ClockIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  );
}

function ActivityIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  );
}

function stepLabel(step) {
  return [step?.step_id, step?.title].filter(Boolean).join(" – ");
}

function runningStepLabels(steps = [], maxVisible = 3) {
  const labels = steps.map((step) => stepLabel(step)).filter(Boolean);
  if (!labels.length) return "";
  if (labels.length <= maxVisible) return labels.join(", ");
  return `${labels.slice(0, maxVisible).join(", ")} +${labels.length - maxVisible}`;
}

export function RunProgressPanel({ detail, planDraft, activeJob }) {
  const { language, t } = useI18n();
  const progress = useMemo(
    () => deriveExecutionProgress(detail, planDraft, activeJob),
    [activeJob, detail, planDraft],
  );
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
          <div className="run-progress-banner__identity">
            <span className="chip-dot chip-dot--info status-badge--pulse" style={{ animation: "live-dot-pulse 1.4s ease-in-out infinite" }} />
            <div className="run-progress-banner__title-stack">
              <span className="eyebrow">{t("run.liveRun")}</span>
              <strong className="run-progress-banner__main-work" title={currentWork || t("action.backgroundJob")}>
                {currentWork || t("action.backgroundJob")}
              </strong>
            </div>
          </div>

          <div className="run-progress-banner__status-group">
            {!progress.indeterminate && progress.percent != null ? (
              <span className="run-progress-banner__percent">
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
          <div className="run-progress-banner__metrics">
            {progress.totalProgressUnits ? (
              <div className="metric-chip">
                <span>{t("run.completedStepsSummary", { completed: progress.completedProgressUnits, total: progress.totalProgressUnits })}</span>
              </div>
            ) : null}
            {progress.runningStepList?.length > 1 ? (
              <div className="metric-chip">
                <span>{t("run.runningNodeSummary", { count: progress.runningStepList.length })}</span>
              </div>
            ) : null}
            {progress.phase !== "planning" ? (
              <div className="metric-chip">
                <ClockIcon />
                <span>{formatDurationCompact(runningStepElapsedSeconds, language)}</span>
              </div>
            ) : null}
            {progress.phase !== "planning" && executionEstimate.remaining_seconds ? (
              <div className="metric-chip metric-chip--dim">
                <span>{t("run.currentRemaining")}: {formatDurationCompact(executionEstimate.remaining_seconds, language)}</span>
              </div>
            ) : null}
            {progress.phase !== "planning" && showEstimatedCost ? (
              <div className="metric-chip metric-chip--accent">
                <span>{formatUsd(costEstimate.estimated_total_cost_usd ?? 0, language)}</span>
              </div>
            ) : null}
          </div>
        </div>

        {/* Planning stages */}
        {progress.phase === "planning" && progress.planningStages.length ? (
          <div className="run-progress-banner__stages" aria-label="Planning stages">
            {progress.planningStages.slice(0, 4).map((stage) => (
              <span
                key={`${stage.key || "stage"}-${stage.index}`}
                className={`run-progress-stage run-progress-stage--${stage.status || "pending"}`}
              >
                <strong>{stage.index}.</strong> {stage.label || stage.key}
                <span className="run-progress-stage__status">{displayStatus(stage.status || "pending", language)}</span>
              </span>
            ))}
            {progress.planningStages.length > 4 ? (
              <span className="run-progress-stage">+{progress.planningStages.length - 4}</span>
            ) : null}
          </div>
        ) : null}

        {/* Headline activity */}
        {progress.headlineActivity ? (
          <div className="run-progress-banner__activity">
            <div className="activity-label">
              <ActivityIcon />
              <span>{t("history.recentActivity")}</span>
            </div>
            <strong>{progress.headlineActivity}</strong>
          </div>
        ) : null}

        {/* Checkpoint notification */}
        {detail?.checkpoints?.pending ? (
          <div className="run-progress-banner__checkpoint">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            </svg>
            <span>
              {language === "ko" ? "체크포인트 대기 중" : "Checkpoint pending"}
              {detail.checkpoints.pending.title ? ` — ${detail.checkpoints.pending.title}` : ""}
            </span>
            <span className="status-badge status-badge--warning" style={{ fontSize: "10px", padding: "1px 6px" }}>
              {displayStatus(detail.checkpoints.pending.status || "pending", language)}
            </span>
          </div>
        ) : null}
      </section>
    </>
  );
}
