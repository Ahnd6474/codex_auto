import { useEffect } from "react";
import { CenterWorkspace } from "./components/layout/CenterWorkspace";
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
      if (event.key >= "1" && event.key <= "5") {
        const tabs = ["run", "dashboard", "reports", "history", "config"];
        controller.setCenterTab(tabs[Number.parseInt(event.key, 10) - 1]);
        event.preventDefault();
      }
      if (event.key.toLowerCase() === "b") {
        controller.setBottomCollapsed((current) => !current);
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
        projectDetail={detail}
        planDraft={controller.planDraft}
        busy={controller.busy}
        activeJob={controller.activeJob}
        onRefresh={controller.forceRefresh}
        onGeneratePlan={controller.generatePlan}
        onRunPlan={controller.runPlan}
        onRunCloseout={controller.runCloseout}
        onApproveCheckpoint={controller.approveCheckpoint}
        onToggleBottom={() => controller.setBottomCollapsed((current) => !current)}
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
        <div className="ide-pane ide-pane--sidebar">
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
            onNewProject={controller.startNewProject}
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
            planDraft={controller.planDraft}
            selectedStepId={controller.selectedStepId}
            modelPresets={controller.modelPresets}
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
      </div>
    </main>
  );
}
