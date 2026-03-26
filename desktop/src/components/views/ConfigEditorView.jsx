import { useI18n } from "../../i18n";
import { defaultReasoningOption, findModelCatalogEntry, reasoningEffortLabel, runtimeSummary, supportedReasoningOptions } from "../../utils";

function EffortButton({ effort, selected, onSelect, disabled, language, description }) {
  return (
    <button className={`choice-card ${selected ? "selected" : ""}`} onClick={() => onSelect(effort)} type="button" disabled={disabled}>
      <div className="choice-card__title">
        <strong>{reasoningEffortLabel(effort, language)}</strong>
        <span>{effort}</span>
      </div>
      <p>{description}</p>
    </button>
  );
}

function autoPresetId(effort) {
  return effort === "medium" ? "auto" : `auto-${effort}`;
}

function effortDescription(modelLabel, effort, language) {
  const reasoningLabel = reasoningEffortLabel(effort, language);
  if (language === "ko") {
    return `${modelLabel}에 ${reasoningLabel} 추론 수준을 적용합니다.`;
  }
  return `Use ${reasoningLabel} reasoning with ${modelLabel}.`;
}

function updateRuntimeModel(currentRuntime, modelCatalog, nextModel, nextEffort = null) {
  const model = String(nextModel || "").trim().toLowerCase() || "auto";
  const supported = supportedReasoningOptions(modelCatalog, model, currentRuntime?.effort || "medium");
  const preferred = nextEffort || currentRuntime?.effort || defaultReasoningOption(modelCatalog, model, "medium");
  const effort = supported.includes(preferred) ? preferred : supported[0] || "medium";
  return {
    ...currentRuntime,
    model,
    effort,
    model_preset: model === "auto" ? autoPresetId(effort) : "",
    model_selection_mode: "slug",
    model_slug_input: model,
  };
}

export function ConfigEditorView({
  form,
  modelPresets,
  modelCatalog,
  busy,
  onChangeForm,
  onChooseDirectory,
  onSaveProject,
}) {
  const runtime = form.runtime || {};
  const { language, t } = useI18n();
  const selectedModel = runtime.model || "auto";
  const selectedCatalogEntry = findModelCatalogEntry(modelCatalog, selectedModel);
  const supportedEfforts = supportedReasoningOptions(modelCatalog, selectedModel, runtime.effort || "medium");
  const selectedEffort = supportedEfforts.includes(runtime.effort) ? runtime.effort : defaultReasoningOption(modelCatalog, selectedModel, "medium");

  const visibleModels = (modelCatalog || []).filter((item) => item && item.model);
  const allModels = visibleModels.length
    ? visibleModels
    : [
        {
          model: "auto",
          display_name: "Auto",
          hidden: false,
        },
      ];
  const recommendedModels = allModels.filter((item) => !item.hidden);
  const additionalModels = allModels.filter((item) => item.hidden);

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
                    runtime: updateRuntimeModel(
                      {
                        ...current.runtime,
                        model_slug_input: event.target.value,
                      },
                      modelCatalog,
                      event.target.value,
                    ),
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
              <span>{runtimeSummary(runtime, modelPresets, language, modelCatalog)}</span>
            </div>
            <label className="field">
              <span>{t("field.model")}</span>
              <select
                value={selectedModel}
                onChange={(event) =>
                  onChangeForm((current) => ({
                    ...current,
                    runtime: updateRuntimeModel(current.runtime, modelCatalog, event.target.value),
                  }))
                }
                disabled={busy}
              >
                {recommendedModels.map((item) => (
                  <option key={item.model} value={item.model}>
                    {item.display_name}
                  </option>
                ))}
                {additionalModels.length ? (
                  <optgroup label={language === "ko" ? "기타 지원 모델" : "Additional Models"}>
                    {additionalModels.map((item) => (
                      <option key={item.model} value={item.model}>
                        {item.display_name}
                      </option>
                    ))}
                  </optgroup>
                ) : null}
              </select>
            </label>
            <div className="choice-grid">
              {supportedEfforts.map((effort) => (
                <EffortButton
                  key={effort}
                  effort={effort}
                  selected={selectedEffort === effort}
                  onSelect={(nextEffort) =>
                    onChangeForm((current) => ({
                      ...current,
                      runtime: updateRuntimeModel(current.runtime, modelCatalog, selectedModel, nextEffort),
                    }))
                  }
                  disabled={busy}
                  language={language}
                  description={effortDescription(selectedCatalogEntry?.display_name || selectedModel || "auto", effort, language)}
                />
              ))}
            </div>
            {selectedCatalogEntry?.description ? <p>{selectedCatalogEntry.description}</p> : null}
          </div>
        </div>
      </div>
    </section>
  );
}
