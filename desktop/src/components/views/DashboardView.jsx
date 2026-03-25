import { runtimeSummary, statusTone } from "../../utils";

function Stat({ label, value, tone = "neutral" }) {
  return (
    <div className={`metric-card metric-card--${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function DashboardView({ detail, planDraft, modelPresets, activeJob }) {
  const usage = detail?.snapshot?.recent_usage || {};
  const pendingSteps = (planDraft?.steps || []).filter((step) => step.status !== "completed");

  return (
    <section className="workspace-view">
      <div className="view-header">
        <div>
          <span className="eyebrow">Dashboard</span>
          <h2>{detail?.project?.display_name || detail?.project?.slug || "No project selected"}</h2>
        </div>
      </div>

      <div className="metrics-grid">
        <Stat label="Status" value={activeJob?.status === "running" ? `${activeJob.command} running` : detail?.project?.current_status || "idle"} tone={statusTone(detail?.project?.current_status)} />
        <Stat label="Remaining Steps" value={pendingSteps.length} tone="info" />
        <Stat label="Checkpoint Pending" value={detail?.checkpoints?.pending ? "Yes" : "No"} tone={detail?.checkpoints?.pending ? "warning" : "neutral"} />
        <Stat label="Last Safe Revision" value={detail?.project?.current_safe_revision || "Not recorded"} />
        <Stat label="Input Tokens" value={usage.input_tokens ?? 0} />
        <Stat label="Output Tokens" value={usage.output_tokens ?? 0} />
      </div>

      <div className="overview-grid">
        <div className="content-card">
          <div className="content-card__header">
            <strong>Runtime</strong>
          </div>
          <p>{runtimeSummary(detail?.runtime || {}, modelPresets)}</p>
          <p>Verification: {detail?.runtime?.test_cmd || "python -m pytest"}</p>
          <p>Branch: {detail?.project?.branch || "Unknown"}</p>
          <p>Origin: {detail?.project?.origin_url || "Local-only"}</p>
        </div>

        <div className="content-card">
          <div className="content-card__header">
            <strong>Checkpoint</strong>
          </div>
          {detail?.checkpoints?.pending ? (
            <>
              <p>{detail.checkpoints.pending.checkpoint_id}: {detail.checkpoints.pending.title}</p>
              <p>Target block {detail.checkpoints.pending.target_block}</p>
              <p>Status: {detail.checkpoints.pending.status}</p>
            </>
          ) : (
            <div className="empty-block">No checkpoint is waiting for review.</div>
          )}
        </div>
      </div>
    </section>
  );
}
