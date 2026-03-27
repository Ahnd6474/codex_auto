import { useEffect, useRef } from "react";
import { CenterWorkspace } from "./components/layout/CenterWorkspace";
import { IdeToolbar } from "./components/layout/IdeToolbar";
import { RunProgressPanel } from "./components/layout/RunProgressPanel";
import { SidebarPane } from "./components/layout/SidebarPane";
import { useDesktopController } from "./hooks/useDesktopController";
import { useI18n } from "./i18n";

export default function App() {
  const controller = useDesktopController();
  const { t } = useI18n();
  const keybindingActionsRef = useRef({
    setCenterTab: controller.setCenterTab,
  });

  useEffect(() => {
    keybindingActionsRef.current = {
      setCenterTab: controller.setCenterTab,
    };
  }, [controller.setCenterTab]);

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
      const { setCenterTab } = keybindingActionsRef.current;
      if (!(event.ctrlKey || event.metaKey)) {
        return;
      }
      if (event.key >= "1" && event.key <= "6") {
        const tabs = ["run", "config", "dashboard", "reports", "history", "app-settings"];
        setCenterTab(tabs[Number.parseInt(event.key, 10) - 1]);
        event.preventDefault();
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const detail = controller.projectDetail;

  return (
    <main className="ide-shell">
      <IdeToolbar
        projectDetail={detail}
        planDraft={controller.planDraft}
        pendingCheckpoint={detail?.checkpoints?.pending || null}
        busy={controller.busy}
        activeJob={controller.activeJob}
        activeCenterTab={controller.centerTab}
        onRefresh={controller.forceRefresh}
        onOpenSettings={() => controller.setCenterTab("app-settings")}
        onGeneratePlan={controller.generatePlan}
        onRunPlan={controller.runPlan}
        onApproveCheckpoint={controller.approveCheckpoint}
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
        <div className="ide-pane ide-pane--sidebar">
          <SidebarPane
            activeTab={controller.sidebarTab}
            onChangeTab={controller.setSidebarTab}
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
            onDeleteProject={controller.deleteProjectById}
            onDeleteAllProjects={controller.deleteAllProjects}
            workspaceTree={detail?.workspace_tree}
            checkpoints={detail?.checkpoints}
            github={detail?.github}
          />
        </div>

        <div className="ide-main">
          <CenterWorkspace
            activeTab={controller.centerTab}
            onChangeTab={controller.setCenterTab}
            detail={detail}
            form={controller.projectForm}
            programSettings={controller.programSettings}
            planDraft={controller.planDraft}
            historyDetail={controller.historyDetail}
            selectedHistoryId={controller.selectedHistoryId}
            shareSettings={controller.shareSettings}
            selectedStepId={controller.selectedStepId}
            modelPresets={controller.modelPresets}
            modelCatalog={controller.modelCatalog}
            busy={controller.busy}
            shareBusy={controller.shareBusy}
            onChangeForm={controller.setProjectForm}
            onChangeProgramSettings={controller.setProgramSettings}
            onChooseDirectory={controller.chooseDirectory}
            onDeleteProject={controller.deleteProject}
            onGenerateShareLink={controller.generateShareLink}
            onCopyShareLink={controller.copyShareLink}
            onRevokeShareLink={controller.revokeShareLink}
            onChangeShareSettings={controller.setShareSettings}
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
            onRequestStop={controller.requestStop}
            onSelectStep={controller.setSelectedStepId}
            onUpdateStepField={controller.updateSelectedStep}
            onSaveStepLocal={controller.saveStepLocal}
            onAddStep={controller.addStep}
            onDeleteStep={controller.deleteStep}
            onMoveStep={controller.moveStep}
            activeJob={controller.activeJob}
          />
        </div>
      </div>
    </main>
  );
}
