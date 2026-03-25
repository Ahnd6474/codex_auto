export function OverviewView({ detail }) {
  return (
    <section className="workspace-view">
      <div className="view-header">
        <div>
          <span className="eyebrow">Overview</span>
          <h2>Workspace Layout</h2>
        </div>
      </div>

      <div className="overview-grid">
        <div className="content-card">
          <div className="content-card__header">
            <strong>Summary</strong>
          </div>
          <pre>{detail?.summary || "No project summary yet."}</pre>
        </div>

        <div className="content-card">
          <div className="content-card__header">
            <strong>Managed Paths</strong>
          </div>
          <div className="dense-list">
            {Object.entries(detail?.files || {}).map(([key, value]) => (
              <div className="dense-row" key={key}>
                <strong>{key}</strong>
                <span>{value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
