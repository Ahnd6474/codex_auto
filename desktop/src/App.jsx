import { useEffect, useMemo, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { bridgeRequest, getBridgeJob, startBridgeJob } from "./api";
import { FlowStage } from "./components/FlowStage";
import { SetupStage } from "./components/SetupStage";
import {
  basename,
  blankProjectForm,
  buildProjectPayload,
  cloneValue,
  commandLabel,
  firstSelectableStepId,
  progressCaption,
  projectFormFromDetail,
} from "./utils";

function messagePayload(tone, text) {
  return text ? { tone, text } : null;
}

export default function App() {
  const [workspaceRoot, setWorkspaceRoot] = useState("");
  const [defaultRuntime, setDefaultRuntime] = useState(null);
  const [modelPresets, setModelPresets] = useState([]);
  const [projects, setProjects] = useState([]);
  const [workspaceStats, setWorkspaceStats] = useState(null);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [setupMode, setSetupMode] = useState("welcome");
  const [currentStage, setCurrentStage] = useState("setup");
  const [projectForm, setProjectForm] = useState(blankProjectForm(null));
  const [projectDetail, setProjectDetail] = useState(null);
  const [planDraft, setPlanDraft] = useState({ steps: [], project_prompt: "", closeout_status: "not_started" });
  const [selectedStepId, setSelectedStepId] = useState("");
  const [planDirty, setPlanDirty] = useState(false);
  const [activeTab, setActiveTab] = useState("activity");
  const [pendingAction, setPendingAction] = useState("");
  const [activeJobId, setActiveJobId] = useState("");
  const [activeJob, setActiveJob] = useState(null);
  const [message, setMessage] = useState(null);

  const busy = Boolean(pendingAction || (activeJob && activeJob.status === "running"));
  const selectedProjectSummary = useMemo(
    () => projects.find((item) => item.repo_id === selectedProjectId)?.summary || "",
    [projects, selectedProjectId],
  );

  useEffect(() => {
    let cancelled = false;

    async function initialize() {
      try {
        const bootstrap = await bridgeRequest("bootstrap");
        if (cancelled) {
          return;
        }
        setWorkspaceRoot(bootstrap.workspace_root);
        setDefaultRuntime(bootstrap.default_runtime);
        setModelPresets(bootstrap.model_presets || []);
        setProjectForm(blankProjectForm(bootstrap.default_runtime));
        const listing = await bridgeRequest("list-projects", null, bootstrap.workspace_root);
        if (cancelled) {
          return;
        }
        setProjects(listing.projects || []);
        setWorkspaceStats(listing.workspace || null);
        if (!selectedProjectId && listing.projects?.length) {
          setSelectedProjectId(listing.projects[0].repo_id);
        }
      } catch (error) {
        if (!cancelled) {
          setMessage(messagePayload("error", String(error)));
        }
      }
    }

    initialize();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function tick() {
      try {
        if (activeJobId) {
          const job = await getBridgeJob(activeJobId);
          if (cancelled || !job) {
            return;
          }
          setActiveJob(job);
          if (job.status !== "running") {
            setActiveJobId("");
            if (job.result?.project) {
              setProjectDetail(job.result);
              setProjectForm(projectFormFromDetail(job.result, defaultRuntime));
              setPlanDraft(cloneValue(job.result.plan));
              setSelectedStepId(firstSelectableStepId(job.result.plan));
              setPlanDirty(false);
              setCurrentStage("flow");
            }
            const listing = await bridgeRequest("list-projects", null, workspaceRoot || null);
            if (!cancelled) {
              setProjects(listing.projects || []);
              setWorkspaceStats(listing.workspace || null);
              setMessage(
                job.status === "completed"
                  ? messagePayload("success", `${commandLabel(job.command)} completed.`)
                  : messagePayload("error", job.error || `${commandLabel(job.command)} failed.`),
              );
            }
          }
          return;
        }

        if (currentStage === "flow" && selectedProjectId) {
          const detail = await bridgeRequest("load-project", { repo_id: selectedProjectId }, workspaceRoot || null);
          if (cancelled) {
            return;
          }
          setProjectDetail(detail);
          if (!planDirty) {
            setPlanDraft(cloneValue(detail.plan));
            setSelectedStepId((current) => current || firstSelectableStepId(detail.plan));
          }
          return;
        }

        const listing = await bridgeRequest("list-projects", null, workspaceRoot || null);
        if (!cancelled) {
          setProjects(listing.projects || []);
          setWorkspaceStats(listing.workspace || null);
        }
      } catch (error) {
        if (!cancelled && !pendingAction) {
          setMessage(messagePayload("error", String(error)));
        }
      }
    }

    const handle = window.setInterval(tick, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(handle);
    };
  }, [activeJobId, currentStage, defaultRuntime, pendingAction, planDirty, selectedProjectId, workspaceRoot]);

  async function refreshProjects() {
    const listing = await bridgeRequest("list-projects", null, workspaceRoot || null);
    setProjects(listing.projects || []);
    setWorkspaceStats(listing.workspace || null);
    if (!selectedProjectId && listing.projects?.length) {
      setSelectedProjectId(listing.projects[0].repo_id);
    }
  }

  async function loadProject(repoId, { openFlow = false, syncEditor = true, syncForm = true } = {}) {
    setPendingAction("load-project");
    try {
      const detail = await bridgeRequest("load-project", { repo_id: repoId }, workspaceRoot || null);
      setSelectedProjectId(repoId);
      setProjectDetail(detail);
      if (syncForm) {
        setProjectForm(projectFormFromDetail(detail, defaultRuntime));
      }
      if (syncEditor) {
        setPlanDraft(cloneValue(detail.plan));
        setSelectedStepId(firstSelectableStepId(detail.plan));
        setPlanDirty(false);
      }
      if (openFlow) {
        setCurrentStage("flow");
      }
      return detail;
    } catch (error) {
      setMessage(messagePayload("error", String(error)));
      return null;
    } finally {
      setPendingAction("");
    }
  }

  async function withPending(label, action) {
    setPendingAction(label);
    setMessage(null);
    try {
      return await action();
    } catch (error) {
      setMessage(messagePayload("error", String(error)));
      return null;
    } finally {
      setPendingAction("");
    }
  }

  function syncPlan(nextPlan) {
    setPlanDraft(nextPlan);
    setPlanDirty(true);
  }

  function updateSelectedStep(field, value) {
    if (!selectedStepId) {
      return;
    }
    syncPlan({
      ...planDraft,
      steps: (planDraft.steps || []).map((step) =>
        step.step_id === selectedStepId
          ? {
              ...step,
              [field]: value,
            }
          : step,
      ),
    });
  }

  async function chooseDirectory() {
    try {
      const selected = await open({
        directory: true,
        multiple: false,
      });
      if (typeof selected !== "string") {
        return;
      }
      setProjectForm((current) => ({
        ...current,
        project_dir: selected,
        display_name: current.display_name || basename(selected),
      }));
    } catch (error) {
      setMessage(messagePayload("error", String(error)));
    }
  }

  function startNewProject() {
    setSetupMode("create");
    setCurrentStage("setup");
    setMessage(null);
    setProjectDetail(null);
    setPlanDirty(false);
    setSelectedStepId("");
    setProjectForm(blankProjectForm(defaultRuntime));
    setPlanDraft({ steps: [], project_prompt: "", closeout_status: "not_started" });
  }

  async function editSelectedProject() {
    if (!selectedProjectId) {
      setMessage(messagePayload("error", "Select a managed project first."));
      return;
    }
    await loadProject(selectedProjectId, { openFlow: false, syncEditor: true, syncForm: true });
    setSetupMode("edit");
  }

  async function openSelectedProject() {
    if (!selectedProjectId) {
      setMessage(messagePayload("error", "Select a managed project first."));
      return;
    }
    await loadProject(selectedProjectId, { openFlow: true, syncEditor: true, syncForm: true });
    setActiveTab("activity");
  }

  async function saveProject(openFlow) {
    await withPending("save-project-setup", async () => {
      const detail = await bridgeRequest("save-project-setup", buildProjectPayload(projectForm), workspaceRoot || null);
      setProjectDetail(detail);
      setSelectedProjectId(detail.project.repo_id);
      setProjectForm(projectFormFromDetail(detail, defaultRuntime));
      setPlanDraft(cloneValue(detail.plan));
      setSelectedStepId(firstSelectableStepId(detail.plan));
      setPlanDirty(false);
      await refreshProjects();
      setSetupMode("edit");
      if (openFlow) {
        setCurrentStage("flow");
      }
      setMessage(messagePayload("success", openFlow ? "Project saved and flow opened." : "Project setup saved."));
    });
  }

  async function savePlan() {
    if (!projectForm.project_dir.trim()) {
      setMessage(messagePayload("error", "Open a project first."));
      return;
    }
    await withPending("save-plan", async () => {
      const detail = await bridgeRequest("save-plan", buildProjectPayload(projectForm, planDraft), workspaceRoot || null);
      setProjectDetail(detail);
      setPlanDraft(cloneValue(detail.plan));
      setSelectedStepId(firstSelectableStepId(detail.plan));
      setPlanDirty(false);
      await refreshProjects();
      setMessage(messagePayload("success", "Edited plan saved."));
    });
  }

  async function resetPlan() {
    if (!projectForm.project_dir.trim()) {
      setMessage(messagePayload("error", "Open a project first."));
      return;
    }
    if (!window.confirm("Reset the saved prompt and remove all execution steps for this project?")) {
      return;
    }
    await withPending("reset-plan", async () => {
      const detail = await bridgeRequest("reset-plan", buildProjectPayload(projectForm), workspaceRoot || null);
      setProjectDetail(detail);
      setPlanDraft(cloneValue(detail.plan));
      setSelectedStepId("");
      setPlanDirty(false);
      await refreshProjects();
      setMessage(messagePayload("success", "Plan reset."));
    });
  }

  async function startJob(command, payload) {
    try {
      setMessage(null);
      const job = await startBridgeJob(command, payload, workspaceRoot || null);
      setActiveJobId(job.id);
      setActiveJob(job);
      setCurrentStage("flow");
      setMessage(messagePayload("info", `${commandLabel(command)} started.`));
    } catch (error) {
      setMessage(messagePayload("error", String(error)));
    }
  }

  async function generatePlan() {
    const prompt = planDraft?.project_prompt?.trim() || "";
    if (!projectForm.project_dir.trim()) {
      setMessage(messagePayload("error", "Prepare or open a project first."));
      return;
    }
    if (!prompt) {
      setMessage(messagePayload("error", "Prompt is required to generate the plan."));
      return;
    }
    if ((planDraft?.steps || []).some((step) => step.status === "completed")) {
      setMessage(messagePayload("error", "The plan already has completed steps. Edit the remaining steps instead of regenerating."));
      return;
    }
    if ((planDraft?.steps || []).length && !window.confirm("Replace the current unstarted plan with a new Codex-generated plan?")) {
      return;
    }
    await startJob("generate-plan", {
      ...buildProjectPayload(projectForm),
      prompt,
      max_steps: Math.max(1, Number.parseInt(String(projectForm.runtime?.max_blocks || 5), 10) || 1),
    });
  }

  async function runPlan() {
    if (!(planDraft?.steps || []).length) {
      setMessage(messagePayload("error", "Create or add at least one planned step first."));
      return;
    }
    await startJob("run-plan", buildProjectPayload(projectForm, planDraft));
  }

  async function runCloseout() {
    if (!(planDraft?.steps || []).length) {
      setMessage(messagePayload("error", "Create and complete the execution plan before running closeout."));
      return;
    }
    if ((planDraft.steps || []).some((step) => step.status !== "completed")) {
      setMessage(messagePayload("error", "Closeout can run only after all steps are completed."));
      return;
    }
    if (!window.confirm("Run final closeout now? This will do final cleanup, verification, smoke checks when possible, and handoff work.")) {
      return;
    }
    await startJob("run-closeout", buildProjectPayload(projectForm, planDraft));
  }

  async function requestStop() {
    if (!projectForm.project_dir.trim()) {
      return;
    }
    await withPending("request-stop", async () => {
      await bridgeRequest(
        "request-stop",
        {
          project_dir: projectForm.project_dir.trim(),
          source: "tauri-react-ui",
        },
        workspaceRoot || null,
      );
      const detail = await bridgeRequest(
        "load-project",
        {
          project_dir: projectForm.project_dir.trim(),
        },
        workspaceRoot || null,
      );
      setProjectDetail(detail);
      setMessage(messagePayload("info", "Stop requested after the current step."));
    });
  }

  async function reloadProject() {
    if (!selectedProjectId) {
      setMessage(messagePayload("error", "No project is open."));
      return;
    }
    await loadProject(selectedProjectId, { openFlow: true, syncEditor: true, syncForm: true });
    setMessage(messagePayload("success", "Project reloaded."));
  }

  function saveStepLocal() {
    if (!selectedStepId) {
      setMessage(messagePayload("error", "Select a pending step first."));
      return;
    }
    const step = (planDraft?.steps || []).find((item) => item.step_id === selectedStepId);
    if (!step || step.status !== "pending") {
      setMessage(messagePayload("error", "Only pending steps can be edited."));
      return;
    }
    setPlanDirty(true);
    setMessage(messagePayload("info", "Step updated locally. Save Edited Plan to persist the change."));
  }

  function addStep() {
    const steps = cloneValue(planDraft?.steps || []);
    if (selectedStepId) {
      const selectedStep = steps.find((step) => step.step_id === selectedStepId);
      if (selectedStep && selectedStep.status !== "pending") {
        setMessage(messagePayload("error", "Insert new steps after a pending step, or clear the selection to append at the end."));
        return;
      }
    }
    const insertAt = selectedStepId ? steps.findIndex((step) => step.step_id === selectedStepId) + 1 : steps.length;
    const newStep = {
      step_id: `TMP${steps.length + 1}`,
      title: "New pending step",
      display_description: "Describe the checkpoint for the user.",
      codex_description: "Describe the implementation work Codex should perform for this checkpoint.",
      test_command: projectForm.runtime?.test_cmd || "python -m pytest",
      success_criteria: "Run the configured verification command successfully.",
      status: "pending",
      notes: "",
    };
    steps.splice(insertAt, 0, newStep);
    syncPlan({
      ...(cloneValue(planDraft) || {}),
      steps,
    });
    setSelectedStepId(newStep.step_id);
  }

  function deleteStep() {
    const step = (planDraft?.steps || []).find((item) => item.step_id === selectedStepId);
    if (!step) {
      setMessage(messagePayload("error", "Select a step first."));
      return;
    }
    if (step.status !== "pending") {
      setMessage(messagePayload("error", "Only pending steps can be deleted."));
      return;
    }
    syncPlan({
      ...(cloneValue(planDraft) || {}),
      steps: (planDraft.steps || []).filter((item) => item.step_id !== selectedStepId),
    });
    setSelectedStepId("");
  }

  function moveStep(direction) {
    const steps = cloneValue(planDraft?.steps || []);
    const index = steps.findIndex((step) => step.step_id === selectedStepId);
    if (index < 0) {
      setMessage(messagePayload("error", "Select a pending step first."));
      return;
    }
    if (steps[index].status !== "pending") {
      setMessage(messagePayload("error", "Only pending steps can be reordered."));
      return;
    }
    const target = index + direction;
    if (target < 0 || target >= steps.length) {
      return;
    }
    if (steps[target].status !== "pending") {
      setMessage(messagePayload("error", "Pending steps can only move within the unstarted portion of the flow."));
      return;
    }
    [steps[index], steps[target]] = [steps[target], steps[index]];
    syncPlan({
      ...(cloneValue(planDraft) || {}),
      steps,
    });
  }

  const headerTitle = currentStage === "setup" ? "codex-auto Desktop" : projectDetail?.project?.display_name || projectDetail?.project?.slug || "codex-auto Desktop";
  const headerSubtitle =
    currentStage === "setup"
      ? "React + Tauri shell for the multi-repository orchestration workspace"
      : progressCaption(planDraft);

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <span className="eyebrow">AI Repo Operations</span>
          <h1>{headerTitle}</h1>
          <p>{headerSubtitle}</p>
        </div>
        <div className="topbar__meta">
          <span>Workspace</span>
          <strong>{workspaceRoot || "Loading..."}</strong>
        </div>
      </header>

      {message ? (
        <section className={`message-banner message-banner--${message.tone}`}>
          <span>{message.text}</span>
          <button className="button button--ghost" onClick={() => setMessage(null)} type="button">
            Dismiss
          </button>
        </section>
      ) : null}

      {activeJob && activeJob.status !== "running" ? (
        <section className={`message-banner message-banner--${activeJob.status === "completed" ? "success" : "error"}`}>
          <span>
            {commandLabel(activeJob.command)} {activeJob.status}.
          </span>
          <button className="button button--ghost" onClick={() => setActiveJob(null)} type="button">
            Hide
          </button>
        </section>
      ) : null}

      {currentStage === "setup" ? (
        <SetupStage
          workspaceRoot={workspaceRoot}
          workspaceStats={workspaceStats}
          projects={projects}
          selectedProjectId={selectedProjectId}
          selectedProjectSummary={selectedProjectSummary}
          setupMode={setupMode}
          form={projectForm}
          modelPresets={modelPresets}
          busy={busy}
          onSelectProject={setSelectedProjectId}
          onCreateNew={startNewProject}
          onEditSelected={editSelectedProject}
          onOpenSelected={openSelectedProject}
          onRefresh={() => withPending("refresh-projects", refreshProjects)}
          onChooseDirectory={chooseDirectory}
          onChangeForm={setProjectForm}
          onSaveProject={saveProject}
        />
      ) : (
        <FlowStage
          detail={projectDetail}
          planDraft={planDraft}
          selectedStepId={selectedStepId}
          activeTab={activeTab}
          modelPresets={modelPresets}
          busy={busy}
          activeJob={activeJob}
          onBack={() => {
            setCurrentStage("setup");
            setSetupMode("welcome");
          }}
          onReload={reloadProject}
          onSetActiveTab={setActiveTab}
          onPromptChange={(value) => {
            syncPlan({
              ...(cloneValue(planDraft) || {}),
              project_prompt: value,
            });
          }}
          onGeneratePlan={generatePlan}
          onSavePlan={savePlan}
          onResetPlan={resetPlan}
          onRunPlan={runPlan}
          onRunCloseout={runCloseout}
          onRequestStop={requestStop}
          onSelectStep={setSelectedStepId}
          onSaveStepLocal={saveStepLocal}
          onAddStep={addStep}
          onDeleteStep={deleteStep}
          onMoveStep={moveStep}
          onClearSelection={() => setSelectedStepId("")}
          onUpdateStepField={updateSelectedStep}
        />
      )}
    </main>
  );
}
