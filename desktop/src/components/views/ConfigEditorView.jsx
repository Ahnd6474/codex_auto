import { memo } from "react";
import { useI18n } from "../../i18n";
import {
  applyConfigRuntimeModelSelection,
  applyProviderDefaults,
  canEditProjectConfig,
  defaultProviderApiKeyEnv,
  defaultProviderBaseUrl,
  isActiveExecutionStatus,
  modelDisplayName,
  normalizeMemoryBudgetGiB,
  normalizedModelProvider,
  providerAvailable,
  providerCardLabel,
  providerStatusReason,
  reasoningEffortLabel,
  resolveRuntimeModelSelectionState,
} from "../../utils";

function ConfigHeaderIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"
        stroke="currentColor"
        strokeWidth="1.5"
      />
      <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

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

function ProjectIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M4.75 7.25A2.5 2.5 0 0 1 7.25 4.75h5.1c.66 0 1.3.26 1.77.73l5.15 5.15c.47.47.73 1.1.73 1.77v4.35a2.5 2.5 0 0 1-2.5 2.5h-10a2.5 2.5 0 0 1-2.5-2.5v-9.5Z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M13 4.9v5.35a1 1 0 0 0 1 1h5.1" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
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

const PROVIDER_CATEGORIES = [
  {
    key: "closed",
    label: "Closed",
    providers: ["openai", "claude", "gemini"],
  },
  {
    key: "opensource",
    label: "Open Source",
    providers: ["qwen_code", "deepseek", "kimi", "minimax", "glm", "openrouter", "opencdk"],
  },
  {
    key: "oss",
    label: "Local / OSS",
    providers: ["ollama", "local_openai", "oss"],
  },
  {
    key: "ensemble",
    label: "Ensemble",
    providers: ["ensemble"],
  },
];

function configEditorViewPropsEqual(previousProps, nextProps) {
  return (
    previousProps.form === nextProps.form
    && previousProps.modelPresets === nextProps.modelPresets
    && previousProps.modelCatalog === nextProps.modelCatalog
    && previousProps.codexStatus === nextProps.codexStatus
    && previousProps.busy === nextProps.busy
    && previousProps.activeJob === nextProps.activeJob
    && previousProps.projectStatus === nextProps.projectStatus
  );
}

export const ConfigEditorView = memo(function ConfigEditorView({
  form,
  modelPresets,
  modelCatalog,
  codexStatus,
  busy,
  activeJob,
  projectStatus = "",
  onChangeForm,
  onChangeProgramSettings,
  onSaveProject,
  onChooseDirectory,
  onArchiveProject,
  onDeleteProject,
}) {
  void modelPresets;
  void codexStatus;
  void onChangeProgramSettings;

  const runtime = form.runtime || {};
  const { language, t } = useI18n();
  const executionLocked = !canEditProjectConfig(projectStatus, activeJob?.status || "");
  const allowSafeRuntimeEdits = isActiveExecutionStatus(projectStatus) || isActiveExecutionStatus(activeJob?.status || "");
  const autoParallelWorkers = String(runtime.parallel_worker_mode || "auto").trim().toLowerCase() !== "manual";
  const selectedProvider = normalizedModelProvider(runtime);
  const selectionState = resolveRuntimeModelSelectionState(runtime, modelCatalog, "", null, codexStatus);
  const visibleModels = selectionState.visibleModels;
  const visibleModelGroups = selectionState.visibleModelGroups;
  const selectedReasoning = selectionState.selectedReasoning;
  const reasoningOptions = selectionState.reasoningOptions;
  const selectedExecutionModel = selectionState.selectedExecutionModel || "";
  const selectedExecutionModelVisible = selectionState.selectedExecutionModelVisible;
  const activeCategory = PROVIDER_CATEGORIES.find((category) => (
    category.providers.some((provider) => provider === selectedProvider)
  ))?.key || "closed";
  const activeCategoryConfig = PROVIDER_CATEGORIES.find((category) => category.key === activeCategory) || PROVIDER_CATEGORIES[0];
  const providerUnavailable = !providerAvailable(selectedProvider, codexStatus);
  const providerReason = providerStatusReason(selectedProvider, codexStatus);
  const aiModelSection = (
    <div className="subsection">
      <SectionHeader
        icon={<ExecutionIcon />}
        title={language === "ko" ? "AI 모델" : "AI Model"}
        description={language === "ko" ? "이 프로젝트에서 사용할 모델과 추론 수준을 설정합니다." : "Model and reasoning used by this project"}
      />

      <div style={{ marginTop: "10px" }}>
        <span style={{ fontSize: "11.5px", color: "var(--text-muted)", display: "block", marginBottom: "6px" }}>
          {t("field.modelProvider")}
        </span>

        <div className="provider-category-tabs">
          {PROVIDER_CATEGORIES.map((category) => (
            <button
              key={category.key}
              className={`provider-cat-tab ${activeCategory === category.key ? "active" : ""}`}
              onClick={() => {
                const firstProvider = category.providers[0] || "openai";
                onChangeForm((current) => ({
                  ...current,
                  runtime: applyProviderDefaults(current.runtime || {}, firstProvider),
                }));
              }}
              type="button"
              disabled={executionLocked}
            >
              {category.label}
            </button>
          ))}
        </div>

        {activeCategory !== "ensemble" ? (
          <div className="provider-sub-grid" style={{ marginTop: "8px" }}>
            {activeCategoryConfig.providers.map((value) => {
              const label = providerCardLabel(value, runtime?.local_model_provider);
              const installed = providerAvailable(value, codexStatus);
              return (
                <button
                  key={value}
                  className={`provider-sub-card ${selectedProvider === value ? "active" : ""}`}
                  onClick={() =>
                    onChangeForm((current) => ({
                      ...current,
                      runtime: applyProviderDefaults(current.runtime || {}, value),
                    }))
                  }
                  type="button"
                  disabled={executionLocked}
                  title={!installed ? providerStatusReason(value, codexStatus) : undefined}
                >
                  <span className="provider-sub-card__name">{label}</span>
                  {!installed ? <span className="provider-sub-card__badge">not installed</span> : null}
                </button>
              );
            })}
          </div>
        ) : (
          <div className="provider-ensemble-info" style={{ marginTop: "8px" }}>
            <div className="provider-ensemble-badge">
              <span>GPT</span>
              <span className="provider-ensemble-plus">+</span>
              <span>Claude</span>
            </div>
            <p style={{ fontSize: "12px", color: "var(--text-muted)", margin: "6px 0 0" }}>
              {language === "ko"
                ? "GPT는 계획과 실행을 맡고, Claude는 세부 단계들을 처리합니다."
                : "GPT handles planning and execution. Claude handles specific steps."}
            </p>
          </div>
        )}

        {providerUnavailable && providerReason ? (
          <div className="info-callout info-callout--warning" style={{ marginTop: "8px" }}>
            <InfoIcon />
            <span>{providerReason}</span>
          </div>
        ) : null}
      </div>

      {selectedProvider === "oss" ? (
        <label className="field">
          <span>{t("field.localProvider")}</span>
          <select
            value={runtime.local_model_provider || "ollama"}
            onChange={(event) =>
              onChangeForm((current) => ({
                ...current,
                runtime: { ...(current.runtime || {}), local_model_provider: event.target.value },
              }))
            }
            disabled={executionLocked}
          >
            <option value="ollama">{t("option.localProviderOllama")}</option>
            <option value="lmstudio">{t("option.localProviderLmStudio")}</option>
          </select>
        </label>
      ) : null}

      {selectedProvider !== "oss" && selectedProvider !== "ollama" ? (
        <label className="field">
          <span>{t("field.providerBaseUrl")}</span>
          <input
            value={runtime.provider_base_url || defaultProviderBaseUrl(runtime.model_provider)}
            onChange={(event) =>
              onChangeForm((current) => ({
                ...current,
                runtime: { ...(current.runtime || {}), provider_base_url: event.target.value },
              }))
            }
            disabled={executionLocked}
          />
        </label>
      ) : null}

      {selectedProvider !== "oss" && selectedProvider !== "ollama" ? (
        <label className="field">
          <span>{t("field.providerApiKeyEnv")}</span>
          <input
            value={runtime.provider_api_key_env || defaultProviderApiKeyEnv(runtime.model_provider)}
            onChange={(event) =>
              onChangeForm((current) => ({
                ...current,
                runtime: { ...(current.runtime || {}), provider_api_key_env: event.target.value },
              }))
            }
            disabled={executionLocked}
          />
          <small className="field-hint">
            {language === "ko" ? "API 키가 들어 있는 환경 변수 이름입니다." : "The environment variable that holds your API key."}
          </small>
        </label>
      ) : null}
      {visibleModels.length || selectedExecutionModel ? (
        <label className="field field--wide" style={{ marginTop: "4px" }}>
          <span>{language === "ko" ? "실행 모델" : "Execution model"}</span>
          <select
            value={selectedExecutionModel}
            onChange={(event) =>
              onChangeForm((current) => ({
                ...current,
                runtime: applyConfigRuntimeModelSelection(
                  current.runtime || {},
                  modelCatalog,
                  event.target.value,
                  null,
                  codexStatus,
                ),
              }))
            }
            disabled={executionLocked}
          >
            {selectedExecutionModel && !selectedExecutionModelVisible ? (
              <option value={selectedExecutionModel}>
                {modelDisplayName(modelCatalog, selectedExecutionModel) || selectedExecutionModel}
              </option>
            ) : null}
            {visibleModelGroups.map((group) => (
              <optgroup key={group.key} label={group.label}>
                {group.options.map((item) => (
                  <option key={item.value} value={item.model}>
                    {item.label}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
          <small className="field-hint">
            {language === "ko"
              ? "계획 생성과 실제 블록 실행 모두 이 모델을 기본으로 사용합니다. 블록별 모델 지정이 있으면 그 설정이 우선합니다."
              : "Used as the default model for both planning and block execution. Per-block model overrides still take precedence."}
          </small>
        </label>
      ) : null}

      <label className="field field--wide" style={{ marginTop: "4px" }}>
        <span>{language === "ko" ? "AI 추론" : "AI Reasoning"}</span>
        <select
          value={selectedReasoning}
          onChange={(event) =>
            onChangeForm((current) => ({
              ...current,
              runtime: applyConfigRuntimeModelSelection(
                current.runtime || {},
                modelCatalog,
                selectedExecutionModel,
                event.target.value,
                codexStatus,
              ),
            }))
          }
          disabled={executionLocked}
        >
          {reasoningOptions.map((effort) => (
            <option key={effort} value={effort}>
              {reasoningEffortLabel(effort, language)}
            </option>
          ))}
        </select>
      </label>
    </div>
  );

  return (
    <section className="workspace-view">
      <div className="view-header">
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <div className="view-header-icon">
            <ConfigHeaderIcon />
          </div>
          <div>
            <span className="eyebrow">{t("tab.config")}</span>
            <h2>{form.display_name || t("tab.config")}</h2>
          </div>
        </div>
        <div className="field-row">
          <button
            className="toolbar-button toolbar-button--accent"
            onClick={onSaveProject}
            type="button"
            disabled={!form.project_dir?.trim() || (executionLocked && !allowSafeRuntimeEdits)}
          >
            {t("action.saveConfiguration")}
          </button>
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
            disabled={busy || !form.project_dir?.trim() || executionLocked}
            style={{ color: executionLocked ? "var(--text-dim)" : "var(--danger)" }}
            title={executionLocked ? (language === "ko" ? "실행 중인 프로젝트는 삭제할 수 없습니다." : "Cannot delete a running project.") : undefined}
          >
            {t("action.deleteProject")}
          </button>
        </div>
      </div>

      {form.display_name || form.project_dir ? (
        <div className="project-summary-card">
          <div className="field">
            <span>{t("config.projectName")}</span>
            <strong>{form.display_name || "-"}</strong>
          </div>
          <div className="field">
            <span>{t("common.branch")}</span>
            <strong>{form.branch || "-"}</strong>
          </div>
          <div className="field" style={{ gridColumn: "1 / -1" }}>
            <span>{t("config.workingDirectory")}</span>
            <p style={{ fontFamily: "monospace", fontSize: "12px" }}>{form.project_dir || "-"}</p>
          </div>
        </div>
      ) : null}

      <div className="form-layout">
        {aiModelSection}
        <div className="form-section">
          <div className="subsection">
            <SectionHeader
              icon={<ProjectIcon />}
              title="Project Basics"
              description="Project name, directory and branch"
            />

            <label className="field" style={{ marginTop: "4px" }}>
              <span>{t("config.projectName")}</span>
              <input
                value={form.display_name}
                onChange={(event) => onChangeForm((current) => ({ ...current, display_name: event.target.value }))}
                disabled={executionLocked}
              />
            </label>

            <label className="field field--wide">
              <span>{t("config.workingDirectory")}</span>
              <div className="field-row">
                <input
                  value={form.project_dir}
                  onChange={(event) => onChangeForm((current) => ({ ...current, project_dir: event.target.value }))}
                  disabled={executionLocked}
                />
                <button className="toolbar-button" onClick={onChooseDirectory} type="button" disabled={executionLocked} style={{ flexShrink: 0 }}>
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
                disabled={executionLocked}
              />
            </label>
          </div>

          <div className="subsection">
            <SectionHeader
              icon={<ExecutionIcon />}
              title="Execution Parameters"
              description="Step limits, parallel workers and optimization"
            />

            {executionLocked ? (
              <div className="info-callout" style={{ marginTop: "8px" }}>
                <InfoIcon />
                <span>
                  {language === "ko"
                    ? "실행 중에도 체크포인트와 보고서 출력 같은 안전한 런타임 설정은 저장할 수 있습니다."
                    : "Safe runtime settings like checkpoints and report output can still be saved while a run is active."}
                </span>
              </div>
            ) : null}

            <div className="choice-grid" style={{ marginTop: "4px" }}>
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
                  disabled={executionLocked}
                >
                  <option value="standard">{t("option.workflowStandard")}</option>
                  <option value="ml">{t("option.workflowML")}</option>
                </select>
              </label>

              {runtime.workflow_mode === "ml" ? (
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
                    disabled={executionLocked}
                  />
                  <small style={{ fontSize: "11px", color: "var(--text-dim)" }}>
                    {language === "ko" ? "ML 최대 반복 횟수" : "Max ML experiment iterations"}
                  </small>
                </label>
              ) : (
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
                    disabled={executionLocked}
                  />
                  <small style={{ fontSize: "11px", color: "var(--text-dim)" }}>
                    "Maximum steps in execution plan"
                  </small>
                </label>
              )}

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
                  disabled={executionLocked || autoParallelWorkers}
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
                  disabled={executionLocked}
                />
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
                      runtime: {
                        ...current.runtime,
                        checkpoint_interval_blocks: Math.max(1, Number.parseInt(event.target.value || "1", 10) || 1),
                      },
                    }))
                  }
                  disabled={executionLocked && !allowSafeRuntimeEdits}
                />
              </label>

              <label className="field">
                <span>{t("field.optimizationMode")}</span>
                <select
                  value={runtime.optimization_mode || "off"}
                  onChange={(event) =>
                    onChangeForm((current) => ({
                      ...current,
                      runtime: { ...current.runtime, optimization_mode: event.target.value },
                    }))
                  }
                  disabled={executionLocked}
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
                hint={language === "ko" ? "자원에 따라 작업자 수를 자동으로 조정합니다." : "Automatically determine parallel worker count"}
                disabled={executionLocked}
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
                disabled={executionLocked}
              />
              <ToggleRow
                checked={Boolean(runtime.require_checkpoint_approval)}
                onChange={(event) =>
                  onChangeForm((current) => ({
                    ...current,
                    runtime: { ...current.runtime, require_checkpoint_approval: event.target.checked },
                  }))
                }
                label={t("option.requireCheckpointApproval")}
                hint={language === "ko" ? "체크포인트에 도달하면 검토를 위해 일시 중지합니다." : "Pause for review when a checkpoint is reached."}
                disabled={executionLocked && !allowSafeRuntimeEdits}
              />
              <label className="field">
                <span>{language === "ko" ? "계획 모드" : "Planning mode"}</span>
                <select
                  value={runtime.planning_mode || (runtime.use_fast_mode ? "compact" : "full")}
                  onChange={(event) =>
                    onChangeForm((current) => ({
                      ...current,
                      runtime: { ...current.runtime, planning_mode: event.target.value },
                    }))
                  }
                  disabled={executionLocked}
                >
                  <option value="no">no planning</option>
                  <option value="compact">compact planning</option>
                  <option value="full">full planning</option>
                </select>
                <small style={{ fontSize: "11px", color: "var(--text-dim)" }}>
                  {language === "ko"
                    ? "no는 planner를 생략하고 바로 실행 블록을 만들고, compact는 Planner A를 건너뛰며, full은 Planner A와 B를 모두 사용합니다."
                    : "no skips planners and creates one execution block, compact skips Planner A, and full runs Planner A and B."}
                </small>
              </label>
            </div>
          </div>
        </div>

        <div className="form-section">
          <div className="subsection">
            <SectionHeader
              icon={<GithubIcon />}
              title={t("config.githubConnection")}
              description={language === "ko" ? "이 프로젝트가 원격 저장소와 연결되는 방식" : "How this project connects to a remote repository"}
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
                    disabled={executionLocked}
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
                  disabled={executionLocked}
                  placeholder="https://github.com/org/repo"
                />
              </label>
            ) : null}
          </div>
        </div>
      </div>
    </section>
  );
}, configEditorViewPropsEqual);

