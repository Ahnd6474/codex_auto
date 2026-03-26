import { useI18n } from "../../i18n";

export function AppSettingsView({
  settings,
  shareSettings,
  shareDetail,
  busy,
  onChangeSettings,
  onGenerateShareLink,
  onCopyShareLink,
  onRevokeShareLink,
  onChangeShareSettings,
}) {
  const { language, languageOptions, setLanguage, t } = useI18n();
  const activeShare = shareDetail?.active_session || null;
  const shareServer = shareDetail?.server || null;

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
              <span>{t("settings.applicationDescription")}</span>
            </div>
            <label className="field">
              <span>{t("common.language")}</span>
              <select value={language} onChange={(event) => setLanguage(event.target.value)} disabled={busy}>
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
                disabled={busy}
              />
              <span>{t("option.lightMode")}</span>
            </label>
            <label className="choice-radio">
              <input
                type="checkbox"
                checked={Boolean(settings.developer_mode)}
                onChange={(event) => onChangeSettings((current) => ({ ...current, developer_mode: event.target.checked }))}
                disabled={busy}
              />
              <span>{t("option.developerMode")}</span>
            </label>
          </div>
        </div>

        <div className="form-section">
          <div className="subsection">
            <div className="subsection__header">
              <strong>{t("settings.executionDefaults")}</strong>
              <span>{t("settings.executionDefaultsDescription")}</span>
            </div>
            <div className="choice-grid">
              <label className="field">
                <span>{t("field.approvalMode")}</span>
                <select
                  value={settings.approval_mode || "never"}
                  onChange={(event) => onChangeSettings((current) => ({ ...current, approval_mode: event.target.value }))}
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
                  value={settings.sandbox_mode || "danger-full-access"}
                  onChange={(event) => onChangeSettings((current) => ({ ...current, sandbox_mode: event.target.value }))}
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
                  value={settings.checkpoint_interval_blocks || 1}
                  onChange={(event) =>
                    onChangeSettings((current) => ({
                      ...current,
                      checkpoint_interval_blocks: Math.max(1, Number.parseInt(event.target.value || "1", 10) || 1),
                    }))
                  }
                  disabled={busy}
                />
              </label>
              <label className="field">
                <span>{t("field.codexPath")}</span>
                <input
                  value={settings.codex_path || "codex.cmd"}
                  onChange={(event) => onChangeSettings((current) => ({ ...current, codex_path: event.target.value }))}
                  disabled={busy}
                />
              </label>
            </div>
            <div className="choice-list">
              <label className="choice-radio">
                <input
                  type="checkbox"
                  checked={Boolean(settings.allow_push)}
                  onChange={(event) => onChangeSettings((current) => ({ ...current, allow_push: event.target.checked }))}
                  disabled={busy}
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
              <strong>{t("run.remoteMonitor")}</strong>
              <span className={`status-badge status-badge--${shareServer?.running ? "success" : "neutral"}`}>
                {shareServer?.running ? t("common.on") : t("common.off")}
              </span>
            </div>
            <p>{t("run.shareDescription")}</p>
            <p>{t("run.sharePoll")}</p>
            <div className="share-panel">
              <label className="field">
                <span>{t("run.shareBindHost")}</span>
                <select
                  value={shareSettings?.bind_host || "127.0.0.1"}
                  onChange={(event) =>
                    onChangeShareSettings((current) => ({
                      ...(current || {}),
                      bind_host: event.target.value,
                    }))
                  }
                  disabled={busy}
                >
                  <option value="127.0.0.1">{t("run.shareBindLocal")}</option>
                  <option value="0.0.0.0">{t("run.shareBindNetwork")}</option>
                </select>
              </label>
              <label className="field field--wide">
                <span>{t("run.sharePublicBaseUrl")}</span>
                <input
                  value={shareSettings?.public_base_url || ""}
                  onChange={(event) =>
                    onChangeShareSettings((current) => ({
                      ...(current || {}),
                      public_base_url: event.target.value,
                    }))
                  }
                  placeholder="https://your-public-share.example"
                  disabled={busy}
                />
              </label>
              <p className="muted">{t("run.shareExternalHint")}</p>
            </div>
            {activeShare?.share_url ? (
              <div className="share-panel">
                <label className="field field--wide">
                  <span>{t("run.shareLink")}</span>
                  <input value={activeShare.share_url} readOnly />
                </label>
                <div className="share-meta">
                  <span>{t("run.shareExpires", { expiresAt: activeShare.expires_at || t("common.unavailable") })}</span>
                  <span>{t("run.shareServerAddress", { address: shareServer?.base_url || t("common.unavailable") })}</span>
                </div>
                {activeShare?.local_url && activeShare.local_url !== activeShare.share_url ? (
                  <label className="field field--wide">
                    <span>{t("run.shareLocalLink")}</span>
                    <input value={activeShare.local_url} readOnly />
                  </label>
                ) : null}
                <div className="action-row">
                  <button className="toolbar-button toolbar-button--accent" onClick={onCopyShareLink} type="button" disabled={busy}>
                    {t("action.copyLink")}
                  </button>
                  <button className="toolbar-button toolbar-button--ghost" onClick={onRevokeShareLink} type="button" disabled={busy}>
                    {t("action.revokeLink")}
                  </button>
                </div>
              </div>
            ) : (
              <div className="empty-block">{t("run.noShareSession")}</div>
            )}
            <div className="action-row">
              <button className="toolbar-button" onClick={onGenerateShareLink} type="button" disabled={busy}>
                {t("action.generateShareLink")}
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
