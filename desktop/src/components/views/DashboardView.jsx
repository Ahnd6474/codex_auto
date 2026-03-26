import { useI18n } from "../../i18n";
import { displayStatus } from "../../locale";
import {
  codexUsageBuckets,
  commandLabel,
  formatDurationCompact,
  formatUsd,
  isDebuggingStatus,
  normalizeDashboardVisibility,
  rateLimitRemainingLabel,
  rateLimitWindowSummary,
  runtimeSummary,
  statusTone,
} from "../../utils";

function Stat({ label, value, tone = "neutral" }) {
  return (
    <div className={`metric-card metric-card--${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function DashboardView({ detail, planDraft, form, busy, modelPresets, modelCatalog, activeJob, onChangeForm, programSettings }) {
  const { language, t } = useI18n();
  const usage = detail?.snapshot?.recent_usage || {};
  const codexStatus = detail?.codex_status || {};
  const runtimeInsights = detail?.runtime_insights || {};
  const executionEstimate = runtimeInsights?.execution || {};
  const costEstimate = runtimeInsights?.cost || {};
  const parallelInsight = runtimeInsights?.parallel || {};
  const account = codexStatus.account || {};
  const usageBuckets = codexUsageBuckets(codexStatus, language);
  const dashboardVisibility = normalizeDashboardVisibility(programSettings?.dashboard_visibility);
  const pendingSteps = (planDraft?.steps || []).filter((step) => step.status !== "completed");
  const projectStatus = detail?.project?.current_status || "idle";
  const activeStatus =
    activeJob?.status === "running" && !isDebuggingStatus(projectStatus)
      ? displayStatus(`running:${commandLabel(activeJob.command, language)}`, language)
      : displayStatus(projectStatus, language);
  const metricItems = [
    { key: "status", label: t("common.status"), value: activeStatus, tone: statusTone(detail?.project?.current_status) },
    { key: "remaining_steps", label: t("dashboard.remainingSteps"), value: pendingSteps.length, tone: "info" },
    {
      key: "checkpoint_pending",
      label: t("dashboard.checkpointPending"),
      value: detail?.checkpoints?.pending ? t("common.yes") : t("common.no"),
      tone: detail?.checkpoints?.pending ? "warning" : "neutral",
    },
    { key: "input_tokens", label: t("dashboard.inputTokens"), value: usage.input_tokens ?? 0 },
    { key: "output_tokens", label: t("dashboard.outputTokens"), value: usage.output_tokens ?? 0 },
    {
      key: "estimated_remaining",
      label: t("dashboard.estimatedRemaining"),
      value: formatDurationCompact(executionEstimate.remaining_seconds ?? 0, language),
      tone: "info",
    },
    { key: "estimated_cost", label: t("dashboard.estimatedCost"), value: formatUsd(costEstimate.estimated_total_cost_usd ?? 0, language) },
    { key: "actual_cost", label: t("dashboard.actualCost"), value: formatUsd(costEstimate?.recent?.estimated_cost_usd ?? 0, language) },
    { key: "codex_plan", label: t("dashboard.codexPlan"), value: account.plan_type || t("common.unavailable"), tone: "neutral" },
    ...usageBuckets.map((bucket) => ({
      key: `rate_limit_${bucket.key}`,
      label: bucket.label,
      value: rateLimitRemainingLabel(bucket.window, language),
      tone: bucket.window && (bucket.window.remaining_percent ?? 0) < 25 ? "warning" : "success",
    })),
  ].filter((item) => dashboardVisibility[item.key] !== false);

  return (
    <section className="workspace-view">
      <div className="view-header">
        <div>
          <span className="eyebrow">{t("dashboard.dashboard")}</span>
          <h2>{detail?.project?.display_name || detail?.project?.slug || t("dashboard.noProjectSelected")}</h2>
        </div>
      </div>

      {metricItems.length ? (
        <div className="metrics-grid">
          {metricItems.map((item) => (
            <Stat key={item.key} label={item.label} value={item.value} tone={item.tone} />
          ))}
        </div>
      ) : null}

      {dashboardVisibility.runtime_card || dashboardVisibility.codex_usage_card ? (
        <div className="overview-grid">
          {dashboardVisibility.runtime_card ? (
            <div className="content-card">
              <div className="content-card__header">
                <strong>{t("dashboard.runtime")}</strong>
              </div>
              <p>{runtimeSummary(detail?.runtime || {}, modelPresets, language, modelCatalog)}</p>
              {String(detail?.runtime?.execution_mode || "serial").trim().toLowerCase() === "parallel" ? (
                <p>
                  {t("field.parallelWorkers")}: {parallelInsight.recommended_workers ?? 1} / {parallelInsight.cpu_parallel_limit ?? 1}
                </p>
              ) : null}
              <p>{t("run.estimatedTotal")}: {formatDurationCompact(executionEstimate.estimated_total_seconds ?? 0, language)}</p>
              <p>{t("common.branch")}: {detail?.project?.branch || t("common.unknown")}</p>
              <p>{t("dashboard.origin")}: {detail?.project?.origin_url || t("common.localOnly")}</p>
            </div>
          ) : null}

          {dashboardVisibility.codex_usage_card ? (
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
          ) : null}
        </div>
      ) : null}

      {dashboardVisibility.word_report_card ? (
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
      ) : null}
    </section>
  );
}
