import { useI18n } from "../../i18n";
import { displayStatus } from "../../locale";
import { commandLabel, isDebuggingStatus, isPlanningProgressRunning, projectStatusWithJob, statusTone, toolbarProgressCaptionDisplay } from "../../utils";

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

  return (
    <header className="ide-toolbar">
      <div className="ide-toolbar__group">
        <button className="toolbar-button toolbar-button--ghost" onClick={onRefresh} type="button">
          {t("action.refresh")}
        </button>
      </div>

      <div className="ide-toolbar__group ide-toolbar__group--grow">
        <div className="toolbar-chip">
          <span>{t("common.project")}</span>
          <strong>{projectName || t("project.none")}</strong>
        </div>
        <div className={`toolbar-status toolbar-status--${statusTone(projectStatus)}`}>
          <span>{t("common.status")}</span>
          <strong>{statusLabel}</strong>
        </div>
        {pendingCheckpoint ? (
          <div className="toolbar-status toolbar-status--warning">
            <span>{t("dashboard.checkpointPending")}</span>
            <strong>{pendingCheckpoint.checkpoint_id || t("common.yes")}</strong>
          </div>
        ) : null}
        <div className="toolbar-status toolbar-status--neutral">
          <span>{t("toolbar.plan")}</span>
          <strong>{planStatusLabel}</strong>
        </div>
      </div>

      <div className="ide-toolbar__group">
        <button
          className={`toolbar-button ${activeCenterTab === "app-settings" ? "toolbar-button--accent" : ""}`}
          onClick={onOpenSettings}
          type="button"
        >
          {t("toolbar.programSettings")}
        </button>
        <button className="toolbar-button" onClick={onGeneratePlan} type="button" disabled={busy}>
          {t("action.generatePlan")}
        </button>
        <button className="toolbar-button toolbar-button--accent" onClick={onRunPlan} type="button" disabled={busy}>
          {t("action.runRemaining")}
        </button>
        {pendingCheckpoint ? (
          <button className="toolbar-button toolbar-button--accent" onClick={onApproveCheckpoint} type="button" disabled={busy}>
            {t("action.approveCheckpoint")}
          </button>
        ) : null}
      </div>
    </header>
  );
}
