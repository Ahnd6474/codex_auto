import { statusTone } from "../../utils";

function HistoryRow({ title, tone, lines }) {
  return (
    <div className="content-card">
      <div className="content-card__header">
        <strong>{title}</strong>
        <span className={`status-badge status-badge--${tone}`}>{lines.length}</span>
      </div>
      <div className="dense-list">
        {lines.length ? lines : <div className="empty-block">No entries.</div>}
      </div>
    </div>
  );
}

export function HistoryView({ history }) {
  const blocks = (history?.blocks || []).map((block, index) => (
    <div className="dense-row" key={`block-${index}`}>
      <div className="dense-row__title">
        <strong>block {block.block_index}</strong>
        <span className={`status-badge status-badge--${statusTone(block.status)}`}>{block.status}</span>
      </div>
      <span>{block.selected_task || "No task title"}</span>
      <span>{block.test_summary || "No test summary"}</span>
    </div>
  ));

  return (
    <section className="workspace-view">
      <div className="view-header">
        <div>
          <span className="eyebrow">History</span>
          <h2>Recent Activity</h2>
        </div>
      </div>

      <div className="history-grid history-grid--single">
        <HistoryRow title="Recent Blocks" tone="info" lines={blocks} />
      </div>
    </section>
  );
}
