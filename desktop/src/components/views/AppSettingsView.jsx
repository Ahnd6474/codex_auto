import { useI18n } from "../../i18n";
import {
  applyProviderDefaults,
  defaultCodexPath,
  defaultProviderApiKeyEnv,
  defaultProviderBaseUrl,
  normalizeMemoryBudgetGiB,
  normalizeDashboardVisibility,
  REASONING_OPTIONS,
  reasoningEffortLabel,
} from "../../utils";

export function AppSettingsView({
  settings,
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
  const dashboardVisibility = normalizeDashboardVisibility(settings?.dashboard_visibility);
  const interfaceBusy = false;
  const runtimeBusy = busy;
  const autoParallelWorkers = String(settings?.parallel_worker_mode || "auto").trim().toLowerCase() !== "manual";
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

  return (
    <section className="workspace-view">
      <div className="view-header">
        <div>
          <span className="eyebrow">{t("tab.programSettings")}</span>
          <h2>{t("tab.programSettings")}</h2>
          <p>{t("settings.programSettingsDescription")}</p>
        </div>
      </div>

      <div className="form-layout">
        <div className="form-section">
          <div className="subsection">
            <div className="subsection__header">
              <strong>{t("settings.application")}</strong>
            </div>
            <label className="field">
              <span>{t("common.language")}</span>
              <select value={language} onChange={(event) => setLanguage(event.target.value)} disabled={interfaceBusy}>
                {languageOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="choice-radio">
              <input
                type="checkbox"
                checked={settings.ui_theme === "light"}
                onChange={(event) => onChangeSettings((current) => ({ ...current, ui_theme: event.target.checked ? "light" : "dark" }))}
                disabled={interfaceBusy}
              />
              <span>{t("option.lightMode")}</span>
            </label>
            <label className="choice-radio">
              <input
                type="checkbox"
                checked={Boolean(settings.developer_mode)}
                onChange={(event) => onChangeSettings((current) => ({ ...current, developer_mode: event.target.checked }))}
                disabled={interfaceBusy}
              />
              <span>{t("option.developerMode")}</span>
            </label>
          </div>

          <div className="subsection">
            <div className="subsection__header">
              <strong>{t("settings.dashboardPreferences")}</strong>
            </div>
            <div className="choice-list">
              {dashboardOptions.map(([key, label]) => (
                <label className="choice-radio" key={key}>
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
                    disabled={interfaceBusy}
                  />
                  <span>{label}</span>
                </label>
              ))}
            </div>
          </div>
        </div>

        <div className="form-section">
          <div className="subsection">
            <div className="subsection__header">
              <strong>{t("settings.executionDefaults")}</strong>
            </div>
            <div className="choice-grid">
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
                  <option value="openai">{t("option.providerOpenAI")}</option>
                  <option value="gemini">Gemini CLI</option>
                  <option value="openrouter">{t("option.providerOpenRouter")}</option>
                  <option value="opencdk">{t("option.providerOpenCDK")}</option>
                  <option value="local_openai">{t("option.providerLocalCompatible")}</option>
                  <option value="oss">{t("option.providerOSS")}</option>
                </select>
              </label>
              {String(settings.model_provider || "openai").trim().toLowerCase() === "oss" ? (
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
              {String(settings.model_provider || "openai").trim().toLowerCase() !== "oss" ? (
                <label className="field">
                  <span>{t("field.providerBaseUrl")}</span>
                  <input
                    value={settings.provider_base_url || defaultProviderBaseUrl(settings.model_provider)}
                    onChange={(event) => onChangeSettings((current) => ({ ...current, provider_base_url: event.target.value }))}
                    disabled={runtimeBusy}
                  />
                </label>
              ) : null}
              {String(settings.model_provider || "openai").trim().toLowerCase() !== "oss" ? (
                <label className="field">
                  <span>{t("field.providerApiKeyEnv")}</span>
                  <input
                    value={settings.provider_api_key_env || defaultProviderApiKeyEnv(settings.model_provider)}
                    onChange={(event) => onChangeSettings((current) => ({ ...current, provider_api_key_env: event.target.value }))}
                    disabled={runtimeBusy}
                  />
                </label>
              ) : null}
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
              <div className="field">
                <span>{t("field.executionMode")}</span>
                <strong>{t("option.executionParallel")}</strong>
              </div>
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
                  disabled={interfaceBusy}
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
              <label className="choice-radio">
                <input
                  type="checkbox"
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
                  disabled={runtimeBusy}
                />
                <span>{t("preset.auto")}</span>
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
            <div className="choice-list">
              <label className="choice-radio">
                <input
                  type="checkbox"
                  checked={Boolean(settings.allow_push)}
                  onChange={(event) => onChangeSettings((current) => ({ ...current, allow_push: event.target.checked }))}
                  disabled={runtimeBusy}
                />
                <span>{t("option.allowPushAfterSafeRuns")}</span>
              </label>
              <label className="choice-radio">
                <input
                  type="checkbox"
                  checked={Boolean(settings.require_checkpoint_approval)}
                  onChange={(event) =>
                    onChangeSettings((current) => ({
                      ...current,
                      require_checkpoint_approval: event.target.checked,
                    }))
                  }
                  disabled={runtimeBusy}
                />
                <span>{t("option.requireCheckpointApproval")}</span>
              </label>
            </div>
          </div>
        </div>

        <div className="form-section">
          <div className="subsection">
            <div className="subsection__header">
              <strong>{t("run.remoteMonitor")}</strong>
              <span className={`status-badge status-badge--${shareServer?.running ? "success" : "neutral"}`}>
                {shareServer?.running ? t("common.on") : t("common.off")}
              </span>
            </div>
            <p>{t("run.shareDescription")}</p>
            <p>{t("run.sharePoll")}</p>
            <div className="share-panel">
              <div className="sidebar-item">
                <span>{t("run.shareBindHost")}</span>
                <strong>0.0.0.0</strong>
              </div>
            </div>
            {activeShare?.share_url ? (
              <div className="share-panel">
                <label className="field field--wide">
                  <span>{t("run.shareLink")}</span>
                  <input value={activeShare.share_url} readOnly />
                </label>
                <div className="share-meta">
                  <span>{t("run.shareExpires", { expiresAt: activeShare.expires_at || t("common.unavailable") })}</span>
                </div>
                <div className="action-row">
                  <button className="toolbar-button toolbar-button--accent" onClick={onCopyShareLink} type="button" disabled={shareBusy}>
                    {t("action.copyLink")}
                  </button>
                  <button className="toolbar-button toolbar-button--ghost" onClick={onRevokeShareLink} type="button" disabled={shareBusy}>
                    {t("action.revokeLink")}
                  </button>
                </div>
              </div>
            ) : (
              <div className="empty-block">{t("run.noShareSession")}</div>
            )}
            <div className="action-row">
              <button className="toolbar-button" onClick={onGenerateShareLink} type="button" disabled={shareBusy}>
                {t("action.generateShareLink")}
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
