import { canEditStep, statusTone } from "../../utils";

function FlowNode({ step, selected, onSelect }) {
  return (
    <button className={`run-node ${selected ? "selected" : ""} run-node--${statusTone(step.status)}`} onClick={() => onSelect(step.step_id)} type="button">
      <span className="run-node__id">{step.step_id}</span>
      <strong>{step.title}</strong>
      <p>{step.display_description || step.test_command || "No summary."}</p>
      <span className="status-badge status-badge--neutral">{step.status}</span>
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

  return (
    <section className="workspace-view">
      <div className="view-header">
        <div>
          <span className="eyebrow">Run Control</span>
          <h2>Prompt, Plan, And Execution</h2>
          <p>Generate the saved execution plan, refine pending steps, and drive the actual long-running workflow without leaving the main workspace.</p>
        </div>
        <div className="action-row">
          <button className="toolbar-button" onClick={onGeneratePlan} type="button" disabled={busy}>
            Generate Plan
          </button>
          <button className="toolbar-button" onClick={onSavePlan} type="button" disabled={busy}>
            Save Plan
          </button>
          <button className="toolbar-button toolbar-button--ghost" onClick={onResetPlan} type="button" disabled={busy}>
            Reset
          </button>
          <button className="toolbar-button toolbar-button--accent" onClick={onRunPlan} type="button" disabled={busy}>
            Run Remaining
          </button>
          <button className="toolbar-button" onClick={onRunCloseout} type="button" disabled={busy}>
            Closeout
          </button>
          <button className="toolbar-button toolbar-button--ghost" onClick={onRequestStop} type="button" disabled={!busy}>
            Stop After Step
          </button>
        </div>
      </div>

      <div className="run-layout">
        <div className="content-card">
          <div className="content-card__header">
            <strong>Project Prompt</strong>
          </div>
          <textarea className="editor-textarea editor-textarea--prompt" value={planDraft?.project_prompt || ""} onChange={(event) => onPromptChange(event.target.value)} disabled={busy} />
        </div>

        <div className="content-card">
          <div className="content-card__header">
            <strong>Execution Strip</strong>
          </div>
          <div className="run-strip">
            {steps.length ? (
              steps.map((step) => (
                <FlowNode key={step.step_id} step={step} selected={step.step_id === selectedStepId} onSelect={onSelectStep} />
              ))
            ) : (
              <div className="empty-block">No steps yet. Generate a plan or add a pending step.</div>
            )}
          </div>
        </div>
      </div>

      <div className="content-card">
        <div className="content-card__header">
          <strong>Selected Step Editor</strong>
          <span className={`status-badge status-badge--${statusTone(selectedStep?.status)}`}>{selectedStep?.status || "none"}</span>
        </div>
        {selectedStep ? (
          <div className="step-editor-grid">
            <label className="field">
              <span>Title</span>
              <input value={selectedStep.title || ""} onChange={(event) => onUpdateStepField("title", event.target.value)} disabled={!editableStep} />
            </label>
            <label className="field">
              <span>Test Command</span>
              <input value={selectedStep.test_command || ""} onChange={(event) => onUpdateStepField("test_command", event.target.value)} disabled={!editableStep} />
            </label>
            <label className="field field--wide">
              <span>Display Description</span>
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
                Save Local Edits
              </button>
              <button className="toolbar-button" onClick={onAddStep} type="button" disabled={busy}>
                Add Step
              </button>
              <button className="toolbar-button toolbar-button--ghost" onClick={onDeleteStep} type="button" disabled={!editableStep}>
                Delete
              </button>
              <button className="toolbar-button toolbar-button--ghost" onClick={() => onMoveStep(-1)} type="button" disabled={!editableStep}>
                Move Up
              </button>
              <button className="toolbar-button toolbar-button--ghost" onClick={() => onMoveStep(1)} type="button" disabled={!editableStep}>
                Move Down
              </button>
            </div>
          </div>
        ) : (
          <div className="empty-block">Select a pending step to edit it.</div>
        )}
      </div>

      <div className="content-card">
        <div className="content-card__header">
          <strong>Run Control State</strong>
        </div>
        <div className="dense-list">
          <div className="dense-row">
            <strong>Current Status</strong>
            <span>{detail?.project?.current_status || "idle"}</span>
          </div>
          <div className="dense-row">
            <strong>Stop Requested</strong>
            <span>{detail?.run_control?.stop_after_current_step ? "Yes" : "No"}</span>
          </div>
          <div className="dense-row">
            <strong>Closeout Status</strong>
            <span>{planDraft?.closeout_status || "not_started"}</span>
          </div>
        </div>
      </div>
    </section>
  );
}
