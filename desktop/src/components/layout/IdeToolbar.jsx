import { useI18n } from "../../i18n";
import { displayStatus } from "../../locale";
import { commandLabel, isDebuggingStatus, isPlanningProgressRunning, projectStatusWithJob, statusTone, toolbarProgressCaptionDisplay } from "../../utils";

function AppLogo() {
  return (
    <div className="toolbar-logo">
      <div className="toolbar-logo__icon">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M12 2L2 7l10 5 10-5-10-5z" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M2 17l10 5 10-5" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M2 12l10 5 10-5" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
      <span className="toolbar-logo__name">jakal-flow</span>
    </div>
  );
}

function RefreshIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M1 4v6h6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M23 20v-6h-6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function SettingsIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="3" stroke="currentColor" />
      <path
        d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"
        stroke="currentColor"
      />
    </svg>
  );
}

function PlanIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M9 11l3 3L22 4" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function RunIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <polygon points="5 3 19 12 5 21 5 3" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" fill="currentColor" fillOpacity="0.18" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <polyline points="20 6 9 17 4 12" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ProjectIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" width="11" height="11" aria-hidden="true">
      <path
        d="M4.75 7.25A2.5 2.5 0 0 1 7.25 4.75h5.1c.66 0 1.3.26 1.77.73l5.15 5.15c.47.47.73 1.1.73 1.77v4.35a2.5 2.5 0 0 1-2.5 2.5h-10a2.5 2.5 0 0 1-2.5-2.5v-9.5Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path d="M13 4.9v5.35a1 1 0 0 0 1 1h5.1" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
    </svg>
  );
}

export function IdeToolbar({
  projectDetail,
  planDraft,
  pendingCheckpoint,
  busy,
  activeJob,
  activeCenterTab,
  onRefresh,
  onOpenSettings,
  onGeneratePlan,
  onRunPlan,
  onApproveCheckpoint,
}) {
  const planningRunning = isPlanningProgressRunning(projectDetail?.planning_progress);
  const projectStatusWithActiveJob = projectStatusWithJob(projectDetail?.project?.current_status || "idle", activeJob) || "idle";
  const projectStatus =
    String(activeJob?.status || "").trim().toLowerCase() === "running" || !planningRunning
      ? projectStatusWithActiveJob
      : "running:generate-plan";
  const livePlan = String(activeJob?.status || "").trim().toLowerCase() === "running" && projectDetail?.plan ? projectDetail.plan : planDraft;
  const projectName = projectDetail?.project?.display_name || projectDetail?.project?.slug || null;
  const { language, t } = useI18n();
  const normalizedProjectStatus = String(projectStatus || "").trim().toLowerCase();
  const statusLabel =
    String(activeJob?.status || "").trim().toLowerCase() === "running"
    && !isDebuggingStatus(projectDetail?.project?.current_status || "")
    && normalizedProjectStatus !== "running:merging"
      ? commandLabel(activeJob.command, language)
      : planningRunning && !isDebuggingStatus(projectDetail?.project?.current_status || "") && normalizedProjectStatus !== "running:merging"
        ? displayStatus("running:generate-plan", language)
      : displayStatus(projectStatus, language);
  const planStatusLabel = toolbarProgressCaptionDisplay(livePlan, language, {
    activeJob,
    planningProgress: projectDetail?.planning_progress,
  });

  const tone = statusTone(projectStatus);

  return (
    <header className="ide-toolbar">
      {/* Branding */}
      <div className="ide-toolbar__group">
        <AppLogo />
        <div className="toolbar-divider" />
        <button
          className="toolbar-button toolbar-button--ghost toolbar-button--icon-only"
          onClick={onRefresh}
          title={t("action.refresh")}
          type="button"
          aria-label={t("action.refresh")}
        >
          <RefreshIcon />
        </button>
      </div>

      {/* Status info */}
      <div className="ide-toolbar__group ide-toolbar__group--grow">
        <div className="toolbar-chip">
          <ProjectIcon />
          <span>{t("common.project")}</span>
          <strong>{projectName || t("project.none")}</strong>
        </div>

        <div className={`toolbar-status toolbar-status--${tone}`}>
          <span className={`chip-dot chip-dot--${tone}`} />
          <span>{t("common.status")}</span>
          <strong>{statusLabel}</strong>
        </div>

        {pendingCheckpoint ? (
          <div className="toolbar-status toolbar-status--warning">
            <span className="chip-dot chip-dot--warning" />
            <span>{t("dashboard.checkpointPending")}</span>
            <strong>{pendingCheckpoint.checkpoint_id || t("common.yes")}</strong>
          </div>
        ) : null}

        <div className="toolbar-status toolbar-status--neutral">
          <span>{t("toolbar.plan")}</span>
          <strong>{planStatusLabel}</strong>
        </div>
      </div>

      {/* Actions */}
      <div className="ide-toolbar__group">
        <button
          className={`toolbar-button ${activeCenterTab === "app-settings" ? "toolbar-button--accent" : "toolbar-button--ghost"}`}
          onClick={onOpenSettings}
          title={`${t("toolbar.programSettings")} (Ctrl+6)`}
          type="button"
        >
          <SettingsIcon />
          {t("toolbar.programSettings")}
        </button>

        <div className="toolbar-divider" />

        <button
          className="toolbar-button"
          onClick={onGeneratePlan}
          type="button"
          disabled={busy}
          title={t("action.generatePlan")}
        >
          <PlanIcon />
          {t("action.generatePlan")}
        </button>

        <button
          className="toolbar-button toolbar-button--accent"
          onClick={onRunPlan}
          type="button"
          disabled={busy}
          title={t("action.runRemaining")}
        >
          <RunIcon />
          {t("action.runRemaining")}
        </button>

        {pendingCheckpoint ? (
          <button
            className="toolbar-button toolbar-button--accent"
            onClick={onApproveCheckpoint}
            type="button"
            disabled={busy}
            title={t("action.approveCheckpoint")}
          >
            <CheckIcon />
            {t("action.approveCheckpoint")}
          </button>
        ) : null}
      </div>
    </header>
  );
}
