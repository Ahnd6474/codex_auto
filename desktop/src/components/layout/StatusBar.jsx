import { memo, useMemo } from "react";
import { useI18n } from "../../i18n";
import { displayStatus } from "../../locale";
import {
  commandLabel,
  deriveExecutionUiState,
  formatUsd,
  isActiveExecutionStatus,
  runtimeSummary,
  sameQueuedJobs,
  shouldShowEstimatedCost,
  statusTone,
} from "../../utils";

function BranchIcon() {
  return (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="6" y1="3" x2="6" y2="15" />
      <circle cx="18" cy="6" r="3" />
      <circle cx="6" cy="18" r="3" />
      <path d="M18 9a9 9 0 0 1-9 9" />
    </svg>
  );
}

function ModelIcon() {
  return (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 2L2 7l10 5 10-5-10-5z" />
      <path d="M2 17l10 5 10-5" />
      <path d="M2 12l10 5 10-5" />
    </svg>
  );
}

function sameModelPresets(previousPresets = [], nextPresets = []) {
  if (previousPresets === nextPresets) {
    return true;
  }
  if (!Array.isArray(previousPresets) || !Array.isArray(nextPresets) || previousPresets.length !== nextPresets.length) {
    return false;
  }
  for (let index = 0; index < previousPresets.length; index += 1) {
    const previousPreset = previousPresets[index];
    const nextPreset = nextPresets[index];
    if (
      previousPreset?.preset_id !== nextPreset?.preset_id
      || previousPreset?.summary !== nextPreset?.summary
    ) {
      return false;
    }
  }
  return true;
}

function sameRuntimeSummaryState(previousRuntime = null, nextRuntime = null) {
  const previous = previousRuntime && typeof previousRuntime === "object" ? previousRuntime : {};
  const next = nextRuntime && typeof nextRuntime === "object" ? nextRuntime : {};
  return (
    previous.model_provider === next.model_provider
    && previous.local_model_provider === next.local_model_provider
    && previous.model_preset === next.model_preset
    && previous.model === next.model
    && previous.workflow_mode === next.workflow_mode
    && previous.parallel_worker_mode === next.parallel_worker_mode
    && previous.parallel_workers === next.parallel_workers
    && previous.effort_selection_mode === next.effort_selection_mode
    && previous.effort === next.effort
    && previous.planning_mode === next.planning_mode
    && previous.use_fast_mode === next.use_fast_mode
  );
}

export const StatusBar = memo(function StatusBar({
  detail,
  activeJob,
  queuedJobs,
  modelPresets,
  onToggleBottom,
  bottomCollapsed,
}) {
  const { language, t } = useI18n();
  const executionState = useMemo(
    () => deriveExecutionUiState(detail, null, activeJob),
    [activeJob, detail],
  );
  const executionJob = executionState.executionJob;
  const project = detail?.project || {};
  const runtime = detail?.runtime || {};
  const costEstimate = detail?.runtime_insights?.cost || {};
  const showCost = shouldShowEstimatedCost(runtime, costEstimate);
  const tone = statusTone(executionState.displayStatusValue);
  const jobStatus = String(executionJob?.status || "").trim().toLowerCase();
  const jobLabel =
    jobStatus === "running"
      ? commandLabel(executionJob?.command, language)
      : jobStatus === "queued"
        ? t("common.queued")
        : null;

  return (
    <footer className="status-bar">
      <div className="status-bar__left">
        <button className="status-bar__widget" type="button" title={t("common.branch")}>
          <BranchIcon />
          <span>{project.branch || "main"}</span>
        </button>

        <div className={`status-bar__widget status-bar__widget--${tone}${isActiveExecutionStatus(executionState.displayStatusValue) ? " status-bar__widget--running" : ""}`}>
          <span className={`status-bar__mini-badge status-bar__mini-badge--${tone}`}>
            <span className={`chip-dot chip-dot--${tone}${isActiveExecutionStatus(executionState.displayStatusValue) ? " chip-dot--pulse" : ""}`} />
            {displayStatus(executionState.displayStatusValue || project.current_status || "idle", language)}
          </span>
        </div>

        {jobLabel ? (
          <div className="status-bar__widget status-bar__widget--info status-bar__widget--running">
            <span className="status-bar__mini-badge status-bar__mini-badge--info">
              <span className="chip-dot chip-dot--info chip-dot--pulse" />
              {jobLabel}
            </span>
          </div>
        ) : null}

        {queuedJobs?.length ? (
          <div className="status-bar__widget">
            <span>{t("run.queuedJobs")}: {queuedJobs.length}</span>
          </div>
        ) : null}
      </div>

      <div className="status-bar__right">
        {showCost ? (
          <div className="status-bar__widget">
            <span>{formatUsd(costEstimate.estimated_total_cost_usd ?? 0, language)}</span>
          </div>
        ) : null}

        <button className="status-bar__widget" type="button" title="Model / Provider">
          <ModelIcon />
          <span>{runtimeSummary(runtime, modelPresets)}</span>
        </button>

        <button
          className={`status-bar__toggle ${!bottomCollapsed ? "status-bar__toggle--active" : ""}`}
          onClick={onToggleBottom}
          type="button"
          title={t("tool.eventJson")}
        >
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <rect x="3" y="14" width="18" height="7" rx="1.5" />
            <rect x="3" y="3" width="18" height="7" rx="1.5" opacity=".35" />
          </svg>
        </button>

      </div>
    </footer>
  );
}, (previousProps, nextProps) => {
  if (!sameQueuedJobs(previousProps.queuedJobs, nextProps.queuedJobs)) {
    return false;
  }
  if (!sameModelPresets(previousProps.modelPresets, nextProps.modelPresets)) {
    return false;
  }
  return (
    previousProps.bottomCollapsed === nextProps.bottomCollapsed
    && previousProps.detail?.project?.branch === nextProps.detail?.project?.branch
    && previousProps.detail?.project?.current_status === nextProps.detail?.project?.current_status
    && sameRuntimeSummaryState(previousProps.detail?.runtime, nextProps.detail?.runtime)
    && previousProps.detail?.runtime_insights?.cost?.estimated_total_cost_usd === nextProps.detail?.runtime_insights?.cost?.estimated_total_cost_usd
    && previousProps.activeJob?.id === nextProps.activeJob?.id
    && previousProps.activeJob?.status === nextProps.activeJob?.status
    && previousProps.activeJob?.command === nextProps.activeJob?.command
  );
});
