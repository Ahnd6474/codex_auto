import { memo, startTransition, useEffect, useRef, useState } from "react";
import { useI18n } from "../../i18n";
import {
  applyConfigRuntimeModelSelection,
  applyProviderDefaults,
  cloneValue,
  configReasoningOptions,
  defaultCodexPath,
  defaultProviderApiKeyEnv,
  defaultProviderBaseUrl,
  defaultModelForRuntime,
  filterModelCatalogByProvider,
  normalizeMemoryBudgetGiB,
  normalizeDashboardVisibility,
  normalizedModelProvider,
  providerAvailable,
  providerUsable,
  providerStatusReason,
  programSettingsEqual,
  programSettingsAllowsModelSlugInput,
  reasoningEffortLabel,
  selectedConfigReasoning,
} from "../../utils";

/* ── Reusable toggle row ── */
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
function AppIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <rect x="3" y="3" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
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

function DashboardIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M18 20V10M12 20V4M6 20v-6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function ShareIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <circle cx="18" cy="5" r="2.5" stroke="currentColor" strokeWidth="1.7" />
      <circle cx="6" cy="12" r="2.5" stroke="currentColor" strokeWidth="1.7" />
      <circle cx="18" cy="19" r="2.5" stroke="currentColor" strokeWidth="1.7" />
      <path d="M8.59 13.51l6.83 3.98M15.41 6.51l-6.82 3.98" stroke="currentColor" strokeWidth="1.7" />
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

function CopyIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" strokeWidth="1.7" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" stroke="currentColor" strokeWidth="1.7" />
    </svg>
  );
}

function SectionHeader({ icon, title, description, badge }) {
  return (
    <div className="section-header">
      <div className="section-header__icon">{icon}</div>
      <div className="section-header__text" style={{ flex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <strong>{title}</strong>
          {badge}
        </div>
        {description ? <small>{description}</small> : null}
      </div>
    </div>
  );
}

const SETTINGS_TAB_KEYS = new Set(["app", "execution", "dashboard", "share"]);
const PROVIDER_CATEGORIES = [
  {
    key: "closed",
    label_ko: "클로즈드",
    label_en: "Closed",
    providers: [
      { value: "openai", label: "OpenAI" },
      { value: "claude", label: "Claude" },
      { value: "gemini", label: "Gemini" },
    ],
  },
  {
    key: "opensource",
    label_ko: "오픈소스",
    label_en: "OpenSource",
    providers: [
      { value: "qwen_code", label: "Qwen Code" },
      { value: "deepseek", label: "DeepSeek" },
      { value: "kimi", label: "Kimi" },
      { value: "minimax", label: "MiniMax" },
      { value: "glm", label: "GLM" },
      { value: "openrouter", label: "OpenRouter" },
      { value: "opencdk", label: "OpenCDK" },
    ],
  },
  {
    key: "oss",
    label_ko: "OSS",
    label_en: "OSS",
    providers: [
      { value: "ollama", label: "Ollama" },
      { value: "local_openai", label: "Local OpenAI" },
      { value: "oss", label: "LM Studio / OSS" },
    ],
  },
  {
    key: "ensemble",
    label_ko: "앙상블",
    label_en: "Ensemble",
    providers: [
      { value: "ensemble", label: "Claude + GPT Ensemble", label_ko: "Claude + GPT 앙상블" },
    ],
  },
];

function cloneSettings(value) {
  return cloneValue(value && typeof value === "object" ? value : {});
}

function sameSettingsSnapshot(left, right) {
  return programSettingsEqual(left, right);
}

function appSettingsViewPropsEqual(previousProps, nextProps) {
  return (
    programSettingsEqual(previousProps.settings, nextProps.settings)
    && previousProps.codexStatus === nextProps.codexStatus
    && previousProps.shareSettings === nextProps.shareSettings
    && previousProps.shareDetail === nextProps.shareDetail
    && previousProps.busy === nextProps.busy
    && previousProps.shareBusy === nextProps.shareBusy
    && previousProps.initialSettingsTab === nextProps.initialSettingsTab
  );
}

export const AppSettingsView = memo(function AppSettingsView({
  settings,
  codexStatus,
  modelCatalog = [],
  shareSettings,
  shareDetail,
  busy,
  shareBusy = false,
  initialSettingsTab = "app",
  onChangeSettings,
  onGenerateShareLink,
  onCopyShareLink,
  onRevokeShareLink,
  onChangeShareSettings,
}) {
  const [settingsTab, setSettingsTab] = useState(() => (
    SETTINGS_TAB_KEYS.has(initialSettingsTab) ? initialSettingsTab : "app"
  ));
  const { language, languageOptions, setLanguage, t } = useI18n();
  const [draftSettings, setDraftSettings] = useState(() => cloneSettings(settings));
  const [localDirty, setLocalDirty] = useState(false);
  const lastIncomingSettingsRef = useRef(cloneSettings(settings));
  const lastOutgoingSettingsRef = useRef(cloneSettings(settings));
  const planningReasoningLabel = language === "ko" ? "계획 추론" : "Planning Reasoning";
  const settingsTabs = [
    { key: "app", label: language === "ko" ? "애플리케이션" : "Application" },
    { key: "execution", label: language === "ko" ? "실행 설정" : "Execution" },
    { key: "dashboard", label: language === "ko" ? "대시보드" : "Dashboard" },
    { key: "share", label: language === "ko" ? "공유" : "Share" },
  ];
  const activeShare = shareDetail?.active_session || shareDetail?.project_active_session || null;
  const shareServer = shareDetail?.server || null;
  const selectedProvider = normalizedModelProvider(draftSettings);
  const scopedModelCatalog = filterModelCatalogByProvider(modelCatalog, draftSettings);
  const visibleModels = scopedModelCatalog.filter((item) => item && item.model && !item.hidden && String(item.model).trim().toLowerCase() !== "auto");
  const selectedModel = String(draftSettings.model_slug_input || draftSettings.model || defaultModelForRuntime(modelCatalog, draftSettings) || "").trim();
  const reasoningOptions = configReasoningOptions(scopedModelCatalog, selectedModel, draftSettings.effort || "medium");
  const selectedReasoning = selectedConfigReasoning(scopedModelCatalog, draftSettings);
  const dashboardVisibility = normalizeDashboardVisibility(draftSettings?.dashboard_visibility);
  const runtimeBusy = busy;
  const autoParallelWorkers = String(draftSettings?.parallel_worker_mode || "auto").trim().toLowerCase() !== "manual";

  useEffect(() => {
    const nextSettings = cloneSettings(settings);
    if (sameSettingsSnapshot(nextSettings, lastOutgoingSettingsRef.current)) {
      lastIncomingSettingsRef.current = nextSettings;
      return;
    }
    if (!sameSettingsSnapshot(nextSettings, lastIncomingSettingsRef.current)) {
      lastIncomingSettingsRef.current = nextSettings;
      setDraftSettings(nextSettings);
      setLocalDirty(false);
    }
  }, [settings]);

  useEffect(() => {
    if (!localDirty || typeof onChangeSettings !== "function") {
      return;
    }
    const nextSettings = cloneSettings(draftSettings);
    lastOutgoingSettingsRef.current = nextSettings;
    startTransition(() => {
      onChangeSettings(nextSettings);
    });
  }, [draftSettings, localDirty, onChangeSettings]);

  function updateDraftSettings(updater) {
    setDraftSettings((current) => {
      const nextDraft = typeof updater === "function" ? updater(current) : updater;
      return cloneSettings(nextDraft);
    });
    setLocalDirty(true);
  }

  function categoryForProvider(provider) {
    for (const cat of PROVIDER_CATEGORIES) {
      if (cat.providers.some((p) => p.value === provider)) return cat.key;
    }
    return "closed";
  }

  const activeCategory = categoryForProvider(selectedProvider);
  const activeCategoryConfig = PROVIDER_CATEGORIES.find((c) => c.key === activeCategory);

  const dashboardOptions = [
    ["status", t("common.status")],
    ["remaining_steps", t("dashboard.remainingSteps")],
    ["checkpoint_pending", t("dashboard.checkpointPending")],
    ["estimated_remaining", t("dashboard.estimatedRemaining")],
    ["runtime_card", t("dashboard.runtime")],
    ["rate_limit_window_5h", t("usage.window5h")],
    ["rate_limit_window_7d", t("usage.window7d")],
    ["rate_limit_codex_spark", t("usage.codexSpark")],
    ["input_tokens", t("dashboard.inputTokens")],
    ["output_tokens", t("dashboard.outputTokens")],
    ["estimated_cost", t("dashboard.estimatedCost")],
    ["actual_cost", t("dashboard.actualCost")],
    ["codex_plan", t("dashboard.codexPlan")],
    ["codex_usage_card", t("dashboard.codexUsage")],
    ["word_report_card", t("reports.closeoutReport")],
  ];

  const providerUnavailable = !providerUsable(selectedProvider, codexStatus);
  const providerReason = providerStatusReason(selectedProvider, codexStatus);

  return (
    <section className="workspace-view">
      <div className="view-header">
        <div>
          <span className="eyebrow">{t("tab.programSettings")}</span>
          <h2>{t("tab.programSettings")}</h2>
          <p style={{ color: "var(--text-muted)", fontSize: "13px" }}>{t("settings.programSettingsDescription")}</p>
        </div>
      </div>

      {/* ── Sub-category tab bar ── */}
      <div className="settings-subtabs">
        {settingsTabs.map((tab) => (
          <button
            key={tab.key}
            className={`settings-subtab ${settingsTab === tab.key ? "settings-subtab--active" : ""}`}
            onClick={() => setSettingsTab(tab.key)}
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="form-layout">

        {/* ── Application tab ── */}
        {settingsTab === "app" ? (
        <div className="form-section" style={{ gridColumn: "1 / -1" }}>
          <div className="subsection">
            <SectionHeader
              icon={<AppIcon />}
              title={t("settings.application")}
              description={language === "ko" ? "언어, 테마, 개발자 모드" : "Language, theme and developer options"}
            />

            <label className="field" style={{ marginTop: "4px" }}>
              <span>{t("common.language")}</span>
              <select value={language} onChange={(event) => setLanguage(event.target.value)}>
                {languageOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>

            <ToggleRow
              checked={draftSettings.ui_theme === "light"}
              onChange={(event) => updateDraftSettings((current) => ({ ...current, ui_theme: event.target.checked ? "light" : "dark" }))}
              label={t("option.lightMode")}
              hint={language === "ko" ? "밝은 배경의 라이트 테마로 전환" : "Switch to light background theme"}
            />

            <ToggleRow
              checked={Boolean(draftSettings.compact_mode)}
              onChange={(event) => updateDraftSettings((current) => ({ ...current, compact_mode: event.target.checked }))}
              label={language === "ko" ? "컴팩트 모드" : "Compact Mode"}
              hint={language === "ko" ? "패널 크기와 여백을 줄여 정보 밀도 증가" : "Reduce panel sizes and padding for higher information density"}
            />

            <ToggleRow
              checked={Boolean(draftSettings.developer_mode)}
              onChange={(event) =>
                updateDraftSettings((current) => ({
                  ...current,
                  developer_mode: event.target.checked,
                  save_project_logs: event.target.checked ? Boolean(current.save_project_logs) : false,
                }))
              }
              label={t("option.developerMode")}
              hint={language === "ko" ? "리포트 탭 및 추가 디버그 정보 표시" : "Show reports tab and extra debug info"}
            />

            {Boolean(draftSettings.developer_mode) ? (
              <ToggleRow
                checked={Boolean(draftSettings.save_project_logs)}
                onChange={(event) => updateDraftSettings((current) => ({ ...current, save_project_logs: event.target.checked }))}
                label={t("option.saveProjectLogs")}
                hint={language === "ko" ? "각 단계의 실행 로그를 파일로 저장" : "Persist execution logs to disk for each step"}
              />
            ) : null}
          </div>
        </div>
        ) : null}

        {/* ── Dashboard tab ── */}
        {settingsTab === "dashboard" ? (
        <div className="form-section" style={{ gridColumn: "1 / -1" }}>
          <div className="subsection">
            <SectionHeader
              icon={<DashboardIcon />}
              title={t("settings.dashboardPreferences")}
              description={language === "ko" ? "대시보드에 표시할 지표 선택" : "Choose which metrics appear on the dashboard"}
            />

            <div className="toggle-grid" style={{ marginTop: "4px" }}>
              {dashboardOptions.map(([key, label]) => (
                <label key={key} className="toggle-row" style={{ padding: "7px 10px" }}>
                  <span className="toggle-row__label">
                    <span style={{ fontSize: "12px" }}>{label}</span>
                  </span>
                  <span className={`toggle-track ${Boolean(dashboardVisibility[key]) ? "toggle-track--on" : ""}`} style={{ width: "30px", height: "17px" }}>
                    <input
                      type="checkbox"
                      checked={Boolean(dashboardVisibility[key])}
                      onChange={(event) =>
                        updateDraftSettings((current) => ({
                          ...current,
                          dashboard_visibility: {
                            ...normalizeDashboardVisibility(current?.dashboard_visibility),
                            [key]: event.target.checked,
                          },
                        }))
                      }
                    />
                    <span className="toggle-thumb" style={{ width: "10px", height: "10px", left: Boolean(dashboardVisibility[key]) ? "calc(100% - 12px)" : "2px" }} />
                  </span>
                </label>
              ))}
            </div>
          </div>
        </div>
        ) : null}

        {/* ── Execution tab ── */}
        {settingsTab === "execution" ? (
        <div className="form-section" style={{ gridColumn: "1 / -1" }}>
          <div className="subsection">
            <SectionHeader
              icon={<ExecutionIcon />}
              title={t("settings.executionDefaults")}
              description={language === "ko" ? "AI 모델, 병렬 실행, 체크포인트 설정" : "AI model provider, parallel execution and checkpoint settings"}
            />

            {/* Provider category selector */}
            <div style={{ marginTop: "10px" }}>
              <span style={{ fontSize: "11.5px", color: "var(--text-muted)", display: "block", marginBottom: "6px" }}>
                {t("field.modelProvider")}
              </span>

              {/* Category tabs */}
              <div className="provider-category-tabs">
                {PROVIDER_CATEGORIES.map((cat) => (
                      <button
                        key={cat.key}
                        className={`provider-cat-tab ${activeCategory === cat.key ? "active" : ""}`}
                        onClick={() => {
                          const first = cat.providers[0].value;
                          updateDraftSettings((current) => applyProviderDefaults(current, first));
                        }}
                    type="button"
                    disabled={runtimeBusy}
                  >
                    {language === "ko" ? cat.label_ko : cat.label_en}
                  </button>
                ))}
              </div>

              {/* Sub-provider buttons */}
              {activeCategory !== "ensemble" ? (
                <div className="provider-sub-grid" style={{ marginTop: "8px" }}>
                  {activeCategoryConfig.providers.map(({ value, label, label_ko: labelKo }) => {
                    const installed = providerAvailable(value, codexStatus);
                    const displayLabel = language === "ko" ? (labelKo || label) : label;
                    return (
                      <button
                        key={value}
                        className={`provider-sub-card ${selectedProvider === value ? "active" : ""}`}
                        onClick={() => updateDraftSettings((current) => applyProviderDefaults(current, value))}
                        type="button"
                        disabled={runtimeBusy}
                        title={!installed ? providerStatusReason(value, codexStatus) : undefined}
                      >
                        <span className="provider-sub-card__name">{displayLabel}</span>
                        {!installed ? (
                          <span className="provider-sub-card__badge">
                            {language === "ko" ? "미설치" : "not installed"}
                          </span>
                        ) : null}
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
                      ? "GPT가 계획·실행을 맡고, Claude가 특정 단계를 처리합니다."
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
                  value={draftSettings.local_model_provider || "ollama"}
                  onChange={(event) => updateDraftSettings((current) => ({ ...current, local_model_provider: event.target.value }))}
                  disabled={runtimeBusy}
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
                  value={draftSettings.provider_base_url || defaultProviderBaseUrl(draftSettings.model_provider)}
                  onChange={(event) => updateDraftSettings((current) => ({ ...current, provider_base_url: event.target.value }))}
                  disabled={runtimeBusy}
                />
              </label>
            ) : null}

            {selectedProvider !== "oss" && selectedProvider !== "ollama" ? (
              <label className="field">
                <span>{t("field.providerApiKeyEnv")}</span>
                <input
                  value={draftSettings.provider_api_key_env || defaultProviderApiKeyEnv(draftSettings.model_provider)}
                  onChange={(event) => updateDraftSettings((current) => ({ ...current, provider_api_key_env: event.target.value }))}
                  disabled={runtimeBusy}
                />
                <small className="field-hint">
                  {language === "ko" ? "해당 환경 변수에 API 키가 저장되어 있어야 합니다." : "The environment variable that holds your API key."}
                </small>
              </label>
            ) : null}

            {programSettingsAllowsModelSlugInput(selectedProvider) ? (
              <>
                {visibleModels.length ? (
                  <label className="field">
                    <span>{t("field.model")}</span>
                    <select
                      value={selectedModel}
                      onChange={(event) => updateDraftSettings((current) => applyConfigRuntimeModelSelection(current, scopedModelCatalog, event.target.value))}
                      disabled={runtimeBusy}
                    >
                      {visibleModels.map((item) => (
                        <option key={item.model} value={item.model}>
                          {item.display_name || item.model}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : null}

                <label className="field">
                  <span>{t("field.customModelSlug")}</span>
                  <input
                    value={draftSettings.model_slug_input || draftSettings.model || ""}
                    onChange={(event) =>
                      updateDraftSettings((current) => applyConfigRuntimeModelSelection(current, scopedModelCatalog, event.target.value))
                    }
                    disabled={runtimeBusy}
                  />
                </label>
              </>
            ) : null}

            {/* 2-col grid for smaller fields */}
            <div className="choice-grid">
              <label className="field">
                <span>{t("field.approvalMode")}</span>
                <select
                  value={draftSettings.approval_mode || "never"}
                  onChange={(event) => updateDraftSettings((current) => ({ ...current, approval_mode: event.target.value }))}
                  disabled={runtimeBusy}
                >
                  <option value="never">never</option>
                  <option value="on-failure">on-failure</option>
                  <option value="untrusted">untrusted</option>
                </select>
              </label>

              <label className="field">
                <span>{t("field.sandboxMode")}</span>
                <select
                  value={draftSettings.sandbox_mode || "danger-full-access"}
                  onChange={(event) => updateDraftSettings((current) => ({ ...current, sandbox_mode: event.target.value }))}
                  disabled={runtimeBusy}
                >
                  <option value="danger-full-access">danger-full-access</option>
                  <option value="workspace-write">workspace-write</option>
                  <option value="read-only">read-only</option>
                </select>
              </label>

              <label className="field">
                <span>{t("field.workflowMode")}</span>
                <select
                  value={draftSettings.workflow_mode || "standard"}
                  onChange={(event) => updateDraftSettings((current) => ({ ...current, workflow_mode: event.target.value }))}
                  disabled={busy}
                >
                  <option value="standard">{t("option.workflowStandard")}</option>
                  <option value="ml">{t("option.workflowML")}</option>
                </select>
              </label>

              <label className="field">
                <span>{t("field.gptReasoning")}</span>
                <select
                  value={selectedReasoning}
                  onChange={(event) =>
                    updateDraftSettings((current) => applyConfigRuntimeModelSelection(current, scopedModelCatalog, selectedModel, event.target.value))
                  }
                  disabled={busy}
                >
                  {reasoningOptions.map((effort) => (
                    <option key={effort} value={effort}>
                      {reasoningEffortLabel(effort, language)}
                    </option>
                  ))}
                </select>
              </label>

              <label className="field">
                <span>{planningReasoningLabel}</span>
                <select
                  value={draftSettings.planning_effort || draftSettings.effort || "medium"}
                  onChange={(event) => updateDraftSettings((current) => ({ ...current, planning_effort: event.target.value }))}
                  disabled={busy}
                >
                  {reasoningOptions.filter((effort) => effort !== "auto").map((effort) => (
                    <option key={effort} value={effort}>
                      {reasoningEffortLabel(effort, language)}
                    </option>
                  ))}
                </select>
              </label>

              <label className="field">
                <span>{t("field.checkpointInterval")}</span>
                <input
                  type="number"
                  min="1"
                  value={draftSettings.checkpoint_interval_blocks || 1}
                  onChange={(event) =>
                    updateDraftSettings((current) => ({
                      ...current,
                      checkpoint_interval_blocks: Math.max(1, Number.parseInt(event.target.value || "1", 10) || 1),
                    }))
                  }
                  disabled={runtimeBusy}
                />
              </label>

              <label className="field">
                <span>{t("field.mlMaxCycles")}</span>
                <input
                  type="number"
                  min="1"
                  value={draftSettings.ml_max_cycles || 3}
                  onChange={(event) =>
                    updateDraftSettings((current) => ({
                      ...current,
                      ml_max_cycles: Math.max(1, Number.parseInt(event.target.value || "1", 10) || 1),
                    }))
                  }
                  disabled={busy}
                />
              </label>
            </div>

            {/* Parallel workers */}
            <div style={{ borderTop: "1px solid var(--border)", paddingTop: "12px", marginTop: "4px" }}>
              <p style={{ fontSize: "12px", color: "var(--text-muted)", margin: "0 0 10px" }}>
                {language === "ko" ? "병렬 실행 설정" : "Parallel execution settings"}
              </p>

              <ToggleRow
                checked={autoParallelWorkers}
                onChange={(event) =>
                  updateDraftSettings((current) => ({
                    ...current,
                    parallel_worker_mode: event.target.checked ? "auto" : "manual",
                    parallel_workers: event.target.checked
                      ? Math.max(0, Number.parseInt(String(current.parallel_workers || "0"), 10) || 0)
                      : Math.max(1, Number.parseInt(String(current.parallel_workers || "4"), 10) || 4),
                  }))
                }
                label={t("preset.auto")}
                hint={language === "ko" ? "시스템 리소스에 따라 작업자 수 자동 조정" : "Automatically adjust worker count based on resources"}
                disabled={runtimeBusy}
              />

              <div className="choice-grid" style={{ marginTop: "8px" }}>
                <label className="field">
                  <span>{t("field.parallelWorkers")}</span>
                  <input
                  type="number"
                  min="1"
                  value={draftSettings.parallel_workers > 0 ? draftSettings.parallel_workers : 4}
                  onChange={(event) =>
                      updateDraftSettings((current) => ({
                        ...current,
                        parallel_workers: Math.max(1, Number.parseInt(event.target.value || "1", 10) || 1),
                      }))
                    }
                    disabled={runtimeBusy || autoParallelWorkers}
                  />
                </label>

                <label className="field">
                  <span>{t("field.parallelMemoryPerWorkerGiB")}</span>
                  <input
                  type="number"
                  min="0.1"
                  step="0.1"
                  value={draftSettings.parallel_memory_per_worker_gib || 3}
                  onChange={(event) =>
                      updateDraftSettings((current) => ({
                        ...current,
                        parallel_memory_per_worker_gib: normalizeMemoryBudgetGiB(
                          event.target.value,
                          current.parallel_memory_per_worker_gib || 3,
                        ),
                      }))
                    }
                    disabled={runtimeBusy}
                  />
                </label>

                <label className="field">
                  <span>{t("field.backgroundConcurrencyLimit")}</span>
                  <input
                  type="number"
                  min="1"
                  value={draftSettings.background_concurrency_limit || 2}
                  onChange={(event) =>
                      updateDraftSettings((current) => ({
                        ...current,
                        background_concurrency_limit: Math.max(1, Number.parseInt(event.target.value || "1", 10) || 1),
                      }))
                    }
                  />
                </label>

                <label className="field">
                  <span>{t("field.codexPath")}</span>
                  <input
                    value={draftSettings.codex_path || defaultCodexPath(draftSettings.model_provider)}
                    onChange={(event) => updateDraftSettings((current) => ({ ...current, codex_path: event.target.value }))}
                    disabled={runtimeBusy}
                  />
                </label>
              </div>
            </div>

            {/* Toggle options */}
            <div style={{ display: "flex", flexDirection: "column", gap: "6px", marginTop: "4px" }}>
              <ToggleRow
                checked={Boolean(draftSettings.allow_push)}
                onChange={(event) => updateDraftSettings((current) => ({ ...current, allow_push: event.target.checked }))}
                label={t("option.allowPushAfterSafeRuns")}
                disabled={runtimeBusy}
              />
              <ToggleRow
                checked={Boolean(draftSettings.require_checkpoint_approval)}
                onChange={(event) =>
                  updateDraftSettings((current) => ({
                    ...current,
                    require_checkpoint_approval: event.target.checked,
                  }))
                }
                label={t("option.requireCheckpointApproval")}
                disabled={runtimeBusy}
              />
            </div>
          </div>
        </div>
        ) : null}

        {/* ── Share tab ── */}
        {settingsTab === "share" ? (
        <div className="form-section" style={{ gridColumn: "1 / -1" }}>
          <div className="subsection">
            <SectionHeader
              icon={<ShareIcon />}
              title={t("run.remoteMonitor")}
              description={language === "ko" ? "원격에서 실행 상태를 모니터링하는 공유 링크" : "Share a link to monitor your run from anywhere"}
              badge={
                <span className={`status-badge status-badge--${shareServer?.running ? "success" : "neutral"}`}>
                  {shareServer?.running ? t("common.on") : t("common.off")}
                </span>
              }
            />

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", marginTop: "4px" }}>
              <div>
                <div className="info-callout" style={{ marginBottom: "10px" }}>
                  <InfoIcon />
                  <span>{t("run.shareDescription")} {t("run.sharePoll")}</span>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                  <div className="sidebar-item">
                    <span style={{ fontSize: "11px", color: "var(--text-dim)" }}>{t("run.shareBindHost")}</span>
                    <strong style={{ fontFamily: "monospace" }}>0.0.0.0</strong>
                  </div>
                </div>
                <div style={{ marginTop: "10px" }}>
                  <button className="toolbar-button" onClick={onGenerateShareLink} type="button" disabled={shareBusy}>
                    {t("action.generateShareLink")}
                  </button>
                </div>
              </div>

              <div>
                {activeShare?.share_url ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                    <label className="field field--wide">
                      <span>{t("run.shareLink")}</span>
                      <div className="share-url-row">
                        <input value={activeShare.share_url} readOnly style={{ fontFamily: "monospace", fontSize: "12px" }} />
                        <button className="toolbar-button toolbar-button--accent" onClick={onCopyShareLink} type="button" disabled={shareBusy} title={t("action.copyLink")}>
                          <CopyIcon />
                        </button>
                      </div>
                    </label>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                      <span style={{ fontSize: "12px", color: "var(--text-dim)" }}>
                        {t("run.shareExpires", { expiresAt: activeShare.expires_at || t("common.unavailable") })}
                      </span>
                      <button className="toolbar-button toolbar-button--ghost" onClick={onRevokeShareLink} type="button" disabled={shareBusy}>
                        {t("action.revokeLink")}
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="empty-block" style={{ height: "100%" }}>
                    <ShareIcon />
                    <span>{t("run.noShareSession")}</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
        ) : null}

      </div>
    </section>
  );
}, appSettingsViewPropsEqual);
