import { DashboardView } from "../views/DashboardView";
import { OverviewView } from "../views/OverviewView";
import { RunControlView } from "../views/RunControlView";
import { ReportsView } from "../views/ReportsView";
import { HistoryView } from "../views/HistoryView";
import { ConfigEditorView } from "../views/ConfigEditorView";

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
  onSelectStep,
  onUpdateStepField,
  onSaveStepLocal,
  onAddStep,
  onDeleteStep,
  onMoveStep,
  activeJob,
}) {
  return (
    <section className="workspace-area">
      <div className="workspace-tabs">
        <WorkspaceTab value="run" activeTab={activeTab} onChange={onChangeTab} label="Flow" />
        <WorkspaceTab value="dashboard" activeTab={activeTab} onChange={onChangeTab} label="Dashboard" />
        <WorkspaceTab value="overview" activeTab={activeTab} onChange={onChangeTab} label="Overview" />
        <WorkspaceTab value="reports" activeTab={activeTab} onChange={onChangeTab} label="Reports" />
        <WorkspaceTab value="history" activeTab={activeTab} onChange={onChangeTab} label="History" />
        <WorkspaceTab value="config" activeTab={activeTab} onChange={onChangeTab} label="Config" />
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
          onSelectStep={onSelectStep}
          onUpdateStepField={onUpdateStepField}
          onSaveStepLocal={onSaveStepLocal}
          onAddStep={onAddStep}
          onDeleteStep={onDeleteStep}
          onMoveStep={onMoveStep}
        />
      ) : null}
      {activeTab === "dashboard" ? <DashboardView detail={detail} planDraft={planDraft} modelPresets={modelPresets} activeJob={activeJob} /> : null}
      {activeTab === "overview" ? <OverviewView detail={detail} /> : null}
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
