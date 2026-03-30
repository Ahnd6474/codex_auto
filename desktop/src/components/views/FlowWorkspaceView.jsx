import { ParallelRunControlView } from "./ParallelRunControlView";

export function FlowWorkspaceView(props) {
  const {
    detail,
    form,
    planDraft,
    activeJob,
    autoRunAfterPlan,
    selectedStepId,
    busy,
    canRequestStop = false,
    canCancelReservation = false,
    queuedJobs = [],
    hidePromptStrip = false,
    onPromptChange,
    onChangeForm,
    onGeneratePlan,
    onSavePlan,
    onResetPlan,
    onRunPlan,
    onRunManualDebugger,
    onRunManualMerger,
    onRequestStop,
    onCancelQueuedJob,
    onChangeAutoRunAfterPlan,
    onSelectStep,
    onUpdateStepField,
    onSaveStepLocal,
    onAddStep,
    onDeleteStep,
  } = props;

  return (
    <ParallelRunControlView
      detail={detail}
      codexStatus={detail?.codex_status}
      planDraft={planDraft}
      activeJob={activeJob}
      autoRunAfterPlan={autoRunAfterPlan}
      selectedStepId={selectedStepId}
      form={form}
      busy={busy}
      canRequestStop={canRequestStop}
      canCancelReservation={canCancelReservation}
      queuedJobs={queuedJobs}
      hidePromptStrip={hidePromptStrip}
      onPromptChange={onPromptChange}
      onChangeForm={onChangeForm}
      onGeneratePlan={onGeneratePlan}
      onSavePlan={onSavePlan}
      onResetPlan={onResetPlan}
      onRunPlan={onRunPlan}
      onRunManualDebugger={onRunManualDebugger}
      onRunManualMerger={onRunManualMerger}
      onRequestStop={onRequestStop}
      onCancelQueuedJob={onCancelQueuedJob}
      onAutoRunAfterPlanChange={onChangeAutoRunAfterPlan}
      onSelectStep={onSelectStep}
      onUpdateStepField={onUpdateStepField}
      onSaveStepLocal={onSaveStepLocal}
      onAddStep={onAddStep}
      onDeleteStep={onDeleteStep}
    />
  );
}
