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
  const gitStatus = data?.git_status || {};
  const testRuns = data?.test_runs || [];

  return (
    <section className="tool-window">
      <div className="tool-window__header">
        <div className="tool-tabs">
          <ToolTab value="execution" activeTab={activeTab} onChange={onChangeTab} label="Execution Log" />
          <ToolTab value="json" activeTab={activeTab} onChange={onChangeTab} label="Event JSON" />
          <ToolTab value="tokens" activeTab={activeTab} onChange={onChangeTab} label="Token Usage" />
          <ToolTab value="tests" activeTab={activeTab} onChange={onChangeTab} label="Test Results" />
          <ToolTab value="git" activeTab={activeTab} onChange={onChangeTab} label="Git / Safe Revision" />
        </div>
      </div>

      {activeTab === "execution" ? (
        <div className="tool-window__body tool-window__body--log">
          <pre>{(data?.execution_log_lines || ["No execution activity yet."]).join("\n")}</pre>
        </div>
      ) : null}

      {activeTab === "json" ? (
        <div className="tool-window__body tool-window__body--log">
          <pre>{JSON.stringify(data?.event_json || {}, null, 2)}</pre>
        </div>
      ) : null}

      {activeTab === "tokens" ? (
        <div className="tool-window__body">
          <div className="metrics-grid">
            <div className="metric-card">
              <span>Input</span>
              <strong>{tokenUsage.input_tokens ?? 0}</strong>
            </div>
            <div className="metric-card">
              <span>Output</span>
              <strong>{tokenUsage.output_tokens ?? 0}</strong>
            </div>
            <div className="metric-card">
              <span>Total</span>
              <strong>{tokenUsage.total_tokens ?? 0}</strong>
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
                    <strong>{run.label || "test run"}</strong>
                    <span className={`status-badge status-badge--${statusTone(run.returncode === 0 ? "completed" : "failed")}`}>
                      {run.returncode === 0 ? "passed" : "failed"}
                    </span>
                  </div>
                  <span>{run.command}</span>
                  <span>{run.summary}</span>
                </div>
              ))
            ) : (
              <div className="empty-block">No test runs recorded yet.</div>
            )}
          </div>
        </div>
      ) : null}

      {activeTab === "git" ? (
        <div className="tool-window__body">
          <div className="dense-list">
            <div className="dense-row">
              <strong>Branch</strong>
              <span>{gitStatus.branch || "Unknown"}</span>
            </div>
            <div className="dense-row">
              <strong>Status</strong>
              <span>{gitStatus.current_status || "Unknown"}</span>
            </div>
            <div className="dense-row">
              <strong>Last Safe Revision</strong>
              <span>{gitStatus.safe_revision || "Not recorded yet"}</span>
            </div>
            <div className="dense-row">
              <strong>Last Commit</strong>
              <span>{gitStatus.last_commit_hash || "None"}</span>
            </div>
            <div className="dense-row">
              <strong>Checkpoint</strong>
              <span>{gitStatus.current_checkpoint_id || "None"}</span>
            </div>
            <div className="dense-row">
              <strong>Approval Pending</strong>
              <span>{gitStatus.pending_checkpoint_approval ? "Yes" : "No"}</span>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
