import { useI18n } from "../../i18n";
import { displayStatus } from "../../locale";
import { commandLabel, runtimeSummary, statusTone } from "../../utils";

function Stat({ label, value, tone = "neutral" }) {
  return (
    <div className={`metric-card metric-card--${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function DashboardView({ detail, planDraft, modelPresets, activeJob }) {
  const usage = detail?.snapshot?.recent_usage || {};
  const pendingSteps = (planDraft?.steps || []).filter((step) => step.status !== "completed");
  const { language, t } = useI18n();
  const activeStatus =
    activeJob?.status === "running"
      ? displayStatus(`running:${commandLabel(activeJob.command, language)}`, language)
      : displayStatus(detail?.project?.current_status || "idle", language);

  return (
    <section className="workspace-view">
      <div className="view-header">
        <div>
          <span className="eyebrow">{t("dashboard.dashboard")}</span>
          <h2>{detail?.project?.display_name || detail?.project?.slug || t("dashboard.noProjectSelected")}</h2>
        </div>
      </div>

      <div className="metrics-grid">
        <Stat label={t("common.status")} value={activeStatus} tone={statusTone(detail?.project?.current_status)} />
        <Stat label={t("dashboard.remainingSteps")} value={pendingSteps.length} tone="info" />
        <Stat label={t("dashboard.checkpointPending")} value={detail?.checkpoints?.pending ? t("common.yes") : t("common.no")} tone={detail?.checkpoints?.pending ? "warning" : "neutral"} />
        <Stat label={t("dashboard.lastSafeRevision")} value={detail?.project?.current_safe_revision || t("common.unavailable")} />
        <Stat label={t("dashboard.inputTokens")} value={usage.input_tokens ?? 0} />
        <Stat label={t("dashboard.outputTokens")} value={usage.output_tokens ?? 0} />
      </div>

      <div className="overview-grid">
        <div className="content-card">
          <div className="content-card__header">
            <strong>{t("dashboard.runtime")}</strong>
          </div>
          <p>{runtimeSummary(detail?.runtime || {}, modelPresets, language)}</p>
          <p>{t("common.verification")}: {detail?.runtime?.test_cmd || "python -m pytest"}</p>
          <p>{t("common.branch")}: {detail?.project?.branch || t("common.unknown")}</p>
          <p>{t("dashboard.origin")}: {detail?.project?.origin_url || t("common.localOnly")}</p>
        </div>

        <div className="content-card">
          <div className="content-card__header">
            <strong>{t("dashboard.checkpoint")}</strong>
          </div>
          {detail?.checkpoints?.pending ? (
            <>
              <p>{detail.checkpoints.pending.checkpoint_id}: {detail.checkpoints.pending.title}</p>
              <p>{t("dashboard.targetBlock", { block: detail.checkpoints.pending.target_block })}</p>
              <p>{t("common.status")}: {displayStatus(detail.checkpoints.pending.status, language)}</p>
            </>
          ) : (
            <div className="empty-block">{t("dashboard.noCheckpointWaiting")}</div>
          )}
        </div>
      </div>
    </section>
  );
}
