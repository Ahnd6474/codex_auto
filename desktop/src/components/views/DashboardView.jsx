import { useI18n } from "../../i18n";
import { displayStatus } from "../../locale";
import { codexUsageBuckets, commandLabel, rateLimitRemainingLabel, rateLimitWindowSummary, runtimeSummary, statusTone } from "../../utils";

function Stat({ label, value, tone = "neutral" }) {
  return (
    <div className={`metric-card metric-card--${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function DashboardView({ detail, planDraft, form, busy, modelPresets, modelCatalog, activeJob, onChangeForm }) {
  const { language, t } = useI18n();
  const usage = detail?.snapshot?.recent_usage || {};
  const codexStatus = detail?.codex_status || {};
  const account = codexStatus.account || {};
  const usageBuckets = codexUsageBuckets(codexStatus, language);
  const pendingSteps = (planDraft?.steps || []).filter((step) => step.status !== "completed");
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
        <Stat label={t("dashboard.inputTokens")} value={usage.input_tokens ?? 0} />
        <Stat label={t("dashboard.outputTokens")} value={usage.output_tokens ?? 0} />
        <Stat label={t("dashboard.codexPlan")} value={account.plan_type || t("common.unavailable")} tone="neutral" />
        {usageBuckets.map((bucket) => (
          <Stat
            key={bucket.key}
            label={bucket.label}
            value={rateLimitRemainingLabel(bucket.window, language)}
            tone={bucket.window && (bucket.window.remaining_percent ?? 0) < 25 ? "warning" : "success"}
          />
        ))}
      </div>

      <div className="overview-grid">
        <div className="content-card">
          <div className="content-card__header">
            <strong>{t("dashboard.runtime")}</strong>
          </div>
          <p>{runtimeSummary(detail?.runtime || {}, modelPresets, language, modelCatalog)}</p>
          <p>{t("common.branch")}: {detail?.project?.branch || t("common.unknown")}</p>
          <p>{t("dashboard.origin")}: {detail?.project?.origin_url || t("common.localOnly")}</p>
        </div>

        <div className="content-card">
          <div className="content-card__header">
            <strong>{t("dashboard.codexUsage")}</strong>
          </div>
          {(usageBuckets || []).some((bucket) => bucket.window) ? (
            <>
              <p>{t("common.auth")}: {account.type || t("common.unavailable")}</p>
              <p>{t("common.account")}: {account.email || t("common.unavailable")}</p>
              {usageBuckets.map((bucket) => (
                <p key={bucket.key}>{bucket.label}: {rateLimitWindowSummary(bucket.window, language)}</p>
              ))}
            </>
          ) : (
            <div className="empty-block">{codexStatus.error || t("common.unavailable")}</div>
          )}
        </div>
      </div>

      <div className="overview-grid">
        <div className="content-card">
          <div className="content-card__header">
            <strong>{t("reports.closeoutReport")}</strong>
          </div>
          <label className="choice-radio">
            <input
              type="checkbox"
              checked={Boolean(form?.runtime?.generate_word_report)}
              onChange={(event) =>
                onChangeForm((current) => ({
                  ...current,
                  runtime: {
                    ...current.runtime,
                    generate_word_report: event.target.checked,
                  },
                }))
              }
              disabled={busy}
            />
            <span>{t("option.generateWordReport")}</span>
          </label>
        </div>
      </div>
    </section>
  );
}
