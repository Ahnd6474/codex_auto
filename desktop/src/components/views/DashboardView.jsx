import { memo, useMemo } from "react";
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
  visibleExecutionJob,
} from "../../utils";

function Stat({ label, value, tone = "neutral", icon, sub }) {
  return (
    <div className={`metric-card metric-card--${tone} metric-card--dashboard`}>
      {icon ? <div className="metric-card__icon-sm">{icon}</div> : null}
      <span className="metric-card__label">{label}</span>
      <strong>{value}</strong>
      {sub ? <span className="metric-card__sub">{sub}</span> : null}
    </div>
  );
}

function StepsIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M9 11l3 3L22 4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function CheckpointIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.7" />
      <path d="M12 7v5l3 2" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

function TokenInIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M12 2L2 7l10 5 10-5-10-5z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
      <path d="M2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
    </svg>
  );
}

function TokenOutIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M18 20V10M12 20V4M6 20v-6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function ClockIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" />
      <path d="M12 7v5l3 2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function PlanIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
      <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
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

function DashboardHeaderIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3" y="3" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
    </svg>
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

function dashboardViewPropsEqual(previousProps, nextProps) {
  return (
    previousProps.detail === nextProps.detail
    && previousProps.planDraft === nextProps.planDraft
    && previousProps.modelPresets === nextProps.modelPresets
    && previousProps.modelCatalog === nextProps.modelCatalog
    && previousProps.activeJob === nextProps.activeJob
    && previousProps.programSettings === nextProps.programSettings
  );
}

export const DashboardView = memo(function DashboardView({ detail, planDraft, modelPresets, modelCatalog, activeJob, programSettings }) {
  const { language, t } = useI18n();
  const executionJob = visibleExecutionJob(activeJob);
  const usage = detail?.snapshot?.recent_usage || {};
  const codexStatus = detail?.codex_status || {};
  const runtimeInsights = detail?.runtime_insights || {};
  const executionEstimate = runtimeInsights?.execution || {};
  const costEstimate = runtimeInsights?.cost || {};
  const parallelInsight = runtimeInsights?.parallel || {};
  const account = codexStatus.account || {};
  const usageBuckets = useMemo(
    () => codexUsageBuckets(codexStatus, language),
    [codexStatus, language],
  );
  const dashboardVisibility = normalizeDashboardVisibility(programSettings?.dashboard_visibility);
  const livePlan = executionJob?.status === "running" && detail?.plan ? detail.plan : planDraft;
  const allSteps = livePlan?.steps || [];
  const stepCounts = useMemo(() => {
    let completed = 0;
    let pending = 0;
    for (const step of allSteps) {
      if (step?.status === "completed") {
        completed += 1;
      } else {
        pending += 1;
      }
    }
    return { completed, pending };
  }, [allSteps]);
  const projectStatus = detail?.project?.current_status || "idle";
  const parallelLimitValue = parallelWorkerLabel(parallelInsight.recommended_workers ?? 1, language);
  const parallelLimitDetails = parallelLimitDescription(parallelInsight, language);
  const showEstimatedCost = shouldShowEstimatedCost(detail?.runtime || {}, costEstimate);
  const activeStatusKey = projectStatusWithJob(projectStatus, executionJob) || "idle";
  const activeStatus = displayStatus(activeStatusKey, language);
  const tone = statusTone(activeStatusKey);

  const metricItems = useMemo(
    () => [
      { key: "remaining_steps", label: t("dashboard.remainingSteps"), value: stepCounts.pending, tone: "info", icon: <StepsIcon /> },
      {
        key: "checkpoint_pending",
        label: t("dashboard.checkpointPending"),
        value: detail?.checkpoints?.pending ? t("common.yes") : t("common.no"),
        tone: detail?.checkpoints?.pending ? "warning" : "neutral",
        icon: <CheckpointIcon />,
      },
      { key: "input_tokens", label: t("dashboard.inputTokens"), value: (usage.input_tokens ?? 0).toLocaleString(), icon: <TokenInIcon /> },
      { key: "output_tokens", label: t("dashboard.outputTokens"), value: (usage.output_tokens ?? 0).toLocaleString(), icon: <TokenOutIcon /> },
      {
        key: "estimated_remaining",
        label: t("dashboard.estimatedRemaining"),
        value: formatDurationCompact(executionEstimate.remaining_seconds ?? 0, language),
        tone: "info",
        icon: <ClockIcon />,
      },
      ...(showEstimatedCost
        ? [
            { key: "estimated_cost", label: t("dashboard.estimatedCost"), value: formatUsd(costEstimate.estimated_total_cost_usd ?? 0, language) },
            { key: "actual_cost", label: t("dashboard.actualCost"), value: formatUsd(costEstimate?.recent?.estimated_cost_usd ?? 0, language) },
          ]
        : []),
      { key: "codex_plan", label: t("dashboard.codexPlan"), value: account.plan_type || t("common.unavailable"), tone: "neutral", icon: <PlanIcon /> },
      ...usageBuckets.map((bucket) => ({
        key: `rate_limit_${bucket.key}`,
        label: bucket.label,
        value: rateLimitRemainingLabel(bucket.window, language),
        tone: bucket.window && (bucket.window.remaining_percent ?? 0) < 25 ? "warning" : "success",
      })),
    ].filter((item) => dashboardVisibility[item.key] !== false),
    [
      account.plan_type,
      costEstimate,
      dashboardVisibility,
      detail?.checkpoints?.pending,
      executionEstimate.remaining_seconds,
      language,
      showEstimatedCost,
      stepCounts.pending,
      t,
      usage.input_tokens,
      usage.output_tokens,
      usageBuckets,
    ],
  );

  return (
    <section className="workspace-view">
      <div className="view-header">
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <div className="view-header-icon">
            <DashboardHeaderIcon />
          </div>
          <div>
            <span className="eyebrow">{t("dashboard.dashboard")}</span>
            <h2>{detail?.project?.display_name || detail?.project?.slug || t("dashboard.noProjectSelected")}</h2>
          </div>
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
                {stepCounts.completed}/{allSteps.length} {language === "ko" ? "단계 완료" : "steps done"}
              </span>
              <ProgressBar completed={stepCounts.completed} total={allSteps.length} tone={tone} />
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
}, dashboardViewPropsEqual);
