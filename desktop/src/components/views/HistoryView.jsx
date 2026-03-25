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

  const passes = (history?.passes || []).map((pass, index) => (
    <div className="dense-row" key={`pass-${index}`}>
      <div className="dense-row__title">
        <strong>{pass.pass_type || "pass"}</strong>
        <span>{pass.returncode === 0 ? "ok" : `exit ${pass.returncode}`}</span>
      </div>
      <span>{(pass.changed_files || []).join(", ") || "No changed files recorded"}</span>
      <span>{pass.last_message || "No final message recorded"}</span>
    </div>
  ));

  const events = (history?.ui_events || []).map((event, index) => (
    <div className="dense-row" key={`event-${index}`}>
      <div className="dense-row__title">
        <strong>{event.event_type}</strong>
        <span>{event.timestamp}</span>
      </div>
      <span>{event.message}</span>
    </div>
  ));

  return (
    <section className="workspace-view">
      <div className="view-header">
        <div>
          <span className="eyebrow">History</span>
          <h2>Recent Activity</h2>
          <p>Runs, passes, and UI events stay browseable as dense operational history rather than disappearing behind transient banners.</p>
        </div>
      </div>

      <div className="history-grid">
        <HistoryRow title="Recent Blocks" tone="info" lines={blocks} />
        <HistoryRow title="Recent Passes" tone="neutral" lines={passes} />
        <HistoryRow title="UI Events" tone="neutral" lines={events} />
      </div>
    </section>
  );
}
