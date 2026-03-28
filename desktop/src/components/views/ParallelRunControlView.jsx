import { useI18n } from "../../i18n";
import { displayStatus } from "../../locale";
import { ExecutionFlowChart } from "../common/ExecutionFlowChart";
import {
  basename,
  canEditStep,
  CLAUDE_DEFAULT_MODEL,
  commandLabel,
  effectiveStepStatus,
  formatDurationCompact,
  formatUsd,
  GEMINI_DEFAULT_MODEL,
  isSystemStep,
  parallelLimitDescription,
  parallelLimitTone,
  parallelWorkerLabel,
  planStepsWithCloseout,
  projectStatusWithJob,
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
    return "gemini-3-flash";
  }
  if (provider === "openai") {
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
      if (!item || seen.has(item)) {
        return false;
      }
      seen.add(item);
      return true;
    });
}

function readyPendingSteps(steps) {
  const completed = new Set((steps || []).filter((step) => step.status === "completed").map((step) => step.step_id));
  return (steps || []).filter(
    (step) => step.status !== "completed" && (step.depends_on || []).every((dependency) => completed.has(dependency)),
  );
}

function queuedPosition(value) {
  return Math.max(1, Number.parseInt(String(value || 0), 10) || 1);
}

function reservationProjectLabel(job, fallbackLabel) {
  return String(job?.display_name || "").trim() || basename(job?.project_dir || "") || String(job?.repo_id || "").trim() || fallbackLabel;
}

export function ParallelRunControlView({
  detail,
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
  const livePlan = activeJob?.status === "running" && detail?.plan ? detail.plan : planDraft;
  const steps = planStepsWithCloseout(livePlan, {
    title: t("run.closeout"),
    description: t("reports.closeoutReport"),
    successCriteria: t("reports.closeoutReport"),
  });
  const readyNodes = readyPendingSteps(steps);
  const selectedStep = steps.find((step) => step.step_id === selectedStepId) || null;
  const runtimeInsights = detail?.runtime_insights || {};
  const executionEstimate = runtimeInsights?.execution || {};
  const costEstimate = runtimeInsights?.cost || {};
  const parallelInsight = runtimeInsights?.parallel || {};
  const selectedStepEstimate = (executionEstimate.step_estimates || []).find((item) => item.step_id === selectedStepId) || null;
  const editableStep = canEditStep(selectedStep, busy);
  const completedCount = steps.filter((step) => step.status === "completed").length;
  const selectedSystemStep = isSystemStep(selectedStep);
  const parallelLimitValue = parallelWorkerLabel(parallelInsight.recommended_workers ?? 1, language);
  const parallelLimitDetails = parallelLimitDescription(parallelInsight, language);
  const parallelLimitCardTone = parallelLimitTone(parallelInsight);
  const projectStatus = projectStatusWithJob(detail?.project?.current_status || "", activeJob);
  const selectedStepStatus = effectiveStepStatus(selectedStep, projectStatus);
  const closeoutStatus = String(livePlan?.closeout_status || "not_started").trim().toLowerCase();
  const showCloseoutStatus = closeoutStatus && closeoutStatus !== "not_started";
  const showEstimatedCost = shouldShowEstimatedCost(detail?.runtime || {}, costEstimate);
  const activeQueuePosition = String(activeJob?.status || "").trim().toLowerCase() === "queued"
    ? queuedPosition(activeJob?.queue_position)
    : 0;
  const latestFailure = detail?.reports?.latest_failure || {};
  const failureArtifacts = Array.isArray(latestFailure?.artifact_files) ? latestFailure.artifact_files.slice(0, 8) : [];
  const showFailureCard = Boolean(
    latestFailure?.summary
      || latestFailure?.report_markdown_file
      || latestFailure?.report_json_file
      || failureArtifacts.length,
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
        <div className="metric-card metric-card--info">
          <span>{t("run.parallelReady")}</span>
          <strong>{readyNodes.length}</strong>
        </div>
        <div className="metric-card metric-card--info">
          <span>{t("run.reservations")}</span>
          <strong>{queuedJobs.length}</strong>
          {activeQueuePosition ? <span>{t("run.queuePosition", { position: activeQueuePosition })}</span> : null}
        </div>
        <div className={`metric-card metric-card--${detail?.run_control?.stop_immediately ? "warning" : "neutral"}`}>
          <span>{t("run.stopAfterStep")}</span>
          <strong>{detail?.run_control?.stop_immediately ? t("common.on") : t("common.off")}</strong>
        </div>
        <div className="metric-card metric-card--info">
          <span>{t("run.estimatedRemaining")}</span>
          <strong>{formatDurationCompact(executionEstimate.remaining_seconds ?? 0, language)}</strong>
        </div>
        <div className={`metric-card metric-card--${parallelLimitCardTone}`}>
          <span>{t("run.parallelLimit")}</span>
          <strong>{parallelLimitValue}</strong>
          <span>{parallelLimitDetails}</span>
        </div>
        {showCloseoutStatus ? (
          <div className={`metric-card metric-card--${statusTone(livePlan?.closeout_status)}`}>
            <span>{t("run.closeout")}</span>
            <strong>{displayStatus(livePlan?.closeout_status || "not_started", language)}</strong>
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
            <label className="choice-radio run-action-toggle">
              <input
                type="checkbox"
                checked={Boolean(autoRunAfterPlan)}
                onChange={(event) => onAutoRunAfterPlanChange?.(event.target.checked)}
                disabled={busy}
              />
              <span>{t("run.autoRunAfterPlan")}</span>
              <strong className={`status-badge status-badge--${autoRunAfterPlan ? "info" : "neutral"}`}>
                {autoRunAfterPlan ? t("common.on") : t("common.off")}
              </strong>
            </label>
            <button className="toolbar-button" onClick={onGeneratePlan} type="button" disabled={busy}>
              {t("action.generate")}
            </button>
            <button className="toolbar-button" onClick={onSavePlan} type="button" disabled={busy}>
              {t("action.save")}
            </button>
            <button className="toolbar-button toolbar-button--ghost" onClick={onResetPlan} type="button" disabled={busy}>
              {t("action.reset")}
            </button>
            <button className="toolbar-button toolbar-button--accent" onClick={onRunPlan} type="button" disabled={busy}>
              {t("action.run")}
            </button>
            {canCancelReservation ? (
              <button
                className="toolbar-button toolbar-button--ghost"
                onClick={() => onCancelQueuedJob?.(activeJob?.id)}
                type="button"
              >
                {t("action.cancelReservation")}
              </button>
            ) : null}
            <button className="toolbar-button toolbar-button--ghost" onClick={onRequestStop} type="button" disabled={!canRequestStop}>
              {t("action.stop")}
            </button>
          </div>
        </div>
        {steps.length ? (
          <ExecutionFlowChart
            steps={steps}
            projectStatus={projectStatus}
            language={language}
            selectedStepId={selectedStepId}
            onSelectStep={onSelectStep}
          />
        ) : (
          <div className="empty-block">{t("run.noSteps")}</div>
        )}
      </div>

      <div className="run-layout">
        <div className="content-card">
          <div className="content-card__header">
            <strong>{t("field.prompt")}</strong>
          </div>
          <textarea className="editor-textarea editor-textarea--prompt" value={livePlan?.project_prompt || ""} onChange={(event) => onPromptChange(event.target.value)} disabled={busy} />
        </div>

        <div className="content-card">
          <div className="content-card__header">
            <strong>{t("run.reservations")}</strong>
            <span className={`status-badge status-badge--${queuedJobs.length ? "info" : "neutral"}`}>{queuedJobs.length}</span>
          </div>
          {queuedJobs.length ? (
            <div className="step-editor-grid">
              {queuedJobs.map((job) => (
                <div className="field field--wide" key={job.id}>
                  <span>{t("run.queuePosition", { position: queuedPosition(job?.queue_position) })}</span>
                  <strong>{reservationProjectLabel(job, t("project.none"))}</strong>
                  <p>{commandLabel(job?.command, language)}</p>
                  <p>{t("run.queuePriority", { priority: Number.parseInt(String(job?.queue_priority ?? 0), 10) || 0 })}</p>
                  <p>{String(job?.project_dir || job?.repo_id || "").trim() || t("common.unavailable")}</p>
                  <div className="action-row">
                    <span className={`status-badge status-badge--${statusTone(`queued:${job?.command || ""}`)}`}>
                      {displayStatus(`queued:${job?.command || ""}`, language)}
                    </span>
                    <button className="toolbar-button toolbar-button--ghost" onClick={() => onCancelQueuedJob?.(job.id)} type="button">
                      {t("action.cancelReservation")}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-block">{t("run.noReservations")}</div>
          )}
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
                  <span>{t("field.dependsOn")}</span>
                  <p>{(selectedStep.depends_on || []).join(", ") || t("common.none")}</p>
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
                    <option value="openai">Codex CLI</option>
                    <option value="claude">Claude Code</option>
                    <option value="gemini">Gemini CLI</option>
                    <option value="openrouter">OpenRouter</option>
                    <option value="opencdk">OpenCDK</option>
                    <option value="local_openai">Local OpenAI-Compatible</option>
                    <option value="oss">Local OSS</option>
                  </select>
                </label>
                <label className="field field--wide">
                  <span>{t("field.model")}</span>
                  <input
                    value={selectedStep.model || ""}
                    placeholder={modelPlaceholder(selectedStep, detail?.runtime)}
                    onChange={(event) => onUpdateStepField("model", event.target.value)}
                    disabled={!editableStep}
                  />
                  <small className="muted">{autoModelHint(language)}</small>
                </label>
                <label className="field field--wide">
                  <span>{t("field.dependsOn")}</span>
                  <input
                    value={(selectedStep.depends_on || []).join(", ")}
                    onChange={(event) => onUpdateStepField("depends_on", normalizeListText(event.target.value))}
                    disabled={!editableStep}
                  />
                </label>
                <label className="field field--wide">
                  <span>{t("field.ownedPaths")}</span>
                  <textarea
                    value={(selectedStep.owned_paths || []).join("\n")}
                    onChange={(event) => onUpdateStepField("owned_paths", normalizeListText(event.target.value))}
                    disabled={!editableStep}
                  />
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
