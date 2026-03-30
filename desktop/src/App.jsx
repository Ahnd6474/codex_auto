import { Suspense, lazy, useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { CenterWorkspace } from "./components/layout/CenterWorkspace";
import { IdeToolbar } from "./components/layout/IdeToolbar";
import { RunProgressPanel } from "./components/layout/RunProgressPanel";
import { Splitter } from "./components/layout/Splitter";
import { StatusBar } from "./components/layout/StatusBar";
import { nextRightSidebarState, nextSidebarTab } from "./controllerHelpers";
import { useDesktopController } from "./hooks/useDesktopController";
import { useI18n } from "./i18n";
import { isActiveExecutionStatus, toggleStepSelection } from "./utils";

const SIDEBAR_MIN = 200;
const SIDEBAR_MAX = 500;
const RIGHT_MIN = 260;
const RIGHT_MAX = 520;
const RIGHT_COLLAPSED_WIDTH = 52;
const BOTTOM_MIN = 120;
const BOTTOM_MAX = 600;

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function lazyNamedExport(loader, exportName) {
  return lazy(() => loader().then((module) => ({ default: module[exportName] })));
}

function scheduleIdleWork(callback) {
  if (typeof window === "undefined") {
    return () => {};
  }
  if (typeof window.requestIdleCallback === "function") {
    const handle = window.requestIdleCallback(callback, { timeout: 1200 });
    return () => window.cancelIdleCallback?.(handle);
  }
  const handle = window.setTimeout(callback, 200);
  return () => window.clearTimeout(handle);
}

function PanelSuspenseFallback({ className = "" }) {
  return <div className={className} aria-hidden="true" />;
}

const LazyCommandPalette = lazyNamedExport(
  () => import("./components/layout/CommandPalette"),
  "CommandPalette",
);
const LazySidebarPane = lazyNamedExport(
  () => import("./components/layout/SidebarPane"),
  "SidebarPane",
);
const LazyRightSidebarPane = lazyNamedExport(
  () => import("./components/layout/RightSidebarPane"),
  "RightSidebarPane",
);
const LazyBottomToolPanel = lazyNamedExport(
  () => import("./components/layout/BottomToolPanel"),
  "BottomToolPanel",
);

export default function App() {
  const controller = useDesktopController();
  const { t } = useI18n();
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const [rightTab, setRightTab] = useState("output");
  const lastShiftRef = useRef(0);
  const controllerCommandRef = useRef({
    setCenterTab: controller.setCenterTab,
    setSidebarTab: controller.setSidebarTab,
    setBottomCollapsed: controller.setBottomCollapsed,
    generatePlan: controller.generatePlan,
    runPlan: controller.runPlan,
    forceRefresh: controller.forceRefresh,
    startNewProject: controller.startNewProject,
  });

  const keybindingActionsRef = useRef({
    setCenterTab: controller.setCenterTab,
    setSidebarTab: controller.setSidebarTab,
    toggleBottom: () => controller.setBottomCollapsed((value) => !value),
  });

  useEffect(() => {
    keybindingActionsRef.current = {
      setCenterTab: controller.setCenterTab,
      setSidebarTab: controller.setSidebarTab,
      toggleBottom: () => controller.setBottomCollapsed((value) => !value),
    };
  }, [controller.setCenterTab, controller.setSidebarTab, controller.setBottomCollapsed]);

  useEffect(() => {
    controllerCommandRef.current = {
      setCenterTab: controller.setCenterTab,
      setSidebarTab: controller.setSidebarTab,
      setBottomCollapsed: controller.setBottomCollapsed,
      generatePlan: controller.generatePlan,
      runPlan: controller.runPlan,
      forceRefresh: controller.forceRefresh,
      startNewProject: controller.startNewProject,
    };
  }, [
    controller.forceRefresh,
    controller.generatePlan,
    controller.runPlan,
    controller.setBottomCollapsed,
    controller.setCenterTab,
    controller.setSidebarTab,
    controller.startNewProject,
  ]);

  useEffect(() => scheduleIdleWork(() => {
    void import("./components/layout/CommandPalette");
    void import("./components/layout/SidebarPane");
    void import("./components/layout/RightSidebarPane");
    void import("./components/layout/BottomToolPanel");
  }), []);

  useEffect(() => {
    const nextTheme = controller.programSettings?.ui_theme === "light" ? "light" : "dark";
    document.documentElement.dataset.theme = nextTheme;
  }, [controller.programSettings?.ui_theme]);

  useEffect(() => {
    if (!controller.message || controller.message.tone === "error") {
      return undefined;
    }
    const timer = window.setTimeout(() => controller.setMessage(null), 3000);
    return () => window.clearTimeout(timer);
  }, [controller.message, controller.setMessage]);

  useEffect(() => {
    function handleKeyDown(event) {
      const { setCenterTab, setSidebarTab, toggleBottom } = keybindingActionsRef.current;

      if ((event.ctrlKey || event.metaKey) && !event.altKey && event.key >= "1" && event.key <= "6") {
        const tabs = ["ai-chat", "config", "flow", "dashboard", "history", "app-settings"];
        setCenterTab(tabs[Number.parseInt(event.key, 10) - 1]);
        event.preventDefault();
        return;
      }

      if (event.altKey && !event.ctrlKey && !event.metaKey && event.key >= "1" && event.key <= "3") {
        const sidebarTabs = ["workspace", "plans", "reservations"];
        const target = sidebarTabs[Number.parseInt(event.key, 10) - 1];
        setSidebarTab((current) => nextSidebarTab(current, target));
        event.preventDefault();
        return;
      }

      if (event.altKey && (event.key === "b" || event.key === "B")) {
        toggleBottom();
        event.preventDefault();
        return;
      }

      if ((event.ctrlKey || event.metaKey) && event.shiftKey && (event.key === "a" || event.key === "A")) {
        setCommandPaletteOpen((value) => !value);
        event.preventDefault();
        return;
      }

      if (event.key === "Shift" && !event.ctrlKey && !event.altKey && !event.metaKey) {
        const now = Date.now();
        if (now - lastShiftRef.current < 400) {
          setCommandPaletteOpen(true);
          lastShiftRef.current = 0;
        } else {
          lastShiftRef.current = now;
        }
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const sidebarSnap = useRef(controller.sidebarWidth);
  const rightSnap = useRef(controller.rightWidth);
  const bottomSnap = useRef(controller.bottomHeight);
  const draggingRef = useRef(null);

  const makeSplitterHandlers = useCallback((name, snap, setter, min, max, sign) => ({
    onResize: (delta) => {
      if (draggingRef.current !== name) {
        snap.current =
          name === "sidebar"
            ? controller.sidebarWidth
            : name === "right"
              ? controller.rightWidth
              : controller.bottomHeight;
        draggingRef.current = name;
      }
      setter(clamp(snap.current + delta * sign, min, max));
    },
    onDragEnd: () => {
      draggingRef.current = null;
    },
  }), [controller.bottomHeight, controller.rightWidth, controller.sidebarWidth]);

  const sidebarSplitter = useMemo(
    () => makeSplitterHandlers("sidebar", sidebarSnap, controller.setSidebarWidth, SIDEBAR_MIN, SIDEBAR_MAX, 1),
    [controller.setSidebarWidth, makeSplitterHandlers],
  );
  const bottomSplitter = useMemo(
    () => makeSplitterHandlers("bottom", bottomSnap, controller.setBottomHeight, BOTTOM_MIN, BOTTOM_MAX, -1),
    [controller.setBottomHeight, makeSplitterHandlers],
  );
  const rightSplitter = useMemo(
    () => makeSplitterHandlers("right", rightSnap, controller.setRightWidth, RIGHT_MIN, RIGHT_MAX, -1),
    [controller.setRightWidth, makeSplitterHandlers],
  );

  const detail = controller.projectDetail;
  const deferredDetail = useDeferredValue(detail);
<<<<<<< Updated upstream
  const deferredPlanDraft = useDeferredValue(controller.planDraft);
  const useLiveExecutionDetail =
    isActiveExecutionStatus(controller.activeJob?.status)
    || isActiveExecutionStatus(detail?.project?.current_status);
  const sidebarDetail = useLiveExecutionDetail ? detail : deferredDetail;
  const sidebarPlanDraft = useLiveExecutionDetail && detail?.plan ? detail.plan : deferredPlanDraft;
=======
>>>>>>> Stashed changes
  const sidebarOpen = Boolean(controller.sidebarTab);
  const showRightSidebar = controller.centerTab !== "ai-chat";
  const sidebarStyle = sidebarOpen ? { width: controller.sidebarWidth, flex: `0 0 ${controller.sidebarWidth}px` } : undefined;
  const rightPaneWidth = controller.rightCollapsed ? RIGHT_COLLAPSED_WIDTH : controller.rightWidth;
  const rightSidebarStyle = showRightSidebar
    ? { width: rightPaneWidth, minWidth: rightPaneWidth, flex: `0 0 ${rightPaneWidth}px` }
    : undefined;
  const compact = Boolean(controller.programSettings?.compact_mode);

  const handleSelectStep = useCallback((stepId) => {
    controller.setSelectedStepId((current) => toggleStepSelection(current, stepId));
  }, [controller.setSelectedStepId]);
  const handleOpenSettings = useCallback(() => {
    controller.setCenterTab("app-settings");
  }, [controller.setCenterTab]);
  const handleToggleBottom = useCallback(() => {
    controller.setBottomCollapsed((value) => !value);
  }, [controller.setBottomCollapsed]);
  const handleCloseCommandPalette = useCallback(() => {
    setCommandPaletteOpen(false);
  }, []);

  const paletteActions = useMemo(() => [
    { id: "tab-ai-chat", label: t("tab.aiChat"), shortcut: "Ctrl+1", category: "Tab", keywords: "ai chat prompt plan flow", onExecute: () => controllerCommandRef.current.setCenterTab("ai-chat") },
    { id: "tab-config", label: t("tab.config"), shortcut: "Ctrl+2", category: "Tab", keywords: "config settings project", onExecute: () => controllerCommandRef.current.setCenterTab("config") },
    { id: "tab-flow", label: t("tab.flow"), shortcut: "Ctrl+3", category: "Tab", keywords: "flow run plan execution", onExecute: () => controllerCommandRef.current.setCenterTab("flow") },
    { id: "tab-dashboard", label: t("tab.dashboard"), shortcut: "Ctrl+4", category: "Tab", keywords: "dashboard metrics", onExecute: () => controllerCommandRef.current.setCenterTab("dashboard") },
    { id: "tab-history", label: t("tab.history"), shortcut: "Ctrl+5", category: "Tab", keywords: "history runs", onExecute: () => controllerCommandRef.current.setCenterTab("history") },
    { id: "tab-settings", label: t("toolbar.programSettings"), shortcut: "Ctrl+6", category: "Tab", keywords: "settings preferences program", onExecute: () => controllerCommandRef.current.setCenterTab("app-settings") },
    { id: "sidebar-workspace", label: t("sidebar.explorer"), shortcut: "Alt+1", category: "Sidebar", keywords: "explorer files workspace", onExecute: () => controllerCommandRef.current.setSidebarTab((current) => nextSidebarTab(current, "workspace")) },
    { id: "sidebar-plans", label: t("tab.flow"), shortcut: "Alt+2", category: "Sidebar", keywords: "flow steps checkpoints", onExecute: () => controllerCommandRef.current.setSidebarTab((current) => nextSidebarTab(current, "plans")) },
    { id: "sidebar-reservations", label: "Job Queue", shortcut: "Alt+3", category: "Sidebar", keywords: "reservations queue jobs", onExecute: () => controllerCommandRef.current.setSidebarTab((current) => nextSidebarTab(current, "reservations")) },
    { id: "toggle-bottom", label: "Toggle Bottom Panel", shortcut: "Alt+B", category: "Panel", keywords: "bottom tool panel logs json tokens", onExecute: () => controllerCommandRef.current.setBottomCollapsed((value) => !value) },
    { id: "generate-plan", label: t("action.generatePlan"), category: "Action", keywords: "generate plan ai", onExecute: () => controllerCommandRef.current.generatePlan() },
    { id: "run-plan", label: t("action.runRemaining"), category: "Action", keywords: "run execute remaining", onExecute: () => controllerCommandRef.current.runPlan() },
    { id: "refresh", label: t("action.refresh"), category: "Action", keywords: "refresh reload", onExecute: () => controllerCommandRef.current.forceRefresh() },
    { id: "new-project", label: t("action.new"), category: "Action", keywords: "new project create", onExecute: () => controllerCommandRef.current.startNewProject() },
  ], [t]);

  return (
    <main className={`ide-shell ${compact ? "ide-shell--compact" : ""}`.trim()}>
      <IdeToolbar
        projects={controller.filteredProjects}
        selectedProjectId={controller.selectedProjectId}
        onSelectProject={controller.loadProject}
        onNewProject={controller.startNewProject}
        projectDetail={detail}
        planDraft={controller.planDraft}
        pendingCheckpoint={detail?.checkpoints?.pending || null}
        busy={controller.busy}
        activeJob={controller.activeJob}
        activeCenterTab={controller.centerTab}
        projectPath={detail?.project?.repo_path || controller.projectForm?.project_dir || ""}
        githubUrl={detail?.github?.origin_url || detail?.github?.repo_url || controller.projectForm?.origin_url || ""}
        shareUrl={
          controller.workspaceShareDetail?.active_session?.share_url
          || controller.workspaceShareDetail?.project_active_session?.share_url
          || ""
        }
        shareBusy={controller.shareBusy}
        onRefresh={controller.forceRefresh}
        onOpenSettings={handleOpenSettings}
        onGeneratePlan={controller.generatePlan}
        onRunPlan={controller.runPlan}
        onApproveCheckpoint={controller.approveCheckpoint}
        onSmartShareLink={controller.smartShareLink}
        onOpenFolder={controller.openRepoInFolder}
        onOpenVsCode={controller.openRepoInVsCode}
        onOpenGithub={controller.openRepoOnGithub}
      />

      <RunProgressPanel detail={detail} planDraft={controller.planDraft} activeJob={controller.activeJob} />

      {controller.message ? (
        <section className={`banner banner--${controller.message.tone}`}>
          <span>{controller.message.text}</span>
          <button className="toolbar-button toolbar-button--ghost" onClick={() => controller.setMessage(null)} type="button">
            {t("action.dismiss")}
          </button>
        </section>
      ) : null}

      <div className="ide-body">
        <div
          className={`ide-pane ide-pane--sidebar ${sidebarOpen ? "" : "ide-pane--sidebar-collapsed"}`.trim()}
          style={sidebarStyle}
        >
          <Suspense fallback={<PanelSuspenseFallback className="ide-pane ide-pane--sidebar" />}>
            <LazySidebarPane
              activeTab={controller.sidebarTab}
              onChangeTab={(nextTab) =>
                controller.setSidebarTab((currentTab) => nextSidebarTab(currentTab, nextTab))
              }
              projects={controller.filteredProjects}
              historyProjects={controller.filteredHistoryProjects}
              selectedProjectId={controller.selectedProjectId}
              selectedHistoryId={controller.selectedHistoryId}
              loadingProjectId={controller.loadingProjectId}
              projectFilter={controller.projectFilter}
              workspaceFilter={controller.workspaceFilter}
              onProjectFilterChange={controller.setProjectFilter}
              onWorkspaceFilterChange={controller.setWorkspaceFilter}
              onSelectProject={controller.loadProject}
              onSelectHistory={controller.setSelectedHistoryId}
              onNewProject={controller.startNewProject}
              onArchiveProject={controller.archiveProjectById}
              onDeleteProject={controller.deleteProjectById}
              onDeleteHistoryEntry={controller.deleteHistoryEntry}
              workspaceTree={sidebarDetail?.workspace_tree}
              checkpoints={sidebarDetail?.checkpoints}
              detail={sidebarDetail}
              planDraft={sidebarPlanDraft}
              activeJob={controller.activeJob}
              selectedStepId={controller.selectedStepId}
              onSelectStep={handleSelectStep}
              github={sidebarDetail?.github}
              planPrompt={sidebarPlanDraft?.project_prompt || ""}
              onOpenFolder={controller.openRepoInFolder}
              onOpenVsCode={controller.openRepoInVsCode}
              onOpenGithub={controller.openRepoOnGithub}
              queuedJobs={controller.queuedJobs}
              onCancelQueuedJob={controller.cancelQueuedReservation}
              busy={controller.busy}
            />
          </Suspense>
        </div>

        {sidebarOpen ? (
          <Splitter axis="vertical" onResize={sidebarSplitter.onResize} onDragEnd={sidebarSplitter.onDragEnd} title="Resize sidebar" />
        ) : null}

<<<<<<< Updated upstream
        {/* ── Center: Full-screen AI Chat ── */}
        <div className="ide-center-column ide-chat-center">
          <Suspense fallback={<PanelSuspenseFallback className="ide-chat-center" />}>
            <LazyRightSidebarPane
              activeTab={rightTab}
              collapsed={false}
              chatCenterMode
              onChangeTab={handleRightTabChange}
              detail={sidebarDetail}
              planDraft={sidebarPlanDraft}
              selectedStepId={controller.selectedStepId}
              modelPresets={controller.modelPresets}
              form={controller.projectForm}
              activeJob={controller.activeJob}
              busy={controller.busy}
              onChangeForm={controller.setProjectForm}
              chat={sidebarDetail?.chat}
              selectedChatSessionId={controller.selectedChatSessionId}
              chatDraftSession={controller.chatDraftSession}
              onSelectChatSession={controller.loadChatSession}
              onStartNewChatSession={controller.startNewChatSession}
              onSendChatMessage={controller.sendChatMessage}
              onResolveCommonRequirement={controller.resolveCommonRequirement}
              onReopenCommonRequirement={controller.reopenCommonRequirement}
              onRecordSpineCheckpoint={controller.recordSpineCheckpoint}
              onUpdateCommonRequirement={controller.updateCommonRequirement}
              onDeleteCommonRequirement={controller.deleteCommonRequirement}
              onUpdateSpineCheckpoint={controller.updateSpineCheckpoint}
              onDeleteSpineCheckpoint={controller.deleteSpineCheckpoint}
              promptValue={controller.planDraft?.project_prompt || ""}
              onPromptChange={(value) =>
                controller.syncPlan({
                  ...(controller.planDraft || {}),
                  project_prompt: value,
                })
              }
              onGeneratePlan={controller.generatePlan}
              onRunPlan={controller.runPlan}
            />
          </Suspense>
        </div>

        {/* Splitter between chat and workspace panel */}
        <Splitter axis="vertical" onResize={workspaceSplitter.onResize} onDragEnd={workspaceSplitter.onDragEnd} title="Resize workspace panel" />

        {/* ── Right: CenterWorkspace (run/config/dashboard/history) ── */}
        <div
          className="ide-pane ide-pane--workspace-right"
          style={{ width: workspaceWidth, flex: `0 0 ${workspaceWidth}px` }}
        >
          <div className="ide-center-column" style={{ height: "100%" }}>
=======
        <div className="ide-pane ide-pane--workspace-right" style={{ flex: "1 1 auto", minWidth: 0 }}>
          <div className="ide-center-column" style={{ height: "100%", flex: "1 1 auto", minWidth: 0 }}>
>>>>>>> Stashed changes
            <div className="ide-main">
              <CenterWorkspace
                activeTab={controller.centerTab}
                onChangeTab={controller.setCenterTab}
                detail={detail}
                workspaceShareDetail={controller.workspaceShareDetail}
                form={controller.projectForm}
                programSettings={controller.programSettings}
                planDraft={controller.planDraft}
                historyDetail={controller.historyDetail}
                selectedHistoryId={controller.selectedHistoryId}
                shareSettings={controller.shareSettings}
                autoRunAfterPlan={controller.autoRunAfterPlan}
                selectedStepId={controller.selectedStepId}
                modelPresets={controller.modelPresets}
                modelCatalog={controller.modelCatalog}
                busy={controller.busy}
                canRequestStop={controller.canRequestStop}
                canCancelReservation={controller.canCancelReservation}
                shareBusy={controller.shareBusy}
                queuedJobs={controller.queuedJobs}
                chat={detail?.chat}
                selectedChatSessionId={controller.selectedChatSessionId}
                chatDraftSession={controller.chatDraftSession}
                onChangeForm={controller.setProjectForm}
                onChangeProgramSettings={controller.setProgramSettings}
                onSaveProject={controller.saveProject}
                onSaveProgramSettings={controller.saveProgramSettings}
                programSettingsDirty={controller.programSettingsDirty}
                onChooseDirectory={controller.chooseDirectory}
                onArchiveProject={controller.archiveProject}
                onDeleteProject={controller.deleteProject}
                onDeleteHistoryEntry={controller.deleteHistoryEntry}
                onGenerateShareLink={controller.generateShareLink}
                onCopyShareLink={controller.copyShareLink}
                onRevokeShareLink={controller.revokeShareLink}
                onChangeShareSettings={controller.setShareSettings}
                onChangeAutoRunAfterPlan={controller.setAutoRunAfterPlan}
                onPromptChange={(value) =>
                  controller.syncPlan({
                    ...(controller.planDraft || {}),
                    project_prompt: value,
                  })
                }
                onGeneratePlan={controller.generatePlan}
                onSavePlan={controller.savePlan}
                onResetPlan={controller.resetPlan}
                onRunPlan={controller.runPlan}
                onRunManualDebugger={controller.runManualDebugger}
                onRunManualMerger={controller.runManualMerger}
                onRequestStop={controller.requestStop}
                onCancelQueuedJob={controller.cancelQueuedReservation}
                onSelectStep={handleSelectStep}
                onUpdateStepField={controller.updateSelectedStep}
                onSaveStepLocal={controller.saveStepLocal}
                onAddStep={controller.addStep}
                onDeleteStep={controller.deleteStep}
                onMoveStep={controller.moveStep}
                onSelectChatSession={controller.loadChatSession}
                onStartNewChatSession={controller.startNewChatSession}
                onSendChatMessage={controller.sendChatMessage}
                onChangeChatModelSelection={controller.setChatModelSelection}
                onChangeChatReasoningEffort={controller.setChatReasoningEffort}
                activeJob={controller.activeJob}
                hidePromptStrip
              />
            </div>

            {!controller.bottomCollapsed ? (
              <>
                <Splitter axis="horizontal" onResize={bottomSplitter.onResize} onDragEnd={bottomSplitter.onDragEnd} title="Resize bottom panel" />
                <div className="ide-pane ide-pane--bottom" style={{ height: controller.bottomHeight, flex: `0 0 ${controller.bottomHeight}px` }}>
                  <Suspense fallback={<PanelSuspenseFallback className="ide-pane ide-pane--bottom" />}>
                    <LazyBottomToolPanel
                      activeTab={controller.bottomTab}
                      onChangeTab={controller.setBottomTab}
                      data={sidebarDetail}
                      onHide={() => controller.setBottomCollapsed(true)}
                    />
                  </Suspense>
                </div>
              </>
            ) : null}
          </div>

          {showRightSidebar ? (
            <>
              <Splitter axis="vertical" onResize={rightSplitter.onResize} onDragEnd={rightSplitter.onDragEnd} title="Resize right sidebar" />
              <div className="ide-pane" style={rightSidebarStyle}>
                <Suspense fallback={<PanelSuspenseFallback className="ide-pane" />}>
                  <LazyRightSidebarPane
                    activeTab={rightTab}
                    collapsed={controller.rightCollapsed}
                    includeChatTab={false}
                    onChangeTab={(nextTab) => {
                      const nextState = nextRightSidebarState(rightTab, nextTab, controller.rightCollapsed);
                      setRightTab(nextState.tab);
                      controller.setRightCollapsed(nextState.collapsed);
                    }}
                    detail={detail}
                    planDraft={controller.planDraft}
                    selectedStepId={controller.selectedStepId}
                    modelPresets={controller.modelPresets}
                    modelCatalog={controller.modelCatalog}
                    form={controller.projectForm}
                    activeJob={controller.activeJob}
                    busy={controller.busy}
                    onChangeForm={controller.setProjectForm}
                    chat={detail?.chat}
                    chatSettings={controller.programSettings}
                    selectedChatSessionId={controller.selectedChatSessionId}
                    chatDraftSession={controller.chatDraftSession}
                    onSelectChatSession={controller.loadChatSession}
                    onStartNewChatSession={controller.startNewChatSession}
                    onSendChatMessage={controller.sendChatMessage}
                    onChangeChatModelSelection={controller.setChatModelSelection}
                    onChangeChatReasoningEffort={controller.setChatReasoningEffort}
                  />
                </Suspense>
              </div>
            </>
          ) : null}
        </div>
      </div>

      <StatusBar
        detail={detail}
        activeJob={controller.activeJob}
        queuedJobs={controller.queuedJobs}
        modelPresets={controller.modelPresets}
        bottomCollapsed={controller.bottomCollapsed}
        onToggleBottom={handleToggleBottom}
      />

      {commandPaletteOpen ? (
        <Suspense fallback={null}>
          <LazyCommandPalette
            open={commandPaletteOpen}
            onClose={handleCloseCommandPalette}
            actions={paletteActions}
          />
        </Suspense>
      ) : null}
    </main>
  );
}
