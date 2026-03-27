import { useI18n } from "../../i18n";
import { displayStatus } from "../../locale";
import { statusTone } from "../../utils";

function HistoryRow({ title, tone, lines }) {
  const { t } = useI18n();
  return (
    <div className="content-card">
      <div className="content-card__header">
        <strong>{title}</strong>
        <span className={`status-badge status-badge--${tone}`}>{lines.length}</span>
      </div>
      <div className="dense-list">
        {lines.length ? lines : <div className="empty-block">{t("history.noEntries")}</div>}
      </div>
    </div>
  );
}

function FlowPreview({ svgText }) {
  const { t } = useI18n();
  if (!svgText) {
    return <div className="empty-block">{t("history.noFlowChart")}</div>;
  }
  return <div className="history-flow__canvas" dangerouslySetInnerHTML={{ __html: svgText }} />;
}

export function HistoryView({ detail }) {
  const { language, t } = useI18n();
  const history = detail?.history || {};
  const project = detail?.project || {};
  const blocks = (history?.blocks || []).map((block, index) => (
    <div className="dense-row" key={`block-${index}`}>
      <div className="dense-row__title">
        <strong>{`block ${block.block_index}`}</strong>
        <span className={`status-badge status-badge--${statusTone(block.status)}`}>{displayStatus(block.status, language)}</span>
      </div>
      <span>{block.selected_task || t("history.noTaskTitle")}</span>
      <span>{block.test_summary || t("history.noTestSummary")}</span>
    </div>
  ));
  const activity = [...(history?.ui_events || [])].reverse().map((event, index) => (
    <div className="dense-row" key={`event-${index}`}>
      <div className="dense-row__title">
        <strong>{event.event_type || "event"}</strong>
        <span>{event.timestamp || ""}</span>
      </div>
      <span>{event.message || t("history.noEntries")}</span>
    </div>
  ));

  if (!detail) {
    return (
      <section className="workspace-view">
        <div className="empty-block">{t("history.noSavedRuns")}</div>
      </section>
    );
  }

  return (
    <section className="workspace-view">
      <div className="view-header">
        <div>
          <span className="eyebrow">{t("history.history")}</span>
          <h2>{project.display_name || project.slug || t("history.history")}</h2>
        </div>
        <div className="history-meta">
          <span className={`status-badge status-badge--${statusTone(project.current_status || "idle")}`}>
            {displayStatus(project.current_status || "idle", language)}
          </span>
          {project.archived_at ? <span>{t("history.archivedAt", { timestamp: project.archived_at })}</span> : null}
        </div>
      </div>

      <div className="content-card content-card--flow">
        <div className="content-card__header">
          <strong>{t("run.flowChart")}</strong>
        </div>
        <div className="history-flow">
          <FlowPreview svgText={history?.flow_svg_text || ""} />
        </div>
      </div>

      <div className="run-layout">
        <div className="content-card">
          <div className="content-card__header">
            <strong>{t("field.prompt")}</strong>
          </div>
          <pre>{detail?.plan?.project_prompt || t("history.noPrompt")}</pre>
        </div>
        <div className="content-card">
          <div className="content-card__header">
            <strong>{t("common.status")}</strong>
          </div>
          <pre>{detail?.summary || t("history.noEntries")}</pre>
        </div>
      </div>

      <div className="history-grid">
        <HistoryRow title={t("history.recentBlocks")} tone="info" lines={blocks} />
        <HistoryRow title={t("history.recentActivity")} tone="neutral" lines={activity} />
      </div>
    </section>
  );
}
