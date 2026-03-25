import { reasoningEffortLabel, runtimeSummary, statusTone } from "../../utils";

export function DetailsPane({ detail, planDraft, selectedStepId, modelPresets }) {
  const selectedStep = (planDraft?.steps || []).find((step) => step.step_id === selectedStepId) || null;
  const pendingCheckpoint = detail?.checkpoints?.pending || null;

  return (
    <aside className="details-pane">
      <section className="details-card">
        <div className="details-card__header">
          <strong>Project Metadata</strong>
          <span className={`status-badge status-badge--${statusTone(detail?.project?.current_status)}`}>{detail?.project?.current_status || "idle"}</span>
        </div>
        <dl className="details-list">
          <div>
            <dt>Name</dt>
            <dd>{detail?.project?.display_name || detail?.project?.slug || "No project"}</dd>
          </div>
          <div>
            <dt>Branch</dt>
            <dd>{detail?.project?.branch || "Unknown"}</dd>
          </div>
          <div>
            <dt>Repo Path</dt>
            <dd>{detail?.project?.repo_path || "Unknown"}</dd>
          </div>
          <div>
            <dt>Model</dt>
            <dd>{runtimeSummary(detail?.runtime || {}, modelPresets)}</dd>
          </div>
          <div>
            <dt>Safe Revision</dt>
            <dd>{detail?.project?.current_safe_revision || "Not recorded yet"}</dd>
          </div>
        </dl>
      </section>

      <section className="details-card">
        <div className="details-card__header">
          <strong>Selected Step</strong>
          <span className={`status-badge status-badge--${statusTone(selectedStep?.status)}`}>{selectedStep?.status || "none"}</span>
        </div>
        {selectedStep ? (
          <div className="details-text">
            <strong>{selectedStep.step_id}: {selectedStep.title}</strong>
            <p>{selectedStep.display_description}</p>
            <p>GPT reasoning: {reasoningEffortLabel(selectedStep.reasoning_effort || detail?.runtime?.effort || "high")}</p>
            <p>{selectedStep.success_criteria}</p>
          </div>
        ) : (
          <div className="empty-block">Select a planned step to inspect its details.</div>
        )}
      </section>

      <section className="details-card">
        <div className="details-card__header">
          <strong>Checkpoint</strong>
          <span className={`status-badge status-badge--${statusTone(pendingCheckpoint?.status)}`}>{pendingCheckpoint?.status || "none"}</span>
        </div>
        {pendingCheckpoint ? (
          <div className="details-text">
            <strong>{pendingCheckpoint.checkpoint_id}</strong>
            <p>{pendingCheckpoint.title}</p>
            <p>Target block {pendingCheckpoint.target_block}</p>
          </div>
        ) : (
          <div className="empty-block">No checkpoint is currently awaiting review.</div>
        )}
      </section>

      <section className="details-card">
        <div className="details-card__header">
          <strong>Report Preview</strong>
        </div>
        <div className="details-text">
          <pre>{detail?.reports?.closeout_report_text || "No report preview available."}</pre>
        </div>
      </section>
    </aside>
  );
}
