import { progressCaption, statusTone } from "../../utils";

export function IdeToolbar({
  projectDetail,
  planDraft,
  busy,
  activeJob,
  onRefresh,
  onGeneratePlan,
  onRunPlan,
  onRunCloseout,
  onApproveCheckpoint,
  onToggleBottom,
}) {
  const status = activeJob?.status === "running" ? "running" : projectDetail?.project?.current_status || "idle";
  const checkpointPending = Boolean(projectDetail?.checkpoints?.pending);
  const projectName = projectDetail?.project?.display_name || projectDetail?.project?.slug || "No Project";

  return (
    <header className="ide-toolbar">
      <div className="ide-toolbar__group">
        <button className="toolbar-button toolbar-button--ghost" onClick={onRefresh} type="button">
          Refresh
        </button>
      </div>

      <div className="ide-toolbar__group ide-toolbar__group--grow">
        <div className="toolbar-chip">
          <span>Project</span>
          <strong>{projectName}</strong>
        </div>
        <div className={`toolbar-status toolbar-status--${statusTone(status)}`}>
          <span>Status</span>
          <strong>{activeJob?.status === "running" ? `${activeJob.command}` : status}</strong>
        </div>
        <div className="toolbar-status toolbar-status--neutral">
          <span>Plan</span>
          <strong>{progressCaption(planDraft)}</strong>
        </div>
      </div>

      <div className="ide-toolbar__group">
        <button className="toolbar-button" onClick={onGeneratePlan} type="button" disabled={busy}>
          Generate Plan
        </button>
        <button className="toolbar-button toolbar-button--accent" onClick={onRunPlan} type="button" disabled={busy}>
          Run Remaining
        </button>
        <button className="toolbar-button" onClick={onRunCloseout} type="button" disabled={busy}>
          Closeout
        </button>
        <button className="toolbar-button" onClick={onApproveCheckpoint} type="button" disabled={busy || !checkpointPending}>
          Approve Checkpoint
        </button>
        <button className="toolbar-button toolbar-button--ghost" onClick={onToggleBottom} type="button" title="Toggle tool window">
          Bottom
        </button>
      </div>
    </header>
  );
}
