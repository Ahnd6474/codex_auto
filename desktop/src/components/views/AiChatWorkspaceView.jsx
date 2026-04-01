import { memo } from "react";
import { RightSidebarPane } from "../layout/RightSidebarPane";

function aiChatWorkspaceViewPropsEqual(previousProps, nextProps) {
  return (
    previousProps.detail === nextProps.detail
    && previousProps.form === nextProps.form
    && previousProps.modelPresets === nextProps.modelPresets
    && previousProps.modelCatalog === nextProps.modelCatalog
    && previousProps.activeJob === nextProps.activeJob
    && previousProps.chatJob === nextProps.chatJob
    && previousProps.selectedStepId === nextProps.selectedStepId
    && previousProps.busy === nextProps.busy
    && previousProps.onRequestChatStop === nextProps.onRequestChatStop
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
  chatJob,
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
  onRequestChatStop,
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
        selectedStepId={selectedStepId}
        modelPresets={modelPresets}
        modelCatalog={modelCatalog}
        form={form}
        activeJob={activeJob}
        chatJob={chatJob}
        busy={busy}
        onChangeForm={onChangeForm}
        chat={chat}
        chatSettings={chatSettings}
        selectedChatSessionId={selectedChatSessionId}
        chatDraftSession={chatDraftSession}
        onSelectChatSession={onSelectChatSession}
        onStartNewChatSession={onStartNewChatSession}
        onSendChatMessage={onSendChatMessage}
        onRequestChatStop={onRequestChatStop}
        onChangeChatModelSelection={onChangeChatModelSelection}
        onChangeChatReasoningEffort={onChangeChatReasoningEffort}
        onGeneratePlan={onGeneratePlan}
      />
    </section>
  );
}, aiChatWorkspaceViewPropsEqual);
