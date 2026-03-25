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

          <div className="subsection">
            <div className="subsection__header">
              <strong>Developer Mode</strong>
              <span>Advanced runtime controls for debugging and custom execution.</span>
            </div>
            <label className="field">
              <span>Custom Model Slug</span>
              <input
                value={runtime.model_slug_input || runtime.model || ""}
                onChange={(event) =>
                  onChangeForm((current) => ({
                    ...current,
                    runtime: {
                      ...current.runtime,
                      model_selection_mode: "slug",
                      model_slug_input: event.target.value,
                      model: event.target.value,
                    },
                  }))
                }
                disabled={busy}
              />
            </label>
            <label className="field field--wide">
              <span>Extra Prompt</span>
              <textarea
                value={runtime.extra_prompt || ""}
                onChange={(event) => onChangeForm((current) => ({ ...current, runtime: { ...current.runtime, extra_prompt: event.target.value } }))}
                disabled={busy}
              />
            </label>
            <div className="choice-grid">
              <label className="field">
                <span>Approval Mode</span>
                <select
                  value={runtime.approval_mode || "never"}
                  onChange={(event) => onChangeForm((current) => ({ ...current, runtime: { ...current.runtime, approval_mode: event.target.value } }))}
                  disabled={busy}
                >
                  <option value="never">never</option>
                  <option value="on-failure">on-failure</option>
                  <option value="untrusted">untrusted</option>
                </select>
              </label>
              <label className="field">
                <span>Sandbox Mode</span>
                <select
                  value={runtime.sandbox_mode || "danger-full-access"}
                  onChange={(event) => onChangeForm((current) => ({ ...current, runtime: { ...current.runtime, sandbox_mode: event.target.value } }))}
                  disabled={busy}
                >
                  <option value="danger-full-access">danger-full-access</option>
                  <option value="workspace-write">workspace-write</option>
                  <option value="read-only">read-only</option>
                </select>
              </label>
              <label className="field">
                <span>Checkpoint Interval</span>
                <input
                  type="number"
                  min="1"
                  value={runtime.checkpoint_interval_blocks || 1}
                  onChange={(event) =>
                    onChangeForm((current) => ({
                      ...current,
                      runtime: { ...current.runtime, checkpoint_interval_blocks: Math.max(1, Number.parseInt(event.target.value || "1", 10) || 1) },
                    }))
                  }
                  disabled={busy}
                />
              </label>
              <label className="field">
                <span>Codex Path</span>
                <input
                  value={runtime.codex_path || "codex.cmd"}
                  onChange={(event) => onChangeForm((current) => ({ ...current, runtime: { ...current.runtime, codex_path: event.target.value } }))}
                  disabled={busy}
                />
              </label>
            </div>
            <div className="choice-list">
              <label className="choice-radio">
                <input
                  type="checkbox"
                  checked={Boolean(runtime.allow_push)}
                  onChange={(event) => onChangeForm((current) => ({ ...current, runtime: { ...current.runtime, allow_push: event.target.checked } }))}
                  disabled={busy}
                />
                <span>Allow push after safe runs</span>
              </label>
              <label className="choice-radio">
                <input
                  type="checkbox"
                  checked={Boolean(runtime.require_checkpoint_approval)}
                  onChange={(event) =>
                    onChangeForm((current) => ({
                      ...current,
                      runtime: { ...current.runtime, require_checkpoint_approval: event.target.checked },
                    }))
                  }
                  disabled={busy}
                />
                <span>Require checkpoint approval</span>
              </label>
            </div>
          </div>
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
