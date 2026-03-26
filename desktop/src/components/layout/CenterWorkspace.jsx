import { DashboardView } from "../views/DashboardView";
import { RunControlView } from "../views/RunControlView";
import { ReportsView } from "../views/ReportsView";
import { HistoryView } from "../views/HistoryView";
import { ConfigEditorView } from "../views/ConfigEditorView";
import { useI18n } from "../../i18n";

function WorkspaceTab({ value, activeTab, onChange, label }) {
  return (
    <button className={`workspace-tab ${activeTab === value ? "active" : ""}`} onClick={() => onChange(value)} type="button">
      {label}
    </button>
  );
}

export function CenterWorkspace({
  activeTab,
  onChangeTab,
  detail,
  form,
  planDraft,
  selectedStepId,
  modelPresets,
  busy,
  onChangeForm,
  onChooseDirectory,
  onSaveProject,
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
  onSelectStep,
  onUpdateStepField,
  onSaveStepLocal,
  onAddStep,
  onDeleteStep,
  onMoveStep,
  activeJob,
}) {
  const { t } = useI18n();

  return (
    <section className="workspace-area">
      <div className="workspace-tabs">
        <WorkspaceTab value="run" activeTab={activeTab} onChange={onChangeTab} label={t("tab.flow")} />
        <WorkspaceTab value="dashboard" activeTab={activeTab} onChange={onChangeTab} label={t("tab.dashboard")} />
        <WorkspaceTab value="reports" activeTab={activeTab} onChange={onChangeTab} label={t("tab.reports")} />
        <WorkspaceTab value="history" activeTab={activeTab} onChange={onChangeTab} label={t("tab.history")} />
        <WorkspaceTab value="config" activeTab={activeTab} onChange={onChangeTab} label={t("tab.config")} />
      </div>

      {activeTab === "run" ? (
        <RunControlView
          detail={detail}
          planDraft={planDraft}
          selectedStepId={selectedStepId}
          busy={busy}
          onPromptChange={onPromptChange}
          onGeneratePlan={onGeneratePlan}
          onSavePlan={onSavePlan}
          onResetPlan={onResetPlan}
          onRunPlan={onRunPlan}
          onRunCloseout={onRunCloseout}
          onRequestStop={onRequestStop}
          onGenerateShareLink={onGenerateShareLink}
          onCopyShareLink={onCopyShareLink}
          onRevokeShareLink={onRevokeShareLink}
          onSelectStep={onSelectStep}
          onUpdateStepField={onUpdateStepField}
          onSaveStepLocal={onSaveStepLocal}
          onAddStep={onAddStep}
          onDeleteStep={onDeleteStep}
          onMoveStep={onMoveStep}
        />
      ) : null}
      {activeTab === "dashboard" ? <DashboardView detail={detail} planDraft={planDraft} modelPresets={modelPresets} activeJob={activeJob} /> : null}
      {activeTab === "reports" ? <ReportsView reports={detail?.reports} /> : null}
      {activeTab === "history" ? <HistoryView history={detail?.history} /> : null}
      {activeTab === "config" ? (
        <ConfigEditorView
          form={form}
          modelPresets={modelPresets}
          busy={busy}
          onChangeForm={onChangeForm}
          onChooseDirectory={onChooseDirectory}
          onSaveProject={onSaveProject}
        />
      ) : null}
    </section>
  );
}
