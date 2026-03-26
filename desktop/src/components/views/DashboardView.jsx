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

export function DashboardView({ detail, planDraft, modelPresets, modelCatalog, activeJob }) {
  const usage = detail?.snapshot?.recent_usage || {};
  const codexStatus = detail?.codex_status || {};
  const account = codexStatus.account || {};
  const rateLimits = codexStatus.rate_limits?.items || [];
  const primaryLimit = rateLimits[0] || {};
  const primaryWindow = primaryLimit.primary || null;
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
        <Stat label={language === "ko" ? "Codex 요금제" : "Codex Plan"} value={account.plan_type || t("common.unavailable")} tone="neutral" />
        <Stat
          label={language === "ko" ? "남은 사용량" : "Remaining Usage"}
          value={primaryWindow ? `${primaryWindow.remaining_percent ?? 0}%` : t("common.unavailable")}
          tone={primaryWindow && (primaryWindow.remaining_percent ?? 0) < 25 ? "warning" : "success"}
        />
      </div>

      <div className="overview-grid">
        <div className="content-card">
          <div className="content-card__header">
            <strong>{t("dashboard.runtime")}</strong>
          </div>
          <p>{runtimeSummary(detail?.runtime || {}, modelPresets, language, modelCatalog)}</p>
          <p>{t("common.verification")}: {detail?.runtime?.test_cmd || "python -m pytest"}</p>
          <p>{t("common.branch")}: {detail?.project?.branch || t("common.unknown")}</p>
          <p>{t("dashboard.origin")}: {detail?.project?.origin_url || t("common.localOnly")}</p>
        </div>

        <div className="content-card">
          <div className="content-card__header">
            <strong>{language === "ko" ? "Codex 사용량" : "Codex Usage"}</strong>
          </div>
          {primaryWindow ? (
            <>
              <p>{language === "ko" ? "인증 방식" : "Auth"}: {account.type || t("common.unavailable")}</p>
              <p>{language === "ko" ? "계정" : "Account"}: {account.email || t("common.unavailable")}</p>
              <p>{language === "ko" ? "현재 창 사용량" : "Primary Window"}: {primaryWindow.used_percent ?? 0}% used / {primaryWindow.remaining_percent ?? 0}% remaining</p>
              <p>{language === "ko" ? "리셋 시각" : "Resets At"}: {primaryWindow.resets_at || t("common.unavailable")}</p>
            </>
          ) : (
            <div className="empty-block">{codexStatus.error || t("common.unavailable")}</div>
          )}
        </div>
      </div>
    </section>
  );
}
