import { Suspense, useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { BottomToolPanel } from "./components/layout/BottomToolPanel";
import { CenterWorkspace } from "./components/layout/CenterWorkspace";
import { IdeToolbar } from "./components/layout/IdeToolbar";
import { RightSidebarPane } from "./components/layout/RightSidebarPane";
import { RunProgressPanel } from "./components/layout/RunProgressPanel";
import { SidebarPane } from "./components/layout/SidebarPane";
import { Splitter } from "./components/layout/Splitter";
import { StatusBar } from "./components/layout/StatusBar";
import { nextRightSidebarState, nextSidebarTab } from "./controllerHelpers";
import { useDesktopController } from "./hooks/useDesktopController";
import { useI18n } from "./i18n";
import { lazyNamedExport } from "./lazyLoad";
import { planHasFlowContent, toggleStepSelection } from "./utils";

const SIDEBAR_MIN = 200;
const SIDEBAR_MAX = 500;
const RIGHT_MIN = 260;
const RIGHT_MAX = 520;
const RIGHT_RAIL_WIDTH = 36;
const BOTTOM_MIN = 120;
const BOTTOM_MAX = 600;

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

const LazyCommandPalette = lazyNamedExport(
  () => import("./components/layout/CommandPalette"),
  "CommandPalette",
);

export default function App() {
  const controller = useDesktopController();
  const { t } = useI18n();
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const [rightTab, setRightTab] = useState("flow");
  const lastShiftRef = useRef(0);
  const hadFlowContentRef = useRef(false);
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
  const sidebarOpen = Boolean(controller.sidebarTab);
  const sidebarStyle = sidebarOpen ? { width: controller.sidebarWidth, flex: `0 0 ${controller.sidebarWidth}px` } : undefined;
  const rightPaneWidth = controller.rightCollapsed ? RIGHT_RAIL_WIDTH : controller.rightWidth;
  const rightSidebarStyle = { width: rightPaneWidth, minWidth: rightPaneWidth, flex: `0 0 ${rightPaneWidth}px` };
  const compact = Boolean(controller.programSettings?.compact_mode);
  const hasFlowContent = useMemo(
    () => planHasFlowContent(detail, controller.planDraft),
    [detail, controller.planDraft],
  );

  useEffect(() => {
    const activeCommand = String(controller.activeJob?.command || "").trim().toLowerCase();
    const activeStatus = String(controller.activeJob?.status || "").trim().toLowerCase();
    if (
      ["generate-plan", "run-plan", "run-closeout", "run-manual-debugger", "run-manual-merger"].includes(activeCommand)
      && ["queued", "running", "completed"].includes(activeStatus)
    ) {
      setRightTab("flow");
    }
  }, [controller.activeJob?.command, controller.activeJob?.status]);

  useEffect(() => {
    if (!hadFlowContentRef.current && hasFlowContent) {
      setRightTab("flow");
    }
    hadFlowContentRef.current = hasFlowContent;
  }, [hasFlowContent]);

  const handleSelectStep = useCallback((stepId) => {
    controller.setSelectedStepId((current) => toggleStepSelection(current, stepId));
  }, [controller.setSelectedStepId]);
  const handleOpenSettings = useCallback(() => {
    controller.setCenterTab("app-settings");
  }, [controller.setCenterTab]);
  const handleToggleBottom = useCallback(() => {
    controller.setBottomCollapsed((value) => !value);
  }, [controller.setBottomCollapsed]);
  const handleRightSidebarChange = useCallback((nextTab) => {
    const nextState = nextRightSidebarState(rightTab, nextTab, controller.rightCollapsed);
    if (nextState.tab) {
      setRightTab(nextState.tab);
    }
    controller.setRightCollapsed(nextState.collapsed);
  }, [controller.rightCollapsed, controller.setRightCollapsed, rightTab]);
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
        onDeleteSelectedProject={controller.deleteProject}
        onDeleteProject={controller.deleteProjectById}
        projectDetail={detail}
        planDraft={controller.planDraft}
        pendingCheckpoint={detail?.checkpoints?.pending || null}
        busy={controller.busy}
        activeJob={controller.activeJob}
        runActionDisabled={controller.runActionDisabled}
        runActionRunning={controller.runActionRunning}
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
          <SidebarPane
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
            workspaceTree={deferredDetail?.workspace_tree}
            checkpoints={deferredDetail?.checkpoints}
            detail={deferredDetail}
            planDraft={controller.planDraft}
            activeJob={controller.activeJob}
            selectedStepId={controller.selectedStepId}
            onSelectStep={handleSelectStep}
            github={deferredDetail?.github}
            planPrompt={controller.planDraft?.project_prompt || ""}
            onRunPlan={controller.runPlan}
            canRunPlan={controller.canRunPlan}
            onOpenFolder={controller.openRepoInFolder}
            onOpenVsCode={controller.openRepoInVsCode}
            onOpenGithub={controller.openRepoOnGithub}
            queuedJobs={controller.queuedJobs}
            onCancelQueuedJob={controller.cancelQueuedReservation}
            busy={controller.busy}
          />
        </div>

        {sidebarOpen ? (
          <Splitter axis="vertical" onResize={sidebarSplitter.onResize} onDragEnd={sidebarSplitter.onDragEnd} title="Resize sidebar" />
        ) : null}

        <div className="ide-pane ide-pane--workspace-right" style={{ flex: "1 1 auto", minWidth: 0 }}>
          <div className="ide-center-column" style={{ height: "100%", flex: "1 1 auto", minWidth: 0 }}>
            <div className="ide-main">
              <CenterWorkspace
                activeTab={controller.centerTab}
                onChangeTab={controller.setCenterTab}
                detail={detail}
                workspaceShareDetail={controller.workspaceShareDetail}
                form={controller.projectForm}
                programSettings={controller.programSettings}
                globalCodexStatus={controller.globalCodexStatus}
                toolingStatus={controller.toolingStatus}
                toolingJobs={controller.toolingJobs}
                planDraft={controller.planDraft}
                historyDetail={controller.historyDetail}
                selectedHistoryId={controller.selectedHistoryId}
                shareSettings={controller.shareSettings}
                autoRunAfterPlan={controller.autoRunAfterPlan}
                selectedStepId={controller.selectedStepId}
                modelPresets={controller.modelPresets}
                modelCatalog={controller.modelCatalog}
                busy={controller.busy}
                runActionDisabled={controller.runActionDisabled}
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
                onInstallTooling={controller.installTooling}
                onConnectOllama={controller.connectOllama}
                appSettingsTab={controller.appSettingsTab}
                ollamaManagerOpen={controller.ollamaManagerOpen}
                ollamaManagerLoading={controller.ollamaManagerLoading}
                onChangeAppSettingsTab={controller.setAppSettingsTab}
                onOpenOllamaManager={controller.openOllamaManager}
                onCloseOllamaManager={controller.closeOllamaManager}
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
                onRequestChatStop={controller.requestChatStop}
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
                chatSettings={controller.chatRuntime || {}}
                activeJob={controller.activeJob}
                chatJob={controller.chatJob}
                hidePromptStrip
              />
            </div>

            {!controller.bottomCollapsed ? (
              <>
                <Splitter axis="horizontal" onResize={bottomSplitter.onResize} onDragEnd={bottomSplitter.onDragEnd} title="Resize bottom panel" />
                <div className="ide-pane ide-pane--bottom" style={{ height: controller.bottomHeight, flex: `0 0 ${controller.bottomHeight}px` }}>
                  <BottomToolPanel
                    activeTab={controller.bottomTab}
                    onChangeTab={controller.setBottomTab}
                    data={deferredDetail}
                    onHide={() => controller.setBottomCollapsed(true)}
                  />
                </div>
              </>
            ) : null}
          </div>

          <>
          {controller.rightCollapsed ? null : (
            <Splitter axis="vertical" onResize={rightSplitter.onResize} onDragEnd={rightSplitter.onDragEnd} title="Resize right sidebar" />
          )}
          <div className="ide-pane" style={rightSidebarStyle}>
            <RightSidebarPane
              activeTab={rightTab}
              collapsed={controller.rightCollapsed}
              includeChatTab={false}
              onChangeTab={handleRightSidebarChange}
              detail={detail}
              planDraft={controller.planDraft}
              selectedStepId={controller.selectedStepId}
              modelPresets={controller.modelPresets}
              modelCatalog={controller.modelCatalog}
              form={controller.projectForm}
              activeJob={controller.activeJob}
              chatJob={controller.chatJob}
              busy={controller.busy}
              runActionDisabled={controller.runActionDisabled}
              autoRunAfterPlan={controller.autoRunAfterPlan}
              canRequestStop={controller.canRequestStop}
              canCancelReservation={controller.canCancelReservation}
              queuedJobs={controller.queuedJobs}
              onChangeForm={controller.setProjectForm}
              chat={detail?.chat}
              chatSettings={controller.chatRuntime || {}}
              selectedChatSessionId={controller.selectedChatSessionId}
              chatDraftSession={controller.chatDraftSession}
              onSelectChatSession={controller.loadChatSession}
              onStartNewChatSession={controller.startNewChatSession}
              onSendChatMessage={controller.sendChatMessage}
              onChangeChatModelSelection={controller.setChatModelSelection}
              onChangeChatReasoningEffort={controller.setChatReasoningEffort}
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
              onRequestChatStop={controller.requestChatStop}
              onCancelQueuedJob={controller.cancelQueuedReservation}
              onChangeAutoRunAfterPlan={controller.setAutoRunAfterPlan}
              onSelectStep={handleSelectStep}
              onUpdateStepField={controller.updateSelectedStep}
              onSaveStepLocal={controller.saveStepLocal}
              onAddStep={controller.addStep}
              onDeleteStep={controller.deleteStep}
            />
          </div>
          </>
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
