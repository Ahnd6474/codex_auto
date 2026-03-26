import { useI18n } from "../../i18n";
import { displayStatus } from "../../locale";
import { canEditStep, REASONING_OPTIONS, reasoningEffortLabel, statusTone } from "../../utils";

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

function buildDagLayers(steps) {
  const orderedSteps = Array.isArray(steps) ? steps : [];
  const stepById = new Map(orderedSteps.map((step) => [step.step_id, step]));
  const visited = new Set();
  const layers = [];
  while (visited.size < orderedSteps.length) {
    const ready = orderedSteps.filter(
      (step) =>
        !visited.has(step.step_id) &&
        (step.depends_on || []).every((dependency) => visited.has(dependency) || !stepById.has(dependency)),
    );
    const layer = ready.length ? ready : orderedSteps.filter((step) => !visited.has(step.step_id)).slice(0, 1);
    layers.push(layer);
    layer.forEach((step) => visited.add(step.step_id));
  }
  return layers;
}

function readyPendingSteps(steps) {
  const completed = new Set((steps || []).filter((step) => step.status === "completed").map((step) => step.step_id));
  return (steps || []).filter(
    (step) => step.status !== "completed" && (step.depends_on || []).every((dependency) => completed.has(dependency)),
  );
}

function DagNode({ step, selected, onSelect, language, t }) {
  const tone = statusTone(step.status);
  return (
    <button className={`run-node run-node--${tone} ${selected ? "selected" : ""}`} onClick={() => onSelect(step.step_id)} type="button">
      <div className="run-node__meta">
        <span className="run-node__id">{step.step_id}</span>
        <span className={`status-badge status-badge--${tone}`}>{displayStatus(step.status, language)}</span>
      </div>
      <strong>{step.title}</strong>
      <p>{step.display_description || step.test_command || t("run.noSummary")}</p>
      <p>{t("field.dependsOn")}: {(step.depends_on || []).join(", ") || t("common.none")}</p>
      <p>{t("field.ownedPaths")}: {(step.owned_paths || []).join(", ") || t("common.none")}</p>
    </button>
  );
}

export function ParallelRunControlView({
  detail,
  planDraft,
  selectedStepId,
  busy,
  onPromptChange,
  onGeneratePlan,
  onSavePlan,
  onResetPlan,
  onRunPlan,
  onRunCloseout,
  onRequestStop,
  onSelectStep,
  onUpdateStepField,
  onSaveStepLocal,
  onAddStep,
  onDeleteStep,
}) {
  const steps = planDraft?.steps || [];
  const layers = buildDagLayers(steps);
  const readyNodes = readyPendingSteps(steps);
  const selectedStep = steps.find((step) => step.step_id === selectedStepId) || null;
  const editableStep = canEditStep(selectedStep, busy);
  const completedCount = steps.filter((step) => step.status === "completed").length;
  const { language, t } = useI18n();

  return (
    <section className="workspace-view">
      <div className="view-header">
        <div>
          <span className="eyebrow">{t("run.flow")}</span>
          <h2>{t("run.executionTree")}</h2>
        </div>
      </div>

      <div className="run-summary">
        <div className={`metric-card metric-card--${statusTone(detail?.project?.current_status)}`}>
          <span>{t("common.status")}</span>
          <strong>{displayStatus(detail?.project?.current_status || "idle", language)}</strong>
        </div>
        <div className="metric-card metric-card--info">
          <span>{t("run.done")}</span>
          <strong>{completedCount}/{steps.length || 0}</strong>
        </div>
        <div className="metric-card metric-card--info">
          <span>{t("run.parallelReady")}</span>
          <strong>{readyNodes.length}</strong>
        </div>
        <div className={`metric-card metric-card--${statusTone(planDraft?.closeout_status)}`}>
          <span>{t("run.closeout")}</span>
          <strong>{displayStatus(planDraft?.closeout_status || "not_started", language)}</strong>
        </div>
      </div>

      <div className="content-card content-card--flow">
        <div className="content-card__header">
          <strong>{t("run.executionTree")}</strong>
          <div className="action-row">
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
            <button className="toolbar-button" onClick={onRunCloseout} type="button" disabled={busy}>
              {t("action.closeout")}
            </button>
            <button className="toolbar-button toolbar-button--ghost" onClick={onRequestStop} type="button" disabled={!busy}>
              {t("action.stop")}
            </button>
          </div>
        </div>
        {layers.length ? (
          <div className="form-layout">
            {layers.map((layer, index) => (
              <div className="form-section" key={`layer-${index + 1}`}>
                <div className="subsection">
                  <div className="subsection__header">
                    <strong>{t("run.dagLayer", { index: index + 1 })}</strong>
                    <span>{layer.length} node(s)</span>
                  </div>
                  <div className="choice-grid">
                    {layer.map((step) => (
                      <DagNode key={step.step_id} step={step} selected={step.step_id === selectedStepId} onSelect={onSelectStep} language={language} t={t} />
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-block">{t("run.noSteps")}</div>
        )}
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
            <span className={`status-badge status-badge--${statusTone(selectedStep?.status)}`}>{selectedStep ? displayStatus(selectedStep.status, language) : t("common.none")}</span>
          </div>
          {selectedStep ? (
            <div className="step-editor-grid">
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
          ) : (
            <div className="empty-block">{t("run.selectStep")}</div>
          )}
        </div>
      </div>
    </section>
  );
}
