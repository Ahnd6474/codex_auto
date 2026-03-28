import { useEffect, useMemo, useState } from "react";
import { useI18n } from "../../i18n";
import { displayStatus } from "../../locale";
import { ExecutionFlowChart } from "../common/ExecutionFlowChart";
import {
  basename,
  canEditStep,
  CLAUDE_DEFAULT_MODEL,
  DEEPSEEK_DEFAULT_MODEL,
  commandLabel,
  effectiveStepStatus,
  formatDurationCompact,
  formatUsd,
  GEMINI_DEFAULT_MODEL,
  GLM_DEFAULT_MODEL,
  isSystemStep,
  KIMI_DEFAULT_MODEL,
  MINIMAX_DEFAULT_MODEL,
  parallelLimitDescription,
  parallelLimitTone,
  parallelWorkerLabel,
  planStepsWithCloseout,
  providerAvailable,
  providerStatusReason,
  projectStatusWithJob,
  QWEN_CODE_DEFAULT_MODEL,
  REASONING_OPTIONS,
  reasoningEffortLabel,
  shouldShowEstimatedCost,
  statusTone,
} from "../../utils";

/* ── Metric card icons ── */
function StatusMetricIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.7" />
      <path d="M12 7v5l3 3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}
function DoneMetricIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <polyline points="20 6 9 17 4 12" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function ParallelMetricIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M5 3v18M12 3v18M19 3v18" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}
function QueueMetricIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M3 12h18M3 6h18M3 18h12" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}
function StopMetricIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <rect x="4" y="4" width="16" height="16" rx="2" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}
function ClockMetricIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.7" />
      <path d="M12 7v5l3 2" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}
function WorkersMetricIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <circle cx="9" cy="7" r="3" stroke="currentColor" strokeWidth="1.6" />
      <path d="M3 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M17 11l2 2 4-4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function CostMetricIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.7" />
      <path d="M12 7v1.5M12 15.5V17M9.5 9.5a2.5 2.5 0 0 1 5 0c0 1.5-1 2-2.5 2.5S9.5 13 9.5 15h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}
function CloseoutMetricIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
      <polyline points="14 2 14 8 20 8" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
      <path d="M9 13l2 2 4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function MetricCard({ tone, icon, iconTone, label, value, sub }) {
  return (
    <div className={`metric-card metric-card--${tone || "neutral"}`}>
      <div className={`metric-card__icon metric-card__icon--${iconTone || tone || "neutral"}`}>{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
      {sub ? <span style={{ fontSize: "11px" }}>{sub}</span> : null}
    </div>
  );
}

/* ── Button icons ── */
function GenerateIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M9 11l3 3L22 4" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function SaveIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" stroke="currentColor" strokeLinejoin="round" />
      <polyline points="17 21 17 13 7 13 7 21" stroke="currentColor" />
      <polyline points="7 3 7 8 15 8" stroke="currentColor" />
    </svg>
  );
}
function RunIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <polygon points="5 3 19 12 5 21 5 3" stroke="currentColor" strokeLinecap="round" fill="currentColor" fillOpacity="0.15" />
    </svg>
  );
}
function StopIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <rect x="4" y="4" width="16" height="16" rx="2" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}
function ResetIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M3 3v5h5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/* ── Helpers ── */
function autoProviderLabel(language) {
  return language === "ko" ? "자동 (AGENTS.md 선호)" : "Auto (AGENTS.md preference)";
}

function stepAutoModelHint(language, runtime) {
  const provider = String(runtime?.model_provider || "openai").trim().toLowerCase();
  if (provider === "ensemble") {
    return language === "ko"
      ? "비워두면 ensemble 라우팅을 따릅니다. 계획과 일반 구현은 Codex CLI를 쓰고, UI/프론트엔드 단계는 Claude Code를 우선 사용하며 Claude가 없으면 Gemini CLI로 대체합니다."
      : "Leave blank to follow ensemble routing: planning and general steps use Codex CLI, UI/frontend steps prefer Claude Code with Gemini CLI as fallback.";
  }
  return language === "ko"
    ? "비워두면 AGENTS.md 규칙에 따라 UI 단계는 Gemini CLI, 그 외 단계는 Codex CLI를 자동 선택합니다."
    : "Leave blank to follow AGENTS.md: UI steps prefer Gemini CLI, other steps prefer Codex CLI.";
}

function stepModelPlaceholder(step, runtime) {
  const provider = String(step?.model_provider || runtime?.model_provider || "").trim().toLowerCase();
  if (provider === "claude") return CLAUDE_DEFAULT_MODEL;
  if (provider === "gemini") return GEMINI_DEFAULT_MODEL;
  if (provider === "qwen_code") return QWEN_CODE_DEFAULT_MODEL;
  if (provider === "deepseek") return DEEPSEEK_DEFAULT_MODEL;
  if (provider === "kimi") return KIMI_DEFAULT_MODEL;
  if (provider === "minimax") return MINIMAX_DEFAULT_MODEL;
  if (provider === "glm") return GLM_DEFAULT_MODEL;
  if (provider === "openai" || provider === "ensemble") {
    return String(runtime?.model || runtime?.model_slug_input || "gpt-5.4").trim() || "gpt-5.4";
  }
  return "";
}

function normalizeListText(value) {
  const rawItems = Array.isArray(value) ? value : String(value || "").split(/[\r\n,]+/);
  const seen = new Set();
  return rawItems
    .map((item) => String(item || "").trim())
    .filter((item) => {
      if (!item || seen.has(item)) return false;
      seen.add(item);
      return true;
    });
}

function readyPendingSteps(steps) {
  const completed = new Set((steps || []).filter((s) => s.status === "completed").map((s) => s.step_id));
  return (steps || []).filter(
    (s) => s.status !== "completed" && (s.depends_on || []).every((dep) => completed.has(dep)),
  );
}

function queuedPosition(value) {
  return Math.max(1, Number.parseInt(String(value || 0), 10) || 1);
}

function reservationProjectLabel(job, fallbackLabel) {
  return String(job?.display_name || "").trim() || basename(job?.project_dir || "") || String(job?.repo_id || "").trim() || fallbackLabel;
}

/* ── Main view ── */
export function ParallelRunControlView({
  detail,
  codexStatus,
  planDraft,
  activeJob,
  autoRunAfterPlan,
  selectedStepId,
  busy,
  canRequestStop = false,
  canCancelReservation = false,
  queuedJobs = [],
  onPromptChange,
  onGeneratePlan,
  onSavePlan,
  onResetPlan,
  onRunPlan,
  onRequestStop,
  onCancelQueuedJob,
  onAutoRunAfterPlanChange,
  onSelectStep,
  onUpdateStepField,
  onSaveStepLocal,
  onAddStep,
  onDeleteStep,
}) {
  const { language, t } = useI18n();
  const providerOptions = [
    ["ensemble", t("option.providerEnsemble")],
    ["openai", "Codex CLI"],
    ["claude", "Claude Code"],
    ["gemini", "Gemini CLI"],
    ["qwen_code", "Qwen Code"],
    ["deepseek", "DeepSeek via Claude Code"],
    ["kimi", "Kimi"],
    ["minimax", "MiniMax via Claude Code"],
    ["glm", "GLM via Claude Code"],
    ["openrouter", "OpenRouter"],
    ["opencdk", "OpenCDK"],
    ["local_openai", "Local OpenAI-Compatible"],
    ["oss", "Local OSS"],
  ];

  const livePlan = activeJob?.status === "running" && detail?.plan ? detail.plan : planDraft;
  const promptValue = livePlan?.project_prompt || "";
  const [promptDraft, setPromptDraft] = useState(promptValue);
  const steps = useMemo(
    () =>
      planStepsWithCloseout(livePlan, {
        title: t("run.closeout"),
        description: t("reports.closeoutReport"),
        successCriteria: t("reports.closeoutReport"),
      }),
    [livePlan?.closeout_status, livePlan?.steps, t],
  );
  const readyNodes = useMemo(() => readyPendingSteps(steps), [steps]);
  const selectedStep = useMemo(
    () => steps.find((step) => step.step_id === selectedStepId) || null,
    [selectedStepId, steps],
  );
  const runtimeInsights = detail?.runtime_insights || {};
  const executionEstimate = runtimeInsights?.execution || {};
  const costEstimate = runtimeInsights?.cost || {};
  const parallelInsight = runtimeInsights?.parallel || {};
  const selectedStepEstimate = useMemo(
    () => (executionEstimate.step_estimates || []).find((item) => item.step_id === selectedStepId) || null,
    [executionEstimate.step_estimates, selectedStepId],
  );
  const editableStep = canEditStep(selectedStep, busy);
  const completedCount = useMemo(
    () => steps.filter((step) => step.status === "completed").length,
    [steps],
  );
  const selectedSystemStep = isSystemStep(selectedStep);
  const parallelLimitValue = parallelWorkerLabel(parallelInsight.recommended_workers ?? 1, language);
  const parallelLimitDetails = parallelLimitDescription(parallelInsight, language);
  const parallelLimitCardTone = parallelLimitTone(parallelInsight);
  const projectStatus = projectStatusWithJob(detail?.project?.current_status || "", activeJob);
  const selectedStepStatus = effectiveStepStatus(selectedStep, projectStatus);
  const closeoutStatus = String(livePlan?.closeout_status || "not_started").trim().toLowerCase();
  const showCloseoutStatus = closeoutStatus && closeoutStatus !== "not_started";
  const showEstimatedCost = shouldShowEstimatedCost(detail?.runtime || {}, costEstimate);
  const activeQueuePosition =
    String(activeJob?.status || "").trim().toLowerCase() === "queued"
      ? queuedPosition(activeJob?.queue_position)
      : 0;
  const latestFailure = detail?.reports?.latest_failure || {};
  const failureArtifacts = useMemo(
    () => (Array.isArray(latestFailure?.artifact_files) ? latestFailure.artifact_files.slice(0, 8) : []),
    [latestFailure?.artifact_files],
  );
  const showFailureCard = Boolean(
    latestFailure?.summary || latestFailure?.report_markdown_file || latestFailure?.report_json_file || failureArtifacts.length,
  );

  useEffect(() => {
    setPromptDraft(promptValue);
  }, [promptValue]);

  useEffect(() => {
    if (promptDraft === promptValue || typeof onPromptChange !== "function") {
      return undefined;
    }
    const timer = window.setTimeout(() => {
      onPromptChange(promptDraft);
    }, 180);
    return () => window.clearTimeout(timer);
  }, [onPromptChange, promptDraft, promptValue]);

  return (
    <section className="workspace-view">
      <div className="view-header">
        <div>
          <span className="eyebrow">{t("run.flow")}</span>
          <h2>{t("run.executionFlow")}</h2>
        </div>
      </div>

      {/* ── Metrics ── */}
      <div className="run-summary">
        <MetricCard tone={statusTone(projectStatus)} icon={<StatusMetricIcon />} iconTone={statusTone(projectStatus)} label={t("common.status")} value={displayStatus(projectStatus || "idle", language)} />
        <MetricCard tone="info" icon={<DoneMetricIcon />} iconTone="success" label={t("run.done")} value={`${completedCount}/${steps.length || 0}`} />
        <MetricCard tone="info" icon={<ParallelMetricIcon />} iconTone="info" label={t("run.parallelReady")} value={readyNodes.length} />
        <MetricCard tone="info" icon={<QueueMetricIcon />} iconTone="info" label={t("run.reservations")} value={queuedJobs.length} sub={activeQueuePosition ? t("run.queuePosition", { position: activeQueuePosition }) : null} />
        <MetricCard tone={detail?.run_control?.stop_immediately ? "warning" : "neutral"} icon={<StopMetricIcon />} iconTone={detail?.run_control?.stop_immediately ? "warning" : "neutral"} label={t("run.stopAfterStep")} value={detail?.run_control?.stop_immediately ? t("common.on") : t("common.off")} />
        <MetricCard tone="info" icon={<ClockMetricIcon />} iconTone="info" label={t("run.estimatedRemaining")} value={formatDurationCompact(executionEstimate.remaining_seconds ?? 0, language)} />
        <MetricCard tone={parallelLimitCardTone} icon={<WorkersMetricIcon />} iconTone={parallelLimitCardTone} label={t("run.parallelLimit")} value={parallelLimitValue} sub={parallelLimitDetails} />
        {showCloseoutStatus ? (
          <MetricCard tone={statusTone(livePlan?.closeout_status)} icon={<CloseoutMetricIcon />} iconTone={statusTone(livePlan?.closeout_status)} label={t("run.closeout")} value={displayStatus(livePlan?.closeout_status || "not_started", language)} />
        ) : null}
        {showEstimatedCost ? (
          <MetricCard tone="neutral" icon={<CostMetricIcon />} label={t("run.estimatedCost")} value={formatUsd(costEstimate.estimated_total_cost_usd ?? 0, language)} />
        ) : null}
      </div>

      {/* ── Failure card ── */}
      {showFailureCard ? (
        <div className="content-card" style={{ borderColor: "rgba(200,93,97,0.4)" }}>
          <div className="content-card__header">
            <strong style={{ color: "var(--danger)" }}>{t("test.failed")}</strong>
            <span className={`status-badge status-badge--${statusTone("failed")}`}>{displayStatus("failed", language)}</span>
          </div>
          <div className="step-editor-grid">
            {latestFailure?.summary ? <div className="field field--wide"><span>{t("common.status")}</span><p>{latestFailure.summary}</p></div> : null}
            {latestFailure?.report_markdown_file ? <div className="field field--wide"><span>Failure report</span><p style={{ fontFamily: "monospace", fontSize: "12px" }}>{latestFailure.report_markdown_file}</p></div> : null}
            {latestFailure?.report_json_file ? <div className="field field--wide"><span>Failure bundle</span><p style={{ fontFamily: "monospace", fontSize: "12px" }}>{latestFailure.report_json_file}</p></div> : null}
            {failureArtifacts.length ? <div className="field field--wide"><span>Failure artifacts</span><p style={{ fontFamily: "monospace", fontSize: "12px" }}>{failureArtifacts.join("\n")}</p></div> : null}
          </div>
        </div>
      ) : null}

      {/* ── Flow chart ── */}
      <div className="content-card content-card--flow">
        <div className="content-card__header">
          <strong>{t("run.flowChart")}</strong>
          <div className="flow-action-bar">
            <label className="auto-run-badge">
              <input type="checkbox" checked={Boolean(autoRunAfterPlan)} onChange={(event) => onAutoRunAfterPlanChange?.(event.target.checked)} disabled={busy} />
              <span>{t("run.autoRunAfterPlan")}</span>
              <span className={`status-badge status-badge--${autoRunAfterPlan ? "info" : "neutral"}`} style={{ fontSize: "11px" }}>
                {autoRunAfterPlan ? t("common.on") : t("common.off")}
              </span>
            </label>
            <div className="toolbar-divider" />
            <button className="toolbar-button" onClick={onGeneratePlan} type="button" disabled={busy}><GenerateIcon />{t("action.generate")}</button>
            <button className="toolbar-button" onClick={onSavePlan} type="button" disabled={busy}><SaveIcon />{t("action.save")}</button>
            <button className="toolbar-button toolbar-button--ghost" onClick={onResetPlan} type="button" disabled={busy}><ResetIcon />{t("action.reset")}</button>
            <div className="toolbar-divider" />
            <button className="toolbar-button toolbar-button--accent" onClick={onRunPlan} type="button" disabled={busy}><RunIcon />{t("action.run")}</button>
            {canCancelReservation ? (
              <button className="toolbar-button toolbar-button--ghost" onClick={() => onCancelQueuedJob?.(activeJob?.id)} type="button">{t("action.cancelReservation")}</button>
            ) : null}
            <button
              className="toolbar-button toolbar-button--ghost"
              onClick={onRequestStop}
              type="button"
              disabled={!canRequestStop}
              style={canRequestStop ? { color: "var(--danger)", borderColor: "rgba(200,93,97,0.4)" } : {}}
            >
              <StopIcon />{t("action.stop")}
            </button>
          </div>
        </div>

        {steps.length ? (
          <ExecutionFlowChart steps={steps} projectStatus={projectStatus} language={language} selectedStepId={selectedStepId} onSelectStep={onSelectStep} />
        ) : (
          <div className="empty-block">
            <svg viewBox="0 0 48 48" fill="none">
              <circle cx="24" cy="24" r="18" stroke="currentColor" strokeWidth="1.8" strokeDasharray="5 4" />
              <path d="M16 24l6 6 10-12" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span>{t("run.noSteps")}</span>
            <span style={{ fontSize: "12px", color: "var(--text-dim)" }}>
              {language === "ko" ? "플랜을 생성하면 단계가 표시됩니다." : "Generate a plan to see execution steps here."}
            </span>
          </div>
        )}
      </div>

      {/* ── Lower section ── */}
      <div className="run-layout">
        {/* Prompt */}
        <div className="content-card">
          <div className="content-card__header">
            <strong>{t("field.prompt")}</strong>
            <span style={{ fontSize: "11px", color: "var(--text-dim)" }}>
              {livePlan?.project_prompt?.length || 0} {language === "ko" ? "자" : "chars"}
            </span>
          </div>
          <textarea
            className="editor-textarea editor-textarea--prompt"
            value={promptDraft}
            onChange={(event) => setPromptDraft(event.target.value)}
            onBlur={() => {
              if (promptDraft !== promptValue) {
                onPromptChange?.(promptDraft);
              }
            }}
            disabled={busy}
            placeholder={language === "ko" ? "이 프로젝트에서 AI가 수행할 작업을 설명하세요..." : "Describe what the AI should accomplish in this project…"}
          />
        </div>

        {/* Queue */}
        <div className="content-card">
          <div className="content-card__header">
            <strong>{t("run.reservations")}</strong>
            <span className={`status-badge status-badge--${queuedJobs.length ? "info" : "neutral"}`}>{queuedJobs.length}</span>
          </div>
          {queuedJobs.length ? (
            <div className="step-editor-grid">
              {queuedJobs.map((job) => (
                <div key={job.id} className="field field--wide" style={{ padding: "8px 10px", background: "var(--bg-panel-alt)", borderRadius: "var(--radius-sm)", border: "1px solid var(--border)" }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "4px" }}>
                    <strong>{reservationProjectLabel(job, t("project.none"))}</strong>
                    <span className={`status-badge status-badge--${statusTone(`queued:${job?.command || ""}`)}`} style={{ fontSize: "11px" }}>
                      {displayStatus(`queued:${job?.command || ""}`, language)}
                    </span>
                  </div>
                  <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>{commandLabel(job?.command, language)}</span>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: "6px" }}>
                    <span style={{ fontSize: "11px", color: "var(--text-dim)" }}>
                      {t("run.queuePosition", { position: queuedPosition(job?.queue_position) })} · {t("run.queuePriority", { priority: Number.parseInt(String(job?.queue_priority ?? 0), 10) || 0 })}
                    </span>
                    <button className="toolbar-button toolbar-button--ghost" onClick={() => onCancelQueuedJob?.(job.id)} type="button" style={{ padding: "4px 8px", fontSize: "11px" }}>
                      {t("action.cancelReservation")}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-block">
              <QueueMetricIcon />
              <span>{t("run.noReservations")}</span>
            </div>
          )}
        </div>

        {/* Step editor */}
        <div className="content-card">
          <div className="content-card__header">
            <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
              <strong>{t("run.selectedStep")}</strong>
              {selectedStep ? <span style={{ fontSize: "11px", color: "var(--text-dim)" }}>{selectedStep.step_id}</span> : null}
            </div>
            <span className={`status-badge status-badge--${statusTone(selectedStepStatus)}`}>
              {selectedStep ? displayStatus(selectedStepStatus, language) : t("common.none")}
            </span>
          </div>

          {selectedStep ? (
            selectedSystemStep ? (
              <div className="step-editor-grid">
                <div className="field field--wide"><span>{t("field.title")}</span><strong>{selectedStep.title || t("run.closeout")}</strong></div>
                <div className="field field--wide"><span>{t("field.description")}</span><p>{selectedStep.display_description || t("run.noSummary")}</p></div>
                <div className="field field--wide"><span>{t("field.dependsOn")}</span><p>{(selectedStep.depends_on || []).join(", ") || t("common.none")}</p></div>
                <div className="field field--wide"><span>{t("field.successCriteria")}</span><p>{selectedStep.success_criteria || t("run.noSummary")}</p></div>
                {selectedStep.notes ? <div className="field field--wide"><span>{t("common.status")}</span><p>{selectedStep.notes}</p></div> : null}
              </div>
            ) : (
              <div className="step-fields-2col">
                {/* Time estimate */}
                {selectedStepEstimate ? (
                  <div className="field field--wide">
                    <div style={{ display: "flex", gap: "16px", padding: "8px 10px", background: "var(--bg-panel-alt)", borderRadius: "var(--radius-sm)", border: "1px solid var(--border)" }}>
                      <div>
                        <span style={{ fontSize: "10.5px", color: "var(--text-dim)", display: "block" }}>{language === "ko" ? "예상 시간" : "Estimated"}</span>
                        <strong style={{ fontSize: "13px" }}>{formatDurationCompact(selectedStepEstimate?.estimated_duration_seconds ?? 0, language)}</strong>
                      </div>
                      <div>
                        <span style={{ fontSize: "10.5px", color: "var(--text-dim)", display: "block" }}>{t("run.currentRemaining")}</span>
                        <strong style={{ fontSize: "13px" }}>{formatDurationCompact(selectedStepEstimate?.remaining_seconds ?? 0, language)}</strong>
                      </div>
                    </div>
                  </div>
                ) : null}

                <label className="field field--wide">
                  <span>{t("field.title")}</span>
                  <input value={selectedStep.title || ""} onChange={(event) => onUpdateStepField("title", event.target.value)} disabled={!editableStep} />
                </label>

                <label className="field">
                  <span>{t("field.gptReasoning")}</span>
                  <select value={selectedStep.reasoning_effort || detail?.runtime?.effort || "high"} onChange={(event) => onUpdateStepField("reasoning_effort", event.target.value)} disabled={!editableStep}>
                    {REASONING_OPTIONS.map((effort) => (
                      <option key={effort} value={effort}>{reasoningEffortLabel(effort, language)}</option>
                    ))}
                  </select>
                </label>

                <label className="field">
                  <span>{t("field.modelProvider")}</span>
                  <select value={selectedStep.model_provider || ""} onChange={(event) => onUpdateStepField("model_provider", event.target.value)} disabled={!editableStep}>
                    <option value="">{autoProviderLabel(language)}</option>
                    {providerOptions.map(([value, label]) => (
                      <option key={value} value={value} disabled={!providerAvailable(value, codexStatus)} title={providerStatusReason(value, codexStatus)}>
                        {label}
                      </option>
                    ))}
                  </select>
                  {selectedStep.model_provider && !providerAvailable(selectedStep.model_provider, codexStatus) && providerStatusReason(selectedStep.model_provider, codexStatus) ? (
                    <small className="field-hint" style={{ color: "var(--warning)" }}>{providerStatusReason(selectedStep.model_provider, codexStatus)}</small>
                  ) : null}
                </label>

                <label className="field field--wide">
                  <span>{t("field.model")}</span>
                  <input value={selectedStep.model || ""} placeholder={stepModelPlaceholder(selectedStep, detail?.runtime)} onChange={(event) => onUpdateStepField("model", event.target.value)} disabled={!editableStep} />
                  <small className="field-hint">{stepAutoModelHint(language, detail?.runtime)}</small>
                </label>

                <label className="field field--wide">
                  <span>{t("field.dependsOn")}</span>
                  <input value={(selectedStep.depends_on || []).join(", ")} onChange={(event) => onUpdateStepField("depends_on", normalizeListText(event.target.value))} disabled={!editableStep} placeholder="step_id1, step_id2" />
                </label>

                <label className="field field--wide">
                  <span>{t("field.ownedPaths")}</span>
                  <textarea value={(selectedStep.owned_paths || []).join("\n")} onChange={(event) => onUpdateStepField("owned_paths", normalizeListText(event.target.value))} disabled={!editableStep} placeholder={language === "ko" ? "한 줄에 하나씩 파일 경로" : "One file path per line"} style={{ minHeight: "60px" }} />
                </label>

                <label className="field field--wide">
                  <span>{t("field.description")}</span>
                  <textarea value={selectedStep.display_description || ""} onChange={(event) => onUpdateStepField("display_description", event.target.value)} disabled={!editableStep} style={{ minHeight: "72px" }} />
                </label>

                <label className="field field--wide">
                  <span>{t("field.codexInstruction")}</span>
                  <textarea value={selectedStep.codex_description || ""} onChange={(event) => onUpdateStepField("codex_description", event.target.value)} disabled={!editableStep} style={{ minHeight: "72px" }} />
                </label>

                <label className="field field--wide">
                  <span>{t("field.successCriteria")}</span>
                  <textarea value={selectedStep.success_criteria || ""} onChange={(event) => onUpdateStepField("success_criteria", event.target.value)} disabled={!editableStep} style={{ minHeight: "60px" }} />
                </label>

                <div className="action-row field--wide" style={{ paddingTop: "8px", borderTop: "1px solid var(--border)" }}>
                  <button className="toolbar-button toolbar-button--accent" onClick={onSaveStepLocal} type="button" disabled={busy}><SaveIcon />{t("action.saveLocal")}</button>
                  <button className="toolbar-button" onClick={onAddStep} type="button" disabled={busy}>{t("action.add")}</button>
                  <button className="toolbar-button toolbar-button--ghost" onClick={onDeleteStep} type="button" disabled={!editableStep} style={editableStep ? { color: "var(--danger)" } : {}}>{t("action.delete")}</button>
                </div>
              </div>
            )
          ) : (
            <div className="empty-block">
              <svg viewBox="0 0 48 48" fill="none">
                <rect x="8" y="8" width="32" height="32" rx="4" stroke="currentColor" strokeWidth="1.8" />
                <path d="M16 24h16M22 18l6 6-6 6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <span>{t("run.selectStep")}</span>
              <span style={{ fontSize: "12px", color: "var(--text-dim)" }}>
                {language === "ko" ? "위 흐름도에서 단계를 클릭하세요." : "Click a step in the flow chart above."}
              </span>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
