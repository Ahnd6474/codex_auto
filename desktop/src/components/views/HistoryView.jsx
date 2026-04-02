import { useRef } from "react";
import { useVirtualWindow } from "../../hooks/useVirtualWindow";
import { useI18n } from "../../i18n";
import { displayStatus } from "../../locale";
import { failureReasonLabel, statusTone } from "../../utils";

function HistoryRow({ title, tone, lines }) {
  const { t } = useI18n();
  const listRef = useRef(null);
  const safeLines = Array.isArray(lines) ? lines : [];
  const shouldVirtualize = safeLines.length > 36;
  const {
    visibleItems,
    topSpacerHeight,
    bottomSpacerHeight,
  } = useVirtualWindow(safeLines, {
    containerRef: listRef,
    itemHeight: 72,
    overscan: 4,
    enabled: shouldVirtualize,
    defaultViewportHeight: 360,
  });

  return (
    <div className="content-card">
      <div className="content-card__header">
        <strong>{title}</strong>
        <span className={`status-badge status-badge--${tone}`}>{safeLines.length}</span>
      </div>
      <div
        className="dense-list"
        ref={listRef}
        style={shouldVirtualize ? { maxHeight: "360px", overflowY: "auto" } : undefined}
      >
        {safeLines.length ? (
          <>
            {topSpacerHeight > 0 ? <div aria-hidden="true" style={{ height: `${topSpacerHeight}px` }} /> : null}
            {(shouldVirtualize ? visibleItems : safeLines)}
            {bottomSpacerHeight > 0 ? <div aria-hidden="true" style={{ height: `${bottomSpacerHeight}px` }} /> : null}
          </>
        ) : <div className="empty-block">{t("history.noEntries")}</div>}
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

export function HistoryView({ detail, busy = false, onDeleteHistoryEntry = null }) {
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
      {failureReasonLabel(block, language) ? <span>{language === "ko" ? `실패 사유: ${failureReasonLabel(block, language)}` : `Failure reason: ${failureReasonLabel(block, language)}`}</span> : null}
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
          {project.archive_id ? (
            <button
              className="toolbar-button"
              onClick={() => onDeleteHistoryEntry?.(project.archive_id)}
              type="button"
              disabled={busy}
            >
              {t("action.deleteArchivedRun")}
            </button>
          ) : null}
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
