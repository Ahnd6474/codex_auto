import { memo } from "react";
import { RightSidebarPane } from "../layout/RightSidebarPane";

function aiChatWorkspaceViewPropsEqual(previousProps, nextProps) {
  return (
    previousProps.detail === nextProps.detail
    && previousProps.form === nextProps.form
    && previousProps.modelPresets === nextProps.modelPresets
    && previousProps.modelCatalog === nextProps.modelCatalog
    && previousProps.activeJob === nextProps.activeJob
    && previousProps.selectedStepId === nextProps.selectedStepId
    && previousProps.busy === nextProps.busy
    && previousProps.selectedChatSessionId === nextProps.selectedChatSessionId
    && previousProps.chatDraftSession === nextProps.chatDraftSession
    && previousProps.chatSettings === nextProps.chatSettings
  );
}

export const AiChatWorkspaceView = memo(function AiChatWorkspaceView({
  detail,
  form,
  modelPresets,
  modelCatalog,
  activeJob,
  selectedStepId,
  busy,
  onChangeForm,
  onGeneratePlan,
  chat,
  chatSettings,
  selectedChatSessionId,
  chatDraftSession,
  onSelectChatSession,
  onStartNewChatSession,
  onSendChatMessage,
  onChangeChatModelSelection,
  onChangeChatReasoningEffort,
}) {
  return (
    <section className="workspace-view ai-chat-workspace">
      <RightSidebarPane
        activeTab="chat"
        collapsed={false}
        chatCenterMode
        detail={detail}
        planDraft={planDraft}
        selectedStepId={selectedStepId}
        modelPresets={modelPresets}
        modelCatalog={modelCatalog}
        form={form}
        activeJob={activeJob}
        busy={busy}
        onChangeForm={onChangeForm}
        chat={chat}
        chatSettings={chatSettings}
        selectedChatSessionId={selectedChatSessionId}
        chatDraftSession={chatDraftSession}
        onSelectChatSession={onSelectChatSession}
        onStartNewChatSession={onStartNewChatSession}
        onSendChatMessage={onSendChatMessage}
        onChangeChatModelSelection={onChangeChatModelSelection}
        onChangeChatReasoningEffort={onChangeChatReasoningEffort}
        onGeneratePlan={onGeneratePlan}
      />
    </section>
  );
}, aiChatWorkspaceViewPropsEqual);
