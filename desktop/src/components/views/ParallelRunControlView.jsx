import { memo, useEffect, useMemo, useRef, useState } from "react";
import { useI18n } from "../../i18n";
import { displayStatus } from "../../locale";
import { ExecutionFlowChart } from "../common/ExecutionFlowChart";
import {
  applyConfigRuntimeModelSelection,
  basename,
  canEditStep,
  canEditStepModel,
  CLAUDE_DEFAULT_MODEL,
  CLOSEOUT_STEP_ID,
  DEEPSEEK_DEFAULT_MODEL,
  commandLabel,
  effectiveStepStatus,
  failureReasonCode,
  failureReasonLabel,
  formatDurationCompact,
  formatUsd,
  GEMINI_DEFAULT_MODEL,
  groupedModelCatalogOptions,
  GLM_DEFAULT_MODEL,
  isSystemStep,
  KIMI_DEFAULT_MODEL,
  modelCatalogOptionValue,
  MINIMAX_DEFAULT_MODEL,
  modelDisplayName,
  mergeModelCatalogs,
  normalizedLocalModelProvider,
  providerOptionLabel,
  providerShortName,
  resolveModelCatalogEntry,
  runtimeExecutionModel,
  stepModelSelectionPatch,
  parallelLimitDescription,
  parallelLimitTone,
  parallelWorkerLabel,
  planStepsWithCloseout,
  providerAvailable,
  providerUsable,
  providerStatusReason,
  isActiveExecutionStatus,
  isPlanningProgressRunning,
  QWEN_CODE_DEFAULT_MODEL,
  REASONING_OPTIONS,
  reasoningEffortLabel,
  AUTO_REASONING_OPTION,
  MODEL_REASONING_OPTIONS,
  sameQueuedJobs,
  shouldShowEstimatedCost,
  statusTone,
  deriveExecutionUiState,
} from "../../utils";

/* ?? Metric card icons ?? */
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

/* ?? Button icons ?? */
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

/* ?? Report format icons ?? */
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

/* ?? Effort labels ?? */
function effortShortLabel(value, language) {
  const ko = language === "ko";
  switch (String(value || "").toLowerCase()) {
    case "auto": return ko ? "Auto" : "Auto";
    case "low": return ko ? "Low" : "Low";
    case "medium": return ko ? "Med" : "Med";
    case "high": return ko ? "High" : "High";
    case "xhigh": return ko ? "Max" : "Max";
    default: return value;
  }
}

function effortDescription(value, language) {
  const ko = language === "ko";
  switch (String(value || "").toLowerCase()) {
    case "auto": return ko ? "자동 조정" : "Dynamic adjustment";
    case "low": return ko ? "가장 빠름" : "Fastest";
    case "medium": return ko ? "균형" : "Balanced";
    case "high": return ko ? "더 철저함" : "More thorough";
    case "xhigh": return ko ? "최대 깊이" : "Maximum depth";
    default: return "";
  }
}

/* ?? Model chip label helpers ?? */
const RUN_PROVIDER_OPTIONS = [
  "ensemble",
  "openai",
  "claude",
  "gemini",
  "ollama",
  "qwen_code",
  "deepseek",
  "kimi",
  "minimax",
  "glm",
  "openrouter",
  "opencdk",
  "local_openai",
  "oss",
];

function parallelRunControlViewPropsEqual(previousProps, nextProps) {
  return (
    previousProps.detail === nextProps.detail
    && previousProps.modelCatalog === nextProps.modelCatalog
    && previousProps.codexStatus === nextProps.codexStatus
    && previousProps.planDraft === nextProps.planDraft
    && previousProps.activeJob === nextProps.activeJob
    && previousProps.autoRunAfterPlan === nextProps.autoRunAfterPlan
    && previousProps.selectedStepId === nextProps.selectedStepId
    && previousProps.form === nextProps.form
    && previousProps.busy === nextProps.busy
    && previousProps.canRequestStop === nextProps.canRequestStop
    && previousProps.canCancelReservation === nextProps.canCancelReservation
    && sameQueuedJobs(previousProps.queuedJobs, nextProps.queuedJobs)
    && previousProps.hidePromptStrip === nextProps.hidePromptStrip
    && previousProps.onPromptChange === nextProps.onPromptChange
    && previousProps.onChangeForm === nextProps.onChangeForm
    && previousProps.onGeneratePlan === nextProps.onGeneratePlan
    && previousProps.onSavePlan === nextProps.onSavePlan
    && previousProps.onResetPlan === nextProps.onResetPlan
    && previousProps.onRunPlan === nextProps.onRunPlan
    && previousProps.onRunManualDebugger === nextProps.onRunManualDebugger
    && previousProps.onRunManualMerger === nextProps.onRunManualMerger
    && previousProps.onRequestStop === nextProps.onRequestStop
    && previousProps.onCancelQueuedJob === nextProps.onCancelQueuedJob
    && previousProps.onAutoRunAfterPlanChange === nextProps.onAutoRunAfterPlanChange
    && previousProps.onSelectStep === nextProps.onSelectStep
    && previousProps.onUpdateStepField === nextProps.onUpdateStepField
    && previousProps.onSaveStepLocal === nextProps.onSaveStepLocal
    && previousProps.onAddStep === nextProps.onAddStep
    && previousProps.onDeleteStep === nextProps.onDeleteStep
  );
}

function modelChipLabel(form, detail, modelCatalog = []) {
  const runtime = form?.runtime || detail?.runtime || {};
  const model = runtimeExecutionModel(runtime);
  const provider = String(form?.runtime?.model_provider || detail?.runtime?.model_provider || "openai").trim().toLowerCase();
  if (model && model !== "auto") {
    const label = modelDisplayName(modelCatalog, model) || model;
    return label.length > 16 ? `${label.slice(0, 15)}\u2026` : label;
  }
  return providerShortName(provider, runtime?.local_model_provider);
}

/* ?? ModelEffortChip: single button + popover ?? */
function ModelEffortChip({ form, detail, busy, onChangeForm, language, modelCatalog = [], codexStatus = {} }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  const runtime = form?.runtime || detail?.runtime || {};
  const selectedModel = runtimeExecutionModel(runtime);
  const reasoningOptions = MODEL_REASONING_OPTIONS;
  const currentEffort = String(runtime?.effort_selection_mode || "").trim().toLowerCase() === AUTO_REASONING_OPTION
    ? AUTO_REASONING_OPTION
    : String(runtime?.effort || "medium").trim().toLowerCase() || "medium";
  const chipModel = modelChipLabel(form, detail, modelCatalog);

  useEffect(() => {
    if (!open) return;
    function onDown(e) {
      if (!wrapRef.current?.contains(e.target)) setOpen(false);
    }
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, [open]);

  return (
    <div className="mec-wrap" ref={wrapRef}>
      <button
        type="button"
        className={`mec-chip${open ? " mec-chip--open" : ""}`}
        onClick={() => setOpen((v) => !v)}
        disabled={busy}
        title={language === "ko" ? "Model and reasoning settings" : "Model & reasoning settings"}
      >
        <span className="mec-chip__model">{chipModel}</span>
        <span className="mec-chip__sep">-</span>
        <span className="mec-chip__effort">{effortShortLabel(currentEffort, language)}</span>
        <svg className="mec-chip__chevron" viewBox="0 0 12 12" fill="none" aria-hidden="true">
          <path d="M2 4l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {open ? (
        <div className="mec-popover">
          <div className="mec-popover__model-row">
            <span className="mec-popover__label">{language === "ko" ? "Model" : "Model"}</span>
            <span className="mec-popover__model-name">{chipModel}</span>
          </div>
          <div className="mec-popover__divider" />
          <div className="mec-popover__section">
            <span className="mec-popover__label">{language === "ko" ? "Reasoning" : "Reasoning"}</span>
            <div className="mec-effort-list">
              {reasoningOptions.map((opt) => (
                <button
                  key={opt}
                  type="button"
                  className={`mec-effort-row${currentEffort === opt ? " mec-effort-row--active" : ""}`}
                  onClick={() => {
                    onChangeForm?.((c) => ({
                      ...c,
                      runtime: applyConfigRuntimeModelSelection(c.runtime || {}, modelCatalog, selectedModel, opt, codexStatus),
                    }));
                    setOpen(false);
                  }}
                  disabled={busy}
                >
                  <span className="mec-effort-row__name">{effortShortLabel(opt, language)}</span>
                  <span className="mec-effort-row__desc">{effortDescription(opt, language)}</span>
                  {currentEffort === opt ? (
                    <svg className="mec-effort-row__check" viewBox="0 0 16 16" fill="none">
                      <path d="M3 8l4 4 6-7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  ) : null}
                </button>
              ))}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/* ?? Helpers ?? */
function autoProviderLabel(language) {
  return language === "ko" ? "Auto (AGENTS.md preference)" : "Auto (AGENTS.md preference)";
}

function stepAutoModelHint(language, runtime) {
  const provider = String(runtime?.model_provider || "openai").trim().toLowerCase();
  if (provider === "ensemble") {
    return language === "ko"
      ? "비워두면 ensemble 라우팅을 따릅니다. 계획과 일반 구현은 Codex CLI를 쓰고, UI/frontend는 Claude Code를 우선 사용하며 Claude가 없으면 Gemini CLI로 대체합니다."
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
    return runtimeExecutionModel(runtime, "gpt-5.4") || "gpt-5.4";
  }
  return "";
}

function executionModelLabel(modelCatalog = [], runtime = {}) {
  const model = runtimeExecutionModel(runtime);
  return modelDisplayName(modelCatalog, model) || model || "gpt-5.4";
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

function sameStringArrayValues(left = [], right = []) {
  if (left === right) {
    return true;
  }
  if (!Array.isArray(left) || !Array.isArray(right) || left.length !== right.length) {
    return false;
  }
  for (let index = 0; index < left.length; index += 1) {
    if (String(left[index] || "") !== String(right[index] || "")) {
      return false;
    }
  }
  return true;
}

function createStepTextDraft(step = null) {
  return {
    title: String(step?.title || ""),
    deadline_at: String(step?.deadline_at || ""),
    depends_on_text: Array.isArray(step?.depends_on) ? step.depends_on.join(", ") : "",
    owned_paths_text: Array.isArray(step?.owned_paths) ? step.owned_paths.join("\n") : "",
    display_description: String(step?.display_description || ""),
    codex_description: String(step?.codex_description || ""),
    success_criteria: String(step?.success_criteria || ""),
  };
}

const StepEditorPanel = memo(function StepEditorPanel({
  selectedStep,
  selectedStepIndex,
  stepsLength,
  selectedStepStatus,
  selectedStepFailureReason,
  selectedStepFailureCode,
  selectedSystemStep,
  selectedStepEstimate,
  editableStep,
  editableStepModel,
  stepNoteLabel,
  language,
  t,
  detail,
  codexStatus,
  providerOptions,
  modelCatalog,
  selectedStepModelValue,
  selectedStepExecutionModelLabel,
  selectedStepModelVisible,
  selectedStepModel,
  selectedStepModelGroups,
  busy,
  onSelectStep,
  onUpdateStepField,
  onSaveStepLocal,
  onAddStep,
  onDeleteStep,
}) {
  const [textDraft, setTextDraft] = useState(() => createStepTextDraft(selectedStep));

  useEffect(() => {
    setTextDraft(createStepTextDraft(selectedStep));
  }, [
    selectedStep?.step_id,
    selectedStep?.title,
    selectedStep?.deadline_at,
    Array.isArray(selectedStep?.depends_on) ? selectedStep.depends_on.join("|") : "",
    Array.isArray(selectedStep?.owned_paths) ? selectedStep.owned_paths.join("|") : "",
    selectedStep?.display_description,
    selectedStep?.codex_description,
    selectedStep?.success_criteria,
  ]);

  function updateDraft(field, value) {
    setTextDraft((current) => ({
      ...current,
      [field]: value,
    }));
  }

  function commitPatch(patch) {
    if (!patch || !Object.keys(patch).length) {
      return;
    }
    onUpdateStepField?.(patch);
  }

  function commitTextDraftField(field) {
    if (!selectedStep) {
      return;
    }
    switch (field) {
      case "title":
        if (textDraft.title !== String(selectedStep.title || "")) {
          commitPatch({ title: textDraft.title });
        }
        break;
      case "deadline_at":
        if (textDraft.deadline_at !== String(selectedStep.deadline_at || "")) {
          commitPatch({ deadline_at: textDraft.deadline_at });
        }
        break;
      case "depends_on_text": {
        const nextValue = normalizeListText(textDraft.depends_on_text);
        if (!sameStringArrayValues(nextValue, selectedStep.depends_on || [])) {
          commitPatch({ depends_on: nextValue });
        }
        break;
      }
      case "owned_paths_text": {
        const nextValue = normalizeListText(textDraft.owned_paths_text);
        if (!sameStringArrayValues(nextValue, selectedStep.owned_paths || [])) {
          commitPatch({ owned_paths: nextValue });
        }
        break;
      }
      case "display_description":
        if (textDraft.display_description !== String(selectedStep.display_description || "")) {
          commitPatch({ display_description: textDraft.display_description });
        }
        break;
      case "codex_description":
        if (textDraft.codex_description !== String(selectedStep.codex_description || "")) {
          commitPatch({ codex_description: textDraft.codex_description });
        }
        break;
      case "success_criteria":
        if (textDraft.success_criteria !== String(selectedStep.success_criteria || "")) {
          commitPatch({ success_criteria: textDraft.success_criteria });
        }
        break;
      default:
        break;
    }
  }

  function commitAllTextDraftFields() {
    if (!selectedStep) {
      return;
    }
    const patch = {};
    if (textDraft.title !== String(selectedStep.title || "")) {
      patch.title = textDraft.title;
    }
    if (textDraft.deadline_at !== String(selectedStep.deadline_at || "")) {
      patch.deadline_at = textDraft.deadline_at;
    }
    const dependsOn = normalizeListText(textDraft.depends_on_text);
    if (!sameStringArrayValues(dependsOn, selectedStep.depends_on || [])) {
      patch.depends_on = dependsOn;
    }
    const ownedPaths = normalizeListText(textDraft.owned_paths_text);
    if (!sameStringArrayValues(ownedPaths, selectedStep.owned_paths || [])) {
      patch.owned_paths = ownedPaths;
    }
    if (textDraft.display_description !== String(selectedStep.display_description || "")) {
      patch.display_description = textDraft.display_description;
    }
    if (textDraft.codex_description !== String(selectedStep.codex_description || "")) {
      patch.codex_description = textDraft.codex_description;
    }
    if (textDraft.success_criteria !== String(selectedStep.success_criteria || "")) {
      patch.success_criteria = textDraft.success_criteria;
    }
    commitPatch(patch);
  }

  if (!selectedStep) {
    return null;
  }

  return (
    <div className="run-step-editor">
      <div className="run-step-editor__header">
        <strong>{selectedStep.step_id}: {textDraft.title || selectedStep.title || t("run.selectedStep")}</strong>
        {selectedStepIndex >= 0 ? (
          <span className="step-position-badge">{selectedStepIndex + 1}/{stepsLength}</span>
        ) : null}
        <span className={`status-badge status-badge--${statusTone(selectedStepStatus)}`}>
          {displayStatus(selectedStepStatus, language)}
        </span>
        <button className="step-editor-close" onClick={() => onSelectStep?.(null)} type="button" title="Close (Esc)" aria-label="Close">x</button>
      </div>

      {selectedSystemStep ? (
        <div className="step-editor-grid">
          <div className="field field--wide"><span>{t("field.description")}</span><p>{selectedStep.display_description || t("run.noSummary")}</p></div>
          {selectedStep.deadline_at ? <div className="field field--wide"><span>{language === "ko" ? "Deadline" : "Deadline"}</span><p>{selectedStep.deadline_at}</p></div> : null}
          <div className="field field--wide"><span>{t("field.dependsOn")}</span><p>{(selectedStep.depends_on || []).join(", ") || t("common.none")}</p></div>
          {String(selectedStepStatus || "").trim().toLowerCase().includes("failed") && selectedStepFailureReason ? (
            <div className="field field--wide">
              <span>{language === "ko" ? "Failure Reason" : "Failure Reason"}</span>
              <p>{selectedStepFailureReason}</p>
              {selectedStepFailureCode ? <small className="field-hint"><code>{selectedStepFailureCode}</code></small> : null}
            </div>
          ) : null}
          {selectedStep.notes ? <div className="field field--wide"><span>{stepNoteLabel}</span><p>{selectedStep.notes}</p></div> : null}
          {selectedStep.step_id === CLOSEOUT_STEP_ID ? (
            <div className="field field--wide">
              <span>{language === "ko" ? "Report Formats" : "Report Formats"}</span>
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
                <div><span style={{ color: "var(--text-dim)" }}>{language === "ko" ? "Est." : "Est."}</span> <strong>{formatDurationCompact(selectedStepEstimate?.estimated_duration_seconds ?? 0, language)}</strong></div>
                <div><span style={{ color: "var(--text-dim)" }}>{t("run.currentRemaining")}</span> <strong>{formatDurationCompact(selectedStepEstimate?.remaining_seconds ?? 0, language)}</strong></div>
              </div>
            </div>
          ) : null}

          <label className="field field--wide"><span>{t("field.title")}</span><input value={textDraft.title} onChange={(event) => updateDraft("title", event.target.value)} onBlur={() => commitTextDraftField("title")} disabled={!editableStep} /></label>

          <label className="field">
            <span>{language === "ko" ? "Deadline" : "Deadline"}</span>
            <input
              value={textDraft.deadline_at}
              onChange={(event) => updateDraft("deadline_at", event.target.value)}
              onBlur={() => commitTextDraftField("deadline_at")}
              disabled={!editableStep}
              placeholder={language === "ko" ? "Example: 2026-04-05 18:00" : "Example: 2026-04-05 18:00"}
            />
          </label>

          <label className="field"><span>{t("field.gptReasoning")}</span>
            <select value={selectedStep.reasoning_effort || detail?.runtime?.effort || "high"} onChange={(event) => onUpdateStepField?.("reasoning_effort", event.target.value)} disabled={!editableStepModel}>
              {REASONING_OPTIONS.map((effort) => (<option key={effort} value={effort}>{reasoningEffortLabel(effort, language)}</option>))}
            </select>
          </label>

          <label className="field"><span>{t("field.modelProvider")}</span>
            <select value={selectedStep.model_provider || ""} onChange={(event) => onUpdateStepField?.("model_provider", event.target.value)} disabled={!editableStepModel}>
              <option value="">{autoProviderLabel(language)}</option>
              {providerOptions.map(([value, label]) => (<option key={value} value={value} disabled={!providerAvailable(value, codexStatus)} title={providerStatusReason(value, codexStatus)}>{label}</option>))}
            </select>
            {selectedStep.model_provider && !providerUsable(selectedStep.model_provider, codexStatus) && providerStatusReason(selectedStep.model_provider, codexStatus) ? (
              <small className="field-hint" style={{ color: "var(--warning)" }}>{providerStatusReason(selectedStep.model_provider, codexStatus)}</small>
            ) : null}
          </label>

          <label className="field field--wide"><span>{t("field.model")}</span>
            <select
              value={selectedStepModelValue}
              onChange={(event) => {
                const nextModel = String(event.target.value || "").trim();
                onUpdateStepField?.(stepModelSelectionPatch(modelCatalog, detail?.runtime || {}, nextModel));
              }}
              disabled={!editableStepModel}
            >
              <option value="">{language === "ko" ? `Use execution model (${selectedStepExecutionModelLabel})` : `Use execution model (${selectedStepExecutionModelLabel})`}</option>
              {!selectedStepModelVisible && selectedStepModel ? (
                <option value={selectedStepModelValue}>
                  {modelDisplayName(modelCatalog, selectedStepModel) || selectedStepModel}
                </option>
              ) : null}
              {selectedStepModelGroups.map((group) => (
                <optgroup key={group.key} label={group.label}>
                  {group.options.map((item) => (
                    <option key={item.value} value={item.value}>
                      {`${item.label} / ${item.provider_label}`}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
            <small className="field-hint">
              {language === "ko"
                ? "Leave this synced with the execution model, or pick another model to override this block."
                : "Leave this synced with the execution model, or pick another model to override this block."}
            </small>
          </label>

          <label className="field field--wide"><span>{t("field.dependsOn")}</span><input value={textDraft.depends_on_text} onChange={(event) => updateDraft("depends_on_text", event.target.value)} onBlur={() => commitTextDraftField("depends_on_text")} disabled={!editableStep} placeholder="step_id1, step_id2" /></label>
          <label className="field field--wide"><span>{t("field.ownedPaths")}</span><textarea value={textDraft.owned_paths_text} onChange={(event) => updateDraft("owned_paths_text", event.target.value)} onBlur={() => commitTextDraftField("owned_paths_text")} disabled={!editableStep} placeholder={language === "ko" ? "One file path per line" : "One file path per line"} style={{ minHeight: "48px" }} /></label>
          <label className="field field--wide"><span>{t("field.description")}</span><textarea value={textDraft.display_description} onChange={(event) => updateDraft("display_description", event.target.value)} onBlur={() => commitTextDraftField("display_description")} disabled={!editableStep} style={{ minHeight: "56px" }} /></label>
          <label className="field field--wide"><span>{t("field.codexInstruction")}</span><textarea value={textDraft.codex_description} onChange={(event) => updateDraft("codex_description", event.target.value)} onBlur={() => commitTextDraftField("codex_description")} disabled={!editableStep} style={{ minHeight: "56px" }} /></label>
          <label className="field field--wide"><span>{t("field.successCriteria")}</span><textarea value={textDraft.success_criteria} onChange={(event) => updateDraft("success_criteria", event.target.value)} onBlur={() => commitTextDraftField("success_criteria")} disabled={!editableStep} style={{ minHeight: "48px" }} /></label>

          {String(selectedStepStatus || "").trim().toLowerCase().includes("failed") && selectedStepFailureReason ? (
            <div className="field field--wide">
              <span>{language === "ko" ? "Failure Reason" : "Failure Reason"}</span>
              <p>{selectedStepFailureReason}</p>
              {selectedStepFailureCode ? <small className="field-hint"><code>{selectedStepFailureCode}</code></small> : null}
            </div>
          ) : null}
          {selectedStep.notes ? <div className="field field--wide"><span>{stepNoteLabel}</span><p>{selectedStep.notes}</p></div> : null}

          <div className="action-row field--wide" style={{ paddingTop: "6px", borderTop: "1px solid var(--border)" }}>
            <button className="toolbar-btn toolbar-btn--accent" onClick={() => { commitAllTextDraftFields(); onSaveStepLocal?.(); }} type="button" disabled={busy}><SaveIcon /><span>{t("action.saveLocal")}</span></button>
            <button className="toolbar-btn" onClick={onAddStep} type="button" disabled={busy || selectedStep?.step_id === CLOSEOUT_STEP_ID}><span>{t("action.add")}</span></button>
            <button className="toolbar-btn" onClick={onDeleteStep} type="button" disabled={!editableStep || selectedStep?.step_id === CLOSEOUT_STEP_ID} style={editableStep && selectedStep?.step_id !== CLOSEOUT_STEP_ID ? { color: "var(--danger)" } : {}}><span>{t("action.delete")}</span></button>
          </div>
        </div>
      )}
    </div>
  );
});

/* ?? Main view ?? */
export const ParallelRunControlView = memo(function ParallelRunControlView({
  detail,
  modelCatalog: sharedModelCatalog = [],
  codexStatus,
  planDraft,
  activeJob,
  autoRunAfterPlan,
  selectedStepId,
  form,
  busy,
  runActionDisabled,
  canRequestStop = false,
  canCancelReservation = false,
  queuedJobs = [],
  hidePromptStrip = false,
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
  const providerOptions = useMemo(
    () => RUN_PROVIDER_OPTIONS.map((value) => [value, value === "ensemble" ? t("option.providerEnsemble") : providerOptionLabel(value)]),
    [t],
  );

  const executionState = useMemo(
    () => deriveExecutionUiState(detail, planDraft, activeJob),
    [detail, planDraft, activeJob],
  );
  const livePlan = executionState.livePlan;
  const promptValue = livePlan?.project_prompt || "";
  const [promptExpanded, setPromptExpanded] = useState(false);
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
  const modelCatalog = mergeModelCatalogs(
    sharedModelCatalog || [],
    codexStatus?.model_catalog || [],
    detail?.codex_status?.model_catalog || [],
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
  const selectedSystemStep = isSystemStep(selectedStep) && selectedStep?.step_id !== CLOSEOUT_STEP_ID;
  const selectedStepIndex = selectedStep ? steps.findIndex((s) => s.step_id === selectedStepId) : -1;
  const selectedStepModel = String(selectedStep?.model || "").trim();
  const selectedStepModelProvider = String(selectedStep?.model_provider || detail?.runtime?.model_provider || "").trim().toLowerCase();
  const selectedStepModelTree = useMemo(
    () => groupedModelCatalogOptions(modelCatalog, detail?.runtime || {}, codexStatus, { scope: "all" }),
    [codexStatus, detail?.runtime, modelCatalog],
  );
  const selectedStepModelOptions = selectedStepModelTree.entries;
  const selectedStepModelGroups = selectedStepModelTree.groups;
  const selectedStepModelLocalProvider =
    selectedStepModelProvider === "oss" ? normalizedLocalModelProvider(detail?.runtime || {}) : "";
  const selectedStepModelValue = selectedStepModel
    ? modelCatalogOptionValue(
      resolveModelCatalogEntry(
        modelCatalog,
        [selectedStepModelProvider || "openai", selectedStepModelLocalProvider, selectedStepModel.toLowerCase()].join("::"),
      ) || {
        provider: selectedStepModelProvider || "openai",
        local_provider: selectedStepModelLocalProvider,
        model: selectedStepModel,
      },
    )
    : "";
  const selectedStepModelVisible = selectedStepModelValue
    ? selectedStepModelOptions.some((item) => item.value === selectedStepModelValue)
    : false;
  const selectedStepExecutionModelLabel = executionModelLabel(modelCatalog, detail?.runtime || {});
  const selectedStepExecutionModel = runtimeExecutionModel(detail?.runtime || {}).toLowerCase();
  const parallelLimitValue = parallelWorkerLabel(parallelInsight.recommended_workers ?? 1, language);
  const parallelLimitDetails = parallelLimitDescription(parallelInsight, language);
  const parallelLimitCardTone = parallelLimitTone(parallelInsight);
  const executionJob = executionState.executionJob;
  const projectStatus = executionState.displayStatusValue;
  const editableStepModel = canEditStepModel(selectedStep, busy, projectStatus);
  const activeCheckpointLineageId = String(
    executionState.checkpointPending?.lineage_id
    || detail?.loop_state?.current_checkpoint_lineage_id
    || detail?.checkpoints?.current_checkpoint_lineage_id
    || detail?.checkpoints?.pending?.lineage_id
    || "",
  ).trim();
  const activeJobStatus = String(executionJob?.status || "").trim().toLowerCase();
  const resolvedRunActionDisabled = typeof runActionDisabled === "boolean"
    ? runActionDisabled
    :
    busy
    || !executionState.consistent
    || isActiveExecutionStatus(projectStatus)
    || isPlanningProgressRunning(detail?.planning_progress)
    || executionState.checkpointFamily === "checkpoint";
  const selectedStepStatus = effectiveStepStatus(selectedStep, projectStatus);
  const selectedStepFailureReason = failureReasonLabel(selectedStep, language);
  const selectedStepFailureCode = failureReasonCode(selectedStep);
  const stepNoteLabel = "Step note";
  const closeoutStatus = String(livePlan?.closeout_status || "not_started").trim().toLowerCase();
  const showCloseoutStatus = closeoutStatus && closeoutStatus !== "not_started";
  const showEstimatedCost = shouldShowEstimatedCost(detail?.runtime || {}, costEstimate);
  const activeQueuePosition =
    activeJobStatus === "queued"
      ? queuedPosition(executionJob?.queue_position)
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
  const manualDebuggerLabel = language === "ko" ? "Run Debugger" : "Run Debugger";
  const manualMergerLabel = language === "ko" ? "Run Merger" : "Run Merger";
  const manualRecoveryHint = language === "ko"
    ? "If automatic recovery fails, rerun the debugger against the latest failure logs or hand the current git conflict to the merger."
    : "When automatic recovery falls short, rerun the debugger against the latest failure logs or hand the current git conflict to the merger.";

  useEffect(() => {
    setFailureDismissed(false);
  }, [latestFailure?.summary, latestFailure?.report_markdown_file, latestFailure?.report_json_file]);

  useEffect(() => {
    setPromptExpanded(false);
  }, [promptValue]);

  // Auto-resize textarea based on content
  useEffect(() => {
    const el = promptRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`;
  }, [promptValue]);

  useEffect(() => {
    if (!selectedStep) return undefined;
    const handler = (e) => { if (e.key === "Escape") onSelectStep?.(null); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [selectedStep, onSelectStep]);

  return (
    <section className="workspace-view run-view">
      {/* ?? Compact metric ribbon ?? */}
      <div className="run-ribbon">
        <div className="run-ribbon__metrics">
          <span className={`run-ribbon__chip run-ribbon__chip--${statusTone(projectStatus)} run-ribbon__chip--primary`}>
            {isActiveExecutionStatus(projectStatus) ? <span className="chip-dot chip-dot--info chip-dot--pulse" style={{ width: 6, height: 6 }} /> : null}
            {displayStatus(projectStatus || "idle", language)}
          </span>
          <span className="run-ribbon__chip run-ribbon__chip--primary">{completedCount}/{steps.length || 0} {t("run.done")}</span>
          <span className="run-ribbon__chip">{readyNodes.length} {t("run.parallelReady")}</span>
          {queuedJobs.length ? <span className="run-ribbon__chip">{queuedJobs.length} {t("run.reservations")}</span> : null}
          {executionEstimate.remaining_seconds ? (
            <span className="run-ribbon__timer">
              <ClockMetricIcon />
              <span>{formatDurationCompact(executionEstimate.remaining_seconds, language)} {t("run.estimatedRemaining")}</span>
            </span>
          ) : null}
          {showEstimatedCost ? <span className="run-ribbon__chip">{formatUsd(costEstimate.estimated_total_cost_usd ?? 0, language)}</span> : null}
          <span className="run-ribbon__chip">{parallelLimitValue} {t("run.parallelLimit")}</span>
          {showCloseoutStatus ? <span className={`run-ribbon__chip run-ribbon__chip--${statusTone(livePlan?.closeout_status)}`}>{t("run.closeout")}: {displayStatus(livePlan?.closeout_status || "not_started", language)}</span> : null}
          {detail?.run_control?.stop_immediately ? <span className="run-ribbon__chip run-ribbon__chip--warning">{t("run.stopAfterStep")}</span> : null}
        </div>
        <div className="run-ribbon__actions">
          <div className="run-ribbon__auto-run-row">
            <label className="auto-run-badge">
              <input type="checkbox" checked={Boolean(autoRunAfterPlan)} onChange={(event) => onAutoRunAfterPlanChange?.(event.target.checked)} disabled={busy} />
              <span>{t("run.autoRunAfterPlan")}</span>
            </label>
          </div>
          <div className="run-ribbon__actions-secondary">
            <button className="toolbar-btn" onClick={onGeneratePlan} type="button" disabled={busy}><GenerateIcon /><span>{t("action.generate")}</span></button>
            <button className="toolbar-btn" onClick={onSavePlan} type="button" disabled={busy}><SaveIcon /><span>{t("action.save")}</span></button>
            <button className="toolbar-btn" onClick={onResetPlan} type="button"><ResetIcon /><span>{t("action.reset")}</span></button>
            {canCancelReservation ? (
              <button className="toolbar-btn" onClick={() => onCancelQueuedJob?.(activeJob?.id)} type="button" style={{ fontSize: "10px" }}>{t("action.cancelReservation")}</button>
            ) : null}
          </div>
          <div className="run-ribbon__actions-primary">
            {canRequestStop ? (
              <button
                className="toolbar-btn toolbar-btn--danger"
                onClick={onRequestStop}
                type="button"
              >
                <StopIcon /><span>{t("action.stop")}</span>
              </button>
            ) : null}
            <button className="toolbar-btn toolbar-btn--accent" onClick={onRunPlan} type="button" disabled={resolvedRunActionDisabled}><RunIcon /><span>{t("action.run")}</span></button>
          </div>
        </div>
      </div>

      {/* ?? Failure card ?? */}
      {showFailureCard && !failureDismissed ? (
        <div className="content-card" style={{ borderColor: "rgba(200,93,97,0.4)" }}>
          <div className="content-card__header">
            <strong style={{ color: "var(--danger)" }}>{t("test.failed")}</strong>
            <span className={`status-badge status-badge--${statusTone("failed")}`}>{displayStatus("failed", language)}</span>
            <button className="step-editor-close" onClick={() => setFailureDismissed(true)} type="button" title="Dismiss" aria-label="Dismiss">x</button>
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

      {/* ?? Flow chart (main area) ?? */}
      <div className="run-flow-area">
        {steps.length ? (
          <ExecutionFlowChart
            steps={steps}
            detail={detail}
            activeJob={activeJob}
            language={language}
            selectedStepId={selectedStepId}
            onSelectStep={onSelectStep}
          />
        ) : (
          <div className="empty-block" style={{ margin: "40px auto" }}>
            <svg viewBox="0 0 48 48" fill="none" style={{ width: 48, height: 48 }}>
              <circle cx="24" cy="24" r="18" stroke="currentColor" strokeWidth="1.8" strokeDasharray="5 4" />
              <path d="M16 24l6 6 10-12" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span>{t("run.noSteps")}</span>
            <span style={{ fontSize: "12px", color: "var(--text-dim)" }}>
              {language === "ko" ? "Generate a plan to see execution steps here." : "Generate a plan to see execution steps here."}
            </span>
          </div>
        )}
      </div>

      {/* ?? Queue (inline if any) ?? */}
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

      {/* P1-5: Execution model info card */}
      {steps.length > 0 ? (
        <div className="execution-model-card">
          <div className="execution-model-card__row">
            <span className="execution-model-card__label">{language === "ko" ? "실행 모델" : "Execution Model"}</span>
            <span className="execution-model-card__value"><strong>{executionModelLabel(modelCatalog, detail?.runtime || {})}</strong></span>
          </div>
          <div className="execution-model-card__row">
            <span className="execution-model-card__label">{language === "ko" ? "Reasoning" : "Reasoning"}</span>
            <span className="execution-model-card__value">{reasoningEffortLabel(detail?.runtime?.effort || "medium", language)}</span>
          </div>
          {executionEstimate?.estimated_total_seconds ? (
            <div className="execution-model-card__row">
              <span className="execution-model-card__label">{language === "ko" ? "예상 소요시간" : "Est. Duration"}</span>
              <span className="execution-model-card__value">{formatDurationCompact(executionEstimate.estimated_total_seconds, language)}</span>
            </div>
          ) : null}
          {executionEstimate?.remaining_seconds ? (
            <div className="execution-model-card__row">
              <span className="execution-model-card__label">{language === "ko" ? "남은 시간" : "Remaining"}</span>
              <span className="execution-model-card__value">{formatDurationCompact(executionEstimate.remaining_seconds, language)}</span>
            </div>
          ) : null}
          {parallelInsight?.recommended_workers ? (
            <div className="execution-model-card__row">
              <span className="execution-model-card__label">{language === "ko" ? "Parallel Workers" : "Parallel Workers"}</span>
              <span className="execution-model-card__value">{parallelInsight.recommended_workers} {language === "ko" ? "개" : ""}</span>
            </div>
          ) : null}
        </div>
      ) : null}

      {/* P1-7: Current step detail card */}
      {selectedStep && !selectedSystemStep ? (
        <div className="current-step-card">
          <div className="current-step-card__header">
            <strong>{selectedStep.step_id}</strong>
            <span className={`status-badge status-badge--${statusTone(selectedStepStatus)}`}>
              {displayStatus(selectedStepStatus, language)}
            </span>
            {selectedStepIndex >= 0 ? (
              <span className="run-ribbon__chip">{selectedStepIndex + 1}/{steps.length}</span>
            ) : null}
          </div>
          
          <div className="current-step-card__row">
            <span className="current-step-card__label">{language === "ko" ? "제목" : "Title"}</span>
            <span className="current-step-card__value">{selectedStep.title || t("run.noSummary")}</span>
          </div>

          {selectedStep.display_description ? (
            <div className="current-step-card__row">
              <span className="current-step-card__label">{language === "ko" ? "설명" : "Description"}</span>
              <div className="current-step-card__value">
                <p>{selectedStep.display_description}</p>
              </div>
            </div>
          ) : null}

          {selectedStepEstimate ? (
            <div className="current-step-card__metrics">
              <div className="current-step-card__metric">
                <span className="current-step-card__metric-value">{formatDurationCompact(selectedStepEstimate.estimated_duration_seconds ?? 0, language)}</span>
                <span className="current-step-card__metric-label">{language === "ko" ? "예상" : "Est."}</span>
              </div>
              <div className="current-step-card__metric">
                <span className="current-step-card__metric-value">{formatDurationCompact(selectedStepEstimate.remaining_seconds ?? 0, language)}</span>
                <span className="current-step-card__metric-label">{language === "ko" ? "남음" : "Remaining"}</span>
              </div>
            </div>
          ) : null}

          {(selectedStep.depends_on || []).length > 0 ? (
            <div className="current-step-card__row">
              <span className="current-step-card__label">{language === "ko" ? "선행 단계" : "Dependencies"}</span>
              <span className="current-step-card__value">{(selectedStep.depends_on || []).join(", ")}</span>
            </div>
          ) : null}

          {selectedStep.deadline_at ? (
            <div className="current-step-card__row">
              <span className="current-step-card__label">{language === "ko" ? "Deadline" : "Deadline"}</span>
              <span className="current-step-card__value">{selectedStep.deadline_at}</span>
            </div>
          ) : null}

          {String(selectedStepStatus || "").trim().toLowerCase().includes("failed") && selectedStepFailureReason ? (
            <div className="current-step-card__row">
              <span className="current-step-card__label">{language === "ko" ? "실패 사유" : "Failure Reason"}</span>
              <div className="current-step-card__value">
                <p>{selectedStepFailureReason}</p>
                {selectedStepFailureCode ? <small style={{ color: "var(--text-dim)" }}><code>{selectedStepFailureCode}</code></small> : null}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

            {/* Closeout detail card */}
      {showCloseoutStatus ? (
        <div className="closeout-card">
          <div className="closeout-card__header">
            <CloseoutMetricIcon />
            <strong>{t("run.closeout")}</strong>
            <span className={`status-badge status-badge--${statusTone(livePlan?.closeout_status)}`} style={{ fontSize: "10px", padding: "1px 6px" }}>
              {displayStatus(livePlan?.closeout_status || "not_started", language)}
            </span>
          </div>
          {livePlan?.closeout_title ? (
            <div className="closeout-card__row">
              <span className="closeout-card__label">TITLE</span>
              <span className="closeout-card__value">{livePlan.closeout_title}</span>
            </div>
          ) : null}
          {livePlan?.closeout_deadline ? (
            <div className="closeout-card__row">
              <span className="closeout-card__label">DEADLINE</span>
              <span className="closeout-card__value">{livePlan.closeout_deadline}</span>
            </div>
          ) : null}
          <div className="closeout-card__row">
            <span className="closeout-card__label">MODEL</span>
            <span className="closeout-card__value">{executionModelLabel(modelCatalog, detail?.runtime || {})}</span>
          </div>
        </div>
      ) : null}

      {/* ?? Step editor (below flow) ?? */}
      {selectedStep ? (
        <StepEditorPanel
          selectedStep={selectedStep}
          selectedStepIndex={selectedStepIndex}
          stepsLength={steps.length}
          selectedStepStatus={selectedStepStatus}
          selectedStepFailureReason={selectedStepFailureReason}
          selectedStepFailureCode={selectedStepFailureCode}
          selectedSystemStep={selectedSystemStep}
          selectedStepEstimate={selectedStepEstimate}
          editableStep={editableStep}
          editableStepModel={editableStepModel}
          stepNoteLabel={stepNoteLabel}
          language={language}
          t={t}
          detail={detail}
          codexStatus={codexStatus}
          providerOptions={providerOptions}
          modelCatalog={modelCatalog}
          selectedStepModelValue={selectedStepModelValue}
          selectedStepExecutionModelLabel={selectedStepExecutionModelLabel}
          selectedStepModelVisible={selectedStepModelVisible}
          selectedStepModel={selectedStepModel}
          selectedStepModelGroups={selectedStepModelGroups}
          busy={busy}
          onSelectStep={onSelectStep}
          onUpdateStepField={onUpdateStepField}
          onSaveStepLocal={onSaveStepLocal}
          onAddStep={onAddStep}
          onDeleteStep={onDeleteStep}
        />
      ) : null}
      {/* ?? Prompt strip (bottom) ??hidden when prompt lives in chat pane ?? */}
      {hidePromptStrip ? null : (
        <div className={`run-prompt-strip run-prompt-strip--bottom run-prompt-strip--fixed${promptExpanded ? "" : " run-prompt-strip--collapsed"}`}>
          {promptExpanded ? (
            <div className="run-prompt-strip__inner">
              <div className="run-prompt-strip__toolbar">
                <span className="run-prompt-strip__count">{promptValue.length} {language === "ko" ? "chars" : "chars"}</span>
                <span className="status-badge status-badge--info" style={{ fontSize: "10px" }}>
                  {language === "ko" ? "Read only" : "Read only"}
                </span>
                <button
                  type="button"
                  className="run-prompt-strip__action-btn"
                  onClick={() => setPromptExpanded(false)}
                >
                  {language === "ko" ? "Collapse" : "Collapse"}
                </button>
                <ModelEffortChip form={form} detail={detail} busy={busy} onChangeForm={onChangeForm} language={language} modelCatalog={modelCatalog} codexStatus={codexStatus} />
              </div>
              <textarea
                ref={promptRef}
                className="run-prompt-strip__input"
                value={promptValue}
                readOnly
                aria-readonly="true"
                tabIndex={-1}
                placeholder={language === "ko" ? "No project prompt." : "No project prompt."}
              />
            </div>
          ) : (
            <div className="run-prompt-collapsed">
              <svg className="run-prompt-collapsed__icon" viewBox="0 0 16 16" fill="none" width="14" height="14">
                <path d="M2 4h12M2 8h8M2 12h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
              <span className="run-prompt-collapsed__text">
                {promptValue
                  ? (promptValue.length > 72 ? `${promptValue.slice(0, 72)}\u2026` : promptValue)
                  : (language === "ko" ? "No prompt" : "No prompt")}
              </span>
              <button
                type="button"
                className="run-prompt-strip__action-btn run-prompt-collapsed__open"
                onClick={() => setPromptExpanded(true)}
              >
                {language === "ko" ? "Open" : "Open"}
              </button>
              <span className="status-badge status-badge--info" style={{ fontSize: "10px" }}>
                {language === "ko" ? "Read only" : "Read only"}
              </span>
              <ModelEffortChip form={form} detail={detail} busy={busy} onChangeForm={onChangeForm} language={language} modelCatalog={modelCatalog} codexStatus={codexStatus} />
            </div>
          )}
        </div>
      )}
    </section>
  );
}, parallelRunControlViewPropsEqual);
