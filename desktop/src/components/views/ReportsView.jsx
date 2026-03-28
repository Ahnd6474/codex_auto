import { useI18n } from "../../i18n";

export function ReportsView({ reports }) {
  const { t } = useI18n();
  const wordReportPath = String(reports?.word_report_path || "").trim();
  const wordReportEnabled = Boolean(reports?.word_report_enabled);

  return (
    <section className="workspace-view">
      <div className="view-header">
        <div>
          <span className="eyebrow">{t("reports.reports")}</span>
          <h2>{t("reports.reports")}</h2>
        </div>
      </div>

      <div className="overview-grid">
        <div className="content-card">
          <div className="content-card__header">
            <strong>ML Experiment Report</strong>
          </div>
          <pre>{reports?.ml_experiment_report_text || "No ML experiment report yet."}</pre>
        </div>

        <div className="content-card">
          <div className="content-card__header">
            <strong>{t("reports.closeoutReport")}</strong>
          </div>
          <pre>{reports?.closeout_report_text || t("reports.noCloseoutReport")}</pre>
          {wordReportPath ? <p>{t("reports.wordReportReady", { path: wordReportPath })}</p> : null}
          {!wordReportPath && !wordReportEnabled ? <p>{t("reports.wordReportDisabled")}</p> : null}
        </div>

        <div className="content-card">
          <div className="content-card__header">
            <strong>{t("reports.attemptHistory")}</strong>
          </div>
          <pre>{reports?.attempt_history_text || t("reports.historyEmpty")}</pre>
        </div>
      </div>
    </section>
  );
}
