import { useEffect, useState } from "react";
import { useI18n } from "../../i18n";
import { displayStatus } from "../../locale";
import { commandLabel, deriveExecutionProgress, executionProgressCaptionDisplay, formatDurationCompact, formatUsd, shouldShowEstimatedCost } from "../../utils";

function stepLabel(step) {
  return [step?.step_id, step?.title].filter(Boolean).join(" - ");
}

function runningStepLabels(steps = [], maxVisible = 3) {
  const labels = steps
    .map((step) => stepLabel(step))
    .filter(Boolean);
  if (!labels.length) {
    return "";
  }
  if (labels.length <= maxVisible) {
    return labels.join(", ");
  }
  return `${labels.slice(0, maxVisible).join(", ")} +${labels.length - maxVisible}`;
}

function planningStageSummary(progress) {
  const currentIndex = progress?.planningCurrentStage?.index || 0;
  const total = progress?.planningStageCount || 0;
  if (!currentIndex || !total) {
    return "";
  }
  return `Planning stage ${currentIndex}/${total}`;
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
    if (!progress.isActive) {
      return undefined;
    }
    const timer = window.setInterval(() => setNowTick(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [progress.isActive]);

  if (!progress.isActive) {
    return null;
  }

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
      ? planningStageSummary(progress)
      : executionProgressCaptionDisplay(progress.plan, language);
  const percentLabel = progress.indeterminate ? t("status.running") : t("run.progressPercent", { percent: progress.percent ?? 0 });
  const runningStartTimes = (progress.runningStepList || [])
    .map((step) => Date.parse(String(step?.started_at || "")))
    .filter((value) => Number.isFinite(value));
  const runningStepElapsedSeconds = runningStartTimes.length
    ? Math.max(0, Math.round((nowTick - Math.min(...runningStartTimes)) / 1000))
    : 0;
  const badgeLabel =
    progress.phase === "debugging"
      ? displayStatus(progress.status || "running:debugging", language)
      : String(progress.status || "").trim().toLowerCase() === "running:merging"
        ? displayStatus(progress.status, language)
        : String(progress.runningStep?.status || "").trim().toLowerCase() === "integrating"
          ? displayStatus("integrating", language)
          : commandLabel(progress.command, language) || t("action.backgroundJob");

  return (
    <section className="run-progress-banner">
      <div className="run-progress-banner__header">
        <div>
          <span className="eyebrow">{t("run.liveRun")}</span>
          <strong>{currentWork || t("action.backgroundJob")}</strong>
        </div>
        <span className="status-badge status-badge--info">{badgeLabel}</span>
      </div>

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

      <div className="run-progress-banner__meta">
        <span>{progressSummary}</span>
        {progress.phase === "planning" && progress.planningCurrentAgentLabel ? <span>{progress.planningCurrentAgentLabel}</span> : null}
        {progress.totalProgressUnits ? (
          <span>{t("run.completedStepsSummary", { completed: progress.completedProgressUnits, total: progress.totalProgressUnits })}</span>
        ) : null}
        {progress.runningStepList?.length > 1 ? <span>{t("run.runningNodeSummary", { count: progress.runningStepList.length })}</span> : null}
        {(!progress.runningStepList || progress.runningStepList.length <= 1) && progress.readyIds.length > 1 ? (
          <span>{t("run.readyNodeSummary", { count: progress.readyIds.length })}</span>
        ) : null}
        {progress.phase !== "planning" ? <span>{t("run.currentElapsed")}: {formatDurationCompact(runningStepElapsedSeconds, language)}</span> : null}
        {progress.phase !== "planning" ? <span>{t("run.currentRemaining")}: {formatDurationCompact(executionEstimate.remaining_seconds ?? 0, language)}</span> : null}
        {progress.phase !== "planning" && showEstimatedCost ? <span>{t("run.estimatedCost")}: {formatUsd(costEstimate.estimated_total_cost_usd ?? 0, language)}</span> : null}
        <span>{percentLabel}</span>
      </div>

      {progress.phase === "planning" && progress.planningStages.length ? (
        <div className="run-progress-banner__stages" aria-label="Planning stages">
          {progress.planningStages.map((stage) => (
            <span
              key={`${stage.key || "stage"}-${stage.index}`}
              className={`run-progress-stage run-progress-stage--${stage.status || "pending"}`}
            >
              <strong>{stage.index}.</strong> {stage.label || stage.key}
            </span>
          ))}
        </div>
      ) : null}

      {progress.headlineActivity ? (
        <div className="run-progress-banner__activity">
          <span>{t("history.recentActivity")}</span>
          <strong>{progress.headlineActivity}</strong>
        </div>
      ) : null}
    </section>
  );
}
