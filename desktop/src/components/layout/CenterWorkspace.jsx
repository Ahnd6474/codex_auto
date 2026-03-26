import { DashboardView } from "../views/DashboardView";
import { ParallelRunControlView } from "../views/ParallelRunControlView";
import { RunControlView } from "../views/RunControlView";
import { ReportsView } from "../views/ReportsView";
import { HistoryView } from "../views/HistoryView";
import { ConfigEditorView } from "../views/ConfigEditorView";
import { AppSettingsView } from "../views/AppSettingsView";
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
  shareSettings,
  programSettings,
  planDraft,
  selectedStepId,
  modelPresets,
  modelCatalog,
  busy,
  onChangeForm,
  onChangeProgramSettings,
  onChooseDirectory,
  onDeleteProject,
  onGenerateShareLink,
  onCopyShareLink,
  onRevokeShareLink,
  onChangeShareSettings,
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
  const { t } = useI18n();
  const developerMode = Boolean(programSettings?.developer_mode);
  const executionMode = String(form?.runtime?.execution_mode || planDraft?.execution_mode || detail?.runtime?.execution_mode || "serial")
    .trim()
    .toLowerCase();

  const visibleTabs = [
    ["run", t("tab.flow")],
    ["config", t("tab.config")],
    ["dashboard", t("tab.dashboard")],
    ...(developerMode
      ? [
          ["reports", t("tab.reports")],
          ["history", t("tab.history")],
        ]
      : []),
  ];

  return (
    <section className="workspace-area">
      <div className="workspace-tabs">
        {visibleTabs.map(([value, label]) => (
          <WorkspaceTab key={value} value={value} activeTab={activeTab} onChange={onChangeTab} label={label} />
        ))}
      </div>

      {activeTab === "run" ? (
        executionMode === "parallel" ? (
          <ParallelRunControlView
            detail={detail}
            planDraft={planDraft}
            shareSettings={shareSettings}
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
            onChangeShareSettings={onChangeShareSettings}
            onSelectStep={onSelectStep}
            onUpdateStepField={onUpdateStepField}
            onSaveStepLocal={onSaveStepLocal}
            onAddStep={onAddStep}
            onDeleteStep={onDeleteStep}
          />
        ) : (
          <RunControlView
            detail={detail}
            planDraft={planDraft}
            shareSettings={shareSettings}
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
            onChangeShareSettings={onChangeShareSettings}
            onSelectStep={onSelectStep}
            onUpdateStepField={onUpdateStepField}
            onSaveStepLocal={onSaveStepLocal}
            onAddStep={onAddStep}
            onDeleteStep={onDeleteStep}
            onMoveStep={onMoveStep}
          />
        )
      ) : null}
      {activeTab === "dashboard" ? (
        <DashboardView
          detail={detail}
          planDraft={planDraft}
          form={form}
          busy={busy}
          modelPresets={modelPresets}
          modelCatalog={modelCatalog}
          activeJob={activeJob}
          onChangeForm={onChangeForm}
        />
      ) : null}
      {developerMode && activeTab === "reports" ? <ReportsView reports={detail?.reports} /> : null}
      {developerMode && activeTab === "history" ? <HistoryView history={detail?.history} /> : null}
      {activeTab === "config" ? (
        <ConfigEditorView
          form={form}
          modelPresets={modelPresets}
          modelCatalog={modelCatalog}
          busy={busy}
          onChangeForm={onChangeForm}
          onChooseDirectory={onChooseDirectory}
          onDeleteProject={onDeleteProject}
        />
      ) : null}
      {activeTab === "app-settings" ? (
        <AppSettingsView
          settings={programSettings}
          shareSettings={shareSettings}
          shareDetail={detail?.share}
          busy={busy}
          onChangeSettings={onChangeProgramSettings}
          onGenerateShareLink={onGenerateShareLink}
          onCopyShareLink={onCopyShareLink}
          onRevokeShareLink={onRevokeShareLink}
          onChangeShareSettings={onChangeShareSettings}
        />
      ) : null}
    </section>
  );
}
