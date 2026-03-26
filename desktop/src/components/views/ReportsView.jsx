import { useMemo } from "react";
import { useI18n } from "../../i18n";

export function ReportsView({ reports }) {
  const serializedLatestReport = useMemo(() => JSON.stringify(reports?.latest_report_json || {}, null, 2), [reports?.latest_report_json]);
  const { t } = useI18n();

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
            <strong>{t("reports.closeoutReport")}</strong>
          </div>
          <pre>{reports?.closeout_report_text || t("reports.noCloseoutReport")}</pre>
        </div>

        <div className="content-card">
          <div className="content-card__header">
            <strong>{t("reports.json")}</strong>
          </div>
          <pre>{serializedLatestReport}</pre>
        </div>
      </div>

      <div className="overview-grid">
        <div className="content-card">
          <div className="content-card__header">
            <strong>{t("reports.blockReview")}</strong>
          </div>
          <pre>{reports?.block_review_text || t("reports.noBlockReview")}</pre>
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
