import { canEditStep, commandLabel, progressCaption, runtimeSummary, statusTone } from "../utils";

function StatCard({ label, value, tone = "neutral" }) {
  return (
    <div className={`stat-card stat-card--${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function FlowNode({ node, selected, onSelect }) {
  return (
    <button
      className={`flow-node flow-node--${statusTone(node.status)} ${selected ? "selected" : ""} ${node.kind === "closeout" ? "flow-node--closeout" : ""}`}
      type="button"
      onClick={() => {
        if (node.kind === "step") {
          onSelect(node.step_id);
        }
      }}
    >
      <span className="flow-node__id">{node.kind === "closeout" ? "CLOSEOUT" : node.step_id}</span>
      <strong>{node.title}</strong>
      <p>{node.body}</p>
      <span className="flow-node__status">{node.status}</span>
    </button>
  );
}

export function FlowStage({
  detail,
  planDraft,
  selectedStepId,
  activeTab,
  modelPresets,
  busy,
  activeJob,
  onBack,
  onReload,
  onSetActiveTab,
  onPromptChange,
  onGeneratePlan,
  onSavePlan,
  onResetPlan,
  onRunPlan,
  onRunCloseout,
  onRequestStop,
  onSelectStep,
  onSaveStepLocal,
  onAddStep,
  onDeleteStep,
  onMoveStep,
  onClearSelection,
  onUpdateStepField,
}) {
  const steps = planDraft?.steps || [];
  const selectedStep = steps.find((step) => step.step_id === selectedStepId) || null;
  const editableStep = canEditStep(selectedStep, busy);
  const nodes = [
    ...steps.map((step) => ({
      kind: "step",
      ...step,
      body: step.display_description || step.test_command || "No step summary.",
    })),
    {
      kind: "closeout",
      step_id: "CLOSEOUT",
      title: "Project closeout",
      body: planDraft?.closeout_notes || "Finalize reports, verify the final state, and capture the closeout commit.",
      status: planDraft?.closeout_status || "not_started",
    },
  ];
  const usage = detail?.snapshot?.recent_usage || {};
  const statusText = activeJob?.status === "running" ? `${commandLabel(activeJob.command)} in progress` : detail?.project?.current_status || "Ready";
  const statusClass = activeJob?.status === "running" ? "info" : statusTone(detail?.project?.current_status);
  const activityText = (detail?.activity || []).join("\n");
  const snapshotText = JSON.stringify(detail?.snapshot || {}, null, 2);

  return (
    <div className="stage-layout stage-layout--flow">
      <section className="panel panel--flow-hero">
        <div className="panel__header panel__header--flow">
          <div>
            <span className="eyebrow">Prompt And Plan</span>
            <h2>{detail?.project?.display_name || detail?.project?.slug || "No project selected"}</h2>
            <p>{progressCaption(planDraft)}</p>
          </div>
          <div className={`status-pill status-pill--${statusClass}`}>{statusText}</div>
        </div>
        <div className="hero-toolbar">
          <button className="button button--ghost" onClick={onBack} type="button">
            Back To Projects
          </button>
          <button className="button button--secondary" onClick={onReload} type="button" disabled={busy}>
            Reload Project
          </button>
        </div>
        <div className="stats-grid">
          <StatCard label="Model" value={detail?.runtime?.model || "Unknown"} />
          <StatCard label="Reasoning" value={detail?.runtime?.effort || "high"} tone="info" />
          <StatCard label="Completed" value={`${detail?.stats?.completed_steps ?? 0}/${detail?.stats?.total_steps ?? 0}`} tone="success" />
          <StatCard label="Closeout" value={planDraft?.closeout_status || "not_started"} tone={statusTone(planDraft?.closeout_status)} />
          <StatCard label="Input Tokens" value={usage.input_tokens ?? 0} />
          <StatCard label="Output Tokens" value={usage.output_tokens ?? 0} />
        </div>
        <p className="runtime-summary">{runtimeSummary(detail?.runtime || {}, modelPresets)}</p>
        <label className="field field--stacked">
          <span>Project Prompt</span>
          <textarea
            className="prompt-area"
            value={planDraft?.project_prompt || ""}
            onChange={(event) => onPromptChange(event.target.value)}
            disabled={busy}
            placeholder="Describe the goal in plain language."
          />
        </label>
        <div className="hero-actions">
          <button className="button button--primary" onClick={onGeneratePlan} type="button" disabled={busy}>
            Generate Plan With Codex
          </button>
          <button className="button button--secondary" onClick={onSavePlan} type="button" disabled={busy}>
            Save Edited Plan
          </button>
          <button className="button button--ghost" onClick={onResetPlan} type="button" disabled={busy}>
            Reset Plan
          </button>
          <button className="button button--primary" onClick={onRunPlan} type="button" disabled={busy}>
            Run Remaining Steps
          </button>
          <button className="button button--secondary" onClick={onRunCloseout} type="button" disabled={busy}>
            Run Closeout
          </button>
          <button className="button button--ghost" onClick={onRequestStop} type="button" disabled={!busy || activeJob?.command !== "run-plan"}>
            Stop After Current Step
          </button>
        </div>
      </section>

      <div className="flow-main">
        <section className="panel panel--flow-strip">
          <div className="panel__header">
            <div>
              <span className="eyebrow">Interactive Flow</span>
              <h2>Checkpoint Strip</h2>
            </div>
          </div>
          <p className="panel-copy">
            Completed nodes stay read-only. Pending nodes can still be reordered and refined before the next run.
          </p>
          <div className="flow-strip">
            {nodes.length ? (
              nodes.map((node, index) => (
                <div className="flow-segment" key={`${node.kind}-${node.step_id}`}>
                  <FlowNode
                    node={node}
                    selected={node.kind === "step" && node.step_id === selectedStepId}
                    onSelect={onSelectStep}
                  />
                  {index < nodes.length - 1 ? <span className="flow-arrow">{"->"}</span> : null}
                </div>
              ))
            ) : (
              <div className="empty-state">
                <strong>No plan yet</strong>
                <p>Generate one from the prompt or add steps manually after loading a project.</p>
              </div>
            )}
          </div>
        </section>

        <section className="panel panel--editor">
          <div className="panel__header">
            <div>
              <span className="eyebrow">Selected Step</span>
              <h2>{selectedStep?.step_id || "No step selected"}</h2>
            </div>
            <div className={`status-pill status-pill--${statusTone(selectedStep?.status)}`}>{selectedStep?.status || "unselected"}</div>
          </div>
          <p className="panel-copy">Titles, descriptions, Codex instructions, test commands, and success criteria are all editable for pending steps only.</p>
          <div className="editor-grid">
            <label className="field">
              <span>Title</span>
              <input
                value={selectedStep?.title || ""}
                onChange={(event) => onUpdateStepField("title", event.target.value)}
                disabled={!editableStep}
              />
            </label>
            <label className="field">
              <span>Test Command</span>
              <input
                value={selectedStep?.test_command || ""}
                onChange={(event) => onUpdateStepField("test_command", event.target.value)}
                disabled={!editableStep}
              />
            </label>
            <label className="field field--wide">
              <span>Display Description</span>
              <textarea
                value={selectedStep?.display_description || ""}
                onChange={(event) => onUpdateStepField("display_description", event.target.value)}
                disabled={!editableStep}
              />
            </label>
            <label className="field field--wide">
              <span>Codex Instruction</span>
              <textarea
                value={selectedStep?.codex_description || ""}
                onChange={(event) => onUpdateStepField("codex_description", event.target.value)}
                disabled={!editableStep}
              />
            </label>
            <label className="field field--wide">
              <span>Success Criteria</span>
              <textarea
                value={selectedStep?.success_criteria || ""}
                onChange={(event) => onUpdateStepField("success_criteria", event.target.value)}
                disabled={!editableStep}
              />
            </label>
          </div>
          <div className="panel-toolbar">
            <button className="button button--primary" onClick={onSaveStepLocal} type="button" disabled={!selectedStep || busy}>
              Save Step
            </button>
            <button className="button button--secondary" onClick={onAddStep} type="button" disabled={busy}>
              Add Step
            </button>
            <button className="button button--ghost" onClick={onDeleteStep} type="button" disabled={!editableStep}>
              Delete Step
            </button>
            <button className="button button--ghost" onClick={() => onMoveStep(-1)} type="button" disabled={!editableStep}>
              Move Up
            </button>
            <button className="button button--ghost" onClick={() => onMoveStep(1)} type="button" disabled={!editableStep}>
              Move Down
            </button>
            <button className="button button--ghost" onClick={onClearSelection} type="button" disabled={busy}>
              Clear Selection
            </button>
          </div>
        </section>
      </div>

      <section className="panel panel--activity">
        <div className="panel__header">
          <div>
            <span className="eyebrow">Logs And Snapshot</span>
            <h2>Traceability</h2>
          </div>
        </div>
        <div className="tab-row">
          <button className={`tab-button ${activeTab === "activity" ? "active" : ""}`} onClick={() => onSetActiveTab("activity")} type="button">
            Activity
          </button>
          <button className={`tab-button ${activeTab === "snapshot" ? "active" : ""}`} onClick={() => onSetActiveTab("snapshot")} type="button">
            Snapshot
          </button>
        </div>
        <div className="trace-box">
          <pre>{activeTab === "activity" ? activityText : snapshotText}</pre>
        </div>
      </section>
    </div>
  );
}
