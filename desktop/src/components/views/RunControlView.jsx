import { canEditStep, REASONING_OPTIONS, reasoningEffortLabel, statusTone } from "../../utils";

function FlowNode({ step, selected, onSelect }) {
  const tone = statusTone(step.status);
  return (
    <button className={`run-node run-node--${tone} ${selected ? "selected" : ""}`} onClick={() => onSelect(step.step_id)} type="button">
      <div className="run-node__meta">
        <span className="run-node__id">{step.step_id}</span>
        <span className={`status-badge status-badge--${tone}`}>{step.status}</span>
      </div>
      <strong>{step.title}</strong>
      <p>{step.display_description || step.test_command || "No summary"}</p>
      <p>Reasoning {reasoningEffortLabel(step.reasoning_effort || "high")}</p>
    </button>
  );
}

export function RunControlView({
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
  onMoveStep,
}) {
  const steps = planDraft?.steps || [];
  const selectedStep = steps.find((step) => step.step_id === selectedStepId) || null;
  const editableStep = canEditStep(selectedStep, busy);
  const completedCount = steps.filter((step) => step.status === "completed").length;
  const flowColumns = 3;

  return (
    <section className="workspace-view">
      <div className="view-header">
        <div>
          <span className="eyebrow">Flow</span>
          <h2>Execution Flow</h2>
        </div>
      </div>

      <div className="run-summary">
        <div className={`metric-card metric-card--${statusTone(detail?.project?.current_status)}`}>
          <span>Status</span>
          <strong>{detail?.project?.current_status || "idle"}</strong>
        </div>
        <div className="metric-card metric-card--info">
          <span>Done</span>
          <strong>{completedCount}/{steps.length || 0}</strong>
        </div>
        <div className={`metric-card metric-card--${detail?.run_control?.stop_after_current_step ? "warning" : "neutral"}`}>
          <span>Stop After Step</span>
          <strong>{detail?.run_control?.stop_after_current_step ? "On" : "Off"}</strong>
        </div>
        <div className={`metric-card metric-card--${statusTone(planDraft?.closeout_status)}`}>
          <span>Closeout</span>
          <strong>{planDraft?.closeout_status || "not_started"}</strong>
        </div>
      </div>

      <div className="content-card content-card--flow">
        <div className="content-card__header">
          <strong>Flow Chart</strong>
          <div className="action-row">
            <button className="toolbar-button" onClick={onGeneratePlan} type="button" disabled={busy}>
              Generate
            </button>
            <button className="toolbar-button" onClick={onSavePlan} type="button" disabled={busy}>
              Save
            </button>
            <button className="toolbar-button toolbar-button--ghost" onClick={onResetPlan} type="button" disabled={busy}>
              Reset
            </button>
            <button className="toolbar-button toolbar-button--accent" onClick={onRunPlan} type="button" disabled={busy}>
              Run
            </button>
            <button className="toolbar-button" onClick={onRunCloseout} type="button" disabled={busy}>
              Closeout
            </button>
            <button className="toolbar-button toolbar-button--ghost" onClick={onRequestStop} type="button" disabled={!busy}>
              Stop
            </button>
          </div>
        </div>
        <div className="run-flow">
          {steps.length ? (
            steps.map((step, index) => (
              <div className="run-flow__item" key={step.step_id}>
                <FlowNode step={step} selected={step.step_id === selectedStepId} onSelect={onSelectStep} />
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
            <div className="empty-block">No steps yet. Generate a plan or add one.</div>
          )}
        </div>
      </div>

      <div className="run-layout">
        <div className="content-card">
          <div className="content-card__header">
            <strong>Prompt</strong>
          </div>
          <textarea className="editor-textarea editor-textarea--prompt" value={planDraft?.project_prompt || ""} onChange={(event) => onPromptChange(event.target.value)} disabled={busy} />
        </div>

        <div className="content-card">
          <div className="content-card__header">
            <strong>Selected Step</strong>
            <span className={`status-badge status-badge--${statusTone(selectedStep?.status)}`}>{selectedStep?.status || "none"}</span>
          </div>
          {selectedStep ? (
            <div className="step-editor-grid">
              <label className="field field--wide">
                <span>Title</span>
                <input value={selectedStep.title || ""} onChange={(event) => onUpdateStepField("title", event.target.value)} disabled={!editableStep} />
              </label>
              <label className="field">
                <span>GPT Reasoning</span>
                <select
                  value={selectedStep.reasoning_effort || detail?.runtime?.effort || "high"}
                  onChange={(event) => onUpdateStepField("reasoning_effort", event.target.value)}
                  disabled={!editableStep}
                >
                  {REASONING_OPTIONS.map((effort) => (
                    <option key={effort} value={effort}>
                      {reasoningEffortLabel(effort)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field field--wide">
                <span>Description</span>
                <textarea value={selectedStep.display_description || ""} onChange={(event) => onUpdateStepField("display_description", event.target.value)} disabled={!editableStep} />
              </label>
              <label className="field field--wide">
                <span>Codex Instruction</span>
                <textarea value={selectedStep.codex_description || ""} onChange={(event) => onUpdateStepField("codex_description", event.target.value)} disabled={!editableStep} />
              </label>
              <label className="field field--wide">
                <span>Success Criteria</span>
                <textarea value={selectedStep.success_criteria || ""} onChange={(event) => onUpdateStepField("success_criteria", event.target.value)} disabled={!editableStep} />
              </label>
              <div className="action-row field--wide">
                <button className="toolbar-button toolbar-button--accent" onClick={onSaveStepLocal} type="button" disabled={busy}>
                  Save Local
                </button>
                <button className="toolbar-button" onClick={onAddStep} type="button" disabled={busy}>
                  Add
                </button>
                <button className="toolbar-button toolbar-button--ghost" onClick={onDeleteStep} type="button" disabled={!editableStep}>
                  Delete
                </button>
                <button className="toolbar-button toolbar-button--ghost" onClick={() => onMoveStep(-1)} type="button" disabled={!editableStep}>
                  Up
                </button>
                <button className="toolbar-button toolbar-button--ghost" onClick={() => onMoveStep(1)} type="button" disabled={!editableStep}>
                  Down
                </button>
              </div>
            </div>
          ) : (
            <div className="empty-block">Select a step.</div>
          )}
        </div>
      </div>
    </section>
  );
}
