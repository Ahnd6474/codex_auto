import { useEffect, useRef, useState } from "react";
import { useI18n } from "../../i18n";
import { displayStatus } from "../../locale";
import { effectiveStepStatus, reasoningEffortLabel, runtimeSummary, statusTone } from "../../utils";

function DocumentIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M14 2v6h6" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M8 13h8M8 17h6M8 9h2" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

function DocumentCard({ title, kind, path, status, muted = false }) {
  return (
    <div className={`details-document ${muted ? "details-document--muted" : ""}`.trim()}>
      <div className="details-document__icon">
        <DocumentIcon />
      </div>
      <div className="details-document__body">
        <strong>{title}</strong>
        <span className="details-document__kind">{kind}</span>
        <span className="details-document__path">{path}</span>
      </div>
      <span className={`status-badge status-badge--${statusTone(status)}`}>{status}</span>
    </div>
  );
}

export function DetailsPane({ detail, planDraft, selectedStepId, modelPresets, onHide }) {
  const { t } = useI18n();
  const [detailsTab, setDetailsTab] = useState("inspector");
  const outputRef = useRef(null);
  const selectedStep = (planDraft?.steps || []).find((step) => step.step_id === selectedStepId) || null;
  const pendingCheckpoint = detail?.checkpoints?.pending || null;
  const selectedStepStatus = effectiveStepStatus(selectedStep, detail?.project?.current_status || "");
  const processOutput = detail?.subprocess_output || detail?.agent_output || detail?.process_log || "";
  const closeoutReportPath = String(detail?.files?.closeout_report_file || "").trim();
  const wordReportActualPath = String(detail?.reports?.word_report_path || "").trim();
  const wordReportTargetPath = String(detail?.files?.word_report_file || "").trim();
  const powerpointReportActualPath = String(detail?.reports?.powerpoint_report_path || "").trim();
  const powerpointTargetPath = String(detail?.reports?.powerpoint_report_target_path || detail?.files?.powerpoint_report_file || "").trim();
  const mlReportPath = String(detail?.files?.ml_experiment_report_file || "").trim();
  const documents = [
    {
      title: t("reports.closeoutReport"),
      kind: "Markdown",
      path: closeoutReportPath || "docs/CLOSEOUT_REPORT.md",
      status: detail?.reports?.closeout_report_text ? "completed" : "pending",
      muted: !detail?.reports?.closeout_report_text,
    },
    {
      title: "Word Report",
      kind: ".docx",
      path: wordReportActualPath || wordReportTargetPath || "reports/CLOSEOUT_REPORT.docx",
      status: wordReportActualPath ? "completed" : (detail?.runtime?.generate_word_report ? "pending" : "paused"),
      muted: !wordReportActualPath,
    },
    {
      title: "PowerPoint Report",
      kind: ".pptx",
      path: powerpointReportActualPath || powerpointTargetPath || "reports/CLOSEOUT_REPORT.pptx",
      status: powerpointReportActualPath ? "completed" : "pending",
      muted: !powerpointReportActualPath,
    },
    {
      title: "ML Experiment Report",
      kind: "Markdown",
      path: mlReportPath || "docs/ML_EXPERIMENT_REPORT.md",
      status: detail?.reports?.ml_experiment_report_text ? "completed" : "pending",
      muted: !detail?.reports?.ml_experiment_report_text,
    },
  ];

  // Auto-scroll output to bottom when new content arrives
  useEffect(() => {
    if (detailsTab === "output" && outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [processOutput, detailsTab]);

  return (
    <aside className="details-pane">
      {/* Header with title + hide */}
      <div className="tool-window__header" style={{ margin: "-8px -8px 0", padding: "0 6px", borderBottom: "1px solid var(--border)" }}>
        <div className="tool-tabs">
          <button
            className={`tool-tab ${detailsTab === "inspector" ? "active" : ""}`}
            onClick={() => setDetailsTab("inspector")}
            type="button"
          >
            Inspector
          </button>
          <button
            className={`tool-tab ${detailsTab === "output" ? "active" : ""}`}
            onClick={() => setDetailsTab("output")}
            type="button"
          >
            Output
            {processOutput ? <span className="details-output-dot" /> : null}
          </button>
        </div>
        {onHide ? (
          <div className="tool-window__header-actions">
            <button
              className="tool-window__header-btn"
              onClick={onHide}
              type="button"
              title={`${t("action.dismiss")} (Alt+R)`}
              aria-label="Hide inspector"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
        ) : null}
      </div>

      {/* ── Output tab ── */}
      {detailsTab === "output" ? (
        <div className="details-output-panel">
          {processOutput ? (
            <pre ref={outputRef} className="details-output-pre">{processOutput}</pre>
          ) : (
            <div className="details-output-empty">
              <svg viewBox="0 0 24 24" fill="none" width="24" height="24">
                <rect x="3" y="4" width="18" height="14" rx="2" stroke="currentColor" strokeWidth="1.6" />
                <path d="M7 8h2M7 12h10M7 16h6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
              </svg>
              <span>No output yet</span>
            </div>
          )}
        </div>
      ) : null}

      {/* ── Inspector tab ── */}
      {detailsTab === "inspector" ? <>
      <section className="details-card">
        <div className="details-card__header">
          <strong>{t("common.project")}</strong>
          <span className={`status-badge status-badge--${statusTone(detail?.project?.current_status)}`}>
            {displayStatus(detail?.project?.current_status || "idle", "en")}
          </span>
        </div>
        <dl className="details-list">
          <div>
            <dt>{t("common.name")}</dt>
            <dd>{detail?.project?.display_name || detail?.project?.slug || t("project.none")}</dd>
          </div>
          <div>
            <dt>{t("common.branch")}</dt>
            <dd>{detail?.project?.branch || t("common.unknown")}</dd>
          </div>
          <div>
            <dt>Path</dt>
            <dd>{detail?.project?.repo_path || t("common.unknown")}</dd>
          </div>
          <div>
            <dt>Model</dt>
            <dd>{runtimeSummary(detail?.runtime || {}, modelPresets)}</dd>
          </div>
          <div>
            <dt>Revision</dt>
            <dd>{detail?.project?.current_safe_revision || "—"}</dd>
          </div>
        </dl>
      </section>

      <section className="details-card">
        <div className="details-card__header">
          <strong>Step</strong>
          <span className={`status-badge status-badge--${statusTone(selectedStepStatus)}`}>
            {selectedStep ? displayStatus(selectedStepStatus, "en") : "—"}
          </span>
        </div>
        {selectedStep ? (
          <div className="details-text">
            <strong>{selectedStep.step_id}: {selectedStep.title}</strong>
            <p style={{ margin: "4px 0", color: "var(--text-muted)" }}>{selectedStep.display_description}</p>
            <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>
              Effort: {reasoningEffortLabel(selectedStep.reasoning_effort || detail?.runtime?.effort || "high")}
            </p>
            {selectedStep.success_criteria ? (
              <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>{selectedStep.success_criteria}</p>
            ) : null}
            {selectedStep.deadline_at ? (
              <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>
                Deadline: {selectedStep.deadline_at}
              </p>
            ) : null}
          </div>
        ) : (
          <div className="details-text" style={{ color: "var(--text-dim)", fontSize: "11px" }}>
            {t("sidebar.noRecordedCheckpoints") || "Select a step to inspect."}
          </div>
        )}
      </section>

      {pendingCheckpoint ? (
        <section className="details-card">
          <div className="details-card__header">
            <strong>Checkpoint</strong>
            <span className={`status-badge status-badge--${statusTone(pendingCheckpoint.status)}`}>
              {displayStatus(pendingCheckpoint.status || "pending", "en")}
            </span>
          </div>
          <div className="details-text">
            <strong>{pendingCheckpoint.checkpoint_id}</strong>
            {pendingCheckpoint.title ? <p style={{ margin: "4px 0" }}>{pendingCheckpoint.title}</p> : null}
            <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>
              Block {pendingCheckpoint.target_block}
            </p>
            {pendingCheckpoint.deadline_at ? (
              <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>
                Deadline: {pendingCheckpoint.deadline_at}
              </p>
            ) : null}
          </div>
        </section>
      ) : null}

      <section className="details-card">
        <div className="details-card__header">
          <strong>Documents</strong>
        </div>
        <div className="details-documents">
          {documents.map((document) => (
            <DocumentCard
              key={`${document.title}-${document.kind}`}
              title={document.title}
              kind={document.kind}
              path={document.path}
              status={document.status}
              muted={document.muted}
            />
          ))}
        </div>
      </section>

      {detail?.reports?.closeout_report_text ? (
        <section className="details-card">
          <div className="details-card__header">
            <strong>Report</strong>
          </div>
          <div className="details-text">
            <pre>{detail.reports.closeout_report_text}</pre>
          </div>
        </section>
      ) : null}
      </> : null}
    </aside>
  );
}
