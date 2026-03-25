export function ReportsView({ reports }) {
  return (
    <section className="workspace-view">
      <div className="view-header">
        <div>
          <span className="eyebrow">Reports</span>
          <h2>Reports</h2>
        </div>
      </div>

      <div className="overview-grid">
        <div className="content-card">
          <div className="content-card__header">
            <strong>Closeout Report</strong>
          </div>
          <pre>{reports?.closeout_report_text || "No closeout report yet."}</pre>
        </div>

        <div className="content-card">
          <div className="content-card__header">
            <strong>Latest Report JSON</strong>
          </div>
          <pre>{JSON.stringify(reports?.latest_report_json || {}, null, 2)}</pre>
        </div>
      </div>

      <div className="overview-grid">
        <div className="content-card">
          <div className="content-card__header">
            <strong>Block Review</strong>
          </div>
          <pre>{reports?.block_review_text || "No block review yet."}</pre>
        </div>

        <div className="content-card">
          <div className="content-card__header">
            <strong>Attempt History</strong>
          </div>
          <pre>{reports?.attempt_history_text || "No attempt history yet."}</pre>
        </div>
      </div>
    </section>
  );
}
