export function OverviewView({ detail, workspaceTree }) {
  return (
    <section className="workspace-view">
      <div className="view-header">
        <div>
          <span className="eyebrow">Project Overview</span>
          <h2>Workspace Layout</h2>
          <p>The managed project keeps repository contents separate from docs, logs, reports, state, and memory so multi-repo automation stays traceable.</p>
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

      <div className="content-card">
        <div className="content-card__header">
          <strong>Workspace Explorer Snapshot</strong>
        </div>
        <div className="dense-list">
          {(workspaceTree || []).map((section) => (
            <div className="dense-row" key={section.path}>
              <strong>{section.label}</strong>
              <span>{section.path}</span>
              <span>{(section.children || []).map((child) => child.label).join(", ") || "No entries"}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
