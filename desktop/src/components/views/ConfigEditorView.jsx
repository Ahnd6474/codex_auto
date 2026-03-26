import { useI18n } from "../../i18n";
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
  const { language, t } = useI18n();

  return (
    <section className="workspace-view">
      <div className="view-header">
        <div>
          <span className="eyebrow">{t("tab.config")}</span>
          <h2>{t("config.projectConfiguration")}</h2>
          <p>{t("config.projectConfigurationDescription")}</p>
        </div>
        <button className="toolbar-button toolbar-button--accent" onClick={onSaveProject} type="button" disabled={busy}>
          {t("action.saveConfiguration")}
        </button>
      </div>

      <div className="form-layout">
        <div className="form-section">
          <label className="field">
            <span>{t("config.projectName")}</span>
            <input value={form.display_name} onChange={(event) => onChangeForm((current) => ({ ...current, display_name: event.target.value }))} disabled={busy} />
          </label>
          <label className="field field--wide">
            <span>{t("config.workingDirectory")}</span>
            <div className="field-row">
              <input value={form.project_dir} onChange={(event) => onChangeForm((current) => ({ ...current, project_dir: event.target.value }))} disabled={busy} />
              <button className="toolbar-button" onClick={onChooseDirectory} type="button" disabled={busy}>
                {t("action.browse")}
              </button>
            </div>
          </label>
          <label className="field">
            <span>{t("common.branch")}</span>
            <input value={form.branch} onChange={(event) => onChangeForm((current) => ({ ...current, branch: event.target.value }))} disabled={busy} />
          </label>
          <label className="field">
            <span>{t("field.verificationCommand")}</span>
            <input
              value={runtime.test_cmd || ""}
              onChange={(event) => onChangeForm((current) => ({ ...current, runtime: { ...current.runtime, test_cmd: event.target.value } }))}
              disabled={busy}
            />
          </label>
          <label className="field">
            <span>{t("config.maxPlannedSteps")}</span>
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
              <strong>{t("config.developerMode")}</strong>
              <span>{t("config.developerModeDescription")}</span>
            </div>
            <label className="field">
              <span>{t("field.customModelSlug")}</span>
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
              <span>{t("field.extraPrompt")}</span>
              <textarea
                value={runtime.extra_prompt || ""}
                onChange={(event) => onChangeForm((current) => ({ ...current, runtime: { ...current.runtime, extra_prompt: event.target.value } }))}
                disabled={busy}
              />
            </label>
            <div className="choice-grid">
              <label className="field">
                <span>{t("field.approvalMode")}</span>
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
                <span>{t("field.sandboxMode")}</span>
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
                <span>{t("field.checkpointInterval")}</span>
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
                <span>{t("field.codexPath")}</span>
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
                <span>{t("option.allowPushAfterSafeRuns")}</span>
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
                <span>{t("option.requireCheckpointApproval")}</span>
              </label>
            </div>
          </div>
        </div>

        <div className="form-section">
          <div className="subsection">
            <div className="subsection__header">
              <strong>{t("config.githubConnection")}</strong>
              <span>{t("config.githubConnectionDescription")}</span>
            </div>
            <div className="choice-list">
              {[
                ["existing", t("config.useExistingOrigin")],
                ["manual", t("config.manualGithubUrl")],
                ["none", t("config.noGithubYet")],
              ].map(([value, label]) => (
                <label className="choice-radio" key={value}>
                  <input type="radio" checked={form.github_mode === value} onChange={() => onChangeForm((current) => ({ ...current, github_mode: value }))} disabled={busy} />
                  <span>{label}</span>
                </label>
              ))}
            </div>
            {form.github_mode === "manual" ? (
              <label className="field field--wide">
                <span>{t("config.githubUrl")}</span>
                <input value={form.origin_url} onChange={(event) => onChangeForm((current) => ({ ...current, origin_url: event.target.value }))} disabled={busy} />
              </label>
            ) : null}
          </div>

          <div className="subsection">
            <div className="subsection__header">
              <strong>{t("config.executionModel")}</strong>
              <span>{runtimeSummary(runtime, modelPresets, language)}</span>
            </div>
            <label className="field">
              <span>{t("field.model")}</span>
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
