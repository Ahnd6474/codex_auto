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

export function HistoryView({ history }) {
  const { language, t } = useI18n();
  const blocks = (history?.blocks || []).map((block, index) => (
    <div className="dense-row" key={`block-${index}`}>
      <div className="dense-row__title">
        <strong>{language === "ko" ? `블록 ${block.block_index}` : `block ${block.block_index}`}</strong>
        <span className={`status-badge status-badge--${statusTone(block.status)}`}>{displayStatus(block.status, language)}</span>
      </div>
      <span>{block.selected_task || t("history.noTaskTitle")}</span>
      <span>{block.test_summary || t("history.noTestSummary")}</span>
    </div>
  ));

  return (
    <section className="workspace-view">
      <div className="view-header">
        <div>
          <span className="eyebrow">{t("history.history")}</span>
          <h2>{t("history.recentActivity")}</h2>
        </div>
      </div>

      <div className="history-grid history-grid--single">
        <HistoryRow title={t("history.recentBlocks")} tone="info" lines={blocks} />
      </div>
    </section>
  );
}
