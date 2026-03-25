import { basename, runtimeSummary } from "../utils";

function WorkspaceCard({ label, value }) {
  return (
    <div className="workspace-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ProjectCard({ project, selected, onSelect }) {
  return (
    <button
      className={`project-card ${selected ? "selected" : ""}`}
      onClick={() => onSelect(project.repo_id)}
      type="button"
    >
      <div className="project-card__icon">{(project.display_name || project.slug || "PR").slice(0, 2).toUpperCase()}</div>
      <div className="project-card__body">
        <strong>{project.display_name}</strong>
        <span>{project.status}</span>
        <span>{project.repo_path}</span>
        <span>{project.detail}</span>
      </div>
    </button>
  );
}

function ModelOption({ preset, checked, onSelect, disabled }) {
  return (
    <button className={`model-option ${checked ? "selected" : ""}`} onClick={onSelect} type="button" disabled={disabled}>
      <div className="model-option__headline">
        <strong>{preset.label}</strong>
        <span>{preset.model}</span>
      </div>
      <p>{preset.description}</p>
    </button>
  );
}

export function SetupStage({
  workspaceRoot,
  workspaceStats,
  projects,
  selectedProjectId,
  selectedProjectSummary,
  setupMode,
  form,
  modelPresets,
  busy,
  onSelectProject,
  onCreateNew,
  onEditSelected,
  onOpenSelected,
  onRefresh,
  onChooseDirectory,
  onChangeForm,
  onSaveProject,
}) {
  const formVisible = setupMode !== "welcome";
  const isCreate = setupMode === "create";
  const currentRuntime = form.runtime || {};
  const presetIds = new Set(modelPresets.map((item) => item.preset_id));
  const showCustomModel = currentRuntime.model && !presetIds.has(currentRuntime.model_preset);

  return (
    <div className="stage-layout stage-layout--setup">
      <section className="panel panel--projects">
        <div className="panel__header">
          <div>
            <span className="eyebrow">Workspace</span>
            <h2>Managed Projects</h2>
          </div>
          <button className="button button--ghost" onClick={onRefresh} type="button" disabled={busy}>
            Refresh
          </button>
        </div>
        <div className="workspace-cards">
          <WorkspaceCard label="Projects" value={workspaceStats?.project_count ?? 0} />
          <WorkspaceCard label="Running" value={workspaceStats?.running ?? 0} />
          <WorkspaceCard label="Failed" value={workspaceStats?.failed ?? 0} />
          <WorkspaceCard label="Ready" value={workspaceStats?.ready_like ?? 0} />
        </div>
        <p className="workspace-path">{workspaceRoot}</p>
        <div className="panel-toolbar">
          <button className="button button--primary" onClick={onCreateNew} type="button" disabled={busy}>
            Create New
          </button>
          <button className="button button--secondary" onClick={onEditSelected} type="button" disabled={busy || !selectedProjectId}>
            Edit Selected
          </button>
          <button className="button button--secondary" onClick={onOpenSelected} type="button" disabled={busy || !selectedProjectId}>
            Open Flow
          </button>
        </div>
        <div className="project-browser">
          {projects.length ? (
            projects.map((project) => (
              <ProjectCard
                key={project.repo_id}
                project={project}
                selected={project.repo_id === selectedProjectId}
                onSelect={onSelectProject}
              />
            ))
          ) : (
            <div className="empty-state">
              <strong>No managed projects yet</strong>
              <p>Create a new managed directory to start using the desktop shell.</p>
            </div>
          )}
        </div>
        <div className="summary-box">
          <span className="summary-box__label">Project Summary</span>
          <pre>{selectedProjectSummary || "Select a managed project to inspect it, or create a new one."}</pre>
        </div>
      </section>

      <section className="panel panel--detail">
        {formVisible ? (
          <>
            <div className="panel__header">
              <div>
                <span className="eyebrow">{isCreate ? "New Project" : "Project Settings"}</span>
                <h2>{isCreate ? "Create Managed Project" : "Edit Managed Project"}</h2>
              </div>
            </div>
            <p className="panel-copy">
              Choose a directory, keep the runtime predictable, and open the flow only after the saved project is ready.
            </p>
            <div className="form-grid">
              <label className="field">
                <span>Project Name</span>
                <input
                  value={form.display_name}
                  onChange={(event) => onChangeForm((current) => ({ ...current, display_name: event.target.value }))}
                  placeholder="Repository display name"
                  disabled={busy}
                />
              </label>
              <label className="field field--wide">
                <span>Working Directory</span>
                <div className="field-row">
                  <input
                    value={form.project_dir}
                    onChange={(event) => onChangeForm((current) => ({ ...current, project_dir: event.target.value }))}
                    placeholder="C:\\path\\to\\repo"
                    disabled={busy}
                  />
                  <button className="button button--secondary" onClick={onChooseDirectory} type="button" disabled={busy}>
                    Browse
                  </button>
                </div>
              </label>
              <label className="field">
                <span>Branch</span>
                <input
                  value={form.branch}
                  onChange={(event) => onChangeForm((current) => ({ ...current, branch: event.target.value }))}
                  placeholder="main"
                  disabled={busy}
                />
              </label>
              <label className="field">
                <span>Verification Command</span>
                <input
                  value={currentRuntime.test_cmd || ""}
                  onChange={(event) =>
                    onChangeForm((current) => ({
                      ...current,
                      runtime: { ...current.runtime, test_cmd: event.target.value },
                    }))
                  }
                  placeholder="python -m pytest"
                  disabled={busy}
                />
              </label>
              <label className="field">
                <span>Max Planned Steps</span>
                <input
                  type="number"
                  min="1"
                  value={currentRuntime.max_blocks || 5}
                  onChange={(event) =>
                    onChangeForm((current) => ({
                      ...current,
                      runtime: {
                        ...current.runtime,
                        max_blocks: Math.max(1, Number.parseInt(event.target.value || "1", 10) || 1),
                      },
                    }))
                  }
                  disabled={busy}
                />
              </label>
            </div>

            <div className="subpanel">
              <div className="subpanel__header">
                <strong>GitHub Connection</strong>
                <span>Keep the setup choices aligned with the original desktop flow.</span>
              </div>
              <div className="radio-list">
                {[
                  ["existing", "Use the existing origin in this folder"],
                  ["manual", "Paste a GitHub repository URL"],
                  ["none", "Do not connect GitHub yet"],
                ].map(([value, label]) => (
                  <label className="radio-card" key={value}>
                    <input
                      type="radio"
                      checked={form.github_mode === value}
                      onChange={() => onChangeForm((current) => ({ ...current, github_mode: value }))}
                      disabled={busy}
                    />
                    <span>{label}</span>
                  </label>
                ))}
              </div>
              {form.github_mode === "manual" ? (
                <label className="field field--wide">
                  <span>GitHub URL</span>
                  <input
                    value={form.origin_url}
                    onChange={(event) => onChangeForm((current) => ({ ...current, origin_url: event.target.value }))}
                    placeholder="https://github.com/example/repo.git"
                    disabled={busy}
                  />
                </label>
              ) : null}
            </div>

            <div className="subpanel">
              <div className="subpanel__header">
                <strong>Execution Model</strong>
                <span>{runtimeSummary(currentRuntime, modelPresets)}</span>
              </div>
              <div className="model-grid">
                {modelPresets.map((preset) => (
                  <ModelOption
                    key={preset.preset_id}
                    preset={preset}
                    checked={currentRuntime.model_preset === preset.preset_id}
                    onSelect={() =>
                      onChangeForm((current) => ({
                        ...current,
                        runtime: {
                          ...current.runtime,
                          model_preset: preset.preset_id,
                          model: preset.model,
                          effort: preset.effort,
                          model_selection_mode: "slug",
                          model_slug_input: preset.model,
                        },
                      }))
                    }
                    disabled={busy}
                  />
                ))}
                {showCustomModel ? (
                  <button
                    className={`model-option ${!currentRuntime.model_preset ? "selected" : ""}`}
                    onClick={() =>
                      onChangeForm((current) => ({
                        ...current,
                        runtime: {
                          ...current.runtime,
                          model_preset: "",
                          model_selection_mode: "slug",
                          model_slug_input: current.runtime.model,
                        },
                      }))
                    }
                    type="button"
                    disabled={busy}
                  >
                    <div className="model-option__headline">
                      <strong>Saved Custom Model</strong>
                      <span>{currentRuntime.model}</span>
                    </div>
                    <p>This project already uses a custom runtime slug. The desktop shell preserves it but does not compose new ones.</p>
                  </button>
                ) : null}
              </div>
            </div>

            <div className="panel-toolbar">
              <button className="button button--secondary" onClick={() => onSaveProject(false)} type="button" disabled={busy}>
                {isCreate ? "Create Project" : "Save Project"}
              </button>
              <button className="button button--primary" onClick={() => onSaveProject(true)} type="button" disabled={busy}>
                {isCreate ? "Create And Open Flow" : "Save And Open Flow"}
              </button>
            </div>
          </>
        ) : (
          <div className="welcome-panel">
            <span className="eyebrow">Desktop Shell</span>
            <h2>React + Tauri Workspace</h2>
            <p>
              The Python orchestration backend stays intact. This shell replaces the Tkinter surface with a
              desktop-friendly setup screen and a flow editor that can keep polling long-running work.
            </p>
            <div className="welcome-notes">
              <div>
                <strong>Flow-first</strong>
                <span>Setup and execution stay in separate stages, matching the original UI feature list.</span>
              </div>
              <div>
                <strong>Traceable</strong>
                <span>Projects, plan state, stop requests, and desktop UI events are all written into the workspace.</span>
              </div>
              <div>
                <strong>Windows-first</strong>
                <span>Folder browsing and the warm card layout are tuned for a packaged desktop app.</span>
              </div>
            </div>
            <div className="panel-toolbar">
              <button className="button button--primary" onClick={onCreateNew} type="button" disabled={busy}>
                Create New Project
              </button>
              <button className="button button--secondary" onClick={onOpenSelected} type="button" disabled={busy || !selectedProjectId}>
                Open Selected Flow
              </button>
            </div>
            {selectedProjectId ? (
              <div className="welcome-selected">
                <span>Selected project</span>
                <strong>{basename(form.project_dir) || form.display_name || "Managed repository"}</strong>
              </div>
            ) : null}
          </div>
        )}
      </section>
    </div>
  );
}
