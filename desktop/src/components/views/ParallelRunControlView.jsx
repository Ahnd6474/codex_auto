import { useEffect, useMemo, useRef, useState } from "react";
import { useI18n } from "../../i18n";
import { displayStatus } from "../../locale";
import { ExecutionFlowChart } from "../common/ExecutionFlowChart";
import {
  basename,
  canEditStep,
  CLAUDE_DEFAULT_MODEL,
  CLOSEOUT_STEP_ID,
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
  providerUsable,
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

/* ── Report format icons ── */
function WordIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <polyline points="14 2 14 8 20 8" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M8 13l2 6 2-4 2 4 2-6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function PptIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <rect x="2" y="4" width="20" height="14" rx="2" stroke="currentColor" strokeWidth="1.6" />
      <path d="M8 18v2M16 18v2M6 20h12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M9 8h3a2 2 0 0 1 0 4H9V8z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
    </svg>
  );
}
function WebpageIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" />
      <path d="M2 12h20M12 3c-2.5 3-4 5.5-4 9s1.5 6 4 9M12 3c2.5 3 4 5.5 4 9s-1.5 6-4 9" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
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
  form,
  busy,
  canRequestStop = false,
  canCancelReservation = false,
  queuedJobs = [],
  onPromptChange,
  onChangeForm,
  onGeneratePlan,
  onSavePlan,
  onResetPlan,
  onRunPlan,
  onRunManualDebugger,
  onRunManualMerger,
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
  const promptRef = useRef(null);
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
  const [failureDismissed, setFailureDismissed] = useState(false);
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
  const selectedStepIndex = selectedStep ? steps.findIndex((s) => s.step_id === selectedStepId) : -1;
  const parallelLimitValue = parallelWorkerLabel(parallelInsight.recommended_workers ?? 1, language);
  const parallelLimitDetails = parallelLimitDescription(parallelInsight, language);
  const parallelLimitCardTone = parallelLimitTone(parallelInsight);
  const projectStatus = projectStatusWithJob(detail?.project?.current_status || "", activeJob);
  const activeJobStatus = String(activeJob?.status || "").trim().toLowerCase();
  const selectedStepStatus = effectiveStepStatus(selectedStep, projectStatus);
  const closeoutStatus = String(livePlan?.closeout_status || "not_started").trim().toLowerCase();
  const showCloseoutStatus = closeoutStatus && closeoutStatus !== "not_started";
  const showEstimatedCost = shouldShowEstimatedCost(detail?.runtime || {}, costEstimate);
  const activeQueuePosition =
    activeJobStatus === "queued"
      ? queuedPosition(activeJob?.queue_position)
      : 0;
  const latestFailure = detail?.reports?.latest_failure || {};
  const failureArtifacts = useMemo(
    () => (Array.isArray(latestFailure?.artifact_files) ? latestFailure.artifact_files.slice(0, 8) : []),
    [latestFailure?.artifact_files],
  );
  const hideFailureCard = activeJobStatus === "queued" || activeJobStatus === "running";
  const showFailureCard = Boolean(
    !hideFailureCard
      && (
        latestFailure?.summary
        || latestFailure?.report_markdown_file
        || latestFailure?.report_json_file
        || failureArtifacts.length
      ),
  );
  const manualDebuggerLabel = language === "ko" ? "디버거 호출" : "Run Debugger";
  const manualMergerLabel = language === "ko" ? "머저 호출" : "Run Merger";
  const manualRecoveryHint = language === "ko"
    ? "자동 복구가 실패했을 때 최근 실패 로그로 debugger를 다시 실행하거나, 현재 git 충돌 상태를 merger에 넘길 수 있습니다."
    : "When automatic recovery falls short, rerun the debugger against the latest failure logs or hand the current git conflict to the merger.";

  useEffect(() => {
    setFailureDismissed(false);
  }, [latestFailure?.summary, latestFailure?.report_markdown_file, latestFailure?.report_json_file]);

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

  // Auto-resize textarea based on content
  useEffect(() => {
    const el = promptRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`;
  }, [promptDraft]);

  useEffect(() => {
    if (!selectedStep) return undefined;
    const handler = (e) => { if (e.key === "Escape") onSelectStep?.(null); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [selectedStep, onSelectStep]);

  return (
    <section className="workspace-view run-view">
      {/* ── Compact metric ribbon ── */}
      <div className="run-ribbon">
        <div className="run-ribbon__metrics">
          <span className={`run-ribbon__chip run-ribbon__chip--${statusTone(projectStatus)}`}>{displayStatus(projectStatus || "idle", language)}</span>
          <span className="run-ribbon__chip">{completedCount}/{steps.length || 0} {t("run.done")}</span>
          <span className="run-ribbon__chip">{readyNodes.length} {t("run.parallelReady")}</span>
          {queuedJobs.length ? <span className="run-ribbon__chip">{queuedJobs.length} {t("run.reservations")}</span> : null}
          {executionEstimate.remaining_seconds ? <span className="run-ribbon__chip">{formatDurationCompact(executionEstimate.remaining_seconds, language)} {t("run.estimatedRemaining")}</span> : null}
          {showEstimatedCost ? <span className="run-ribbon__chip">{formatUsd(costEstimate.estimated_total_cost_usd ?? 0, language)}</span> : null}
          <span className="run-ribbon__chip">{parallelLimitValue} {t("run.parallelLimit")}</span>
          {showCloseoutStatus ? <span className={`run-ribbon__chip run-ribbon__chip--${statusTone(livePlan?.closeout_status)}`}>{t("run.closeout")}: {displayStatus(livePlan?.closeout_status || "not_started", language)}</span> : null}
          {detail?.run_control?.stop_immediately ? <span className="run-ribbon__chip run-ribbon__chip--warning">{t("run.stopAfterStep")}</span> : null}
        </div>
        <div className="run-ribbon__actions">
          <label className="auto-run-badge">
            <input type="checkbox" checked={Boolean(autoRunAfterPlan)} onChange={(event) => onAutoRunAfterPlanChange?.(event.target.checked)} disabled={busy} />
            <span>{t("run.autoRunAfterPlan")}</span>
          </label>
          <button className="toolbar-btn" onClick={onGeneratePlan} type="button" disabled={busy}><GenerateIcon /><span>{t("action.generate")}</span></button>
          <button className="toolbar-btn" onClick={onSavePlan} type="button" disabled={busy}><SaveIcon /><span>{t("action.save")}</span></button>
          <button className="toolbar-btn" onClick={onResetPlan} type="button"><ResetIcon /><span>{t("action.reset")}</span></button>
          <div className="toolbar-divider" />
          <button className="toolbar-btn toolbar-btn--accent" onClick={onRunPlan} type="button" disabled={busy}><RunIcon /><span>{t("action.run")}</span></button>
          {canCancelReservation ? (
            <button className="toolbar-btn" onClick={() => onCancelQueuedJob?.(activeJob?.id)} type="button">{t("action.cancelReservation")}</button>
          ) : null}
          <button
            className="toolbar-btn"
            onClick={onRequestStop}
            type="button"
            disabled={!canRequestStop}
            style={canRequestStop ? { color: "var(--danger)" } : {}}
          >
            <StopIcon /><span>{t("action.stop")}</span>
          </button>
        </div>
      </div>

      {/* ── Failure card ── */}
      {showFailureCard && !failureDismissed ? (
        <div className="content-card" style={{ borderColor: "rgba(200,93,97,0.4)" }}>
          <div className="content-card__header">
            <strong style={{ color: "var(--danger)" }}>{t("test.failed")}</strong>
            <span className={`status-badge status-badge--${statusTone("failed")}`}>{displayStatus("failed", language)}</span>
            <button
              className="step-editor-close"
              onClick={() => setFailureDismissed(true)}
              type="button"
              title={language === "ko" ? "닫기" : "Dismiss"}
              aria-label={language === "ko" ? "닫기" : "Dismiss"}
            >✕</button>
          </div>
          <div className="step-editor-grid">
            {latestFailure?.summary ? <div className="field field--wide"><span>{t("common.status")}</span><p>{latestFailure.summary}</p></div> : null}
            {latestFailure?.report_markdown_file ? <div className="field field--wide"><span>Failure report</span><p style={{ fontFamily: "monospace", fontSize: "12px" }}>{latestFailure.report_markdown_file}</p></div> : null}
            {latestFailure?.report_json_file ? <div className="field field--wide"><span>Failure bundle</span><p style={{ fontFamily: "monospace", fontSize: "12px" }}>{latestFailure.report_json_file}</p></div> : null}
            {failureArtifacts.length ? <div className="field field--wide"><span>Failure artifacts</span><p style={{ fontFamily: "monospace", fontSize: "12px" }}>{failureArtifacts.join("\n")}</p></div> : null}
          </div>
          <div className="action-row" style={{ marginTop: "12px" }}>
            <button className="toolbar-btn toolbar-btn--accent" onClick={onRunManualDebugger} type="button" disabled={busy}>
              <RunIcon /><span>{manualDebuggerLabel}</span>
            </button>
            <button className="toolbar-btn" onClick={onRunManualMerger} type="button" disabled={busy}>
              <RunIcon /><span>{manualMergerLabel}</span>
            </button>
          </div>
          <p style={{ marginTop: "10px", fontSize: "12px", color: "var(--text-dim)" }}>{manualRecoveryHint}</p>
        </div>
      ) : null}

      {/* ── Flow chart (main area) ── */}
      <div className="run-flow-area">
        {steps.length ? (
          <ExecutionFlowChart steps={steps} projectStatus={projectStatus} language={language} selectedStepId={selectedStepId} onSelectStep={onSelectStep} />
        ) : (
          <div className="empty-block" style={{ margin: "40px auto" }}>
            <svg viewBox="0 0 48 48" fill="none" style={{ width: 48, height: 48 }}>
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

      {/* ── Queue (inline if any) ── */}
      {queuedJobs.length ? (
        <div className="run-queue-strip">
          <strong>{t("run.reservations")} ({queuedJobs.length})</strong>
          <div className="run-queue-strip__list">
            {queuedJobs.map((job) => (
              <div key={job.id} className="run-queue-strip__item">
                <span>{reservationProjectLabel(job, t("project.none"))}</span>
                <span className="status-badge status-badge--info" style={{ fontSize: "10px" }}>#{queuedPosition(job?.queue_position)}</span>
                <button className="toolbar-btn" onClick={() => onCancelQueuedJob?.(job.id)} type="button" style={{ fontSize: "10px", padding: "2px 4px" }}>{t("action.cancelReservation")}</button>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {/* ── Step editor (below flow) ── */}
      {selectedStep ? (
        <div className="run-step-editor">
          <div className="run-step-editor__header">
            <strong>{selectedStep.step_id}: {selectedStep.title || t("run.selectedStep")}</strong>
            {selectedStepIndex >= 0 ? (
              <span className="step-position-badge">{selectedStepIndex + 1}/{steps.length}</span>
            ) : null}
            <span className={`status-badge status-badge--${statusTone(selectedStepStatus)}`}>
              {displayStatus(selectedStepStatus, language)}
            </span>
            <button
              className="step-editor-close"
              onClick={() => onSelectStep?.(null)}
              type="button"
              title={language === "ko" ? "닫기 (Esc)" : "Close (Esc)"}
              aria-label={language === "ko" ? "닫기" : "Close"}
            >✕</button>
          </div>

          {selectedSystemStep ? (
            <div className="step-editor-grid">
              <div className="field field--wide"><span>{t("field.description")}</span><p>{selectedStep.display_description || t("run.noSummary")}</p></div>
              {selectedStep.deadline_at ? <div className="field field--wide"><span>{language === "ko" ? "마감" : "Deadline"}</span><p>{selectedStep.deadline_at}</p></div> : null}
              <div className="field field--wide"><span>{t("field.dependsOn")}</span><p>{(selectedStep.depends_on || []).join(", ") || t("common.none")}</p></div>
              {selectedStep.notes ? <div className="field field--wide"><span>{t("common.status")}</span><p>{selectedStep.notes}</p></div> : null}
              {selectedStep.step_id === CLOSEOUT_STEP_ID ? (
                <div className="field field--wide">
                  <span>{language === "ko" ? "보고서 형식" : "Report Formats"}</span>
                  <div className="report-format-row">
                    <span className="report-format-chip report-format-chip--word"><WordIcon />Word</span>
                    <span className="report-format-chip report-format-chip--ppt"><PptIcon />PowerPoint</span>
                    <span className="report-format-chip report-format-chip--web"><WebpageIcon />Webpage</span>
                  </div>
                </div>
              ) : null}
            </div>
          ) : (
            <div className="step-fields-2col">
              {selectedStepEstimate ? (
                <div className="field field--wide">
                  <div style={{ display: "flex", gap: "16px", padding: "6px 10px", background: "var(--bg-panel-alt)", borderRadius: "var(--radius-sm)", border: "1px solid var(--border)", fontSize: "11px" }}>
                    <div><span style={{ color: "var(--text-dim)" }}>{language === "ko" ? "예상" : "Est."}</span> <strong>{formatDurationCompact(selectedStepEstimate?.estimated_duration_seconds ?? 0, language)}</strong></div>
                    <div><span style={{ color: "var(--text-dim)" }}>{t("run.currentRemaining")}</span> <strong>{formatDurationCompact(selectedStepEstimate?.remaining_seconds ?? 0, language)}</strong></div>
                  </div>
                </div>
              ) : null}

              <label className="field field--wide"><span>{t("field.title")}</span><input value={selectedStep.title || ""} onChange={(event) => onUpdateStepField("title", event.target.value)} disabled={!editableStep} /></label>

              <label className="field">
                <span>{language === "ko" ? "마감" : "Deadline"}</span>
                <input
                  value={selectedStep.deadline_at || ""}
                  onChange={(event) => onUpdateStepField("deadline_at", event.target.value)}
                  disabled={!editableStep}
                  placeholder={language === "ko" ? "예: 2026-04-05 18:00" : "Example: 2026-04-05 18:00"}
                />
              </label>

              <label className="field"><span>{t("field.gptReasoning")}</span>
                <select value={selectedStep.reasoning_effort || detail?.runtime?.effort || "high"} onChange={(event) => onUpdateStepField("reasoning_effort", event.target.value)} disabled={!editableStep}>
                  {REASONING_OPTIONS.map((effort) => (<option key={effort} value={effort}>{reasoningEffortLabel(effort, language)}</option>))}
                </select>
              </label>

              <label className="field"><span>{t("field.modelProvider")}</span>
                <select value={selectedStep.model_provider || ""} onChange={(event) => onUpdateStepField("model_provider", event.target.value)} disabled={!editableStep}>
                  <option value="">{autoProviderLabel(language)}</option>
                  {providerOptions.map(([value, label]) => (<option key={value} value={value} disabled={!providerUsable(value, codexStatus)} title={providerStatusReason(value, codexStatus)}>{label}</option>))}
                </select>
                {selectedStep.model_provider && !providerUsable(selectedStep.model_provider, codexStatus) && providerStatusReason(selectedStep.model_provider, codexStatus) ? (
                  <small className="field-hint" style={{ color: "var(--warning)" }}>{providerStatusReason(selectedStep.model_provider, codexStatus)}</small>
                ) : null}
              </label>

              <label className="field field--wide"><span>{t("field.model")}</span>
                <input value={selectedStep.model || ""} placeholder={stepModelPlaceholder(selectedStep, detail?.runtime)} onChange={(event) => onUpdateStepField("model", event.target.value)} disabled={!editableStep} />
                <small className="field-hint">{stepAutoModelHint(language, detail?.runtime)}</small>
              </label>

              <label className="field field--wide"><span>{t("field.dependsOn")}</span><input value={(selectedStep.depends_on || []).join(", ")} onChange={(event) => onUpdateStepField("depends_on", normalizeListText(event.target.value))} disabled={!editableStep} placeholder="step_id1, step_id2" /></label>
              <label className="field field--wide"><span>{t("field.ownedPaths")}</span><textarea value={(selectedStep.owned_paths || []).join("\n")} onChange={(event) => onUpdateStepField("owned_paths", normalizeListText(event.target.value))} disabled={!editableStep} placeholder={language === "ko" ? "한 줄에 하나씩 파일 경로" : "One file path per line"} style={{ minHeight: "48px" }} /></label>
              <label className="field field--wide"><span>{t("field.description")}</span><textarea value={selectedStep.display_description || ""} onChange={(event) => onUpdateStepField("display_description", event.target.value)} disabled={!editableStep} style={{ minHeight: "56px" }} /></label>
              <label className="field field--wide"><span>{t("field.codexInstruction")}</span><textarea value={selectedStep.codex_description || ""} onChange={(event) => onUpdateStepField("codex_description", event.target.value)} disabled={!editableStep} style={{ minHeight: "56px" }} /></label>
              <label className="field field--wide"><span>{t("field.successCriteria")}</span><textarea value={selectedStep.success_criteria || ""} onChange={(event) => onUpdateStepField("success_criteria", event.target.value)} disabled={!editableStep} style={{ minHeight: "48px" }} /></label>

              <div className="action-row field--wide" style={{ paddingTop: "6px", borderTop: "1px solid var(--border)" }}>
                <button className="toolbar-btn toolbar-btn--accent" onClick={onSaveStepLocal} type="button" disabled={busy}><SaveIcon /><span>{t("action.saveLocal")}</span></button>
                <button className="toolbar-btn" onClick={onAddStep} type="button" disabled={busy}><span>{t("action.add")}</span></button>
                <button className="toolbar-btn" onClick={onDeleteStep} type="button" disabled={!editableStep} style={editableStep ? { color: "var(--danger)" } : {}}><span>{t("action.delete")}</span></button>
              </div>
            </div>
          )}
        </div>
      ) : null}
      {/* ── Prompt (bottom, ChatGPT-style) ── */}
      <div className="run-prompt-strip run-prompt-strip--bottom">
        <div className="run-prompt-strip__inner">
          <div className="run-prompt-strip__label-right">
            <span className="run-prompt-strip__count">{livePlan?.project_prompt?.length || 0} {language === "ko" ? "자" : "chars"}</span>
            <select
              className="run-effort-pill"
              value={form?.runtime?.effort || detail?.runtime?.effort || "high"}
              onChange={(event) =>
                onChangeForm?.((current) => ({
                  ...current,
                  runtime: { ...current.runtime, effort: event.target.value },
                }))
              }
              disabled={busy}
              title={language === "ko" ? "모델 추론 강도" : "Reasoning strength"}
            >
              {REASONING_OPTIONS.map((opt) => (
                <option key={opt} value={opt}>{reasoningEffortLabel(opt, language)}</option>
              ))}
            </select>
          </div>
          <textarea
            ref={promptRef}
            className="run-prompt-strip__input"
            value={promptDraft}
            onChange={(event) => setPromptDraft(event.target.value)}
            onBlur={() => { if (promptDraft !== promptValue) onPromptChange?.(promptDraft); }}
            disabled={busy}
            placeholder={language === "ko" ? "프로젝트 프롬프트를 입력하세요..." : "Enter your project prompt…"}
          />
        </div>
      </div>
    </section>
  );
}
