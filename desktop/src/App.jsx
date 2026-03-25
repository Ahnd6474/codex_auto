import { useEffect } from "react";
import { CenterWorkspace } from "./components/layout/CenterWorkspace";
import { DetailsPane } from "./components/layout/DetailsPane";
import { BottomToolPanel } from "./components/layout/BottomToolPanel";
import { IdeToolbar } from "./components/layout/IdeToolbar";
import { SidebarPane } from "./components/layout/SidebarPane";
import { Splitter } from "./components/layout/Splitter";
import { useDesktopController } from "./hooks/useDesktopController";

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

export default function App() {
  const controller = useDesktopController();

  useEffect(() => {
    function handleKeyDown(event) {
      if (!(event.ctrlKey || event.metaKey)) {
        return;
      }
      if (event.key >= "1" && event.key <= "6") {
        const tabs = ["dashboard", "overview", "run", "reports", "history", "config"];
        controller.setCenterTab(tabs[Number.parseInt(event.key, 10) - 1]);
        event.preventDefault();
      }
      if (event.key.toLowerCase() === "b") {
        controller.setBottomCollapsed((current) => !current);
        event.preventDefault();
      }
      if (event.key.toLowerCase() === "\\") {
        controller.setDetailsCollapsed((current) => !current);
        event.preventDefault();
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [controller]);

  const detail = controller.projectDetail;

  return (
    <main className="ide-shell">
      <IdeToolbar
        workspaceRoot={controller.workspaceRoot}
        projects={controller.projects}
        selectedProjectId={controller.selectedProjectId}
        projectDetail={detail}
        planDraft={controller.planDraft}
        busy={controller.busy}
        activeJob={controller.activeJob}
        onSelectProject={(repoId) => {
          controller.setSelectedProjectId(repoId);
          if (repoId) {
            controller.loadProject(repoId);
          }
        }}
        onNewProject={controller.startNewProject}
        onRefresh={() => (controller.selectedProjectId ? controller.reloadProject() : controller.refreshProjects())}
        onGeneratePlan={controller.generatePlan}
        onRunPlan={controller.runPlan}
        onRunCloseout={controller.runCloseout}
        onApproveCheckpoint={controller.approveCheckpoint}
        onOpenConfig={() => controller.setCenterTab("config")}
        onToggleSidebar={() => controller.setSidebarCollapsed((current) => !current)}
        onToggleBottom={() => controller.setBottomCollapsed((current) => !current)}
        onToggleDetails={() => controller.setDetailsCollapsed((current) => !current)}
      />

      {controller.message ? (
        <section className={`banner banner--${controller.message.tone}`}>
          <span>{controller.message.text}</span>
          <button className="toolbar-button toolbar-button--ghost" onClick={() => controller.setMessage(null)} type="button">
            Dismiss
          </button>
        </section>
      ) : null}

      <div className="ide-body">
        {!controller.sidebarCollapsed ? (
          <>
            <div className="ide-pane ide-pane--sidebar" style={{ width: `${controller.sidebarWidth}px` }}>
              <SidebarPane
                activeTab={controller.sidebarTab}
                onChangeTab={controller.setSidebarTab}
                projects={controller.filteredProjects}
                selectedProjectId={controller.selectedProjectId}
                selectedProjectSummary={controller.selectedProjectSummary}
                projectFilter={controller.projectFilter}
                workspaceFilter={controller.workspaceFilter}
                onProjectFilterChange={controller.setProjectFilter}
                onWorkspaceFilterChange={controller.setWorkspaceFilter}
                onSelectProject={(repoId) => {
                  controller.setSelectedProjectId(repoId);
                  controller.loadProject(repoId);
                }}
                workspaceTree={detail?.workspace_tree}
                checkpoints={detail?.checkpoints}
                github={detail?.github}
              />
            </div>
            <Splitter axis="vertical" onResize={(delta) => controller.setSidebarWidth((current) => clamp(current + delta, 220, 520))} />
          </>
        ) : null}

        <div className="ide-main">
          <CenterWorkspace
            activeTab={controller.centerTab}
            onChangeTab={controller.setCenterTab}
            detail={detail}
            form={controller.projectForm}
            planDraft={controller.planDraft}
            selectedStepId={controller.selectedStepId}
            modelPresets={controller.modelPresets}
            workspaceTree={detail?.workspace_tree}
            busy={controller.busy}
            onChangeForm={controller.setProjectForm}
            onChooseDirectory={controller.chooseDirectory}
            onSaveProject={controller.saveProject}
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
            onRunCloseout={controller.runCloseout}
            onRequestStop={controller.requestStop}
            onSelectStep={controller.setSelectedStepId}
            onUpdateStepField={controller.updateSelectedStep}
            onSaveStepLocal={controller.saveStepLocal}
            onAddStep={controller.addStep}
            onDeleteStep={controller.deleteStep}
            onMoveStep={controller.moveStep}
            activeJob={controller.activeJob}
          />

          {!controller.bottomCollapsed ? (
            <>
              <Splitter axis="horizontal" onResize={(delta) => controller.setBottomHeight((current) => clamp(current - delta, 160, 420))} />
              <div className="ide-pane ide-pane--bottom" style={{ height: `${controller.bottomHeight}px` }}>
                <BottomToolPanel activeTab={controller.bottomTab} onChangeTab={controller.setBottomTab} data={detail?.bottom_panels} />
              </div>
            </>
          ) : null}
        </div>

        {!controller.detailsCollapsed ? (
          <>
            <Splitter axis="vertical" onResize={(delta) => controller.setDetailsWidth((current) => clamp(current - delta, 260, 460))} />
            <div className="ide-pane ide-pane--details" style={{ width: `${controller.detailsWidth}px` }}>
              <DetailsPane detail={detail} planDraft={controller.planDraft} selectedStepId={controller.selectedStepId} modelPresets={controller.modelPresets} />
            </div>
          </>
        ) : null}
      </div>
    </main>
  );
}
