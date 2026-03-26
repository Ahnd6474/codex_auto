import { useI18n } from "../../i18n";
import {
  AUTO_REASONING_OPTION,
  autoRoutingPresetLabel,
  configReasoningOptions,
  defaultReasoningOption,
  findModelCatalogEntry,
  reasoningEffortLabel,
  runtimeSummary,
  selectedConfigReasoning,
} from "../../utils";

function EffortButton({ effort, selected, onSelect, disabled, language, description, label }) {
  return (
    <button className={`choice-card ${selected ? "selected" : ""}`} onClick={() => onSelect(effort)} type="button" disabled={disabled}>
      <div className="choice-card__title">
        <strong>{label}</strong>
        <span>{effort}</span>
      </div>
      <p>{description}</p>
    </button>
  );
}

function autoPresetId(effort) {
  return effort === AUTO_REASONING_OPTION ? "auto" : effort;
}

function effortDescription(modelLabel, effort, language) {
  if (String(modelLabel || "").trim().toLowerCase() === "auto") {
    if (language === "ko") {
      if (effort === AUTO_REASONING_OPTION) {
        return "Codex 자동 라우팅의 기본 추론 설정을 사용합니다.";
      }
      return `Codex 자동 라우팅을 유지하면서 추론은 ${autoRoutingPresetLabel(effort, language)}으로 고정합니다.`;
    }
    if (effort === AUTO_REASONING_OPTION) {
      return "Use Codex automatic routing with its default reasoning setting.";
    }
    return `Keep Codex automatic routing enabled and lock reasoning to ${autoRoutingPresetLabel(effort, language)}.`;
  }
  const reasoningLabel = reasoningEffortLabel(effort, language);
  if (language === "ko") {
    if (effort === AUTO_REASONING_OPTION) {
      return `${modelLabel}의 기본 추론 수준을 사용합니다.`;
    }
    return `${modelLabel}에 ${reasoningLabel} 추론 수준을 적용합니다.`;
  }
  if (effort === AUTO_REASONING_OPTION) {
    return `Use ${modelLabel}'s default reasoning level.`;
  }
  return `Use ${reasoningLabel} reasoning with ${modelLabel}.`;
}

function updateRuntimeModel(currentRuntime, modelCatalog, nextModel, nextEffort = null) {
  const model = String(nextModel || "").trim().toLowerCase() || "auto";
  const supported = configReasoningOptions(modelCatalog, model, currentRuntime?.effort || "medium");
  const preferred = nextEffort || selectedConfigReasoning(modelCatalog, { ...currentRuntime, model });
  const selection = supported.includes(preferred) ? preferred : supported[0] || "medium";
  const effort = selection === AUTO_REASONING_OPTION ? defaultReasoningOption(modelCatalog, model, "medium") : selection;
  return {
    ...currentRuntime,
    model,
    effort,
    model_preset: model === "auto" ? autoPresetId(selection) : "",
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
  onDeleteProject,
}) {
  const runtime = form.runtime || {};
  const { language, t } = useI18n();
  const selectedModel = runtime.model || "auto";
  const selectedCatalogEntry = findModelCatalogEntry(modelCatalog, selectedModel);
  const supportedEfforts = configReasoningOptions(modelCatalog, selectedModel, runtime.effort || "medium");
  const selectedEffort = selectedConfigReasoning(modelCatalog, runtime);

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
          <h2>{t("tab.config")}</h2>
          <p>{t("config.projectConfigurationDescription")}</p>
        </div>
        <div className="field-row">
          <button className="toolbar-button" onClick={onDeleteProject} type="button" disabled={busy || !form.project_dir?.trim()}>
            {t("action.delete")}
          </button>
          <button className="toolbar-button toolbar-button--accent" onClick={onSaveProject} type="button" disabled={busy}>
            {t("action.saveConfiguration")}
          </button>
        </div>
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
          <label className="choice-radio">
            <input
              type="checkbox"
              checked={Boolean(runtime.use_fast_mode)}
              onChange={(event) =>
                onChangeForm((current) => ({
                  ...current,
                  runtime: {
                    ...current.runtime,
                    use_fast_mode: event.target.checked,
                  },
                }))
              }
              disabled={busy}
            />
            <span>{t("option.useFastMode")}</span>
          </label>
          <label className="choice-radio">
            <input
              type="checkbox"
              checked={Boolean(runtime.generate_word_report)}
              onChange={(event) =>
                onChangeForm((current) => ({
                  ...current,
                  runtime: {
                    ...current.runtime,
                    generate_word_report: event.target.checked,
                  },
                }))
              }
              disabled={busy}
            />
            <span>{t("option.generateWordReport")}</span>
          </label>
          <p>{t("config.fastModeDescription")}</p>
          <p>{t("config.wordReportDescription")}</p>

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
            <p>{t("config.programSettingsMoved")}</p>
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
                  label={selectedModel === "auto" ? autoRoutingPresetLabel(effort, language) : reasoningEffortLabel(effort, language)}
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
