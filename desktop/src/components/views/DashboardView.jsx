import { useI18n } from "../../i18n";
import { displayStatus } from "../../locale";
import {
  codexUsageBuckets,
  formatDurationCompact,
  formatUsd,
  normalizeDashboardVisibility,
  parallelLimitDescription,
  parallelWorkerLabel,
  projectStatusWithJob,
  rateLimitRemainingLabel,
  rateLimitWindowSummary,
  runtimeSummary,
  shouldShowEstimatedCost,
  statusTone,
} from "../../utils";

function Stat({ label, value, tone = "neutral", icon, sub }) {
  return (
    <div className={`metric-card metric-card--${tone} metric-card--dashboard`}>
      {icon ? <div className="metric-card__icon-sm">{icon}</div> : null}
      <span>{label}</span>
      <strong>{value}</strong>
      {sub ? <span className="metric-card__sub">{sub}</span> : null}
    </div>
  );
}

function ProgressBar({ completed, total, tone }) {
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
  return (
    <div className="dashboard-progress">
      <div className="dashboard-progress__bar">
        <div
          className={`dashboard-progress__fill dashboard-progress__fill--${tone || "info"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="dashboard-progress__label">{pct}%</span>
    </div>
  );
}

function RuntimeIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" />
      <path d="M12 7v5l3 2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function UsageIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M18 20V10M12 20V4M6 20v-6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

export function DashboardView({ detail, planDraft, modelPresets, modelCatalog, activeJob, programSettings }) {
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
  const livePlan = activeJob?.status === "running" && detail?.plan ? detail.plan : planDraft;
  const allSteps = livePlan?.steps || [];
  const completedSteps = allSteps.filter((step) => step.status === "completed");
  const pendingSteps = allSteps.filter((step) => step.status !== "completed");
  const projectStatus = detail?.project?.current_status || "idle";
  const parallelLimitValue = parallelWorkerLabel(parallelInsight.recommended_workers ?? 1, language);
  const parallelLimitDetails = parallelLimitDescription(parallelInsight, language);
  const showEstimatedCost = shouldShowEstimatedCost(detail?.runtime || {}, costEstimate);
  const activeStatusKey = projectStatusWithJob(projectStatus, activeJob) || "idle";
  const activeStatus = displayStatus(activeStatusKey, language);
  const tone = statusTone(activeStatusKey);

  const metricItems = [
    { key: "remaining_steps", label: t("dashboard.remainingSteps"), value: pendingSteps.length, tone: "info" },
    {
      key: "checkpoint_pending",
      label: t("dashboard.checkpointPending"),
      value: detail?.checkpoints?.pending ? t("common.yes") : t("common.no"),
      tone: detail?.checkpoints?.pending ? "warning" : "neutral",
    },
    { key: "input_tokens", label: t("dashboard.inputTokens"), value: (usage.input_tokens ?? 0).toLocaleString() },
    { key: "output_tokens", label: t("dashboard.outputTokens"), value: (usage.output_tokens ?? 0).toLocaleString() },
    {
      key: "estimated_remaining",
      label: t("dashboard.estimatedRemaining"),
      value: formatDurationCompact(executionEstimate.remaining_seconds ?? 0, language),
      tone: "info",
    },
    ...(showEstimatedCost
      ? [
          { key: "estimated_cost", label: t("dashboard.estimatedCost"), value: formatUsd(costEstimate.estimated_total_cost_usd ?? 0, language) },
          { key: "actual_cost", label: t("dashboard.actualCost"), value: formatUsd(costEstimate?.recent?.estimated_cost_usd ?? 0, language) },
        ]
      : []),
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

      {dashboardVisibility.status !== false ? (
        <div className={`dashboard-hero dashboard-hero--${tone}`}>
          <div className="dashboard-hero__left">
            <div className={`dashboard-hero__dot dashboard-hero__dot--${tone}`} />
            <div>
              <span className="dashboard-hero__eyebrow">{language === "ko" ? "현재 상태" : "Current Status"}</span>
              <strong className="dashboard-hero__status">{activeStatus}</strong>
            </div>
          </div>
          {allSteps.length > 0 ? (
            <div className="dashboard-hero__right">
              <span className="dashboard-hero__progress-label">
                {completedSteps.length}/{allSteps.length} {language === "ko" ? "단계 완료" : "steps done"}
              </span>
              <ProgressBar completed={completedSteps.length} total={allSteps.length} tone={tone} />
            </div>
          ) : null}
        </div>
      ) : null}

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
                <RuntimeIcon />
                <strong>{t("dashboard.runtime")}</strong>
              </div>
              <div className="dashboard-detail-list">
                <div className="dashboard-detail-row"><span>{language === "ko" ? "모델" : "Model"}</span><strong>{runtimeSummary(detail?.runtime || {}, modelPresets, language, modelCatalog)}</strong></div>
                <div className="dashboard-detail-row"><span>{t("field.parallelWorkers")}</span><strong>{parallelLimitValue}</strong></div>
                <div className="dashboard-detail-row"><span>{t("run.parallelLimit")}</span><strong>{parallelLimitDetails}</strong></div>
                <div className="dashboard-detail-row"><span>{t("run.estimatedTotal")}</span><strong>{formatDurationCompact(executionEstimate.estimated_total_seconds ?? 0, language)}</strong></div>
                <div className="dashboard-detail-row"><span>{t("common.branch")}</span><strong>{detail?.project?.branch || t("common.unknown")}</strong></div>
                <div className="dashboard-detail-row"><span>{t("dashboard.origin")}</span><strong style={{ wordBreak: "break-all", fontSize: "11px" }}>{detail?.project?.origin_url || t("common.localOnly")}</strong></div>
              </div>
            </div>
          ) : null}

          {dashboardVisibility.codex_usage_card ? (
            <div className="content-card">
              <div className="content-card__header">
                <UsageIcon />
                <strong>{t("dashboard.codexUsage")}</strong>
              </div>
              {(usageBuckets || []).some((bucket) => bucket.window) ? (
                <div className="dashboard-detail-list">
                  <div className="dashboard-detail-row"><span>{t("common.auth")}</span><strong>{account.type || t("common.unavailable")}</strong></div>
                  <div className="dashboard-detail-row"><span>{t("common.account")}</span><strong>{account.email || t("common.unavailable")}</strong></div>
                  {usageBuckets.map((bucket) => (
                    <div key={bucket.key} className="dashboard-detail-row">
                      <span>{bucket.label}</span>
                      <strong>{rateLimitWindowSummary(bucket.window, language)}</strong>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="empty-block">{codexStatus.error || t("common.unavailable")}</div>
              )}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
