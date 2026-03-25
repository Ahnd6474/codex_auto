import { progressCaption, statusTone } from "../../utils";

export function IdeToolbar({
  workspaceRoot,
  projects,
  selectedProjectId,
  projectDetail,
  planDraft,
  busy,
  activeJob,
  onSelectProject,
  onNewProject,
  onRefresh,
  onGeneratePlan,
  onRunPlan,
  onRunCloseout,
  onApproveCheckpoint,
  onOpenConfig,
  onToggleSidebar,
  onToggleBottom,
}) {
  const status = activeJob?.status === "running" ? "running" : projectDetail?.project?.current_status || "idle";
  const checkpointPending = Boolean(projectDetail?.checkpoints?.pending);

  return (
    <header className="ide-toolbar">
      <div className="ide-toolbar__group">
        <button className="toolbar-button toolbar-button--ghost" onClick={onToggleSidebar} type="button" title="Toggle sidebar">
          Sidebar
        </button>
        <button className="toolbar-button toolbar-button--ghost" onClick={onNewProject} type="button">
          New Project
        </button>
        <button className="toolbar-button toolbar-button--ghost" onClick={onOpenConfig} type="button">
          Config
        </button>
      </div>

      <div className="ide-toolbar__group ide-toolbar__group--grow">
        <div className="toolbar-chip">
          <span>Workspace</span>
          <strong>{workspaceRoot || "Loading"}</strong>
        </div>
        <label className="toolbar-select">
          <span>Project</span>
          <select value={selectedProjectId || ""} onChange={(event) => onSelectProject(event.target.value)} disabled={busy}>
            <option value="">No project selected</option>
            {projects.map((project) => (
              <option key={project.repo_id} value={project.repo_id}>
                {project.display_name}
              </option>
            ))}
          </select>
        </label>
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
        <button className="toolbar-button toolbar-button--ghost" onClick={onRefresh} type="button" disabled={busy}>
          Refresh
        </button>
        <button className="toolbar-button toolbar-button--ghost" onClick={onToggleBottom} type="button" title="Toggle tool window">
          Bottom
        </button>
      </div>
    </header>
  );
}
