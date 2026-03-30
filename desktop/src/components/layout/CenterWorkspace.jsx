import { Suspense, lazy, memo, useEffect } from "react";
import { useI18n } from "../../i18n";

function AiChatTabIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ConfigTabIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"
        stroke="currentColor"
        strokeWidth="1.5"
      />
      <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

function DashboardTabIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3" y="3" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

function FlowTabIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3" y="10" width="5" height="5" rx="1.4" stroke="currentColor" strokeWidth="1.6" />
      <rect x="16" y="4" width="5" height="5" rx="1.4" stroke="currentColor" strokeWidth="1.6" />
      <rect x="16" y="15" width="5" height="5" rx="1.4" stroke="currentColor" strokeWidth="1.6" />
      <path d="M8 12.5h4m0 0V6.5m0 6v6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M12 6.5h4M12 18.5h4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function HistoryTabIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="7.25" stroke="currentColor" strokeWidth="1.7" />
      <path d="M12 8v4.5l3 1.75" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ReportsTabIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinejoin="round"
      />
      <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

const TAB_ICONS = {
  "ai-chat": <AiChatTabIcon />,
  config: <ConfigTabIcon />,
  flow: <FlowTabIcon />,
  dashboard: <DashboardTabIcon />,
  history: <HistoryTabIcon />,
  reports: <ReportsTabIcon />,
};

function createLazyNamedView(loader, exportName) {
  let loadedComponent = null;
  let pendingModule = null;

  function load() {
    if (!pendingModule) {
      pendingModule = loader().then((module) => {
        loadedComponent = module[exportName];
        return { default: module[exportName] };
      });
    }
    return pendingModule;
  }

  const LazyComponent = lazy(load);

  function PreloadableView(props) {
    if (loadedComponent) {
      const Component = loadedComponent;
      return <Component {...props} />;
    }
    return <LazyComponent {...props} />;
  }

  PreloadableView.preload = load;
  return PreloadableView;
}

const AiChatWorkspaceView = createLazyNamedView(() => import("../views/AiChatWorkspaceView"), "AiChatWorkspaceView");
const FlowWorkspaceView = createLazyNamedView(() => import("../views/FlowWorkspaceView"), "FlowWorkspaceView");
const DashboardView = createLazyNamedView(() => import("../views/DashboardView"), "DashboardView");
const ReportsView = createLazyNamedView(() => import("../views/ReportsView"), "ReportsView");
const HistoryView = createLazyNamedView(() => import("../views/HistoryView"), "HistoryView");
const ConfigEditorView = createLazyNamedView(() => import("../views/ConfigEditorView"), "ConfigEditorView");
const AppSettingsView = createLazyNamedView(() => import("../views/AppSettingsView"), "AppSettingsView");

function scheduleIdlePrefetch(callback) {
  if (typeof window !== "undefined" && typeof window.requestIdleCallback === "function") {
    const handle = window.requestIdleCallback(callback, { timeout: 400 });
    return () => window.cancelIdleCallback(handle);
  }
  if (typeof window !== "undefined") {
    const handle = window.setTimeout(callback, 120);
    return () => window.clearTimeout(handle);
  }
  return () => {};
}

function ViewLoadingFallback() {
  return (
    <section className="workspace-view" aria-busy="true">
      <div className="empty-block" style={{ marginTop: "40px" }}>
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" style={{ animation: "skeleton-pulse 1.2s ease-in-out infinite" }}>
          <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.8" strokeDasharray="4 4" />
        </svg>
        <span style={{ color: "var(--text-dim)", fontSize: "13px" }}>Loading view...</span>
      </div>
    </section>
  );
}

function WorkspaceTab({ value, activeTab, onChange, onPrefetch, label }) {
  const icon = TAB_ICONS[value] || null;
  return (
    <button
      className={`workspace-tab ${activeTab === value ? "active" : ""}`}
      onClick={() => onChange(value)}
      onMouseEnter={() => onPrefetch?.(value)}
      onFocus={() => onPrefetch?.(value)}
      type="button"
    >
      {icon}
      {label}
    </button>
  );
}

function sameQueuedJobs(previousJobs = [], nextJobs = []) {
  if (previousJobs === nextJobs) {
    return true;
  }
  if (!Array.isArray(previousJobs) || !Array.isArray(nextJobs) || previousJobs.length !== nextJobs.length) {
    return false;
  }
  for (let index = 0; index < previousJobs.length; index += 1) {
    const previousJob = previousJobs[index];
    const nextJob = nextJobs[index];
    if (
      previousJob?.id !== nextJob?.id
      || previousJob?.status !== nextJob?.status
      || previousJob?.queue_position !== nextJob?.queue_position
    ) {
      return false;
    }
  }
  return true;
}

function normalizeWorkspaceTab(tab) {
  return tab === "run" ? "flow" : tab;
}

function planHasFlowContent(detail, planDraft) {
  const planningStatus = String(detail?.planning_progress?.status || detail?.planning_progress?.planningStatus || "").trim().toLowerCase();
  const livePlan = detail?.plan || planDraft;
  return Boolean(
    planningStatus === "running"
    || String(livePlan?.project_prompt || "").trim()
    || (Array.isArray(livePlan?.steps) && livePlan.steps.length > 0),
  );
}

function centerWorkspacePropsEqual(previousProps, nextProps) {
  const previousTab = normalizeWorkspaceTab(previousProps.activeTab);
  const nextTab = normalizeWorkspaceTab(nextProps.activeTab);
  if (previousTab !== nextTab) {
    return false;
  }
  const previousDeveloperMode = Boolean(previousProps.programSettings?.developer_mode);
  const nextDeveloperMode = Boolean(nextProps.programSettings?.developer_mode);
  if (previousDeveloperMode !== nextDeveloperMode) {
    return false;
  }

  switch (nextTab) {
    case "ai-chat":
      return (
        previousProps.detail === nextProps.detail
        && previousProps.activeJob === nextProps.activeJob
        && previousProps.selectedStepId === nextProps.selectedStepId
        && previousProps.form === nextProps.form
        && previousProps.busy === nextProps.busy
        && previousProps.chat === nextProps.chat
        && previousProps.selectedChatSessionId === nextProps.selectedChatSessionId
        && previousProps.chatDraftSession === nextProps.chatDraftSession
        && previousProps.programSettings === nextProps.programSettings
      );
    case "flow":
      return (
        previousProps.detail === nextProps.detail
        && previousProps.planDraft === nextProps.planDraft
        && previousProps.activeJob === nextProps.activeJob
        && previousProps.autoRunAfterPlan === nextProps.autoRunAfterPlan
        && previousProps.selectedStepId === nextProps.selectedStepId
        && previousProps.form === nextProps.form
        && previousProps.busy === nextProps.busy
        && previousProps.canRequestStop === nextProps.canRequestStop
        && previousProps.canCancelReservation === nextProps.canCancelReservation
        && sameQueuedJobs(previousProps.queuedJobs, nextProps.queuedJobs)
      );
    case "dashboard":
      return (
        previousProps.detail === nextProps.detail
        && previousProps.planDraft === nextProps.planDraft
        && previousProps.programSettings === nextProps.programSettings
        && previousProps.modelPresets === nextProps.modelPresets
        && previousProps.modelCatalog === nextProps.modelCatalog
        && previousProps.activeJob === nextProps.activeJob
      );
    case "reports":
      return previousProps.detail?.reports === nextProps.detail?.reports;
    case "history":
      return (
        previousProps.selectedHistoryId === nextProps.selectedHistoryId
        && previousProps.historyDetail === nextProps.historyDetail
        && previousProps.detail === nextProps.detail
        && previousProps.busy === nextProps.busy
      );
    case "config":
      return (
        previousProps.form === nextProps.form
        && previousProps.modelPresets === nextProps.modelPresets
        && previousProps.modelCatalog === nextProps.modelCatalog
        && previousProps.detail?.codex_status === nextProps.detail?.codex_status
        && previousProps.busy === nextProps.busy
        && previousProps.activeJob === nextProps.activeJob
      );
    case "app-settings":
      return (
        previousProps.programSettings === nextProps.programSettings
        && previousProps.detail?.codex_status === nextProps.detail?.codex_status
        && previousProps.shareSettings === nextProps.shareSettings
        && previousProps.workspaceShareDetail === nextProps.workspaceShareDetail
        && previousProps.busy === nextProps.busy
        && previousProps.shareBusy === nextProps.shareBusy
        && previousProps.programSettingsDirty === nextProps.programSettingsDirty
      );
    default:
      return false;
  }
}

export const CenterWorkspace = memo(function CenterWorkspace({
  activeTab,
  onChangeTab,
  detail,
  workspaceShareDetail,
  historyDetail,
  selectedHistoryId,
  form,
  shareSettings,
  autoRunAfterPlan,
  programSettings,
  planDraft,
  selectedStepId,
  modelPresets,
  modelCatalog,
  busy,
  canRequestStop,
  canCancelReservation,
  shareBusy,
  queuedJobs,
  onChangeForm,
  onChangeProgramSettings,
  onSaveProject,
  onSaveProgramSettings,
  programSettingsDirty = false,
  onChooseDirectory,
  onArchiveProject,
  onDeleteProject,
  onDeleteHistoryEntry,
  onGenerateShareLink,
  onCopyShareLink,
  onRevokeShareLink,
  onChangeShareSettings,
  onChangeAutoRunAfterPlan,
  onPromptChange,
  onGeneratePlan,
  onSavePlan,
  onResetPlan,
  onRunPlan,
  onRunManualDebugger,
  onRunManualMerger,
  onRequestStop,
  onCancelQueuedJob,
  onSelectStep,
  onUpdateStepField,
  onSaveStepLocal,
  onAddStep,
  onDeleteStep,
  onMoveStep,
  activeJob,
  hidePromptStrip = false,
  chat,
  selectedChatSessionId,
  chatDraftSession,
  onSelectChatSession,
  onStartNewChatSession,
  onSendChatMessage,
  onChangeChatModelSelection,
  onChangeChatReasoningEffort,
}) {
  const { t } = useI18n();
  const developerMode = Boolean(programSettings?.developer_mode);
  const visibleHistoryDetail = selectedHistoryId ? historyDetail : detail;
  const normalizedActiveTab = normalizeWorkspaceTab(activeTab);
  const hasFlowTab = planHasFlowContent(detail, planDraft);

  function resolveTabView(tab) {
    switch (normalizeWorkspaceTab(tab)) {
      case "ai-chat": return AiChatWorkspaceView;
      case "flow": return FlowWorkspaceView;
      case "dashboard": return DashboardView;
      case "reports": return developerMode ? ReportsView : null;
      case "history": return HistoryView;
      case "config": return ConfigEditorView;
      case "app-settings": return AppSettingsView;
      default: return null;
    }
  }

  function preloadTab(tab) {
    const ViewComponent = resolveTabView(tab);
    ViewComponent?.preload?.();
  }

  useEffect(() => {
    preloadTab(hasFlowTab ? normalizedActiveTab : (normalizedActiveTab === "flow" ? "ai-chat" : normalizedActiveTab));
    const likelyNextTabs =
      normalizedActiveTab === "ai-chat"
        ? [hasFlowTab ? "flow" : "config", "dashboard"]
        : normalizedActiveTab === "flow"
          ? ["ai-chat", "dashboard"]
        : normalizedActiveTab === "config"
          ? [hasFlowTab ? "flow" : "ai-chat", "dashboard"]
          : normalizedActiveTab === "dashboard"
            ? [hasFlowTab ? "flow" : "ai-chat", "config"]
            : normalizedActiveTab === "reports"
              ? ["history", "dashboard"]
              : normalizedActiveTab === "history"
                ? ["reports", "dashboard"]
                : ["config"];
    return scheduleIdlePrefetch(() => {
      likelyNextTabs.forEach((tab) => preloadTab(tab));
    });
  }, [developerMode, hasFlowTab, normalizedActiveTab]);

  useEffect(() => {
    if (!developerMode && normalizedActiveTab === "reports") {
      onChangeTab("ai-chat");
    }
  }, [developerMode, normalizedActiveTab, onChangeTab]);

  useEffect(() => {
    if (!hasFlowTab && normalizedActiveTab === "flow") {
      onChangeTab("ai-chat");
    }
  }, [hasFlowTab, normalizedActiveTab, onChangeTab]);

  const visibleTabs = [
    ["ai-chat", t("tab.aiChat")],
    ["config", t("tab.config")],
    ...(hasFlowTab ? [["flow", t("tab.flow")]] : []),
    ["dashboard", t("tab.dashboard")],
    ["history", t("tab.history")],
    ...(developerMode ? [["reports", t("tab.reports")]] : []),
  ];

  return (
    <section className="workspace-area">
      <div className="workspace-tabs">
        {visibleTabs.map(([value, label]) => (
          <WorkspaceTab
            key={value}
            value={value}
            activeTab={normalizedActiveTab}
            onChange={onChangeTab}
            onPrefetch={preloadTab}
            label={label}
          />
        ))}
      </div>

      <Suspense fallback={<ViewLoadingFallback />}>
        {normalizedActiveTab === "ai-chat" ? (
          <AiChatWorkspaceView
            detail={detail}
            form={form}
            modelPresets={modelPresets}
            modelCatalog={modelCatalog}
            activeJob={activeJob}
            selectedStepId={selectedStepId}
            busy={busy}
            onChangeForm={onChangeForm}
            onGeneratePlan={onGeneratePlan}
            chat={chat}
            chatSettings={programSettings}
            selectedChatSessionId={selectedChatSessionId}
            chatDraftSession={chatDraftSession}
            onSelectChatSession={onSelectChatSession}
            onStartNewChatSession={onStartNewChatSession}
            onSendChatMessage={onSendChatMessage}
            onChangeChatModelSelection={onChangeChatModelSelection}
            onChangeChatReasoningEffort={onChangeChatReasoningEffort}
          />
        ) : null}
        {normalizedActiveTab === "flow" ? (
          <FlowWorkspaceView
            detail={detail}
            form={form}
            planDraft={planDraft}
            activeJob={activeJob}
            autoRunAfterPlan={autoRunAfterPlan}
            selectedStepId={selectedStepId}
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
            onChangeAutoRunAfterPlan={onChangeAutoRunAfterPlan}
            onSelectStep={onSelectStep}
            onUpdateStepField={onUpdateStepField}
            onSaveStepLocal={onSaveStepLocal}
            onAddStep={onAddStep}
            onDeleteStep={onDeleteStep}
          />
        ) : null}
        {normalizedActiveTab === "dashboard" ? (
          <DashboardView
            detail={detail}
            planDraft={planDraft}
            programSettings={programSettings}
            modelPresets={modelPresets}
            modelCatalog={modelCatalog}
            activeJob={activeJob}
          />
        ) : null}
        {developerMode && normalizedActiveTab === "reports" ? <ReportsView reports={detail?.reports} /> : null}
        {normalizedActiveTab === "history" ? (
          <HistoryView detail={visibleHistoryDetail} busy={busy} onDeleteHistoryEntry={onDeleteHistoryEntry} />
        ) : null}
        {normalizedActiveTab === "config" ? (
          <ConfigEditorView
            form={form}
            modelPresets={modelPresets}
            modelCatalog={modelCatalog}
            codexStatus={detail?.codex_status}
            busy={busy}
            activeJob={activeJob}
            onChangeForm={onChangeForm}
            onChangeProgramSettings={onChangeProgramSettings}
            onSaveProject={onSaveProject}
            onChooseDirectory={onChooseDirectory}
            onArchiveProject={onArchiveProject}
            onDeleteProject={onDeleteProject}
          />
        ) : null}
        {normalizedActiveTab === "app-settings" ? (
          <AppSettingsView
            settings={programSettings}
            codexStatus={detail?.codex_status}
            shareSettings={shareSettings}
            shareDetail={workspaceShareDetail}
            busy={busy}
            shareBusy={shareBusy}
            dirty={programSettingsDirty}
            onChangeSettings={onChangeProgramSettings}
            onSaveSettings={onSaveProgramSettings}
            onGenerateShareLink={onGenerateShareLink}
            onCopyShareLink={onCopyShareLink}
            onRevokeShareLink={onRevokeShareLink}
            onChangeShareSettings={onChangeShareSettings}
          />
        ) : null}
      </Suspense>
    </section>
  );
}, centerWorkspacePropsEqual);
