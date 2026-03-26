import { useI18n } from "../../i18n";
import { displayStatus } from "../../locale";
import { canEditStep, REASONING_OPTIONS, reasoningEffortLabel, statusTone } from "../../utils";

function FlowNode({ step, selected, onSelect, language, t }) {
  const tone = statusTone(step.status);
  return (
    <button className={`run-node run-node--${tone} ${selected ? "selected" : ""}`} onClick={() => onSelect(step.step_id)} type="button">
      <div className="run-node__meta">
        <span className="run-node__id">{step.step_id}</span>
        <span className={`status-badge status-badge--${tone}`}>{displayStatus(step.status, language)}</span>
      </div>
      <strong>{step.title}</strong>
      <p>{step.display_description || step.test_command || t("run.noSummary")}</p>
      <p>{t("run.reasoning", { effort: reasoningEffortLabel(step.reasoning_effort || "high", language) })}</p>
    </button>
  );
}

export function RunControlView({
  detail,
  planDraft,
  shareSettings,
  selectedStepId,
  busy,
  onPromptChange,
  onGeneratePlan,
  onSavePlan,
  onResetPlan,
  onRunPlan,
  onRunCloseout,
  onRequestStop,
  onGenerateShareLink,
  onCopyShareLink,
  onRevokeShareLink,
  onChangeShareSettings,
  onSelectStep,
  onUpdateStepField,
  onSaveStepLocal,
  onAddStep,
  onDeleteStep,
  onMoveStep,
}) {
  const steps = planDraft?.steps || [];
  const selectedStep = steps.find((step) => step.step_id === selectedStepId) || null;
  const editableStep = canEditStep(selectedStep, busy);
  const completedCount = steps.filter((step) => step.status === "completed").length;
  const flowColumns = 3;
  const { language, t } = useI18n();
  const activeShare = detail?.share?.active_session || null;
  const shareServer = detail?.share?.server || null;

  return (
    <section className="workspace-view">
      <div className="view-header">
        <div>
          <span className="eyebrow">{t("run.flow")}</span>
          <h2>{t("run.executionFlow")}</h2>
        </div>
      </div>

      <div className="run-summary">
        <div className={`metric-card metric-card--${statusTone(detail?.project?.current_status)}`}>
          <span>{t("common.status")}</span>
          <strong>{displayStatus(detail?.project?.current_status || "idle", language)}</strong>
        </div>
        <div className="metric-card metric-card--info">
          <span>{t("run.done")}</span>
          <strong>{completedCount}/{steps.length || 0}</strong>
        </div>
        <div className={`metric-card metric-card--${detail?.run_control?.stop_after_current_step ? "warning" : "neutral"}`}>
          <span>{t("run.stopAfterStep")}</span>
          <strong>{detail?.run_control?.stop_after_current_step ? t("common.on") : t("common.off")}</strong>
        </div>
        <div className={`metric-card metric-card--${statusTone(planDraft?.closeout_status)}`}>
          <span>{t("run.closeout")}</span>
          <strong>{displayStatus(planDraft?.closeout_status || "not_started", language)}</strong>
        </div>
      </div>

      <div className="content-card content-card--flow">
        <div className="content-card__header">
          <strong>{t("run.flowChart")}</strong>
          <div className="action-row">
            <button className="toolbar-button" onClick={onGeneratePlan} type="button" disabled={busy}>
              {t("action.generate")}
            </button>
            <button className="toolbar-button" onClick={onSavePlan} type="button" disabled={busy}>
              {t("action.save")}
            </button>
            <button className="toolbar-button toolbar-button--ghost" onClick={onResetPlan} type="button" disabled={busy}>
              {t("action.reset")}
            </button>
            <button className="toolbar-button toolbar-button--accent" onClick={onRunPlan} type="button" disabled={busy}>
              {t("action.run")}
            </button>
            <button className="toolbar-button" onClick={onRunCloseout} type="button" disabled={busy}>
              {t("action.closeout")}
            </button>
            <button className="toolbar-button toolbar-button--ghost" onClick={onRequestStop} type="button" disabled={!busy}>
              {t("action.stop")}
            </button>
          </div>
        </div>
        <div className="run-flow">
          {steps.length ? (
            steps.map((step, index) => (
              <div className="run-flow__item" key={step.step_id}>
                <FlowNode step={step} selected={step.step_id === selectedStepId} onSelect={onSelectStep} language={language} t={t} />
                {index < steps.length - 1 ? (
                  <div
                    className={`run-flow__connector ${
                      (index + 1) % flowColumns === 0 ? "run-flow__connector--down" : "run-flow__connector--right"
                    }`}
                    aria-hidden="true"
                  />
                ) : null}
              </div>
            ))
          ) : (
            <div className="empty-block">{t("run.noSteps")}</div>
          )}
        </div>
      </div>

      <div className="run-layout">
        <div className="content-card">
          <div className="content-card__header">
            <strong>{t("field.prompt")}</strong>
          </div>
          <textarea className="editor-textarea editor-textarea--prompt" value={planDraft?.project_prompt || ""} onChange={(event) => onPromptChange(event.target.value)} disabled={busy} />
        </div>

        <div className="content-card">
          <div className="content-card__header">
            <strong>{t("run.remoteMonitor")}</strong>
            <span className={`status-badge status-badge--${shareServer?.running ? "success" : "neutral"}`}>
              {shareServer?.running ? t("common.on") : t("common.off")}
            </span>
          </div>
          <p>{t("run.shareDescription")}</p>
          <p>{t("run.sharePoll")}</p>
          <div className="share-panel">
            <label className="field">
              <span>{t("run.shareBindHost")}</span>
              <select
                value={shareSettings?.bind_host || "127.0.0.1"}
                onChange={(event) =>
                  onChangeShareSettings((current) => ({
                    ...(current || {}),
                    bind_host: event.target.value,
                  }))
                }
                disabled={busy}
              >
                <option value="127.0.0.1">{t("run.shareBindLocal")}</option>
                <option value="0.0.0.0">{t("run.shareBindNetwork")}</option>
              </select>
            </label>
            <label className="field field--wide">
              <span>{t("run.sharePublicBaseUrl")}</span>
              <input
                value={shareSettings?.public_base_url || ""}
                onChange={(event) =>
                  onChangeShareSettings((current) => ({
                    ...(current || {}),
                    public_base_url: event.target.value,
                  }))
                }
                placeholder="https://your-public-share.example"
                disabled={busy}
              />
            </label>
            <p className="muted">{t("run.shareExternalHint")}</p>
          </div>
          {activeShare?.share_url ? (
            <div className="share-panel">
              <label className="field field--wide">
                <span>{t("run.shareLink")}</span>
                <input value={activeShare.share_url} readOnly />
              </label>
              <div className="share-meta">
                <span>{t("run.shareExpires", { expiresAt: activeShare.expires_at || t("common.unavailable") })}</span>
                <span>{t("run.shareServerAddress", { address: shareServer?.base_url || t("common.unavailable") })}</span>
              </div>
              {activeShare?.local_url && activeShare.local_url !== activeShare.share_url ? (
                <label className="field field--wide">
                  <span>{t("run.shareLocalLink")}</span>
                  <input value={activeShare.local_url} readOnly />
                </label>
              ) : null}
              <div className="action-row">
                <button className="toolbar-button toolbar-button--accent" onClick={onCopyShareLink} type="button" disabled={busy}>
                  {t("action.copyLink")}
                </button>
                <button className="toolbar-button toolbar-button--ghost" onClick={onRevokeShareLink} type="button" disabled={busy}>
                  {t("action.revokeLink")}
                </button>
              </div>
            </div>
          ) : (
            <div className="empty-block">{t("run.noShareSession")}</div>
          )}
          <div className="action-row">
            <button className="toolbar-button" onClick={onGenerateShareLink} type="button" disabled={busy}>
              {t("action.generateShareLink")}
            </button>
          </div>
        </div>

        <div className="content-card">
          <div className="content-card__header">
            <strong>{t("run.selectedStep")}</strong>
            <span className={`status-badge status-badge--${statusTone(selectedStep?.status)}`}>{selectedStep ? displayStatus(selectedStep.status, language) : t("common.none")}</span>
          </div>
          {selectedStep ? (
            <div className="step-editor-grid">
              <label className="field field--wide">
                <span>{t("field.title")}</span>
                <input value={selectedStep.title || ""} onChange={(event) => onUpdateStepField("title", event.target.value)} disabled={!editableStep} />
              </label>
              <label className="field">
                <span>{t("field.gptReasoning")}</span>
                <select
                  value={selectedStep.reasoning_effort || detail?.runtime?.effort || "high"}
                  onChange={(event) => onUpdateStepField("reasoning_effort", event.target.value)}
                  disabled={!editableStep}
                >
                  {REASONING_OPTIONS.map((effort) => (
                    <option key={effort} value={effort}>
                      {reasoningEffortLabel(effort, language)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field field--wide">
                <span>{t("field.description")}</span>
                <textarea value={selectedStep.display_description || ""} onChange={(event) => onUpdateStepField("display_description", event.target.value)} disabled={!editableStep} />
              </label>
              <label className="field field--wide">
                <span>{t("field.codexInstruction")}</span>
                <textarea value={selectedStep.codex_description || ""} onChange={(event) => onUpdateStepField("codex_description", event.target.value)} disabled={!editableStep} />
              </label>
              <label className="field field--wide">
                <span>{t("field.successCriteria")}</span>
                <textarea value={selectedStep.success_criteria || ""} onChange={(event) => onUpdateStepField("success_criteria", event.target.value)} disabled={!editableStep} />
              </label>
              <div className="action-row field--wide">
                <button className="toolbar-button toolbar-button--accent" onClick={onSaveStepLocal} type="button" disabled={busy}>
                  {t("action.saveLocal")}
                </button>
                <button className="toolbar-button" onClick={onAddStep} type="button" disabled={busy}>
                  {t("action.add")}
                </button>
                <button className="toolbar-button toolbar-button--ghost" onClick={onDeleteStep} type="button" disabled={!editableStep}>
                  {t("action.delete")}
                </button>
                <button className="toolbar-button toolbar-button--ghost" onClick={() => onMoveStep(-1)} type="button" disabled={!editableStep}>
                  {t("action.up")}
                </button>
                <button className="toolbar-button toolbar-button--ghost" onClick={() => onMoveStep(1)} type="button" disabled={!editableStep}>
                  {t("action.down")}
                </button>
              </div>
            </div>
          ) : (
            <div className="empty-block">{t("run.selectStep")}</div>
          )}
        </div>
      </div>
    </section>
  );
}
