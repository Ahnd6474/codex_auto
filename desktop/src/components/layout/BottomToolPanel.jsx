import { useMemo } from "react";
import { useI18n } from "../../i18n";
import { displayStatus } from "../../locale";
import { statusTone } from "../../utils";

function ToolTab({ value, activeTab, onChange, label }) {
  return (
    <button className={`tool-tab ${activeTab === value ? "active" : ""}`} onClick={() => onChange(value)} type="button">
      {label}
    </button>
  );
}

export function BottomToolPanel({ activeTab, onChangeTab, data }) {
  const tokenUsage = data?.token_usage || {};
  const codexStatus = data?.codex_status || {};
  const account = codexStatus.account || {};
  const rateLimits = codexStatus.rate_limits?.items || [];
  const primaryLimit = rateLimits[0] || {};
  const primaryWindow = primaryLimit.primary || null;
  const secondaryWindow = primaryLimit.secondary || null;
  const gitStatus = data?.git_status || {};
  const testRuns = data?.test_runs || [];
  const serializedEventJson = useMemo(() => JSON.stringify(data?.event_json || {}, null, 2), [data?.event_json]);
  const { language, t } = useI18n();

  return (
    <section className="tool-window">
      <div className="tool-window__header">
        <div className="tool-tabs">
          <ToolTab value="json" activeTab={activeTab} onChange={onChangeTab} label={t("tool.eventJson")} />
          <ToolTab value="tokens" activeTab={activeTab} onChange={onChangeTab} label={t("tool.tokenUsage")} />
          <ToolTab value="tests" activeTab={activeTab} onChange={onChangeTab} label={t("test.result")} />
          <ToolTab value="git" activeTab={activeTab} onChange={onChangeTab} label={t("tool.gitSafeRevision")} />
        </div>
      </div>

      {activeTab === "json" ? (
        <div className="tool-window__body tool-window__body--log">
          <pre>{serializedEventJson}</pre>
        </div>
      ) : null}

      {activeTab === "tokens" ? (
        <div className="tool-window__body">
          <div className="metrics-grid">
            <div className="metric-card">
              <span>{t("common.input")}</span>
              <strong>{tokenUsage.input_tokens ?? 0}</strong>
            </div>
            <div className="metric-card">
              <span>{t("common.output")}</span>
              <strong>{tokenUsage.output_tokens ?? 0}</strong>
            </div>
            <div className="metric-card">
              <span>{t("common.total")}</span>
              <strong>{tokenUsage.total_tokens ?? 0}</strong>
            </div>
            <div className="metric-card">
              <span>{language === "ko" ? "요금제" : "Plan"}</span>
              <strong>{account.plan_type || t("common.unavailable")}</strong>
            </div>
            <div className="metric-card">
              <span>{language === "ko" ? "남은 사용량" : "Remaining"}</span>
              <strong>{primaryWindow ? `${primaryWindow.remaining_percent ?? 0}%` : t("common.unavailable")}</strong>
            </div>
          </div>
          <div className="dense-list">
            <div className="dense-row">
              <strong>{language === "ko" ? "인증 방식" : "Auth"}</strong>
              <span>{account.type || t("common.unavailable")}</span>
            </div>
            <div className="dense-row">
              <strong>{language === "ko" ? "계정" : "Account"}</strong>
              <span>{account.email || t("common.unavailable")}</span>
            </div>
            <div className="dense-row">
              <strong>{language === "ko" ? "현재 창" : "Primary Window"}</strong>
              <span>
                {primaryWindow
                  ? `${primaryWindow.used_percent ?? 0}% used, reset ${primaryWindow.resets_at || t("common.unavailable")}`
                  : codexStatus.error || t("common.unavailable")}
              </span>
            </div>
            <div className="dense-row">
              <strong>{language === "ko" ? "주간 창" : "Secondary Window"}</strong>
              <span>
                {secondaryWindow
                  ? `${secondaryWindow.used_percent ?? 0}% used, reset ${secondaryWindow.resets_at || t("common.unavailable")}`
                  : t("common.unavailable")}
              </span>
            </div>
          </div>
        </div>
      ) : null}

      {activeTab === "tests" ? (
        <div className="tool-window__body">
          <div className="dense-list">
            {testRuns.length ? (
              testRuns.map((run, index) => (
                <div className="dense-row" key={`${run.label || "test"}-${index}`}>
                  <div className="dense-row__title">
                    <strong>{run.label || t("test.run")}</strong>
                    <span className={`status-badge status-badge--${statusTone(run.returncode === 0 ? "completed" : "failed")}`}>
                      {run.returncode === 0 ? t("test.passed") : t("test.failed")}
                    </span>
                  </div>
                  <span>{run.command}</span>
                  <span>{run.summary}</span>
                </div>
              ))
            ) : (
              <div className="empty-block">{t("test.noRuns")}</div>
            )}
          </div>
        </div>
      ) : null}

      {activeTab === "git" ? (
        <div className="tool-window__body">
          <div className="dense-list">
            <div className="dense-row">
              <strong>{t("common.branch")}</strong>
              <span>{gitStatus.branch || t("common.unknown")}</span>
            </div>
            <div className="dense-row">
              <strong>{t("common.status")}</strong>
              <span>{displayStatus(gitStatus.current_status || "unknown", language)}</span>
            </div>
            <div className="dense-row">
              <strong>{t("dashboard.lastSafeRevision")}</strong>
              <span>{gitStatus.safe_revision || t("common.unavailable")}</span>
            </div>
            <div className="dense-row">
              <strong>{language === "ko" ? "마지막 커밋" : "Last Commit"}</strong>
              <span>{gitStatus.last_commit_hash || t("common.none")}</span>
            </div>
            <div className="dense-row">
              <strong>{t("sidebar.checkpoints")}</strong>
              <span>{gitStatus.current_checkpoint_id || t("common.none")}</span>
            </div>
            <div className="dense-row">
              <strong>{language === "ko" ? "승인 대기" : "Approval Pending"}</strong>
              <span>{gitStatus.pending_checkpoint_approval ? t("common.yes") : t("common.no")}</span>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
