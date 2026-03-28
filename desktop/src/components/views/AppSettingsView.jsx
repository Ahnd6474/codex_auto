import { useI18n } from "../../i18n";
import {
  applyProviderDefaults,
  defaultCodexPath,
  defaultProviderApiKeyEnv,
  defaultProviderBaseUrl,
  normalizeMemoryBudgetGiB,
  normalizeDashboardVisibility,
  providerAvailable,
  providerStatusReason,
  programSettingsAllowsModelSlugInput,
  REASONING_OPTIONS,
  reasoningEffortLabel,
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

export function AppSettingsView({
  settings,
  codexStatus,
  shareSettings,
  shareDetail,
  busy,
  shareBusy = false,
  onChangeSettings,
  onGenerateShareLink,
  onCopyShareLink,
  onRevokeShareLink,
  onChangeShareSettings,
}) {
  const { language, languageOptions, setLanguage, t } = useI18n();
  const planningReasoningLabel = language === "ko" ? "계획 추론" : "Planning Reasoning";
  const activeShare = shareDetail?.active_session || null;
  const shareServer = shareDetail?.server || null;
  const selectedProvider = String(settings.model_provider || "openai").trim().toLowerCase();
  const dashboardVisibility = normalizeDashboardVisibility(settings?.dashboard_visibility);
  const runtimeBusy = busy;
  const autoParallelWorkers = String(settings?.parallel_worker_mode || "auto").trim().toLowerCase() !== "manual";
  const comingSoonLabel = language === "ko" ? "추가 예정" : "Coming soon";

  const providerOptions = [
    { value: "openai", label: "GPT Codex only", enabled: true },
    { value: "ensemble", label: t("option.providerEnsemble"), enabled: false },
    { value: "claude", label: "Claude Code", enabled: false },
    { value: "gemini", label: "Gemini CLI", enabled: false },
    { value: "qwen_code", label: "Qwen Code", enabled: false },
    { value: "deepseek", label: "DeepSeek via Claude Code", enabled: false },
    { value: "kimi", label: "Kimi", enabled: false },
    { value: "minimax", label: "MiniMax via Claude Code", enabled: false },
    { value: "glm", label: "GLM via Claude Code", enabled: false },
    { value: "openrouter", label: t("option.providerOpenRouter"), enabled: false },
    { value: "opencdk", label: t("option.providerOpenCDK"), enabled: false },
    { value: "local_openai", label: t("option.providerLocalCompatible"), enabled: false },
    { value: "oss", label: t("option.providerOSS"), enabled: false },
  ];

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

  const providerUnavailable = !providerAvailable(selectedProvider, codexStatus);
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

      <div className="form-layout">
        {/* ── Left column ── */}
        <div className="form-section">

          {/* Application section */}
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
              checked={settings.ui_theme === "light"}
              onChange={(event) => onChangeSettings((current) => ({ ...current, ui_theme: event.target.checked ? "light" : "dark" }))}
              label={t("option.lightMode")}
              hint={language === "ko" ? "밝은 배경의 라이트 테마로 전환" : "Switch to light background theme"}
            />

            <ToggleRow
              checked={Boolean(settings.developer_mode)}
              onChange={(event) =>
                onChangeSettings((current) => ({
                  ...current,
                  developer_mode: event.target.checked,
                  save_project_logs: event.target.checked ? Boolean(current.save_project_logs) : false,
                }))
              }
              label={t("option.developerMode")}
              hint={language === "ko" ? "리포트 탭 및 추가 디버그 정보 표시" : "Show reports tab and extra debug info"}
            />

            {Boolean(settings.developer_mode) ? (
              <ToggleRow
                checked={Boolean(settings.save_project_logs)}
                onChange={(event) => onChangeSettings((current) => ({ ...current, save_project_logs: event.target.checked }))}
                label={t("option.saveProjectLogs")}
                hint={language === "ko" ? "각 단계의 실행 로그를 파일로 저장" : "Persist execution logs to disk for each step"}
              />
            ) : null}
          </div>

          {/* Dashboard Preferences */}
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
                        onChangeSettings((current) => ({
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

        {/* ── Right column ── */}
        <div className="form-section">
          <div className="subsection">
            <SectionHeader
              icon={<ExecutionIcon />}
              title={t("settings.executionDefaults")}
              description={language === "ko" ? "AI 모델, 병렬 실행, 체크포인트 설정" : "AI model provider, parallel execution and checkpoint settings"}
            />

            <div className="info-callout" style={{ marginTop: "10px" }}>
              <InfoIcon />
              <span>{language === "ko" ? "프로그램 설정에서는 현재 GPT Codex only만 사용할 수 있습니다. 다른 제공자는 추가 예정입니다." : "Program Settings currently supports GPT Codex only. Other providers are listed as coming soon."}</span>
            </div>

            {/* Provider select */}
            <div style={{ marginTop: "4px" }}>
              <label className="field">
                <span>{t("field.modelProvider")}</span>
                <select
                  value={settings.model_provider || "openai"}
                  onChange={(event) =>
                    onChangeSettings((current) => ({
                      ...applyProviderDefaults(current, event.target.value),
                    }))
                  }
                  disabled={runtimeBusy}
                >
                  {providerOptions.map(({ value, label, enabled }) => {
                    const isInstalled = providerAvailable(value, codexStatus);
                    const disabled = !enabled || !isInstalled;
                    const reason = !enabled ? comingSoonLabel : providerStatusReason(value, codexStatus);
                    const suffix = !enabled ? ` (${comingSoonLabel})` : !isInstalled ? " (unavailable)" : "";
                    return (
                    <option
                      key={value}
                      value={value}
                      disabled={disabled}
                      title={reason}
                    >
                      {label}{suffix}
                    </option>
                    );
                  })}
                </select>
              </label>

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
                  value={settings.local_model_provider || "ollama"}
                  onChange={(event) => onChangeSettings((current) => ({ ...current, local_model_provider: event.target.value }))}
                  disabled={runtimeBusy}
                >
                  <option value="ollama">{t("option.localProviderOllama")}</option>
                  <option value="lmstudio">{t("option.localProviderLmStudio")}</option>
                </select>
              </label>
            ) : null}

            {selectedProvider !== "oss" ? (
              <label className="field">
                <span>{t("field.providerBaseUrl")}</span>
                <input
                  value={settings.provider_base_url || defaultProviderBaseUrl(settings.model_provider)}
                  onChange={(event) => onChangeSettings((current) => ({ ...current, provider_base_url: event.target.value }))}
                  disabled={runtimeBusy}
                />
              </label>
            ) : null}

            {selectedProvider !== "oss" ? (
              <label className="field">
                <span>{t("field.providerApiKeyEnv")}</span>
                <input
                  value={settings.provider_api_key_env || defaultProviderApiKeyEnv(settings.model_provider)}
                  onChange={(event) => onChangeSettings((current) => ({ ...current, provider_api_key_env: event.target.value }))}
                  disabled={runtimeBusy}
                />
                <small className="field-hint">
                  {language === "ko" ? "해당 환경 변수에 API 키가 저장되어 있어야 합니다." : "The environment variable that holds your API key."}
                </small>
              </label>
            ) : null}

            {programSettingsAllowsModelSlugInput(selectedProvider) ? (
              <label className="field">
                <span>{t("field.customModelSlug")}</span>
                <input
                  value={settings.model_slug_input || settings.model || ""}
                  onChange={(event) =>
                    onChangeSettings((current) => {
                      const nextModel = event.target.value.trim().toLowerCase();
                      return {
                        ...current,
                        model: nextModel,
                        model_preset: nextModel === "auto" ? "auto" : "",
                        model_selection_mode: "slug",
                        model_slug_input: event.target.value,
                      };
                    })
                  }
                  disabled={runtimeBusy}
                />
              </label>
            ) : null}

            {/* 2-col grid for smaller fields */}
            <div className="choice-grid">
              <label className="field">
                <span>{t("field.approvalMode")}</span>
                <select
                  value={settings.approval_mode || "never"}
                  onChange={(event) => onChangeSettings((current) => ({ ...current, approval_mode: event.target.value }))}
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
                  value={settings.sandbox_mode || "danger-full-access"}
                  onChange={(event) => onChangeSettings((current) => ({ ...current, sandbox_mode: event.target.value }))}
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
                  value={settings.workflow_mode || "standard"}
                  onChange={(event) => onChangeSettings((current) => ({ ...current, workflow_mode: event.target.value }))}
                  disabled={busy}
                >
                  <option value="standard">{t("option.workflowStandard")}</option>
                  <option value="ml">{t("option.workflowML")}</option>
                </select>
              </label>

              <label className="field">
                <span>{planningReasoningLabel}</span>
                <select
                  value={settings.planning_effort || settings.effort || "medium"}
                  onChange={(event) => onChangeSettings((current) => ({ ...current, planning_effort: event.target.value }))}
                  disabled={busy}
                >
                  {REASONING_OPTIONS.map((effort) => (
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
                  value={settings.checkpoint_interval_blocks || 1}
                  onChange={(event) =>
                    onChangeSettings((current) => ({
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
                  value={settings.ml_max_cycles || 3}
                  onChange={(event) =>
                    onChangeSettings((current) => ({
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
                  onChangeSettings((current) => ({
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
                    value={settings.parallel_workers > 0 ? settings.parallel_workers : 4}
                    onChange={(event) =>
                      onChangeSettings((current) => ({
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
                    value={settings.parallel_memory_per_worker_gib || 3}
                    onChange={(event) =>
                      onChangeSettings((current) => ({
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
                    value={settings.background_concurrency_limit || 2}
                    onChange={(event) =>
                      onChangeSettings((current) => ({
                        ...current,
                        background_concurrency_limit: Math.max(1, Number.parseInt(event.target.value || "1", 10) || 1),
                      }))
                    }
                  />
                </label>

                <label className="field">
                  <span>{t("field.codexPath")}</span>
                  <input
                    value={settings.codex_path || defaultCodexPath(settings.model_provider)}
                    onChange={(event) => onChangeSettings((current) => ({ ...current, codex_path: event.target.value }))}
                    disabled={runtimeBusy}
                  />
                </label>
              </div>
            </div>

            {/* Toggle options */}
            <div style={{ display: "flex", flexDirection: "column", gap: "6px", marginTop: "4px" }}>
              <ToggleRow
                checked={Boolean(settings.allow_push)}
                onChange={(event) => onChangeSettings((current) => ({ ...current, allow_push: event.target.checked }))}
                label={t("option.allowPushAfterSafeRuns")}
                disabled={runtimeBusy}
              />
              <ToggleRow
                checked={Boolean(settings.require_checkpoint_approval)}
                onChange={(event) =>
                  onChangeSettings((current) => ({
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

        {/* ── Remote Monitor (full width row) ── */}
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
      </div>
    </section>
  );
}
