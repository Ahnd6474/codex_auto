import { useI18n } from "../../i18n";
import { displayStatus } from "../../locale";
import {
  commandLabel,
  formatUsd,
  runtimeSummary,
  shouldShowEstimatedCost,
  statusTone,
  visibleExecutionJob,
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

export function StatusBar({
  detail,
  activeJob,
  queuedJobs,
  modelPresets,
  onToggleBottom,
  bottomCollapsed,
}) {
  const { language, t } = useI18n();
  const executionJob = visibleExecutionJob(activeJob);
  const project = detail?.project || {};
  const runtime = detail?.runtime || {};
  const costEstimate = detail?.runtime_insights?.cost || {};
  const showCost = shouldShowEstimatedCost(runtime, costEstimate);
  const tone = statusTone(project.current_status || "idle");
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

        <div className={`status-bar__widget status-bar__widget--${tone}`}>
          <span className={`chip-dot chip-dot--${tone}`} />
          <span>{displayStatus(project.current_status || "idle", language)}</span>
        </div>

        {jobLabel ? (
          <div className="status-bar__widget status-bar__widget--info">
            <span className="chip-dot chip-dot--info" style={{ animation: "live-dot-pulse 1.4s ease-in-out infinite" }} />
            <span>{jobLabel}</span>
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
}
