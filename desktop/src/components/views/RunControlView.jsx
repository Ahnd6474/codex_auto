import { useState } from "react";
import { useI18n } from "../../i18n";
import { displayStatus } from "../../locale";
import {
  canEditStep,
  CLAUDE_DEFAULT_MODEL,
  DEEPSEEK_DEFAULT_MODEL,
  effectiveStepStatus,
  formatDurationCompact,
  formatUsd,
  GEMINI_DEFAULT_MODEL,
  GLM_DEFAULT_MODEL,
  isSystemStep,
  KIMI_DEFAULT_MODEL,
  MINIMAX_DEFAULT_MODEL,
  planStepsWithCloseout,
  providerAvailable,
  providerUsable,
  providerStatusReason,
  projectStatusWithJob,
  QWEN_CODE_DEFAULT_MODEL,
  REASONING_OPTIONS,
  reasoningEffortLabel,
  shouldShowEstimatedCost,
  statusTone,
} from "../../utils";

function autoProviderLabel(language) {
  return language === "ko" ? "자동 (AGENTS.md 선호)" : "Auto (AGENTS.md preference)";
}

function autoModelHint(language) {
  return language === "ko"
    ? "비워두면 AGENTS.md 규칙에 따라 UI 단계는 Gemini CLI, 그 외 단계는 Codex CLI를 자동 선택합니다."
    : "Leave blank to follow AGENTS.md: UI steps prefer Gemini CLI and other steps prefer Codex CLI.";
}

function modelPlaceholder(step, runtime) {
  const provider = String(step?.model_provider || "").trim().toLowerCase();
  if (provider === "claude") {
    return "sonnet";
  }
  if (provider === "gemini") {
    return GEMINI_DEFAULT_MODEL;
  }
  if (provider === "qwen_code") {
    return QWEN_CODE_DEFAULT_MODEL;
  }
  if (provider === "deepseek") {
    return DEEPSEEK_DEFAULT_MODEL;
  }
  if (provider === "kimi") {
    return KIMI_DEFAULT_MODEL;
  }
  if (provider === "minimax") {
    return MINIMAX_DEFAULT_MODEL;
  }
  if (provider === "glm") {
    return GLM_DEFAULT_MODEL;
  }
  if (provider === "openai") {
    return String(runtime?.model || runtime?.model_slug_input || "gpt-5.4").trim() || "gpt-5.4";
  }
  return "";
}

function stepAutoModelHint(language, runtime) {
  const provider = String(runtime?.model_provider || "openai").trim().toLowerCase();
  if (provider === "ensemble") {
    return language === "ko"
      ? "비워두면 ensemble 라우팅을 따릅니다. 계획과 일반 구현은 Codex CLI를 쓰고, UI/프론트엔드 단계는 Claude Code를 우선 사용하며 Claude가 없으면 Gemini CLI로 대체합니다."
      : "Leave blank to follow ensemble routing: planning and general steps use Codex CLI, UI and frontend steps use Claude Code, and Gemini CLI is the fallback when Claude is unavailable.";
  }
  return language === "ko"
    ? "비워두면 AGENTS.md 규칙에 따라 UI 단계는 Gemini CLI, 그 외 단계는 Codex CLI를 자동 선택합니다."
    : "Leave blank to follow AGENTS.md: UI steps prefer Gemini CLI and other steps prefer Codex CLI.";
}

function stepModelPlaceholder(step, runtime) {
  const provider = String(step?.model_provider || runtime?.model_provider || "").trim().toLowerCase();
  if (provider === "claude") {
    return CLAUDE_DEFAULT_MODEL;
  }
  if (provider === "gemini") {
    return GEMINI_DEFAULT_MODEL;
  }
  if (provider === "qwen_code") {
    return QWEN_CODE_DEFAULT_MODEL;
  }
  if (provider === "deepseek") {
    return DEEPSEEK_DEFAULT_MODEL;
  }
  if (provider === "kimi") {
    return KIMI_DEFAULT_MODEL;
  }
  if (provider === "minimax") {
    return MINIMAX_DEFAULT_MODEL;
  }
  if (provider === "glm") {
    return GLM_DEFAULT_MODEL;
  }
  if (provider === "openai" || provider === "ensemble") {
    return String(runtime?.model || runtime?.model_slug_input || "gpt-5.4").trim() || "gpt-5.4";
  }
  return modelPlaceholder(step, runtime);
}

function FlowNode({ step, projectStatus, selected, onSelect, language, t }) {
  const [tooltipVisible, setTooltipVisible] = useState(false);
  const stepStatus = effectiveStepStatus(step, projectStatus);
  const tone = statusTone(stepStatus);
  const summary = step.display_description || step.success_criteria || t("run.noSummary");
  return (
    <div
      className="run-node-wrapper"
      onMouseEnter={() => setTooltipVisible(true)}
      onMouseLeave={() => setTooltipVisible(false)}
    >
      <button
        className={`run-node run-node--${tone} ${selected ? "selected" : ""}`}
        onClick={() => { onSelect(step.step_id); setTooltipVisible((v) => !v); }}
        type="button"
      >
        <div className="run-node__meta">
          <span className="run-node__id">{step.step_id}</span>
          <span className={`status-badge status-badge--${tone}`}>{displayStatus(stepStatus, language)}</span>
        </div>
        <strong>{step.title}</strong>
      </button>
      {tooltipVisible && summary ? (
        <div className="run-node__tooltip" role="tooltip">{summary}</div>
      ) : null}
    </div>
  );
}

export function RunControlView({
  detail,
  codexStatus,
  planDraft,
  activeJob,
  selectedStepId,
  busy,
  canRequestStop = false,
  onPromptChange,
  onGeneratePlan,
  onSavePlan,
  onResetPlan,
  onRunPlan,
  onRequestStop,
  onSelectStep,
  onUpdateStepField,
  onSaveStepLocal,
  onAddStep,
  onDeleteStep,
  onMoveStep,
}) {
  const { language, t } = useI18n();
  const providerOptions = [
    ["ensemble", t("option.providerEnsemble")],
    ["openai", "Codex CLI"],
    ["claude", "Claude Code"],
    ["gemini", "Gemini CLI"],
    ["ollama", "Ollama"],
    ["qwen_code", "Qwen Code"],
    ["deepseek", "DeepSeek via Claude Code"],
    ["kimi", "Kimi"],
    ["minimax", "MiniMax via Claude Code"],
    ["glm", "GLM via Claude Code"],
    ["openrouter", "OpenRouter"],
    ["opencdk", "OpenCDK"],
    ["local_openai", "Local OpenAI-Compatible"],
    ["oss", "LM Studio / Local OSS"],
  ];
  const steps = planStepsWithCloseout(planDraft, {
    title: t("run.closeout"),
    description: t("reports.closeoutReport"),
    successCriteria: t("reports.closeoutReport"),
  });
  const selectedStep = steps.find((step) => step.step_id === selectedStepId) || null;
  const runtimeInsights = detail?.runtime_insights || {};
  const executionEstimate = runtimeInsights?.execution || {};
  const costEstimate = runtimeInsights?.cost || {};
  const selectedStepEstimate = (executionEstimate.step_estimates || []).find((item) => item.step_id === selectedStepId) || null;
  const editableStep = canEditStep(selectedStep, busy);
  const completedCount = steps.filter((step) => step.status === "completed").length;
  const executionMode = "parallel";
  const flowColumns = 3;
  const selectedSystemStep = isSystemStep(selectedStep);
  const projectStatus = projectStatusWithJob(detail?.project?.current_status || "", activeJob);
  const activeJobStatus = String(activeJob?.status || "").trim().toLowerCase();
  const selectedStepStatus = effectiveStepStatus(selectedStep, projectStatus);
  const closeoutStatus = String(planDraft?.closeout_status || "not_started").trim().toLowerCase();
  const showCloseoutStatus = closeoutStatus && closeoutStatus !== "not_started";
  const showEstimatedCost = shouldShowEstimatedCost(detail?.runtime || {}, costEstimate);
  const isPlanningJobRunning =
    activeJobStatus === "running"
    && String(activeJob?.command || "").trim().toLowerCase() === "generate-plan";
  const canResetPlan = !busy || isPlanningJobRunning;
  const latestFailure = detail?.reports?.latest_failure || {};
  const failureArtifacts = Array.isArray(latestFailure?.artifact_files) ? latestFailure.artifact_files.slice(0, 8) : [];
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

  return (
    <section className="workspace-view">
      <div className="view-header">
        <div>
          <span className="eyebrow">{t("run.flow")}</span>
          <h2>{t("run.executionFlow")}</h2>
        </div>
      </div>

      <div className="run-summary">
        <div className={`metric-card metric-card--${statusTone(projectStatus)}`}>
          <span>{t("common.status")}</span>
          <strong>{displayStatus(projectStatus || "idle", language)}</strong>
        </div>
        <div className="metric-card metric-card--info">
          <span>{t("run.done")}</span>
          <strong>{completedCount}/{steps.length || 0}</strong>
        </div>
        <div className={`metric-card metric-card--${detail?.run_control?.stop_immediately ? "warning" : "neutral"}`}>
          <span>{t("run.stopAfterStep")}</span>
          <strong>{detail?.run_control?.stop_immediately ? t("common.on") : t("common.off")}</strong>
        </div>
        <div className="metric-card metric-card--info">
          <span>{t("run.estimatedRemaining")}</span>
          <strong>{formatDurationCompact(executionEstimate.remaining_seconds ?? 0, language)}</strong>
        </div>
        <div className="metric-card metric-card--info">
          <span>{t("run.executionMode")}</span>
          <strong>{t("option.executionParallel")}</strong>
        </div>
        {showCloseoutStatus ? (
          <div className={`metric-card metric-card--${statusTone(planDraft?.closeout_status)}`}>
            <span>{t("run.closeout")}</span>
            <strong>{displayStatus(planDraft?.closeout_status || "not_started", language)}</strong>
          </div>
        ) : null}
        {showEstimatedCost ? (
          <div className="metric-card">
            <span>{t("run.estimatedCost")}</span>
            <strong>{formatUsd(costEstimate.estimated_total_cost_usd ?? 0, language)}</strong>
          </div>
        ) : null}
      </div>

      {showFailureCard ? (
        <div className="content-card">
          <div className="content-card__header">
            <strong>{t("test.failed")}</strong>
            <span className={`status-badge status-badge--${statusTone("failed")}`}>{displayStatus("failed", language)}</span>
          </div>
          <div className="step-editor-grid">
            {latestFailure?.summary ? (
              <div className="field field--wide">
                <span>{t("common.status")}</span>
                <p>{latestFailure.summary}</p>
              </div>
            ) : null}
            {latestFailure?.report_markdown_file ? (
              <div className="field field--wide">
                <span>Failure report</span>
                <p>{latestFailure.report_markdown_file}</p>
              </div>
            ) : null}
            {latestFailure?.report_json_file ? (
              <div className="field field--wide">
                <span>Failure bundle</span>
                <p>{latestFailure.report_json_file}</p>
              </div>
            ) : null}
            {failureArtifacts.length ? (
              <div className="field field--wide">
                <span>Failure artifacts</span>
                <p>{failureArtifacts.join("\n")}</p>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      <div className="content-card content-card--flow">
        <div className="content-card__header">
          <strong>{t("run.flowChart")}</strong>
          <div className="action-row">
            <button className="toolbar-button toolbar-button--accent" onClick={onRunPlan} type="button" disabled={busy}>
              {t("action.run")}
            </button>
            <button className="toolbar-button" onClick={onGeneratePlan} type="button" disabled={busy}>
              {t("action.generate")}
            </button>
            <button className="toolbar-button toolbar-button--ghost" onClick={onSavePlan} type="button" disabled={busy}>
              {t("action.save")}
            </button>
            <div className="action-row__divider" />
            <button className="toolbar-button toolbar-button--ghost" onClick={onRequestStop} type="button" disabled={!canRequestStop}>
              {t("action.stop")}
            </button>
            <button className="toolbar-button toolbar-button--ghost" onClick={onResetPlan} type="button" disabled={!canResetPlan}>
              {t("action.reset")}
            </button>
          </div>
        </div>
        <div className="run-flow">
            {steps.length ? (
              steps.map((step, index) => (
                <div className="run-flow__item" key={step.step_id}>
                <FlowNode step={step} projectStatus={projectStatus} selected={step.step_id === selectedStepId} onSelect={onSelectStep} language={language} t={t} />
                {index < steps.length - 1 ? (
                  <div
                    className={`run-flow__connector ${
                      (index + 1) % flowColumns === 0 ? "run-flow__connector--down" : "run-flow__connector--right"
                    }`}
                    aria-hidden="true"
                  />
                ) : null}
              </div>
            ))
          ) : (
            <div className="empty-block empty-block--action">
              <span>{t("run.noSteps")}</span>
              <button className="toolbar-button toolbar-button--accent" onClick={onGeneratePlan} type="button" disabled={busy}>
                {t("action.generatePlan")}
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="run-layout">
        <div className="content-card">
          <div className="content-card__header">
            <strong>{t("field.prompt")}</strong>
          </div>
          <textarea className="editor-textarea editor-textarea--prompt" value={planDraft?.project_prompt || ""} onChange={(event) => onPromptChange(event.target.value)} disabled={busy} />
        </div>

        <div className="content-card">
          <div className="content-card__header">
            <strong>{t("run.selectedStep")}</strong>
            <span className={`status-badge status-badge--${statusTone(selectedStepStatus)}`}>{selectedStep ? displayStatus(selectedStepStatus, language) : t("common.none")}</span>
          </div>
          {selectedStep ? (
            selectedSystemStep ? (
              <div className="step-editor-grid">
                <div className="field field--wide">
                  <span>{t("field.title")}</span>
                  <strong>{selectedStep.title || t("run.closeout")}</strong>
                </div>
                <div className="field field--wide">
                  <span>{t("field.description")}</span>
                  <p>{selectedStep.display_description || t("run.noSummary")}</p>
                </div>
                <div className="field field--wide">
                  <span>{t("field.successCriteria")}</span>
                  <p>{selectedStep.success_criteria || t("run.noSummary")}</p>
                </div>
                {selectedStep.notes ? (
                  <div className="field field--wide">
                    <span>{t("common.status")}</span>
                    <p>{selectedStep.notes}</p>
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="step-editor-grid">
                <div className="field field--wide">
                  <span>{t("run.stepEstimate")}</span>
                  <strong>
                    {formatDurationCompact(selectedStepEstimate?.estimated_duration_seconds ?? 0, language)}
                    {" | "}
                    {t("run.currentRemaining")}: {formatDurationCompact(selectedStepEstimate?.remaining_seconds ?? 0, language)}
                  </strong>
                </div>
                <label className="field field--wide">
                  <span>{t("field.title")}</span>
                  <input value={selectedStep.title || ""} onChange={(event) => onUpdateStepField("title", event.target.value)} disabled={!editableStep} />
                </label>
                <label className="field">
                  <span>{t("field.gptReasoning")}</span>
                  <select
                    value={selectedStep.reasoning_effort || detail?.runtime?.effort || "high"}
                    onChange={(event) => onUpdateStepField("reasoning_effort", event.target.value)}
                    disabled={!editableStep}
                  >
                    {REASONING_OPTIONS.map((effort) => (
                      <option key={effort} value={effort}>
                        {reasoningEffortLabel(effort, language)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>{t("field.modelProvider")}</span>
                  <select value={selectedStep.model_provider || ""} onChange={(event) => onUpdateStepField("model_provider", event.target.value)} disabled={!editableStep}>
                    <option value="">{autoProviderLabel(language)}</option>
                    {providerOptions.map(([value, label]) => (
                      <option
                          key={value}
                          value={value}
                        disabled={!providerAvailable(value, codexStatus)}
                        title={providerStatusReason(value, codexStatus)}
                      >
                        {label}
                      </option>
                    ))}
                  </select>
                  {selectedStep.model_provider && !providerUsable(selectedStep.model_provider, codexStatus) && providerStatusReason(selectedStep.model_provider, codexStatus) ? (
                    <small className="muted">{providerStatusReason(selectedStep.model_provider, codexStatus)}</small>
                  ) : null}
                </label>
                <label className="field field--wide">
                  <span>{t("field.model")}</span>
                  <input
                    value={selectedStep.model || ""}
                    placeholder={stepModelPlaceholder(selectedStep, detail?.runtime)}
                    onChange={(event) => onUpdateStepField("model", event.target.value)}
                    disabled={!editableStep}
                  />
                  <small className="muted">{stepAutoModelHint(language, detail?.runtime)}</small>
                </label>
                <label className="field">
                  <span>{t("field.parallelGroup")}</span>
                  <input value={selectedStep.parallel_group || ""} onChange={(event) => onUpdateStepField("parallel_group", event.target.value)} disabled={!editableStep} />
                </label>
                <label className="field field--wide">
                  <span>{t("field.description")}</span>
                  <textarea value={selectedStep.display_description || ""} onChange={(event) => onUpdateStepField("display_description", event.target.value)} disabled={!editableStep} />
                </label>
                <label className="field field--wide">
                  <span>{t("field.codexInstruction")}</span>
                  <textarea value={selectedStep.codex_description || ""} onChange={(event) => onUpdateStepField("codex_description", event.target.value)} disabled={!editableStep} />
                </label>
                <label className="field field--wide">
                  <span>{t("field.successCriteria")}</span>
                  <textarea value={selectedStep.success_criteria || ""} onChange={(event) => onUpdateStepField("success_criteria", event.target.value)} disabled={!editableStep} />
                </label>
                <div className="action-row field--wide">
                  <button className="toolbar-button toolbar-button--accent" onClick={onSaveStepLocal} type="button" disabled={busy}>
                    {t("action.saveLocal")}
                  </button>
                  <button className="toolbar-button" onClick={onAddStep} type="button" disabled={busy}>
                    {t("action.add")}
                  </button>
                  <button className="toolbar-button toolbar-button--ghost" onClick={onDeleteStep} type="button" disabled={!editableStep}>
                    {t("action.delete")}
                  </button>
                  <button className="toolbar-button toolbar-button--ghost" onClick={() => onMoveStep(-1)} type="button" disabled={!editableStep}>
                    {t("action.up")}
                  </button>
                  <button className="toolbar-button toolbar-button--ghost" onClick={() => onMoveStep(1)} type="button" disabled={!editableStep}>
                    {t("action.down")}
                  </button>
                </div>
              </div>
            )
          ) : (
            <div className="empty-block">{t("run.selectStep")}</div>
          )}
        </div>
      </div>
    </section>
  );
}
