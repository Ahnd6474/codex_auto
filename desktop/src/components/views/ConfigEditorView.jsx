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

/* ── Toggle row ── */
function ToggleRow({ checked, onChange, disabled, label, hint }) {
  return (
    <label className="toggle-row">
      <span className="toggle-row__label">
        <span>{label}</span>
        {hint ? <small>{hint}</small> : null}
      </span>
      <span className={`toggle-track ${checked ? "toggle-track--on" : ""}`}>
        <input type="checkbox" checked={checked} onChange={onChange} disabled={disabled} />
        <span className="toggle-thumb" />
      </span>
    </label>
  );
}

/* ── Section icons ── */
function ProjectIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M4.75 7.25A2.5 2.5 0 0 1 7.25 4.75h5.1c.66 0 1.3.26 1.77.73l5.15 5.15c.47.47.73 1.1.73 1.77v4.35a2.5 2.5 0 0 1-2.5 2.5h-10a2.5 2.5 0 0 1-2.5-2.5v-9.5Z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M13 4.9v5.35a1 1 0 0 0 1 1h5.1" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
    </svg>
  );
}

function ModelIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M12 2a5 5 0 1 0 0 10A5 5 0 0 0 12 2z" stroke="currentColor" strokeWidth="1.6" />
      <path d="M12 12v10M8 16l4 4 4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function GithubIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ExecutionIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <polygon points="5 3 19 12 5 21 5 3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" fill="currentColor" fillOpacity="0.12" />
    </svg>
  );
}

function InfoIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.7" />
      <path d="M12 8v1M12 11v5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function FolderIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
    </svg>
  );
}

function SectionHeader({ icon, title, description, trailing }) {
  return (
    <div className="section-header">
      <div className="section-header__icon">{icon}</div>
      <div className="section-header__text" style={{ flex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <strong>{title}</strong>
          {trailing}
        </div>
        {description ? <small>{description}</small> : null}
      </div>
    </div>
  );
}

/* ── Effort button ── */
function EffortButton({ effort, selected, onSelect, disabled, label, description }) {
  return (
    <button
      className={`choice-card ${selected ? "selected" : ""}`}
      onClick={() => onSelect(effort)}
      type="button"
      disabled={disabled}
    >
      <div className="choice-card__title">
        <strong>{label}</strong>
        <span style={{ fontSize: "11px", color: "var(--text-dim)" }}>{effort}</span>
      </div>
      <p style={{ fontSize: "12px" }}>{description}</p>
    </button>
  );
}

function effortDescription(modelLabel, effort, language) {
  if (String(modelLabel || "").trim().toLowerCase() === "auto") {
    if (language === "ko") {
      if (effort === AUTO_REASONING_OPTION) return "Codex 자동 라우팅의 기본 추론 설정을 사용합니다.";
      return `Codex 자동 라우팅을 유지하면서 추론은 ${autoRoutingPresetLabel(effort, language)}으로 고정합니다.`;
    }
    if (effort === AUTO_REASONING_OPTION) return "Use Codex automatic routing with its default reasoning setting.";
    return `Keep Codex automatic routing enabled and lock reasoning to ${autoRoutingPresetLabel(effort, language)}.`;
  }
  const reasoningLabel = reasoningEffortLabel(effort, language);
  if (language === "ko") {
    if (effort === AUTO_REASONING_OPTION) return `${modelLabel}의 기본 추론 수준을 사용합니다.`;
    return `${modelLabel}에 ${reasoningLabel} 추론 수준을 적용합니다.`;
  }
  if (effort === AUTO_REASONING_OPTION) return `Use ${modelLabel}'s default reasoning level.`;
  return `Use ${reasoningLabel} reasoning with ${modelLabel}.`;
}

function modelReasoningSummary(entry, language) {
  const supported = Array.isArray(entry?.supported_reasoning_efforts) ? entry.supported_reasoning_efforts : [];
  if (!supported.length) return "";
  const labels = supported.map((effort) => reasoningEffortLabel(effort, language)).join(", ");
  const defaultLabel = reasoningEffortLabel(entry?.default_reasoning_effort || supported[0] || "medium", language);
  if (language === "ko") return `지원 추론: ${labels} | 기본: ${defaultLabel}`;
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
  const planningModel = planningRuntime.model || planningRuntime.model_slug_input || defaultModelForRuntime(modelCatalog, planningRuntime) || selectedModel;
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
    : [{ model: selectedModel || "", display_name: selectedCatalogEntry?.display_name || selectedModel || t("common.none"), hidden: false }];
  const selectedModelOption =
    selectedModel && !allModels.some((item) => item?.model === selectedModel)
      ? { model: selectedModel, display_name: selectedCatalogEntry?.display_name || selectedModel || t("common.none"), hidden: false }
      : null;
  const recommendedModels = [...(selectedModelOption ? [selectedModelOption] : []), ...allModels.filter((item) => !item.hidden)];
  const additionalModels = allModels.filter((item) => item.hidden);

  function applyModelChange(nextModel, nextEffort = null) {
    const nextRuntime = applyConfigRuntimeModelSelection(runtime, scopedModelCatalog, nextModel, nextEffort);
    onChangeForm((current) => ({ ...current, runtime: nextRuntime }));
    if (typeof onChangeProgramSettings === "function") {
      onChangeProgramSettings((current) => syncProgramSettingsModel(current, nextRuntime));
    }
  }

  function applyRuntimePatch(runtimePatch) {
    const nextRuntime = { ...runtime, ...runtimePatch };
    onChangeForm((current) => ({ ...current, runtime: nextRuntime }));
    if (typeof onChangeProgramSettings === "function") {
      onChangeProgramSettings((current) => syncProgramSettingsModel(current, nextRuntime));
    }
  }

  const providerUnavailable = !providerAvailable(selectedProvider, codexStatus);
  const providerReason = providerStatusReason(selectedProvider, codexStatus);

  return (
    <section className="workspace-view">
      <div className="view-header">
        <div>
          <span className="eyebrow">{t("tab.config")}</span>
          <h2>{t("tab.config")}</h2>
        </div>
        <div className="field-row">
          <button
            className="toolbar-button toolbar-button--ghost"
            onClick={onArchiveProject}
            type="button"
            disabled={busy || !form.project_dir?.trim()}
          >
            {t("action.archiveProject")}
          </button>
          <button
            className="toolbar-button"
            onClick={onDeleteProject}
            type="button"
            disabled={busy || !form.project_dir?.trim()}
            style={{ color: "var(--danger)" }}
          >
            {t("action.deleteProject")}
          </button>
        </div>
      </div>

      {/* Project info summary card */}
      {form.display_name || form.project_dir ? (
        <div className="project-summary-card">
          <div className="field">
            <span>{t("config.projectName")}</span>
            <strong>{form.display_name || "—"}</strong>
          </div>
          <div className="field">
            <span>{t("common.branch")}</span>
            <strong>{form.branch || "—"}</strong>
          </div>
          <div className="field" style={{ gridColumn: "1 / -1" }}>
            <span>{t("config.workingDirectory")}</span>
            <p style={{ fontFamily: "monospace", fontSize: "12px" }}>{form.project_dir || "—"}</p>
          </div>
        </div>
      ) : null}

      <div className="form-layout">
        {/* ── Left column — Project & Execution ── */}
        <div className="form-section">
          {/* Project basics */}
          <div className="subsection">
            <SectionHeader
              icon={<ProjectIcon />}
              title={language === "ko" ? "프로젝트 기본 설정" : "Project Basics"}
              description={language === "ko" ? "이름, 디렉터리, 브랜치" : "Project name, directory and branch"}
            />

            <label className="field" style={{ marginTop: "4px" }}>
              <span>{t("config.projectName")}</span>
              <input
                value={form.display_name}
                onChange={(event) => onChangeForm((current) => ({ ...current, display_name: event.target.value }))}
                disabled={busy}
              />
            </label>

            <label className="field field--wide">
              <span>{t("config.workingDirectory")}</span>
              <div className="field-row">
                <input
                  value={form.project_dir}
                  onChange={(event) => onChangeForm((current) => ({ ...current, project_dir: event.target.value }))}
                  disabled={busy}
                />
                <button className="toolbar-button" onClick={onChooseDirectory} type="button" disabled={busy} style={{ flexShrink: 0 }}>
                  <FolderIcon />
                  {t("action.browse")}
                </button>
              </div>
            </label>

            <label className="field">
              <span>{t("common.branch")}</span>
              <input
                value={form.branch}
                onChange={(event) => onChangeForm((current) => ({ ...current, branch: event.target.value }))}
                disabled={busy}
              />
            </label>
          </div>

          {/* Execution params */}
          <div className="subsection">
            <SectionHeader
              icon={<ExecutionIcon />}
              title={language === "ko" ? "실행 설정" : "Execution Parameters"}
              description={language === "ko" ? "단계 수, 병렬 실행, 최적화" : "Step limits, parallel workers and optimization"}
            />

            <div className="choice-grid" style={{ marginTop: "4px" }}>
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
                      runtime: { ...current.runtime, workflow_mode: event.target.value },
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
                      runtime: { ...current.runtime, planning_effort: event.target.value },
                    }))
                  }
                  disabled={busy}
                >
                  {planningSupportedEfforts.map((effort) => (
                    <option key={effort} value={effort}>{reasoningEffortLabel(effort, language)}</option>
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
                      runtime: { ...current.runtime, ml_max_cycles: Math.max(1, Number.parseInt(event.target.value || "1", 10) || 1) },
                    }))
                  }
                  disabled={busy}
                />
              </label>

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

              <label className="field">
                <span>{t("field.optimizationMode")}</span>
                <select
                  value={runtime.optimization_mode || "light"}
                  onChange={(event) =>
                    onChangeForm((current) => ({
                      ...current,
                      runtime: { ...current.runtime, optimization_mode: event.target.value },
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

            <div style={{ display: "flex", flexDirection: "column", gap: "6px", marginTop: "4px" }}>
              <ToggleRow
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
                label={t("preset.auto")}
                hint={language === "ko" ? "병렬 작업자 수를 자동으로 결정" : "Automatically determine parallel worker count"}
                disabled={busy}
              />
              <ToggleRow
                checked={runtime.allow_background_queue ?? true}
                onChange={(event) =>
                  onChangeForm((current) => ({
                    ...current,
                    runtime: { ...current.runtime, allow_background_queue: event.target.checked },
                  }))
                }
                label={t("field.allowBackgroundQueue")}
                disabled={busy}
              />
              <ToggleRow
                checked={Boolean(runtime.use_fast_mode)}
                onChange={(event) =>
                  onChangeForm((current) => ({
                    ...current,
                    runtime: { ...current.runtime, use_fast_mode: event.target.checked },
                  }))
                }
                label={t("option.useFastMode")}
                hint={language === "ko" ? "더 빠른 응답을 위해 스트리밍 속도 증가" : "Increase streaming speed for faster output"}
                disabled={busy}
              />
            </div>
          </div>
        </div>

        {/* ── Right column — GitHub + Model ── */}
        <div className="form-section">
          {/* GitHub */}
          <div className="subsection">
            <SectionHeader
              icon={<GithubIcon />}
              title={t("config.githubConnection")}
              description={language === "ko" ? "원격 저장소 연결 방식" : "How this project connects to a remote repository"}
            />
            <div style={{ display: "flex", flexDirection: "column", gap: "6px", marginTop: "4px" }}>
              {[
                ["existing", t("config.useExistingOrigin")],
                ["manual", t("config.manualGithubUrl")],
                ["none", t("config.noGithubYet")],
              ].map(([value, label]) => (
                <label key={value} className="toggle-row">
                  <span className="toggle-row__label"><span>{label}</span></span>
                  <input
                    type="radio"
                    checked={form.github_mode === value}
                    onChange={() => onChangeForm((current) => ({ ...current, github_mode: value }))}
                    disabled={busy}
                    style={{ width: "auto", border: "none", background: "none", padding: 0, accentColor: "var(--info)" }}
                  />
                </label>
              ))}
            </div>
            {form.github_mode === "manual" ? (
              <label className="field field--wide" style={{ marginTop: "8px" }}>
                <span>{t("config.githubUrl")}</span>
                <input
                  value={form.origin_url}
                  onChange={(event) => onChangeForm((current) => ({ ...current, origin_url: event.target.value }))}
                  disabled={busy}
                  placeholder="https://github.com/org/repo"
                />
              </label>
            ) : null}
          </div>

          {/* Model selection */}
          <div className="subsection">
            <SectionHeader
              icon={<ModelIcon />}
              title={t("config.executionModel")}
              description={runtimeSummary(runtime, modelPresets, language, modelCatalog)}
            />

            {providerUnavailable && providerReason ? (
              <div className="info-callout info-callout--warning" style={{ marginTop: "4px" }}>
                <InfoIcon />
                <span>{providerReason}</span>
              </div>
            ) : null}

            <label className="field" style={{ marginTop: "4px" }}>
              <span>
                {selectedProvider === "ensemble"
                  ? (language === "ko" ? "Codex 모델" : "Codex Model")
                  : t("field.model")}
              </span>
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
                  placeholder={language === "ko" ? "모델 슬러그 입력" : "Enter model slug"}
                />
              )}
            </label>

            {!providerHasCatalog ? (
              <div className="info-callout" style={{ marginTop: "4px" }}>
                <InfoIcon />
                <span>{providerHasAutoModel ? t("config.providerPresetModelHint") : t("config.customProviderModelHint")}</span>
              </div>
            ) : null}

            {/* Effort buttons */}
            {supportedEfforts.length > 0 ? (
              <div style={{ marginTop: "8px" }}>
                <span style={{ fontSize: "11.5px", color: "var(--text-muted)", display: "block", marginBottom: "6px" }}>
                  {language === "ko" ? "추론 강도" : "Reasoning effort"}
                </span>
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
              </div>
            ) : null}

            {/* Ensemble sub-models */}
            {selectedProvider === "ensemble" ? (
              <div style={{ display: "flex", flexDirection: "column", gap: "10px", marginTop: "8px", borderTop: "1px solid var(--border)", paddingTop: "10px" }}>
                <label className="field">
                  <span>{language === "ko" ? "Gemini 모델" : "Gemini Model"}</span>
                  <select
                    value={ensembleGeminiModel}
                    onChange={(event) => applyRuntimePatch({ ensemble_gemini_model: event.target.value })}
                    disabled={busy}
                  >
                    {ensembleGeminiCatalog.map((item) => (
                      <option key={item.model} value={item.model}>{item.display_name || item.model}</option>
                    ))}
                  </select>
                  {modelReasoningSummary(ensembleGeminiEntry, language) ? (
                    <small className="field-hint">{modelReasoningSummary(ensembleGeminiEntry, language)}</small>
                  ) : null}
                </label>
                <label className="field">
                  <span>{language === "ko" ? "Claude 모델" : "Claude Model"}</span>
                  <select
                    value={ensembleClaudeModel}
                    onChange={(event) => applyRuntimePatch({ ensemble_claude_model: event.target.value })}
                    disabled={busy}
                  >
                    {ensembleClaudeCatalog.map((item) => (
                      <option key={item.model} value={item.model}>{item.display_name || item.model}</option>
                    ))}
                  </select>
                  {modelReasoningSummary(ensembleClaudeEntry, language) ? (
                    <small className="field-hint">{modelReasoningSummary(ensembleClaudeEntry, language)}</small>
                  ) : null}
                </label>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </section>
  );
}
