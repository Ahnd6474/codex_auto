import { useI18n } from "../../i18n";
import {
  AUTO_REASONING_OPTION,
  applyConfigRuntimeModelSelection,
  autoRoutingPresetLabel,
  clampReasoningEffort,
  configReasoningOptions,
  defaultModelForRuntime,
  filterModelCatalogByProvider,
  findModelCatalogEntry,
  normalizeMemoryBudgetGiB,
  normalizedModelProvider,
  providerAvailable,
  providerStatusReason,
  providerSupportsAutoModel,
  providerSupportsCatalog,
  REASONING_OPTIONS,
  reasoningEffortLabel,
  runtimeSummary,
  selectedConfigReasoning,
  syncProgramSettingsModel,
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

function modelReasoningSummary(entry, language) {
  const supported = Array.isArray(entry?.supported_reasoning_efforts) ? entry.supported_reasoning_efforts : [];
  if (!supported.length) {
    return "";
  }
  const labels = supported.map((effort) => reasoningEffortLabel(effort, language)).join(", ");
  const defaultLabel = reasoningEffortLabel(entry?.default_reasoning_effort || supported[0] || "medium", language);
  if (language === "ko") {
    return `지원 추론: ${labels} | 기본: ${defaultLabel}`;
  }
  return `Supported reasoning: ${labels} | default: ${defaultLabel}`;
}

export function ConfigEditorView({
  form,
  modelPresets,
  modelCatalog,
  codexStatus,
  busy,
  onChangeForm,
  onChangeProgramSettings,
  onChooseDirectory,
  onArchiveProject,
  onDeleteProject,
}) {
  const runtime = form.runtime || {};
  const { language, t } = useI18n();
  const planningReasoningLabel = language === "ko" ? "계획 추론" : "Planning Reasoning";
  const selectedProvider = normalizedModelProvider(runtime);
  const providerHasCatalog = providerSupportsCatalog(selectedProvider);
  const providerHasAutoModel = providerSupportsAutoModel(selectedProvider);
  const scopedModelCatalog = filterModelCatalogByProvider(modelCatalog, runtime);
  const selectedModel = runtime.model || defaultModelForRuntime(modelCatalog, runtime) || (providerHasAutoModel ? "auto" : "");
  const autoParallelWorkers = String(runtime.parallel_worker_mode || "auto").trim().toLowerCase() !== "manual";
  const selectedCatalogEntry = findModelCatalogEntry(scopedModelCatalog, selectedModel);
  const supportedEfforts = configReasoningOptions(scopedModelCatalog, selectedModel, runtime.effort || "medium");
  const selectedEffort = selectedConfigReasoning(scopedModelCatalog, runtime);
  const planningRuntime =
    selectedProvider === "ensemble"
      ? {
          ...runtime,
          model_provider: "openai",
          model: runtime.ensemble_openai_model || runtime.model || defaultModelForRuntime(modelCatalog, { ...runtime, model_provider: "openai" }) || "auto",
          model_slug_input: runtime.ensemble_openai_model || runtime.model_slug_input || runtime.model || "",
        }
      : runtime;
  const planningCatalog = filterModelCatalogByProvider(modelCatalog, planningRuntime);
  const planningModel =
    planningRuntime.model
    || planningRuntime.model_slug_input
    || defaultModelForRuntime(modelCatalog, planningRuntime)
    || selectedModel;
  const planningEntry = findModelCatalogEntry(planningCatalog, planningModel);
  const planningSupportedEfforts = (
    planningEntry?.supported_reasoning_efforts?.length
      ? planningEntry.supported_reasoning_efforts
      : REASONING_OPTIONS
  ).filter((effort) => REASONING_OPTIONS.includes(effort));
  const planningSelectedEffort = clampReasoningEffort(
    planningCatalog,
    planningModel,
    runtime.planning_effort || runtime.effort || "medium",
    runtime.effort || "medium",
  );
  const ensembleGeminiRuntime = { ...runtime, model_provider: "gemini", model: runtime.ensemble_gemini_model || "" };
  const ensembleGeminiCatalog = filterModelCatalogByProvider(modelCatalog, ensembleGeminiRuntime);
  const ensembleGeminiModel = runtime.ensemble_gemini_model || defaultModelForRuntime(modelCatalog, ensembleGeminiRuntime) || "";
  const ensembleGeminiEntry = findModelCatalogEntry(ensembleGeminiCatalog, ensembleGeminiModel);
  const ensembleClaudeRuntime = { ...runtime, model_provider: "claude", model: runtime.ensemble_claude_model || "" };
  const ensembleClaudeCatalog = filterModelCatalogByProvider(modelCatalog, ensembleClaudeRuntime);
  const ensembleClaudeModel = runtime.ensemble_claude_model || defaultModelForRuntime(modelCatalog, ensembleClaudeRuntime) || "";
  const ensembleClaudeEntry = findModelCatalogEntry(ensembleClaudeCatalog, ensembleClaudeModel);

  const visibleModels = (scopedModelCatalog || []).filter(
    (item) => item && item.model && (item.model !== "auto" || selectedModel === "auto"),
  );
  const allModels = visibleModels.length
    ? visibleModels
    : [
        {
          model: selectedModel || "",
          display_name: selectedCatalogEntry?.display_name || selectedModel || t("common.none"),
          hidden: false,
        },
      ];
  const selectedModelOption =
    selectedModel && !allModels.some((item) => item?.model === selectedModel)
      ? {
          model: selectedModel,
          display_name: selectedCatalogEntry?.display_name || selectedModel || t("common.none"),
          hidden: false,
        }
      : null;
  const recommendedModels = [
    ...(selectedModelOption ? [selectedModelOption] : []),
    ...allModels.filter((item) => !item.hidden),
  ];
  const additionalModels = allModels.filter((item) => item.hidden);

  function applyModelChange(nextModel, nextEffort = null) {
    const nextRuntime = applyConfigRuntimeModelSelection(runtime, scopedModelCatalog, nextModel, nextEffort);
    onChangeForm((current) => ({
      ...current,
      runtime: nextRuntime,
    }));
    if (typeof onChangeProgramSettings === "function") {
      onChangeProgramSettings((current) => syncProgramSettingsModel(current, nextRuntime));
    }
  }

  function applyRuntimePatch(runtimePatch) {
    const nextRuntime = {
      ...runtime,
      ...runtimePatch,
    };
    onChangeForm((current) => ({
      ...current,
      runtime: nextRuntime,
    }));
    if (typeof onChangeProgramSettings === "function") {
      onChangeProgramSettings((current) => syncProgramSettingsModel(current, nextRuntime));
    }
  }

  return (
    <section className="workspace-view">
      <div className="view-header">
        <div>
          <span className="eyebrow">{t("tab.config")}</span>
          <h2>{t("tab.config")}</h2>
        </div>
        <div className="field-row">
          <button className="toolbar-button toolbar-button--ghost" onClick={onArchiveProject} type="button" disabled={busy || !form.project_dir?.trim()}>
            {t("action.archiveProject")}
          </button>
          <button className="toolbar-button" onClick={onDeleteProject} type="button" disabled={busy || !form.project_dir?.trim()}>
            {t("action.deleteProject")}
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
          <label className="field">
            <span>{t("field.workflowMode")}</span>
            <select
              value={runtime.workflow_mode || "standard"}
              onChange={(event) =>
                onChangeForm((current) => ({
                  ...current,
                  runtime: {
                    ...current.runtime,
                    workflow_mode: event.target.value,
                  },
                }))
              }
              disabled={busy}
            >
              <option value="standard">{t("option.workflowStandard")}</option>
              <option value="ml">{t("option.workflowML")}</option>
            </select>
          </label>
          <label className="field">
            <span>{planningReasoningLabel}</span>
            <select
              value={planningSelectedEffort}
              onChange={(event) =>
                onChangeForm((current) => ({
                  ...current,
                  runtime: {
                    ...current.runtime,
                    planning_effort: event.target.value,
                  },
                }))
              }
              disabled={busy}
            >
              {planningSupportedEfforts.map((effort) => (
                <option key={effort} value={effort}>
                  {reasoningEffortLabel(effort, language)}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>{t("field.mlMaxCycles")}</span>
            <input
              type="number"
              min="1"
              value={runtime.ml_max_cycles || 3}
              onChange={(event) =>
                onChangeForm((current) => ({
                  ...current,
                  runtime: {
                    ...current.runtime,
                    ml_max_cycles: Math.max(1, Number.parseInt(event.target.value || "1", 10) || 1),
                  },
                }))
              }
              disabled={busy}
            />
          </label>
          <label className="choice-radio">
            <input
              type="checkbox"
              checked={runtime.allow_background_queue ?? true}
              onChange={(event) =>
                onChangeForm((current) => ({
                  ...current,
                  runtime: {
                    ...current.runtime,
                    allow_background_queue: event.target.checked,
                  },
                }))
              }
              disabled={busy}
            />
            <span>{t("field.allowBackgroundQueue")}</span>
          </label>
          <label className="field">
            <span>{t("field.backgroundQueuePriority")}</span>
            <input
              type="number"
              step="1"
              value={Number.parseInt(String(runtime.background_queue_priority ?? 0), 10) || 0}
              onChange={(event) =>
                onChangeForm((current) => ({
                  ...current,
                  runtime: {
                    ...current.runtime,
                    background_queue_priority: Number.parseInt(event.target.value || "0", 10) || 0,
                  },
                }))
              }
              disabled={busy}
            />
          </label>
          <div className="field">
            <span>{t("field.executionMode")}</span>
            <strong>{t("option.executionParallel")}</strong>
          </div>
          <label className="field">
            <span>{t("field.parallelWorkers")}</span>
            <input
              type="number"
              min="1"
              value={runtime.parallel_workers > 0 ? runtime.parallel_workers : 4}
              onChange={(event) =>
                onChangeForm((current) => ({
                  ...current,
                  runtime: {
                    ...current.runtime,
                    parallel_workers: Math.max(1, Number.parseInt(event.target.value || "1", 10) || 1),
                  },
                }))
              }
              disabled={busy || autoParallelWorkers}
            />
          </label>
          <label className="field">
            <span>{t("field.parallelMemoryPerWorkerGiB")}</span>
            <input
              type="number"
              min="0.1"
              step="0.1"
              value={runtime.parallel_memory_per_worker_gib || 3}
              onChange={(event) =>
                onChangeForm((current) => ({
                  ...current,
                  runtime: {
                    ...current.runtime,
                    parallel_memory_per_worker_gib: normalizeMemoryBudgetGiB(
                      event.target.value,
                      current.runtime?.parallel_memory_per_worker_gib || 3,
                    ),
                  },
                }))
              }
              disabled={busy}
            />
          </label>
          <label className="choice-radio">
            <input
              type="checkbox"
              checked={autoParallelWorkers}
              onChange={(event) =>
                onChangeForm((current) => ({
                  ...current,
                  runtime: {
                    ...current.runtime,
                    parallel_worker_mode: event.target.checked ? "auto" : "manual",
                    parallel_workers: event.target.checked
                      ? Math.max(0, Number.parseInt(String(current.runtime?.parallel_workers || "0"), 10) || 0)
                      : Math.max(1, Number.parseInt(String(current.runtime?.parallel_workers || "4"), 10) || 4),
                  },
                }))
              }
              disabled={busy}
            />
            <span>{t("preset.auto")}</span>
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
          <label className="field">
            <span>{t("field.optimizationMode")}</span>
            <select
              value={runtime.optimization_mode || "light"}
              onChange={(event) =>
                onChangeForm((current) => ({
                  ...current,
                  runtime: {
                    ...current.runtime,
                    optimization_mode: event.target.value,
                  },
                }))
              }
              disabled={busy}
            >
              <option value="off">{t("option.optimizationOff")}</option>
              <option value="light">{t("option.optimizationLight")}</option>
              <option value="refactor">{t("option.optimizationRefactor")}</option>
            </select>
          </label>
        </div>

        <div className="form-section">
          <div className="subsection">
            <div className="subsection__header">
              <strong>{t("config.githubConnection")}</strong>
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
            {!providerAvailable(selectedProvider, codexStatus) && providerStatusReason(selectedProvider, codexStatus) ? (
              <p className="muted">{providerStatusReason(selectedProvider, codexStatus)}</p>
            ) : null}
            <label className="field">
              <span>{selectedProvider === "ensemble" ? (language === "ko" ? "Codex 모델" : "Codex Model") : t("field.model")}</span>
              {providerHasCatalog ? (
                <select value={selectedModel} onChange={(event) => applyModelChange(event.target.value)} disabled={busy}>
                  {(recommendedModels.length ? recommendedModels : allModels).map((item) => (
                    <option key={item.model || "custom"} value={item.model}>
                      {item.display_name || item.model || t("common.none")}
                    </option>
                  ))}
                  {additionalModels.length ? (
                    <optgroup label={t("config.additionalModels")}>
                      {additionalModels.map((item) => (
                        <option key={item.model} value={item.model}>
                          {item.display_name}
                        </option>
                      ))}
                    </optgroup>
                  ) : null}
                </select>
              ) : (
                <input
                  value={runtime.model_slug_input || runtime.model || ""}
                  onChange={(event) => applyModelChange(event.target.value)}
                  disabled={busy}
                />
              )}
            </label>
            <div className="choice-grid">
              {supportedEfforts.map((effort) => (
                <EffortButton
                  key={effort}
                  effort={effort}
                  label={selectedModel === "auto" ? autoRoutingPresetLabel(effort, language) : reasoningEffortLabel(effort, language)}
                  selected={selectedEffort === effort}
                  onSelect={(nextEffort) => applyModelChange(selectedModel, nextEffort)}
                  disabled={busy}
                  language={language}
                  description={effortDescription(selectedCatalogEntry?.display_name || selectedModel || "auto", effort, language)}
                />
              ))}
            </div>
            {selectedProvider === "ensemble" ? (
              <div className="choice-list">
                <label className="field">
                  <span>{language === "ko" ? "Gemini 모델" : "Gemini Model"}</span>
                  <select
                    value={ensembleGeminiModel}
                    onChange={(event) => applyRuntimePatch({ ensemble_gemini_model: event.target.value })}
                    disabled={busy}
                  >
                    {ensembleGeminiCatalog.map((item) => (
                      <option key={item.model} value={item.model}>
                        {item.display_name || item.model}
                      </option>
                    ))}
                  </select>
                  {modelReasoningSummary(ensembleGeminiEntry, language) ? <small className="muted">{modelReasoningSummary(ensembleGeminiEntry, language)}</small> : null}
                </label>
                <label className="field">
                  <span>{language === "ko" ? "Claude 모델" : "Claude Model"}</span>
                  <select
                    value={ensembleClaudeModel}
                    onChange={(event) => applyRuntimePatch({ ensemble_claude_model: event.target.value })}
                    disabled={busy}
                  >
                    {ensembleClaudeCatalog.map((item) => (
                      <option key={item.model} value={item.model}>
                        {item.display_name || item.model}
                      </option>
                    ))}
                  </select>
                  {modelReasoningSummary(ensembleClaudeEntry, language) ? <small className="muted">{modelReasoningSummary(ensembleClaudeEntry, language)}</small> : null}
                </label>
              </div>
            ) : null}
            {!providerHasCatalog ? <p className="muted">{providerHasAutoModel ? t("config.providerPresetModelHint") : t("config.customProviderModelHint")}</p> : null}
          </div>
        </div>
      </div>
    </section>
  );
}
