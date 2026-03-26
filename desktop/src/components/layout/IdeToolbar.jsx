import { useI18n } from "../../i18n";
import { displayStatus } from "../../locale";
import { commandLabel, progressCaption, statusTone } from "../../utils";

export function IdeToolbar({
  projectDetail,
  planDraft,
  busy,
  activeJob,
  onRefresh,
  onGeneratePlan,
  onRunPlan,
  onRunCloseout,
  onApproveCheckpoint,
  onToggleBottom,
}) {
  const status = activeJob?.status === "running" ? "running" : projectDetail?.project?.current_status || "idle";
  const checkpointPending = Boolean(projectDetail?.checkpoints?.pending);
  const projectName = projectDetail?.project?.display_name || projectDetail?.project?.slug || null;
  const { language, languageOptions, setLanguage, t } = useI18n();
  const statusLabel = activeJob?.status === "running" ? commandLabel(activeJob.command, language) : displayStatus(status, language);

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
        <div className={`toolbar-status toolbar-status--${statusTone(status)}`}>
          <span>{t("common.status")}</span>
          <strong>{statusLabel}</strong>
        </div>
        <div className="toolbar-status toolbar-status--neutral">
          <span>{t("toolbar.plan")}</span>
          <strong>{progressCaption(planDraft, language)}</strong>
        </div>
      </div>

      <div className="ide-toolbar__group">
        <label className="toolbar-select">
          <span>{t("common.language")}</span>
          <select value={language} onChange={(event) => setLanguage(event.target.value)}>
            {languageOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <button className="toolbar-button" onClick={onGeneratePlan} type="button" disabled={busy}>
          {t("action.generatePlan")}
        </button>
        <button className="toolbar-button toolbar-button--accent" onClick={onRunPlan} type="button" disabled={busy}>
          {t("action.runRemaining")}
        </button>
        <button className="toolbar-button" onClick={onRunCloseout} type="button" disabled={busy}>
          {t("action.closeout")}
        </button>
        <button className="toolbar-button" onClick={onApproveCheckpoint} type="button" disabled={busy || !checkpointPending}>
          {t("action.approveCheckpoint")}
        </button>
        <button className="toolbar-button toolbar-button--ghost" onClick={onToggleBottom} type="button" title={t("toolbar.toggleBottom")}>
          {t("toolbar.bottom")}
        </button>
      </div>
    </header>
  );
}
