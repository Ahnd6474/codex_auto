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

/* ?? Section icons ?? */
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

function ToolingIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M14.5 4.5a4 4 0 0 0-5.63 5.64l-5.37 5.36a1.5 1.5 0 1 0 2.12 2.12l5.36-5.37a4 4 0 0 0 5.64-5.63l-2.42 2.41-2-2 2.3-2.53Z" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
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

function ToolingCard({
  title,
  description,
  badge,
  reason,
  version,
  command,
  extra,
  buttonLabel,
  buttonTone = "accent",
  disabled = false,
  onAction,
  accentColor = null,
  children = null,
}) {
  return (
    <div
      className="subsection"
      style={{
        gap: "10px",
        borderLeft: accentColor ? `3px solid ${accentColor}` : undefined,
        paddingLeft: accentColor ? "10px" : undefined,
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "10px" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
          <strong style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            {accentColor ? (
              <span
                style={{
                  width: "8px",
                  height: "8px",
                  borderRadius: "50%",
                  background: accentColor,
                  flexShrink: 0,
                }}
              />
            ) : null}
            {title}
          </strong>
          <small style={{ color: "var(--text-muted)" }}>{description}</small>
        </div>
        <span className={`status-badge status-badge--${badge.tone}`}>{badge.label}</span>
      </div>
      {reason ? <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>{reason}</div> : null}
      {version ? (
        <div className="sidebar-item">
          <span style={{ fontSize: "11px", color: "var(--text-dim)" }}>Version</span>
          <strong style={{ fontFamily: "monospace" }}>{version}</strong>
        </div>
      ) : null}
      {command ? (
        <div className="sidebar-item">
          <span style={{ fontSize: "11px", color: "var(--text-dim)" }}>Command</span>
          <strong style={{ fontFamily: "monospace" }}>{command}</strong>
        </div>
      ) : null}
      {extra ? <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>{extra}</div> : null}
      {children}
      {buttonLabel ? (
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
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
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 9999,
        background: "rgba(0, 0, 0, 0.55)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: "var(--bg-panel)",
          border: "1px solid var(--border)",
          borderRadius: "10px",
          padding: "24px",
          width: "520px",
          maxWidth: "92vw",
          maxHeight: "82vh",
          overflow: "auto",
          display: "flex",
          flexDirection: "column",
          gap: "16px",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <strong style={{ fontSize: "15px" }}>
            {language === "ko" ? "Ollama 모델 관리" : "Ollama Model Manager"}
          </strong>
          <button className="toolbar-button toolbar-button--ghost" onClick={onClose} type="button">
            ✕
          </button>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          <span style={{ fontSize: "12px", color: "var(--text-dim)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em" }}>
            {language === "ko" ? "설치된 모델" : "Installed models"}
          </span>
          <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>
            {language === "ko"
              ? "이 목록은 모델을 새로 내려받거나 다시 연결한 뒤 갱신됩니다."
              : "This list refreshes after you pull a model or reconnect Ollama."}
          </div>
          {loading ? (
            <div style={{ fontSize: "12px", color: "var(--text-muted)", padding: "8px 0" }}>
              {language === "ko" ? "설치된 모델 목록을 불러오는 중입니다." : "Loading installed models..."}
            </div>
          ) : installedModels.length ? (
            <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
              {installedModels.map((model) => (
                <button
                  key={model}
                  type="button"
                  className={`toolbar-button ${selectedModel === model ? "toolbar-button--accent" : "toolbar-button--ghost"}`}
                  onClick={() => setSelectedModel(model)}
                  disabled={loading}
                >
                  {model}
                </button>
              ))}
            </div>
          ) : (
            <div style={{ fontSize: "12px", color: "var(--text-muted)", padding: "8px 0" }}>
              {language === "ko" ? "아직 설치된 Ollama 모델이 없습니다." : "No Ollama models installed yet."}
            </div>
          )}
        </div>

        <div style={{ borderTop: "1px solid var(--border)" }} />

        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          <span style={{ fontSize: "12px", color: "var(--text-dim)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em" }}>
            {language === "ko" ? "새 모델 추가" : "Add new model"}
          </span>

          <label className="field field--wide" style={{ marginTop: 0 }}>
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
            <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>
              {language === "ko" ? "추천 모델을 준비하는 중입니다." : "Preparing recommended models..."}
            </div>
          ) : filteredAddable.length ? (
            <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
              {filteredAddable.slice(0, 12).map((model) => (
                <button
                  key={model}
                  type="button"
                  className={`toolbar-button ${selectedModel === model ? "toolbar-button--accent" : "toolbar-button--ghost"}`}
                  onClick={() => setSelectedModel(model)}
                  disabled={loading || Boolean(ollamaJob)}
                >
                  {model}
                </button>
              ))}
            </div>
          ) : (
            <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>
              {language === "ko"
                ? "검색 결과가 없습니다. 입력한 모델 slug를 그대로 설치할 수 있습니다."
                : "No preset matches. The typed model slug can still be pulled directly."}
            </div>
          )}

          <div className="sidebar-item">
            <span style={{ fontSize: "11px", color: "var(--text-dim)" }}>
              {language === "ko" ? "선택된 모델" : "Selected model"}
            </span>
            <strong style={{ fontFamily: "monospace" }}>{pendingModel || "-"}</strong>
          </div>

          <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", paddingTop: "4px" }}>
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
  settingsTab = "app",
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
  const activeSettingsTab = normalizeSettingsTabKey(settingsTab);
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

  return (
    <section className="workspace-view">
      <div className="view-header">
        <div>
          <span className="eyebrow">{t("tab.programSettings")}</span>
          <h2>{t("tab.programSettings")}</h2>
          <p style={{ color: "var(--text-muted)", fontSize: "13px" }}>{t("settings.programSettingsDescription")}</p>
        </div>
      </div>

      {/* ?? Sub-category tab bar ?? */}
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

      <div className="form-layout">

        {/* ?? Application tab ?? */}
        {activeSettingsTab === "app" ? (
        <div className="form-section" style={{ gridColumn: "1 / -1" }}>
          <div className="subsection">
            <SectionHeader
              icon={<AppIcon />}
              title={t("settings.application")}
              description={language === "ko" ? "언어, 테마, 개발자 옵션" : "Language, theme and developer options"}
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
        <div className="form-section" style={{ gridColumn: "1 / -1" }}>
          <div className="subsection">
            <SectionHeader
              icon={<ToolingIcon />}
              title={language === "ko" ? "AI 도구 설치" : "AI Tooling"}
              description={language === "ko" ? "터미널 에이전트와 Ollama 연결을 여기서 관리합니다." : "Install terminal agents and manage the local Ollama connection here."}
            />

            {!npmStatus?.installed ? (
              <div className="info-callout" style={{ marginTop: "10px" }}>
                <InfoIcon />
                <span>
                  {language === "ko"
                    ? "Codex, Gemini, Claude Code 설치에는 Node.js/npm이 필요합니다."
                    : "Node.js/npm is required before installing Codex, Gemini, or Claude Code."}
                </span>
              </div>
            ) : null}

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: "12px", marginTop: "12px" }}>
              <ToolingCard
                title="Codex CLI"
                description={language === "ko" ? "OpenAI Codex CLI 설치 상태" : "OpenAI Codex CLI installation status"}
                accentColor="#10a37f"
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
                description={language === "ko" ? "Gemini CLI 설치 상태" : "Gemini CLI installation status"}
                accentColor="#4285f4"
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
                description={language === "ko" ? "Claude Code CLI 설치 상태" : "Claude Code CLI installation status"}
                accentColor="#d97706"
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
                description={language === "ko" ? "로컬 Ollama 연결과 모델 저장소 관리" : "Connect a local Ollama server and manage the model store"}
                accentColor="#8b5cf6"
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
                    <div className="sidebar-item">
                      <span style={{ fontSize: "11px", color: "var(--text-dim)" }}>{language === "ko" ? "모델 저장 경로" : "Model store path"}</span>
                      <strong style={{ fontFamily: "monospace", wordBreak: "break-all" }}>{ollamaTool.model_store_path || "-"}</strong>
                    </div>
                    {ollamaDetailsLoaded && installedOllamaModels.length ? (
                      <div className="sidebar-item">
                        <span style={{ fontSize: "11px", color: "var(--text-dim)" }}>
                          {language === "ko" ? "설치된 모델" : "Installed models"}
                        </span>
                        <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>
                          {installedOllamaModels.length}{language === "ko" ? "개" : " model(s)"}
                        </span>
                      </div>
                    ) : null}
                    {!ollamaDetailsLoaded ? (
                      <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>
                        {language === "ko"
                          ? "설치된 모델 목록은 새 모델을 내려받거나 다시 연결한 뒤 갱신됩니다."
                          : "Installed-model details refresh after you pull a model or reconnect Ollama."}
                      </div>
                    ) : null}
                    <div style={{ display: "flex", justifyContent: "flex-end" }}>
                      <button
                        className="toolbar-button toolbar-button--ghost"
                        onClick={() => onOpenOllamaManager?.()}
                        type="button"
                        disabled={Boolean(ollamaJob)}
                      >
                        {language === "ko" ? "모델 관리" : "Manage Models"}
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
        <div className="form-section" style={{ gridColumn: "1 / -1" }}>
          <div className="subsection">
            <SectionHeader
              icon={<DashboardIcon />}
              title={t("settings.dashboardPreferences")}
              description={language === "ko" ? "대시보드에 표시할 항목을 선택합니다." : "Choose which metrics appear on the dashboard"}
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

        {/* ?? Execution tab ?? */}
        {activeSettingsTab === "execution" ? (
        <div className="form-section" style={{ gridColumn: "1 / -1" }}>
          <div className="subsection">
            <SectionHeader
              icon={<ExecutionIcon />}
              title={t("settings.executionDefaults")}
              description={language === "ko" ? "병렬 실행과 체크포인트 설정" : "Parallel execution and checkpoint settings"}
            />

                        <div className="info-callout" style={{ marginTop: "10px" }}>
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
                hint={language === "ko" ? "자원에 따라 작업자 수를 자동으로 조정합니다." : "Automatically adjust worker count based on resources"}
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

        {/* ?? Share tab ?? */}
        {activeSettingsTab === "share" ? (
        <div className="form-section" style={{ gridColumn: "1 / -1" }}>
          <div className="subsection">
            <SectionHeader
              icon={<ShareIcon />}
              title={t("run.remoteMonitor")}
              description={language === "ko" ? "어디서든 실행 상태를 모니터링할 수 있는 공유 링크" : "Share a link to monitor your run from anywhere"}
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



