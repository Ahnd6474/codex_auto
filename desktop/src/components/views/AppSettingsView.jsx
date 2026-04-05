import { memo, startTransition, useEffect, useRef, useState } from "react";
import { useI18n } from "../../i18n";
import {
  canEditProjectConfig,
  cloneValue,
  defaultCodexPath,
  normalizeMemoryBudgetGiB,
  normalizeDashboardVisibility,
  programSettingsEqual,
} from "../../utils";

/* ?? Reusable toggle row ?? */
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

function SectionHeader({ eyebrow = "", title, description = "", badge = null }) {
  return (
    <div className="settings-section-header">
      <div className="settings-section-header__title">
        {eyebrow ? <span className="settings-section-header__eyebrow">{eyebrow}</span> : null}
        <strong>{title}</strong>
        {description ? <p>{description}</p> : null}
      </div>
      {badge ? <div className="settings-section-header__meta">{badge}</div> : null}
    </div>
  );
}

const SETTINGS_TAB_KEYS = new Set(["app", "tooling", "execution", "dashboard", "share"]);
const TOOL_PROVIDER_KEYS = Object.freeze({
  codex: "openai",
  claude: "claude",
  gemini: "gemini",
  ollama: "ollama",
});
const OLLAMA_RECOMMENDED_MODELS = Object.freeze([
  "qwen2.5-coder:0.5b",
  "qwen2.5-coder:7b",
  "qwen3:8b",
  "deepseek-r1:8b",
  "llama3.2:3b",
  "gemma3:4b",
  "mistral-small:24b",
]);

function cloneSettings(value) {
  return cloneValue(value && typeof value === "object" ? value : {});
}

function normalizeSettingsTabKey(value) {
  const normalized = String(value || "").trim().toLowerCase();
  return SETTINGS_TAB_KEYS.has(normalized) ? normalized : "app";
}

function sameSettingsSnapshot(left, right) {
  return programSettingsEqual(left, right);
}

function toolingEntry(toolingStatus = {}, tool = "") {
  const entry = toolingStatus?.[tool];
  return entry && typeof entry === "object" ? entry : {};
}

function activeToolingJob(toolingJobs = [], tool = "") {
  return (Array.isArray(toolingJobs) ? toolingJobs : []).find((job) => {
    const repoId = String(job?.repo_id || "").trim().toLowerCase();
    const status = String(job?.status || "").trim().toLowerCase();
    return repoId === `tooling:${String(tool || "").trim().toLowerCase()}`
      && ["queued", "running"].includes(status);
  }) || null;
}

function toolingBadge(status = {}, { connectedLabel = "Connected", installedLabel = "Installed", missingLabel = "Missing" } = {}) {
  if (status?.running === true) {
    return { tone: "success", label: connectedLabel };
  }
  if (status?.installed) {
    return { tone: "success", label: installedLabel };
  }
  return { tone: "neutral", label: missingLabel };
}

function ToolingMetaRow({ label, value, mono = false }) {
  if (!value) {
    return null;
  }
  return (
    <div className="tooling-card__meta-row">
      <span className="tooling-card__meta-label">{label}</span>
      <strong className={`tooling-card__meta-value${mono ? " tooling-card__meta-value--mono" : ""}`}>{value}</strong>
    </div>
  );
}

function ToolingCard({
  title,
  badge,
  reason,
  version,
  command,
  extra,
  buttonLabel,
  buttonTone = "accent",
  disabled = false,
  onAction,
  children = null,
}) {
  return (
    <div className="subsection tooling-card">
      <div className="tooling-card__header">
        <div className="tooling-card__title">
          <strong>{title}</strong>
        </div>
        <span className={`status-badge status-badge--${badge.tone}`}>{badge.label}</span>
      </div>
      {reason ? <p className="tooling-card__note">{reason}</p> : null}
      {(version || command) ? (
        <div className="tooling-card__meta">
          <ToolingMetaRow label="Version" value={version} mono />
          <ToolingMetaRow label="Command" value={command} mono />
        </div>
      ) : null}
      {extra ? <p className="tooling-card__note">{extra}</p> : null}
      {children}
      {buttonLabel ? (
        <div className="tooling-card__actions">
          <button
            className={`toolbar-button${buttonTone === "ghost" ? " toolbar-button--ghost" : " toolbar-button--accent"}`}
            onClick={onAction}
            type="button"
            disabled={disabled}
          >
            {buttonLabel}
          </button>
        </div>
      ) : null}
    </div>
  );
}

function settingsLeadFor(tabKey, language) {
  switch (tabKey) {
    case "tooling":
      return language === "ko"
        ? "설치 상태와 연결 경로를 한 화면에서 관리하는 AI 작업 제어면입니다."
        : "A single control surface for AI tooling installs, connection state, and launch paths.";
    case "execution":
      return language === "ko"
        ? "안전성, 병렬성, 런타임 기본값을 조정해 실행 행동을 고정합니다."
        : "Tune safety, parallelism, and runtime defaults to shape how runs behave.";
    case "dashboard":
      return language === "ko"
        ? "대시보드에 표시할 신호를 선택해 운영 화면의 밀도를 조절합니다."
        : "Choose which signals appear on the dashboard so the operations view stays focused.";
    case "share":
      return language === "ko"
        ? "원격 모니터 링크를 발급하고 만료 상태를 추적합니다."
        : "Issue remote monitor links and keep the active share session under control.";
    case "app":
    default:
      return language === "ko"
        ? "테마, 언어, 개발자 기능 같은 전역 데스크톱 환경을 다룹니다."
        : "Adjust the global desktop environment, including theme, language, and developer features.";
  }
}

function OllamaModelManagerModal({
  onClose,
  installedModels,
  recommendedModels,
  ollamaSearch,
  setOllamaSearch,
  selectedModel,
  setSelectedModel,
  pendingModel,
  ollamaJob,
  onConnectOllama,
  language,
  loading = false,
}) {
  const normalizedSearch = String(ollamaSearch || "").trim().toLowerCase();
  const addableModels = recommendedModels.filter((m) => !installedModels.includes(m));
  const filteredAddable = addableModels.filter((m) => !normalizedSearch || m.toLowerCase().includes(normalizedSearch));

  return (
    <div
      className="settings-modal-backdrop"
      onClick={onClose}
    >
      <div
        className="settings-modal settings-modal--wide"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="settings-modal__header">
          <div className="settings-modal__title">
            <strong>{language === "ko" ? "Ollama 모델 관리" : "Ollama Model Manager"}</strong>
            <p>
              {language === "ko"
                ? "설치된 모델을 확인하고 새 모델을 바로 내려받을 수 있습니다."
                : "Review installed models and pull a new model without leaving the settings flow."}
            </p>
          </div>
          <button className="toolbar-button toolbar-button--ghost" onClick={onClose} type="button">
            ✕
          </button>
        </div>

        <div className="settings-modal__section">
          <span className="settings-modal__section-title">{language === "ko" ? "설치된 모델" : "Installed models"}</span>
          <p className="settings-inline-note">
            {language === "ko"
              ? "이 목록은 모델을 새로 내려받거나 다시 연결한 뒤 갱신됩니다."
              : "This list refreshes after you pull a model or reconnect Ollama."}
          </p>
          {loading ? (
            <div className="settings-inline-note">
              {language === "ko" ? "설치된 모델 목록을 불러오는 중입니다." : "Loading installed models..."}
            </div>
          ) : installedModels.length ? (
            <div className="settings-chip-grid">
              {installedModels.map((model) => (
                <button
                  key={model}
                  type="button"
                  className={`settings-chip ${selectedModel === model ? "settings-chip--active" : ""}`}
                  onClick={() => setSelectedModel(model)}
                  disabled={loading}
                >
                  {model}
                </button>
              ))}
            </div>
          ) : (
            <div className="settings-inline-note">
              {language === "ko" ? "아직 설치된 Ollama 모델이 없습니다." : "No Ollama models installed yet."}
            </div>
          )}
        </div>

        <div className="settings-divider" />

        <div className="settings-modal__section">
          <span className="settings-modal__section-title">{language === "ko" ? "새 모델 추가" : "Add new model"}</span>

          <label className="field field--wide settings-field">
            <span>{language === "ko" ? "모델 검색" : "Search models"}</span>
            <input
              value={ollamaSearch}
              onChange={(e) => setOllamaSearch(e.target.value)}
              placeholder="qwen2.5-coder:7b"
              disabled={loading || Boolean(ollamaJob)}
              autoFocus
            />
          </label>

          {loading ? (
            <div className="settings-inline-note">
              {language === "ko" ? "추천 모델을 준비하는 중입니다." : "Preparing recommended models..."}
            </div>
          ) : filteredAddable.length ? (
            <div className="settings-chip-grid">
              {filteredAddable.slice(0, 12).map((model) => (
                <button
                  key={model}
                  type="button"
                  className={`settings-chip ${selectedModel === model ? "settings-chip--active" : ""}`}
                  onClick={() => setSelectedModel(model)}
                  disabled={loading || Boolean(ollamaJob)}
                >
                  {model}
                </button>
              ))}
            </div>
          ) : (
            <div className="settings-inline-note">
              {language === "ko"
                ? "검색 결과가 없습니다. 입력한 모델 slug를 그대로 설치할 수 있습니다."
                : "No preset matches. The typed model slug can still be pulled directly."}
            </div>
          )}

          <div className="settings-keyline">
            <span>{language === "ko" ? "선택된 모델" : "Selected model"}</span>
            <strong>{pendingModel || "-"}</strong>
          </div>

          <div className="settings-modal__footer">
            <button className="toolbar-button toolbar-button--ghost" onClick={onClose} type="button">
              {language === "ko" ? "닫기" : "Close"}
            </button>
            <button
              className="toolbar-button toolbar-button--accent"
              onClick={() => onConnectOllama?.(pendingModel)}
              type="button"
              disabled={loading || Boolean(ollamaJob) || !pendingModel}
            >
              {ollamaJob
                ? (String(ollamaJob.status || "").trim().toLowerCase() === "queued"
                  ? (language === "ko" ? "대기 중" : "Queued")
                  : (language === "ko" ? "설치 중..." : "Pulling..."))
                : (language === "ko" ? "선택 모델 설치" : "Pull Selected Model")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function appSettingsViewPropsEqual(previousProps, nextProps) {
  return (
    programSettingsEqual(previousProps.settings, nextProps.settings)
    && previousProps.codexStatus === nextProps.codexStatus
    && previousProps.toolingStatus === nextProps.toolingStatus
    && previousProps.toolingJobs === nextProps.toolingJobs
    && previousProps.shareSettings === nextProps.shareSettings
    && previousProps.shareDetail === nextProps.shareDetail
    && previousProps.busy === nextProps.busy
    && previousProps.shareBusy === nextProps.shareBusy
    && previousProps.settingsTab === nextProps.settingsTab
    && previousProps.initialSettingsTab === nextProps.initialSettingsTab
    && previousProps.projectStatus === nextProps.projectStatus
    && previousProps.ollamaManagerOpen === nextProps.ollamaManagerOpen
    && previousProps.ollamaManagerLoading === nextProps.ollamaManagerLoading
    && previousProps.onInstallTooling === nextProps.onInstallTooling
    && previousProps.onConnectOllama === nextProps.onConnectOllama
    && previousProps.onChangeSettingsTab === nextProps.onChangeSettingsTab
    && previousProps.onOpenOllamaManager === nextProps.onOpenOllamaManager
    && previousProps.onCloseOllamaManager === nextProps.onCloseOllamaManager
  );
}

export const AppSettingsView = memo(function AppSettingsView({
  settings,
  codexStatus,
  toolingStatus = {},
  toolingJobs = [],
  modelCatalog = [],
  shareSettings,
  shareDetail,
  busy,
  shareBusy = false,
  settingsTab,
  initialSettingsTab,
  projectStatus = "",
  ollamaManagerOpen = false,
  ollamaManagerLoading = false,
  onChangeSettings,
  onChangeSettingsTab,
  onInstallTooling,
  onConnectOllama,
  onOpenOllamaManager,
  onCloseOllamaManager,
  onGenerateShareLink,
  onCopyShareLink,
  onRevokeShareLink,
  onChangeShareSettings,
}) {
  const { language, languageOptions, setLanguage, t } = useI18n();
  const [draftSettings, setDraftSettings] = useState(() => cloneSettings(settings));
  const [localDirty, setLocalDirty] = useState(false);
  const [ollamaSearch, setOllamaSearch] = useState("");
  const [selectedOllamaModel, setSelectedOllamaModel] = useState("");
  const lastIncomingSettingsRef = useRef(cloneSettings(settings));
  const lastOutgoingSettingsRef = useRef(cloneSettings(settings));
  const settingsTabs = [
    { key: "app", label: language === "ko" ? "애플리케이션" : "Application" },
    { key: "tooling", label: language === "ko" ? "AI 도구" : "AI Tooling" },
    { key: "execution", label: language === "ko" ? "실행 설정" : "Execution" },
    { key: "dashboard", label: "Dashboard" },
    { key: "share", label: language === "ko" ? "공유" : "Share" },
  ];
  const activeSettingsTab = normalizeSettingsTabKey(settingsTab ?? initialSettingsTab ?? "app");
  const activeShare = shareDetail?.active_session || shareDetail?.project_active_session || null;
  const shareServer = shareDetail?.server || null;
  const dashboardVisibility = normalizeDashboardVisibility(draftSettings?.dashboard_visibility);
  const runtimeBusy = !canEditProjectConfig(projectStatus);
  void busy;
  void modelCatalog;
  void shareSettings;
  void onChangeShareSettings;
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

  useEffect(() => {
    const installedModels = Array.isArray(toolingStatus?.ollama?.models) ? toolingStatus.ollama.models : [];
    const suggestedModels = Array.isArray(toolingStatus?.ollama?.recommended_models) && toolingStatus.ollama.recommended_models.length
      ? toolingStatus.ollama.recommended_models
      : OLLAMA_RECOMMENDED_MODELS;
    const preferredModel = [...suggestedModels, ...installedModels].find(Boolean) || "qwen2.5-coder:0.5b";
    if (!selectedOllamaModel) {
      setSelectedOllamaModel(String(preferredModel).trim());
    }
  }, [selectedOllamaModel, toolingStatus?.ollama?.models, toolingStatus?.ollama?.recommended_models]);

  function updateDraftSettings(updater) {
    setDraftSettings((current) => {
      const nextDraft = typeof updater === "function" ? updater(current) : updater;
      return cloneSettings(nextDraft);
    });
    setLocalDirty(true);
  }

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
  const providerStatuses = codexStatus?.provider_statuses || {};
  const npmStatus = toolingEntry(toolingStatus, "npm");
  const codexTool = toolingEntry(toolingStatus, "codex");
  const geminiTool = toolingEntry(toolingStatus, "gemini");
  const claudeTool = toolingEntry(toolingStatus, "claude");
  const ollamaTool = toolingEntry(toolingStatus, "ollama");
  const codexProvider = providerStatuses[TOOL_PROVIDER_KEYS.codex] || {};
  const geminiProvider = providerStatuses[TOOL_PROVIDER_KEYS.gemini] || {};
  const claudeProvider = providerStatuses[TOOL_PROVIDER_KEYS.claude] || {};
  const ollamaProvider = providerStatuses[TOOL_PROVIDER_KEYS.ollama] || {};
  const codexJob = activeToolingJob(toolingJobs, "codex");
  const geminiJob = activeToolingJob(toolingJobs, "gemini");
  const claudeJob = activeToolingJob(toolingJobs, "claude");
  const ollamaJob = activeToolingJob(toolingJobs, "ollama");
  const ollamaDetailsLoaded = ollamaTool.running !== null && ollamaTool.running !== undefined;
  const installedOllamaModels = Array.isArray(ollamaTool.models) ? ollamaTool.models : [];
  const recommendedOllamaModels = Array.isArray(ollamaTool.recommended_models) && ollamaTool.recommended_models.length
    ? ollamaTool.recommended_models
    : OLLAMA_RECOMMENDED_MODELS;
  const addableOllamaModels = recommendedOllamaModels.filter((model) => !installedOllamaModels.includes(model));
  const normalizedOllamaSearch = String(ollamaSearch || "").trim().toLowerCase();
  const filteredAddableOllamaModels = addableOllamaModels.filter((model) => (
    !normalizedOllamaSearch || model.toLowerCase().includes(normalizedOllamaSearch)
  ));
  const exactInstalledOllamaModel = installedOllamaModels.find((model) => model.toLowerCase() === normalizedOllamaSearch) || "";
  const exactSuggestedOllamaModel = recommendedOllamaModels.find((model) => model.toLowerCase() === normalizedOllamaSearch) || "";
  const pendingOllamaModel = String(
    selectedOllamaModel
    || exactSuggestedOllamaModel
    || (normalizedOllamaSearch && !exactInstalledOllamaModel ? normalizedOllamaSearch : "")
  ).trim();
  const activeSettingsEntry = settingsTabs.find((tab) => tab.key === activeSettingsTab) || settingsTabs[0];
  const connectedToolCount = [codexTool, geminiTool, claudeTool, ollamaTool].filter((tool) => (
    tool?.installed || tool?.running === true
  )).length;
  const settingsHeaderStats = [
    {
      label: language === "ko" ? "현재 섹션" : "Active section",
      value: activeSettingsEntry.label,
    },
    {
      label: language === "ko" ? "편집 상태" : "Editing state",
      value: runtimeBusy
        ? (language === "ko" ? "읽기 전용" : "Read only")
        : (language === "ko" ? "편집 가능" : "Editable"),
    },
    {
      label: language === "ko" ? "도구 연결" : "Tooling linked",
      value: `${connectedToolCount}/4`,
    },
  ];

  return (
    <section className="workspace-view settings-view">
      <div className="settings-page-header settings-page-header--hero">
        <div className="settings-page-header__copy">
          <span className="settings-page-header__eyebrow">
            {language === "ko" ? "프로그램 제어" : "Program control"}
          </span>
          <h2>{t("tab.programSettings")}</h2>
          <p>{settingsLeadFor(activeSettingsTab, language)}</p>
        </div>
        <div className="settings-page-header__stats">
          {settingsHeaderStats.map((item) => (
            <div key={item.label} className="settings-page-header__stat">
              <span>{item.label}</span>
              <strong>{item.value}</strong>
            </div>
          ))}
        </div>
      </div>

      <div className="settings-subtabs">
        {settingsTabs.map((tab) => (
          <button
            key={tab.key}
            className={`settings-subtab ${activeSettingsTab === tab.key ? "settings-subtab--active" : ""}`}
            onClick={() => onChangeSettingsTab?.(tab.key)}
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="form-layout settings-layout">

        {/* ?? Application tab ?? */}
        {activeSettingsTab === "app" ? (
        <div className="form-section settings-pane" style={{ gridColumn: "1 / -1" }}>
          <div className="subsection">
            <SectionHeader
              eyebrow={language === "ko" ? "환경" : "Environment"}
              title={t("settings.application")}
              description={language === "ko"
                ? "데스크톱 전역 환경을 바꾸는 설정입니다."
                : "Controls that change the overall desktop environment."}
            />

            <label className="field settings-field">
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
              hint={language === "ko" ? "밝은 배경 테마로 전환합니다." : "Switch to light background theme"}
            />

            <ToggleRow
              checked={Boolean(draftSettings.compact_mode)}
              onChange={(event) => updateDraftSettings((current) => ({ ...current, compact_mode: event.target.checked }))}
              label={language === "ko" ? "컴팩트 모드" : "Compact Mode"}
              hint={language === "ko" ? "패널 크기와 여백을 줄여 더 많은 정보를 보여줍니다." : "Reduce panel sizes and padding for higher information density"}
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
              hint={language === "ko" ? "리포트 탭과 추가 디버그 정보를 표시합니다." : "Show reports tab and extra debug info"}
            />

            {Boolean(draftSettings.developer_mode) ? (
              <ToggleRow
                checked={Boolean(draftSettings.save_project_logs)}
                onChange={(event) => updateDraftSettings((current) => ({ ...current, save_project_logs: event.target.checked }))}
                label={t("option.saveProjectLogs")}
                hint="Persist execution logs to disk for each step"
              />
            ) : null}
          </div>
        </div>
        ) : null}

        {activeSettingsTab === "tooling" ? (
        <div className="form-section settings-pane" style={{ gridColumn: "1 / -1" }}>
          <div className="subsection">
            <SectionHeader
              eyebrow={language === "ko" ? "에이전트 런타임" : "Agent runtime"}
              title={language === "ko" ? "AI 도구 설치" : "AI Tooling"}
              description={language === "ko"
                ? "설치 상태, 실행 경로, 모델 저장소를 이곳에서 확인합니다."
                : "Check install status, launch commands, and model storage from one place."}
            />

            {!npmStatus?.installed ? (
              <div className="info-callout">
                <InfoIcon />
                <span>
                  {language === "ko"
                    ? "Codex, Gemini, Claude Code 설치에는 Node.js/npm이 필요합니다."
                    : "Node.js/npm is required before installing Codex, Gemini, or Claude Code."}
                </span>
              </div>
            ) : null}

            <div className="tooling-list">
              <ToolingCard
                title="Codex CLI"
                badge={toolingBadge(codexTool, {
                  installedLabel: language === "ko" ? "설치됨" : "Installed",
                  missingLabel: language === "ko" ? "없음" : "Missing",
                })}
                reason={codexProvider.reason || codexTool.reason}
                version={codexTool.version}
                command={codexTool.resolved_command || codexTool.command}
                extra={codexProvider.reason && codexProvider.reason !== codexTool.reason ? codexTool.reason : ""}
                buttonLabel={
                  codexJob
                    ? (String(codexJob.status || "").trim().toLowerCase() === "queued"
                      ? (language === "ko" ? "대기 중" : "Queued")
                      : (language === "ko" ? "설치 중..." : "Installing..."))
                    : (!codexTool.installed ? (language === "ko" ? "설치" : "Install") : "")
                }
                disabled={Boolean(codexJob)}
                onAction={() => onInstallTooling?.("codex")}
              />

              <ToolingCard
                title="Gemini CLI"
                badge={toolingBadge(geminiTool, {
                  installedLabel: language === "ko" ? "설치됨" : "Installed",
                  missingLabel: language === "ko" ? "없음" : "Missing",
                })}
                reason={geminiProvider.reason || geminiTool.reason}
                version={geminiTool.version}
                command={geminiTool.resolved_command || geminiTool.command}
                extra={geminiProvider.reason && geminiProvider.reason !== geminiTool.reason ? geminiTool.reason : ""}
                buttonLabel={
                  geminiJob
                    ? (String(geminiJob.status || "").trim().toLowerCase() === "queued"
                      ? (language === "ko" ? "대기 중" : "Queued")
                      : (language === "ko" ? "설치 중..." : "Installing..."))
                    : (!geminiTool.installed ? (language === "ko" ? "설치" : "Install") : "")
                }
                disabled={Boolean(geminiJob)}
                onAction={() => onInstallTooling?.("gemini")}
              />

              <ToolingCard
                title="Claude Code"
                badge={toolingBadge(claudeTool, {
                  installedLabel: language === "ko" ? "설치됨" : "Installed",
                  missingLabel: language === "ko" ? "없음" : "Missing",
                })}
                reason={claudeProvider.reason || claudeTool.reason}
                version={claudeTool.version}
                command={claudeTool.resolved_command || claudeTool.command}
                extra={claudeProvider.reason && claudeProvider.reason !== claudeTool.reason ? claudeTool.reason : ""}
                buttonLabel={
                  claudeJob
                    ? (String(claudeJob.status || "").trim().toLowerCase() === "queued"
                      ? (language === "ko" ? "대기 중" : "Queued")
                      : (language === "ko" ? "설치 중..." : "Installing..."))
                    : (!claudeTool.installed ? (language === "ko" ? "설치" : "Install") : "")
                }
                disabled={Boolean(claudeJob)}
                onAction={() => onInstallTooling?.("claude")}
              />

              <ToolingCard
                title="Ollama"
                badge={toolingBadge(ollamaTool, {
                  connectedLabel: language === "ko" ? "연결됨" : "Connected",
                  installedLabel: language === "ko" ? "설치됨" : "Installed",
                  missingLabel: language === "ko" ? "없음" : "Missing",
                })}
                reason={ollamaTool.reason}
                version={ollamaTool.version}
                command={ollamaTool.resolved_command || ollamaTool.command}
                extra={ollamaProvider.reason && ollamaProvider.reason !== ollamaTool.reason ? ollamaProvider.reason : ""}
                buttonLabel={
                  !ollamaTool.installed
                    ? (
                      ollamaJob
                        ? (String(ollamaJob.status || "").trim().toLowerCase() === "queued"
                          ? (language === "ko" ? "대기 중" : "Queued")
                          : (language === "ko" ? "설치 중..." : "Installing..."))
                        : (language === "ko" ? "설치" : "Install")
                    )
                    : ""
                }
                disabled={Boolean(ollamaJob)}
                onAction={() => onInstallTooling?.("ollama")}
              >
                {ollamaTool.installed ? (
                  <>
                    <div className="tooling-card__meta">
                      <ToolingMetaRow
                        label={language === "ko" ? "모델 저장 경로" : "Model store path"}
                        value={ollamaTool.model_store_path || "-"}
                        mono
                      />
                      {ollamaDetailsLoaded && installedOllamaModels.length ? (
                        <ToolingMetaRow
                          label={language === "ko" ? "설치된 모델" : "Installed models"}
                          value={`${installedOllamaModels.length}${language === "ko" ? "개" : " model(s)"}`}
                        />
                      ) : null}
                    </div>
                    {!ollamaDetailsLoaded ? (
                      <p className="tooling-card__note">
                        {language === "ko"
                          ? "설치된 모델 목록은 새 모델을 내려받거나 다시 연결한 뒤 갱신됩니다."
                          : "Installed-model details refresh after you pull a model or reconnect Ollama."}
                      </p>
                    ) : null}
                    <div className="tooling-card__actions">
                      <button
                        className="toolbar-button toolbar-button--ghost"
                        onClick={() => onOpenOllamaManager?.()}
                        type="button"
                        disabled={Boolean(ollamaJob)}
                      >
                        {language === "ko" ? "모델 관리" : "Model Manager"}
                      </button>
                    </div>
                  </>
                ) : null}
              </ToolingCard>
            </div>
          </div>
        </div>
        ) : null}

        {/* Dashboard tab */}
        {activeSettingsTab === "dashboard" ? (
        <div className="form-section settings-pane" style={{ gridColumn: "1 / -1" }}>
          <div className="subsection">
            <SectionHeader
              eyebrow={language === "ko" ? "가시성" : "Visibility"}
              title={t("settings.dashboardPreferences")}
              description={language === "ko"
                ? "운영 대시보드에 어떤 신호를 표시할지 선택합니다."
                : "Choose which operational signals are visible on the dashboard."}
            />

            <div className="toggle-grid settings-toggle-grid">
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

        {/* ?? Execution tab ?? */}
        {activeSettingsTab === "execution" ? (
        <div className="form-section settings-pane" style={{ gridColumn: "1 / -1" }}>
          <div className="subsection">
            <SectionHeader
              eyebrow={language === "ko" ? "런타임 규칙" : "Runtime policy"}
              title={t("settings.executionDefaults")}
              description={language === "ko"
                ? "승인, 샌드박스, 병렬성 기본값을 이 프로젝트 기준으로 맞춥니다."
                : "Set approval, sandboxing, and parallelism defaults for this project."}
            />

            <div className="info-callout">
              <InfoIcon />
              <span>
                {language === "ko"
                  ? "AI 설정은 이제 프로젝트 설정 탭에서 편집합니다."
                  : "AI settings are now edited in the project settings tab."}
              </span>
            </div>

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
                  disabled={runtimeBusy}
                >
                  <option value="standard">{t("option.workflowStandard")}</option>
                  <option value="ml">{t("option.workflowML")}</option>
                </select>
              </label>

              <label className="field">
                <span>{language === "ko" ? "계획 모드" : "Planning mode"}</span>
                <select
                  value={draftSettings.planning_mode || (draftSettings.use_fast_mode ? "compact" : "full")}
                  onChange={(event) => updateDraftSettings((current) => ({ ...current, planning_mode: event.target.value }))}
                  disabled={runtimeBusy}
                >
                  <option value="no">no planning</option>
                  <option value="compact">compact planning</option>
                  <option value="full">full planning</option>
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
                  disabled={runtimeBusy}
                />
              </label>
            </div>

            {/* Parallel workers */}
            <div className="settings-divider settings-divider--section">
              <p className="settings-inline-note">
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
                hint={language === "ko" ? "자원에 따라 작업자 수를 자동으로 조정합니다." : "Automatically adjust worker count based on resources"}
                disabled={runtimeBusy}
              />

              <div className="choice-grid settings-choice-grid">
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
            <div className="settings-toggle-stack">
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

        {/* ?? Share tab ?? */}
        {activeSettingsTab === "share" ? (
        <div className="form-section settings-pane" style={{ gridColumn: "1 / -1" }}>
          <div className="subsection">
            <SectionHeader
              eyebrow={language === "ko" ? "원격 가시성" : "Remote visibility"}
              title={t("run.remoteMonitor")}
              description={language === "ko"
                ? "진행 상황을 외부에서 읽기 전용으로 공유하는 세션입니다."
                : "Create a read-only monitor session for external visibility."}
              badge={
                <span className={`status-badge status-badge--${shareServer?.running ? "success" : "neutral"}`}>
                  {shareServer?.running ? t("common.on") : t("common.off")}
                </span>
              }
            />

            <div className="settings-split-grid">
              <div className="settings-stack">
                <div className="info-callout">
                  <InfoIcon />
                  <span>{t("run.shareDescription")} {t("run.sharePoll")}</span>
                </div>
                <div className="settings-stack settings-stack--dense">
                  <div className="sidebar-item">
                    <span style={{ fontSize: "11px", color: "var(--text-dim)" }}>{t("run.shareBindHost")}</span>
                    <strong style={{ fontFamily: "monospace" }}>0.0.0.0</strong>
                  </div>
                </div>
                <div className="settings-action-row">
                  <button className="toolbar-button" onClick={onGenerateShareLink} type="button" disabled={shareBusy}>
                    {t("action.generateShareLink")}
                  </button>
                </div>
              </div>

              <div className="settings-share-card">
                {activeShare?.share_url ? (
                  <div className="settings-stack">
                    <label className="field field--wide">
                      <span>{t("run.shareLink")}</span>
                      <div className="share-url-row settings-share-link-row">
                        <input value={activeShare.share_url} readOnly style={{ fontFamily: "monospace", fontSize: "12px" }} />
                        <button className="toolbar-button toolbar-button--accent" onClick={onCopyShareLink} type="button" disabled={shareBusy} title={t("action.copyLink")}>
                          <CopyIcon />
                        </button>
                      </div>
                    </label>
                    <div className="settings-share-meta">
                      <span className="settings-inline-note">
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

      {ollamaManagerOpen ? (
        <OllamaModelManagerModal
          onClose={onCloseOllamaManager}
          installedModels={installedOllamaModels}
          recommendedModels={recommendedOllamaModels}
          ollamaSearch={ollamaSearch}
          setOllamaSearch={setOllamaSearch}
          selectedModel={selectedOllamaModel}
          setSelectedModel={setSelectedOllamaModel}
          pendingModel={pendingOllamaModel}
          ollamaJob={ollamaJob}
          onConnectOllama={onConnectOllama}
          language={language}
          loading={ollamaManagerLoading}
        />
      ) : null}
    </section>
  );
}, appSettingsViewPropsEqual);



