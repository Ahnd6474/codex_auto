import { useEffect, useState } from "react";
import { useI18n } from "../../i18n";
import { displayStatus } from "../../locale";
import { commandLabel, deriveExecutionProgress, executionProgressCaption, formatDurationCompact, formatUsd } from "../../utils";

function stepLabel(step) {
  return [step?.step_id, step?.title].filter(Boolean).join(" - ");
}

export function RunProgressPanel({ detail, planDraft, activeJob }) {
  const { language, t } = useI18n();
  const progress = deriveExecutionProgress(detail, planDraft, activeJob);
  const runtimeInsights = detail?.runtime_insights || {};
  const executionEstimate = runtimeInsights?.execution || {};
  const costEstimate = runtimeInsights?.cost || {};
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
    currentWork = t("run.planGeneration");
  } else if (progress.phase === "closeout") {
    currentWork = t("run.closeoutRunning");
  } else if (progress.phase === "debugging") {
    currentWork = t("run.debugging");
  } else if (progress.runningStep) {
    currentWork = t("run.workingOnStep", { step: stepLabel(progress.runningStep) });
  } else if (progress.nextStep) {
    currentWork = t("run.preparingStep", { step: stepLabel(progress.nextStep) });
  }

  const progressSummary = executionProgressCaption(progress.plan, language);
  const percentLabel = progress.indeterminate ? t("status.running") : t("run.progressPercent", { percent: progress.percent ?? 0 });
  const runningStepElapsedSeconds = progress.runningStep?.started_at
    ? Math.max(0, Math.round((nowTick - new Date(progress.runningStep.started_at).getTime()) / 1000))
    : 0;
  const badgeLabel =
    progress.phase === "debugging"
      ? displayStatus(progress.status || "running:debugging", language)
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
        {progress.totalSteps ? (
          <span>{t("run.completedStepsSummary", { completed: progress.completedSteps, total: progress.totalSteps })}</span>
        ) : null}
        {progress.readyIds.length > 1 ? <span>{t("run.readyNodeSummary", { count: progress.readyIds.length })}</span> : null}
        <span>{t("run.currentElapsed")}: {formatDurationCompact(runningStepElapsedSeconds, language)}</span>
        <span>{t("run.currentRemaining")}: {formatDurationCompact(executionEstimate.remaining_seconds ?? 0, language)}</span>
        <span>{t("run.estimatedCost")}: {formatUsd(costEstimate.estimated_total_cost_usd ?? 0, language)}</span>
        <span>{percentLabel}</span>
      </div>

      {progress.headlineActivity ? (
        <div className="run-progress-banner__activity">
          <span>{t("history.recentActivity")}</span>
          <strong>{progress.headlineActivity}</strong>
        </div>
      ) : null}
    </section>
  );
}
