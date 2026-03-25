import { runtimeSummary } from "../../utils";

function EffortButton({ preset, checked, onSelect, disabled }) {
  return (
    <button className={`choice-card ${checked ? "selected" : ""}`} onClick={onSelect} type="button" disabled={disabled}>
      <div className="choice-card__title">
        <strong>{preset.label}</strong>
        <span>{preset.effort}</span>
      </div>
      <p>{preset.description}</p>
    </button>
  );
}

export function ConfigEditorView({
  form,
  modelPresets,
  busy,
  onChangeForm,
  onChooseDirectory,
  onSaveProject,
}) {
  const runtime = form.runtime || {};

  return (
    <section className="workspace-view">
      <div className="view-header">
        <div>
          <span className="eyebrow">Config Editor</span>
          <h2>Project Configuration</h2>
          <p>Repository setup stays editable here so the operations console can manage isolated workspaces without hiding the underlying runtime.</p>
        </div>
        <button className="toolbar-button toolbar-button--accent" onClick={onSaveProject} type="button" disabled={busy}>
          Save Configuration
        </button>
      </div>

      <div className="form-layout">
        <div className="form-section">
          <label className="field">
            <span>Project Name</span>
            <input value={form.display_name} onChange={(event) => onChangeForm((current) => ({ ...current, display_name: event.target.value }))} disabled={busy} />
          </label>
          <label className="field field--wide">
            <span>Working Directory</span>
            <div className="field-row">
              <input value={form.project_dir} onChange={(event) => onChangeForm((current) => ({ ...current, project_dir: event.target.value }))} disabled={busy} />
              <button className="toolbar-button" onClick={onChooseDirectory} type="button" disabled={busy}>
                Browse
              </button>
            </div>
          </label>
          <label className="field">
            <span>Branch</span>
            <input value={form.branch} onChange={(event) => onChangeForm((current) => ({ ...current, branch: event.target.value }))} disabled={busy} />
          </label>
          <label className="field">
            <span>Verification Command</span>
            <input
              value={runtime.test_cmd || ""}
              onChange={(event) => onChangeForm((current) => ({ ...current, runtime: { ...current.runtime, test_cmd: event.target.value } }))}
              disabled={busy}
            />
          </label>
          <label className="field">
            <span>Max Planned Steps</span>
            <input
              type="number"
              min="1"
              value={runtime.max_blocks || 5}
              onChange={(event) =>
                onChangeForm((current) => ({
                  ...current,
                  runtime: { ...current.runtime, max_blocks: Math.max(1, Number.parseInt(event.target.value || "1", 10) || 1) },
                }))
              }
              disabled={busy}
            />
          </label>
        </div>

        <div className="form-section">
          <div className="subsection">
            <div className="subsection__header">
              <strong>GitHub Connection</strong>
              <span>Keep local and GitHub-backed repositories explicit.</span>
            </div>
            <div className="choice-list">
              {[
                ["existing", "Use existing origin in this folder"],
                ["manual", "Paste a GitHub repository URL"],
                ["none", "Do not connect GitHub yet"],
              ].map(([value, label]) => (
                <label className="choice-radio" key={value}>
                  <input type="radio" checked={form.github_mode === value} onChange={() => onChangeForm((current) => ({ ...current, github_mode: value }))} disabled={busy} />
                  <span>{label}</span>
                </label>
              ))}
            </div>
            {form.github_mode === "manual" ? (
              <label className="field field--wide">
                <span>GitHub URL</span>
                <input value={form.origin_url} onChange={(event) => onChangeForm((current) => ({ ...current, origin_url: event.target.value }))} disabled={busy} />
              </label>
            ) : null}
          </div>

          <div className="subsection">
            <div className="subsection__header">
              <strong>Execution Model</strong>
              <span>{runtimeSummary(runtime, modelPresets)}</span>
            </div>
            <label className="field">
              <span>Model</span>
              <input value={runtime.model || "gpt-5.4"} disabled />
            </label>
            <div className="choice-grid">
              {modelPresets.map((preset) => (
                <EffortButton
                  key={preset.preset_id}
                  preset={preset}
                  checked={runtime.model_preset === preset.preset_id}
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
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
