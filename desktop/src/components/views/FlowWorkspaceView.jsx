import { memo } from "react";
import { ParallelRunControlView } from "./ParallelRunControlView";

function flowWorkspaceViewPropsEqual(previousProps, nextProps) {
  return (
    previousProps.detail === nextProps.detail
    && previousProps.form === nextProps.form
    && previousProps.planDraft === nextProps.planDraft
    && previousProps.activeJob === nextProps.activeJob
    && previousProps.autoRunAfterPlan === nextProps.autoRunAfterPlan
    && previousProps.selectedStepId === nextProps.selectedStepId
    && previousProps.busy === nextProps.busy
    && previousProps.canRequestStop === nextProps.canRequestStop
    && previousProps.canCancelReservation === nextProps.canCancelReservation
    && previousProps.queuedJobs === nextProps.queuedJobs
  );
}

export const FlowWorkspaceView = memo(function FlowWorkspaceView({
  detail,
  form,
  planDraft,
  activeJob,
  autoRunAfterPlan,
  selectedStepId,
  busy,
  canRequestStop,
  canCancelReservation,
  queuedJobs,
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
}) {
  return (
    <section className="workspace-view">
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
        hidePromptStrip
      />
    </section>
  );
}, flowWorkspaceViewPropsEqual);
