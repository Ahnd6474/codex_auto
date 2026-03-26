import { startTransition, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { bridgeRequest, getBridgeJob, listBridgeJobs, startBridgeJob } from "../api";
import {
  defaultShareSettings,
  emptyPlanDraft,
  messagePayload,
  needsExpandedProjectDetail,
  shareSettingsFromDetail,
} from "../controllerHelpers";
import { useI18n } from "../i18n";
import { translate } from "../locale";
import {
  applyProgramSettings,
  applyProgramSettingsToForm,
  basename,
  blankProjectForm,
  buildProjectPayload,
  cloneValue,
  commandLabel,
  detailApplySignature,
  firstSelectableStepId,
  mergeProjectDetailCodexStatus,
  programSettingsFromRuntime,
  projectFormFromDetail,
  sanitizeProjectDetailForJobState,
  sanitizeProjectListForJobState,
  shouldKeepUnsavedPlan,
  shouldReplaceVisibleProject,
  workspaceStatsFromProjects,
} from "../utils";
import { usePersistentState } from "./usePersistentState";

const AUTO_SYNC_INTERVAL_MS = 5000;

export function useDesktopController() {
  const { language } = useI18n();
  const [workspaceRoot, setWorkspaceRoot] = useState("");
  const [baseRuntime, setBaseRuntime] = useState(null);
  const [modelPresets, setModelPresets] = useState([]);
  const [modelCatalog, setModelCatalog] = useState([]);
  const [projects, setProjects] = useState([]);
  const [workspaceStats, setWorkspaceStats] = useState(null);
  const [selectedProjectId, setSelectedProjectId] = usePersistentState("jakal-flow:selected-project", "");
  const [storedProgramSettings, setStoredProgramSettings] = usePersistentState("jakal-flow:program-settings", null);
  const [projectForm, setProjectForm] = useState(blankProjectForm(null));
  const [programSettings, setProgramSettings] = useState(programSettingsFromRuntime(null));
  const [projectDetail, setProjectDetail] = useState(null);
  const [planDraft, setPlanDraft] = useState(() => emptyPlanDraft());
  const [selectedStepId, setSelectedStepId] = usePersistentState("jakal-flow:selected-step", "");
  const [planDirty, setPlanDirty] = useState(false);
  const [pendingAction, setPendingAction] = useState("");
  const [loadingProjectId, setLoadingProjectId] = useState("");
  const [activeJobId, setActiveJobId] = useState("");
  const [activeJob, setActiveJob] = useState(null);
  const [message, setMessage] = useState(null);
  const [shareSettings, setShareSettings] = useState(() => defaultShareSettings());
  const projectAutosaveTimerRef = useRef(null);
  const lastAppliedDetailSignatureRef = useRef("");

  const [centerTab, setCenterTab] = usePersistentState("jakal-flow:center-tab", "run");
  const [bottomTab, setBottomTab] = usePersistentState("jakal-flow:bottom-tab", "json");
  const [sidebarTab, setSidebarTab] = usePersistentState("jakal-flow:sidebar-tab", "projects");
  const [bottomCollapsed, setBottomCollapsed] = usePersistentState("jakal-flow:bottom-collapsed", false);
  const [bottomHeight, setBottomHeight] = usePersistentState("jakal-flow:bottom-height", 250);
  const [projectFilter, setProjectFilter] = usePersistentState("jakal-flow:project-filter", "");
  const [workspaceFilter, setWorkspaceFilter] = usePersistentState("jakal-flow:workspace-filter", "");
  const deferredProjectFilter = useDeferredValue(projectFilter);
  const defaultRuntime = useMemo(() => applyProgramSettings(baseRuntime, storedProgramSettings), [baseRuntime, storedProgramSettings]);

  const busy = Boolean(pendingAction || (activeJob && activeJob.status === "running"));
  const programSettingsDirty = useMemo(() => JSON.stringify(programSettings) !== JSON.stringify(programSettingsFromRuntime(storedProgramSettings)), [programSettings, storedProgramSettings]);

  const filteredProjects = useMemo(() => {
    const query = deferredProjectFilter.trim().toLowerCase();
    if (!query) {
      return projects;
    }
    return projects.filter((project) =>
      [project.display_name, project.slug, project.status, project.detail, project.repo_path]
        .join(" ")
        .toLowerCase()
        .includes(query),
    );
  }, [deferredProjectFilter, projects]);

  useEffect(() => {
    if (centerTab === "overview") {
      setCenterTab("run");
    }
  }, [centerTab, setCenterTab]);

  useEffect(() => {
    if (sidebarTab === "github") {
      setSidebarTab("projects");
    }
  }, [sidebarTab, setSidebarTab]);

  useEffect(() => {
    return () => {
      if (projectAutosaveTimerRef.current) {
        window.clearTimeout(projectAutosaveTimerRef.current);
      }
    };
  }, []);

  async function fetchProjectDetail(repoId, options = {}) {
    return bridgeRequest(
      "load-project",
      {
        repo_id: repoId,
        refresh_codex_status: options.refreshCodexStatus ?? true,
        detail_level: options.detailLevel ?? "full",
      },
      workspaceRoot || null,
    );
  }

  function applyListingPayload(listing, runningJob = null) {
    const nextProjects = sanitizeProjectListForJobState(listing?.projects || [], runningJob);
    setProjects(nextProjects);
    setWorkspaceStats(workspaceStatsFromProjects(nextProjects));
    return nextProjects;
  }

  async function syncRunningJobSnapshot(preferredJobId = "") {
    const jobs = await listBridgeJobs();
    const preferredJob = preferredJobId ? jobs.find((job) => job.id === preferredJobId) || null : null;
    const runningJob = preferredJob?.status === "running" ? preferredJob : jobs.find((job) => job.status === "running") || null;
    if (runningJob) {
      setActiveJobId(runningJob.id);
      setActiveJob(runningJob);
      return runningJob;
    }
    setActiveJobId("");
    setActiveJob(preferredJob && preferredJob.status !== "running" ? preferredJob : null);
    return null;
  }

  useEffect(() => {
    let cancelled = false;

    async function initialize() {
      try {
        const bootstrap = await bridgeRequest("bootstrap");
        if (cancelled) {
          return;
        }
        setWorkspaceRoot(bootstrap.workspace_root);
        setBaseRuntime(bootstrap.default_runtime);
        setModelPresets(bootstrap.model_presets || []);
        setModelCatalog(bootstrap.model_catalog || []);
        const nextProgramSettings = programSettingsFromRuntime(storedProgramSettings || bootstrap.default_runtime);
        setStoredProgramSettings(nextProgramSettings);
        setProgramSettings(nextProgramSettings);
        setProjectForm(blankProjectForm(applyProgramSettings(bootstrap.default_runtime, nextProgramSettings)));
        const listing = await bridgeRequest("list-projects", null, bootstrap.workspace_root);
        const runningJob = await syncRunningJobSnapshot();
        if (cancelled) {
          return;
        }
        const nextProjects = applyListingPayload(listing, runningJob);
        if (!nextProjects.some((item) => item.repo_id === selectedProjectId)) {
          setSelectedProjectId(nextProjects[0]?.repo_id || "");
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

  function applyProjectDetail(detail, options = {}) {
    const mergedDetail = mergeProjectDetailCodexStatus(detail, projectDetail?.codex_status, modelCatalog);
    const normalizedDetail = sanitizeProjectDetailForJobState(mergedDetail, options.runningJob ?? activeJob);
    const applySignature = detailApplySignature(normalizedDetail, options.runningJob ?? activeJob);
    if (
      !options.force &&
      applySignature &&
      lastAppliedDetailSignatureRef.current === applySignature &&
      normalizedDetail?.project?.repo_id === projectDetail?.project?.repo_id
    ) {
      setLoadingProjectId("");
      return;
    }
    const preserveDirtyPlan = shouldKeepUnsavedPlan(
      projectDetail?.project?.repo_id,
      normalizedDetail?.project?.repo_id,
      options.preserveDirtyPlan ?? planDirty,
    );
    lastAppliedDetailSignatureRef.current = applySignature;
    startTransition(() => {
      setProjectDetail(normalizedDetail);
      setModelCatalog(normalizedDetail?.codex_status?.model_catalog || modelCatalog);
      setShareSettings(shareSettingsFromDetail(normalizedDetail));
      setLoadingProjectId("");
      setProjectForm((current) => {
        if (current.project_dir && preserveDirtyPlan) {
          return current;
        }
        return applyProgramSettingsToForm(projectFormFromDetail(normalizedDetail, defaultRuntime), storedProgramSettings);
      });
      if (!preserveDirtyPlan) {
        setPlanDraft(cloneValue(normalizedDetail.plan));
        if (options.preserveSelectedStep) {
          setSelectedStepId((current) => current || firstSelectableStepId(normalizedDetail.plan));
        } else {
          setSelectedStepId(firstSelectableStepId(normalizedDetail.plan));
        }
        setPlanDirty(false);
      }
    });
  }

  useEffect(() => {
    let cancelled = false;

    async function tickJob() {
      try {
        const job = await getBridgeJob(activeJobId);
        if (cancelled) {
          return;
        }
        if (!job) {
          const runningJob = await syncRunningJobSnapshot(activeJobId);
          if (!runningJob && selectedProjectId) {
            const detail = await fetchProjectDetail(selectedProjectId, { refreshCodexStatus: false, detailLevel: "core" });
            if (!cancelled) {
              applyProjectDetail(detail, { preserveSelectedStep: true, runningJob: null });
            }
          }
          return;
        }
        setActiveJob(job);
        if (job.status === "running") {
          if (selectedProjectId) {
            try {
              const detail = await fetchProjectDetail(selectedProjectId, { refreshCodexStatus: false, detailLevel: "core" });
              if (!cancelled) {
                applyProjectDetail(detail, { preserveSelectedStep: true, runningJob: job });
              }
            } catch {
              // Ignore background refresh failures while the job is still running.
            }
          }
          return;
        }
        setActiveJobId("");
        if (job.result?.project && shouldReplaceVisibleProject(selectedProjectId, job.result.project.repo_id)) {
          applyProjectDetail(job.result, { preserveDirtyPlan: false, runningJob: null });
        }
        const listing = await bridgeRequest("list-projects", null, workspaceRoot || null);
        if (!cancelled) {
          applyListingPayload(listing, null);
          setMessage(
            job.status === "completed"
              ? messagePayload(
                  "success",
                  translate(language, "message.commandCompleted", {
                    command: commandLabel(job.command, language),
                  }),
                )
              : messagePayload(
                  "error",
                  job.error ||
                    translate(language, "message.commandFailed", {
                      command: commandLabel(job.command, language),
                    }),
                ),
          );
        }
      } catch (error) {
        if (!cancelled) {
          try {
            const runningJob = await syncRunningJobSnapshot(activeJobId);
            if (!runningJob) {
              const listing = await bridgeRequest("list-projects", null, workspaceRoot || null);
              if (!cancelled) {
                applyListingPayload(listing, null);
              }
              if (selectedProjectId) {
                const detail = await fetchProjectDetail(selectedProjectId, { refreshCodexStatus: false, detailLevel: "core" });
                if (!cancelled) {
                  applyProjectDetail(detail, { preserveSelectedStep: true, runningJob: null });
                }
              }
            }
          } catch {
            // Keep the last known state if local job reconciliation also fails.
          }
          setMessage(messagePayload("error", String(error)));
        }
      }
    }

    if (!activeJobId) {
      return undefined;
    }

    tickJob();
    const handle = window.setInterval(tickJob, 1000);
    return () => {
      cancelled = true;
      window.clearInterval(handle);
    };
  }, [activeJobId, defaultRuntime, language, workspaceRoot]);

  useEffect(() => {
    let cancelled = false;

    async function loadSelectedProject() {
      try {
        setLoadingProjectId(selectedProjectId);
        const detail = await fetchProjectDetail(selectedProjectId, { refreshCodexStatus: false });
        if (cancelled) {
          return;
        }
        applyProjectDetail(detail);
      } catch (error) {
        if (!cancelled) {
          setLoadingProjectId("");
        }
        if (!cancelled && !pendingAction) {
          setMessage(messagePayload("error", String(error)));
        }
      }
    }

    if (!selectedProjectId || activeJobId || pendingAction || loadingProjectId) {
      return undefined;
    }
    if (projectDetail?.project?.repo_id === selectedProjectId) {
      return undefined;
    }

    loadSelectedProject();
    return () => {
      cancelled = true;
    };
  }, [activeJobId, defaultRuntime, loadingProjectId, pendingAction, planDirty, projectDetail?.project?.repo_id, selectedProjectId, workspaceRoot]);

  useEffect(() => {
    let cancelled = false;

    async function loadExpandedProjectDetail() {
      try {
        const detail = await fetchProjectDetail(selectedProjectId, {
          refreshCodexStatus: centerTab === "dashboard" || (!bottomCollapsed && bottomTab === "tokens"),
          detailLevel: "full",
        });
        if (cancelled) {
          return;
        }
        applyProjectDetail(detail, { preserveSelectedStep: true });
      } catch (error) {
        if (!cancelled) {
          setMessage(messagePayload("error", String(error)));
        }
      }
    }

    if (!selectedProjectId || activeJobId || pendingAction || loadingProjectId) {
      return undefined;
    }
    if (projectDetail?.project?.repo_id !== selectedProjectId) {
      return undefined;
    }
    if (projectDetail?.detail_level === "full") {
      return undefined;
    }
    if (!needsExpandedProjectDetail({ centerTab, sidebarTab, bottomCollapsed, bottomTab })) {
      return undefined;
    }

    loadExpandedProjectDetail();
    return () => {
      cancelled = true;
    };
  }, [
    activeJobId,
    bottomCollapsed,
    bottomTab,
    centerTab,
    loadingProjectId,
    pendingAction,
    projectDetail?.detail_level,
    projectDetail?.project?.repo_id,
    selectedProjectId,
    sidebarTab,
    workspaceRoot,
  ]);

  useEffect(() => {
    let cancelled = false;
    let syncInFlight = false;

    async function syncDesktopState() {
      if (!workspaceRoot || pendingAction || loadingProjectId || syncInFlight) {
        return;
      }
      syncInFlight = true;
      try {
        const runningJob = await syncRunningJobSnapshot(activeJobId);
        if (cancelled) {
          return;
        }

        const listing = await bridgeRequest("list-projects", null, workspaceRoot || null);
        if (cancelled) {
          return;
        }
        const nextProjects = applyListingPayload(listing, runningJob || null);
        if (!selectedProjectId) {
          if (nextProjects.length) {
            setSelectedProjectId(nextProjects[0].repo_id);
          }
          return;
        }

        const repoStillExists = nextProjects.some((project) => project.repo_id === selectedProjectId);
        if (!repoStillExists) {
          if (nextProjects.length) {
            setSelectedProjectId(nextProjects[0].repo_id);
          } else {
            clearSelectedProjectState(defaultRuntime);
          }
          return;
        }

        const detailLevel = needsExpandedProjectDetail({ centerTab, sidebarTab, bottomCollapsed, bottomTab }) ? "full" : "core";
        const detail = await fetchProjectDetail(selectedProjectId, {
          refreshCodexStatus: false,
          detailLevel,
        });
        if (!cancelled) {
          applyProjectDetail(detail, { preserveSelectedStep: true, runningJob: runningJob || null });
        }
      } catch {
        // Keep background sync quiet; manual refresh still surfaces explicit errors.
      } finally {
        syncInFlight = false;
      }
    }

    if (!workspaceRoot) {
      return undefined;
    }

    void syncDesktopState();
    const handle = window.setInterval(() => {
      void syncDesktopState();
    }, AUTO_SYNC_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(handle);
    };
  }, [
    activeJobId,
    bottomCollapsed,
    bottomTab,
    centerTab,
    defaultRuntime,
    loadingProjectId,
    pendingAction,
    selectedProjectId,
    sidebarTab,
    workspaceRoot,
  ]);

  async function refreshProjects() {
    const listing = await bridgeRequest("list-projects", null, workspaceRoot || null);
    const nextProjects = applyListingPayload(listing, activeJob?.status === "running" ? activeJob : null);
    if (!selectedProjectId && nextProjects.length) {
      setSelectedProjectId(nextProjects[0].repo_id);
    }
  }

  async function forceRefresh() {
    try {
      const runningJob = await syncRunningJobSnapshot(activeJobId);

      const listing = await bridgeRequest("list-projects", null, workspaceRoot || null);
      const nextProjects = applyListingPayload(listing, runningJob);

      if (selectedProjectId) {
        const detail = await fetchProjectDetail(selectedProjectId, { refreshCodexStatus: true });
        applyProjectDetail(detail, { preserveSelectedStep: true, runningJob });
      } else if (nextProjects.length) {
        setSelectedProjectId(nextProjects[0].repo_id);
      }

      setMessage(messagePayload("info", activeJobId ? translate(language, "message.runStateRefreshed") : translate(language, "message.projectStateRefreshed")));
    } catch (error) {
      setMessage(messagePayload("error", String(error)));
    }
  }

  async function loadProject(repoId, options = {}) {
    if (!repoId) {
      return null;
    }
    if (projectAutosaveTimerRef.current) {
      window.clearTimeout(projectAutosaveTimerRef.current);
      projectAutosaveTimerRef.current = null;
    }
    const previousProjectId = selectedProjectId;
    setLoadingProjectId(repoId);
    setSelectedProjectId(repoId);
    try {
      const detail = await fetchProjectDetail(repoId, {
        refreshCodexStatus: options.refreshCodexStatus ?? false,
        detailLevel: options.detailLevel ?? "core",
      });
      applyProjectDetail(detail, { runningJob: activeJob?.status === "running" ? activeJob : null });
      return detail;
    } catch (error) {
      setLoadingProjectId("");
      setSelectedProjectId(previousProjectId);
      setMessage(messagePayload("error", String(error)));
      return null;
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

  function clearSelectedProjectState(nextRuntime = defaultRuntime) {
    lastAppliedDetailSignatureRef.current = "";
    setProjectDetail(null);
    setSelectedProjectId("");
    setSelectedStepId("");
    setPlanDirty(false);
    setLoadingProjectId("");
    setProjectForm(blankProjectForm(nextRuntime));
    setPlanDraft(emptyPlanDraft());
    setShareSettings(defaultShareSettings());
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
      updateProjectForm((current) => ({
        ...current,
        project_dir: selected,
        display_name: current.display_name || basename(selected),
      }));
    } catch (error) {
      setMessage(messagePayload("error", String(error)));
    }
  }

  function startNewProject() {
    if (projectAutosaveTimerRef.current) {
      window.clearTimeout(projectAutosaveTimerRef.current);
      projectAutosaveTimerRef.current = null;
    }
    setMessage(null);
    clearSelectedProjectState(defaultRuntime);
    setCenterTab("config");
    setSidebarTab("projects");
  }

  function applyProgramSettingsNow(nextSettings) {
    setStoredProgramSettings(nextSettings);
    setProgramSettings(nextSettings);
    setProjectForm((current) => applyProgramSettingsToForm(current, nextSettings));
  }

  function updateProgramSettings(updater) {
    setProgramSettings((current) => {
      const draft = typeof updater === "function" ? updater(current) : updater;
      const nextSettings = programSettingsFromRuntime(draft);
      setStoredProgramSettings(nextSettings);
      setProjectForm((form) => applyProgramSettingsToForm(form, nextSettings));
      return nextSettings;
    });
  }

  function saveProgramSettings() {
    const nextSettings = programSettingsFromRuntime(programSettings);
    applyProgramSettingsNow(nextSettings);
    setMessage(messagePayload("success", translate(language, "message.programSettingsSaved")));
  }

  async function saveProject(options = {}) {
    const { formOverride = null, silent = false } = options;
    const formToSave = applyProgramSettingsToForm(formOverride || projectForm, storedProgramSettings);
    await withPending("save-project-setup", async () => {
      const detail = await bridgeRequest(
        "save-project-setup",
        buildProjectPayload(formToSave),
        workspaceRoot || null,
      );
      lastAppliedDetailSignatureRef.current = "";
      setProjectDetail(detail);
      setModelCatalog(detail?.codex_status?.model_catalog || []);
      setShareSettings(shareSettingsFromDetail(detail));
      setSelectedProjectId(detail.project.repo_id);
      setProjectForm(applyProgramSettingsToForm(projectFormFromDetail(detail, defaultRuntime), storedProgramSettings));
      setPlanDraft(cloneValue(detail.plan));
      setSelectedStepId(firstSelectableStepId(detail.plan));
      setPlanDirty(false);
      await refreshProjects();
      if (!silent) {
        setMessage(messagePayload("success", translate(language, "message.projectConfigurationSaved")));
      }
    });
  }

  function scheduleProjectAutosave(nextForm) {
    if (projectAutosaveTimerRef.current) {
      window.clearTimeout(projectAutosaveTimerRef.current);
      projectAutosaveTimerRef.current = null;
    }
    if (!String(nextForm?.project_dir || "").trim()) {
      return;
    }
    projectAutosaveTimerRef.current = window.setTimeout(() => {
      projectAutosaveTimerRef.current = null;
      void saveProject({ formOverride: nextForm, silent: true });
    }, 500);
  }

  function updateProjectForm(updater) {
    setProjectForm((current) => {
      const next = typeof updater === "function" ? updater(current) : updater;
      scheduleProjectAutosave(next);
      return next;
    });
  }

  async function deleteProject() {
    if (!selectedProjectId) {
      setMessage(messagePayload("error", translate(language, "message.openProjectFirst")));
      return;
    }
    if (!window.confirm(translate(language, "prompt.confirmDeleteProject"))) {
      return;
    }
    await withPending("delete-project", async () => {
      const result = await bridgeRequest(
        "delete-project",
        {
          repo_id: selectedProjectId,
        },
        workspaceRoot || null,
      );
      setProjects(result.projects || []);
      setWorkspaceStats(result.workspace || null);
      clearSelectedProjectState(defaultRuntime);
      if ((result.projects || []).length) {
        setSelectedProjectId(result.projects[0].repo_id);
      }
      setMessage(messagePayload("success", translate(language, "message.projectDeleted")));
    });
  }

  async function deleteProjectById(repoId) {
    if (!repoId) {
      return;
    }
    if (!window.confirm(translate(language, "prompt.confirmDeleteProject"))) {
      return;
    }
    await withPending("delete-project", async () => {
      const result = await bridgeRequest(
        "delete-project",
        {
          repo_id: repoId,
        },
        workspaceRoot || null,
      );
      setProjects(result.projects || []);
      setWorkspaceStats(result.workspace || null);
      if (repoId === selectedProjectId) {
        clearSelectedProjectState(defaultRuntime);
      }
      if ((result.projects || []).length && (!selectedProjectId || repoId === selectedProjectId)) {
        setSelectedProjectId(result.projects[0].repo_id);
      }
      setMessage(messagePayload("success", translate(language, "message.projectDeleted")));
    });
  }

  async function deleteAllProjects() {
    if (!projects.length) {
      return;
    }
    if (!window.confirm(translate(language, "prompt.confirmDeleteAllProjects"))) {
      return;
    }
    await withPending("delete-all-projects", async () => {
      const result = await bridgeRequest("delete-all-projects", {}, workspaceRoot || null);
      setProjects(result.projects || []);
      setWorkspaceStats(result.workspace || null);
      clearSelectedProjectState(defaultRuntime);
      setMessage(messagePayload("success", translate(language, "message.allProjectsDeleted")));
    });
  }

  async function savePlan() {
    if (!projectForm.project_dir.trim()) {
      setMessage(messagePayload("error", translate(language, "message.openOrCreateProjectFirst")));
      return;
    }
    await withPending("save-plan", async () => {
      const detail = await bridgeRequest(
        "save-plan",
        buildProjectPayload(applyProgramSettingsToForm(projectForm, storedProgramSettings), planDraft),
        workspaceRoot || null,
      );
      lastAppliedDetailSignatureRef.current = "";
      setProjectDetail(detail);
      setModelCatalog(detail?.codex_status?.model_catalog || []);
      setShareSettings(shareSettingsFromDetail(detail));
      setPlanDraft(cloneValue(detail.plan));
      setSelectedStepId(firstSelectableStepId(detail.plan));
      setPlanDirty(false);
      await refreshProjects();
      setMessage(messagePayload("success", translate(language, "message.planSaved")));
    });
  }

  async function resetPlan() {
    if (!projectForm.project_dir.trim()) {
      setMessage(messagePayload("error", translate(language, "message.openOrCreateProjectFirst")));
      return;
    }
    if (!window.confirm(translate(language, "prompt.confirmResetPlan"))) {
      return;
    }
    await withPending("reset-plan", async () => {
      const detail = await bridgeRequest(
        "reset-plan",
        buildProjectPayload(applyProgramSettingsToForm(projectForm, storedProgramSettings)),
        workspaceRoot || null,
      );
      lastAppliedDetailSignatureRef.current = "";
      setProjectDetail(detail);
      setModelCatalog(detail?.codex_status?.model_catalog || []);
      setShareSettings(shareSettingsFromDetail(detail));
      setPlanDraft(cloneValue(detail.plan));
      setSelectedStepId("");
      setPlanDirty(false);
      await refreshProjects();
      setMessage(messagePayload("success", translate(language, "message.planReset")));
    });
  }

  async function startJob(command, payload) {
    try {
      setMessage(null);
      const job = await startBridgeJob(command, payload, workspaceRoot || null);
      setActiveJobId(job.id);
      setActiveJob(job);
      setCenterTab("run");
      setBottomTab("json");
      setMessage(
        messagePayload(
          "info",
          translate(language, "message.commandStarted", {
            command: commandLabel(command, language),
          }),
        ),
      );
    } catch (error) {
      setMessage(messagePayload("error", String(error)));
    }
  }

  async function generatePlan() {
    const prompt = planDraft?.project_prompt?.trim() || "";
    if (!projectForm.project_dir.trim()) {
      setMessage(messagePayload("error", translate(language, "message.prepareProjectFirst")));
      return;
    }
    if (!prompt) {
      setMessage(messagePayload("error", translate(language, "message.promptRequired")));
      return;
    }
    if ((planDraft?.steps || []).some((step) => step.status === "completed")) {
      setMessage(messagePayload("error", translate(language, "message.editRemainingSteps")));
      return;
    }
    if ((planDraft?.steps || []).length && !window.confirm(translate(language, "prompt.confirmRegeneratePlan"))) {
      return;
    }
    await startJob("generate-plan", {
      ...buildProjectPayload(applyProgramSettingsToForm(projectForm, storedProgramSettings)),
      prompt,
      max_steps: Math.max(1, Number.parseInt(String(projectForm.runtime?.max_blocks || 5), 10) || 1),
    });
  }

  async function runPlan() {
    if (!(planDraft?.steps || []).length) {
      setMessage(messagePayload("error", translate(language, "message.createStepBeforeRun")));
      return;
    }
    await startJob("run-plan", buildProjectPayload(applyProgramSettingsToForm(projectForm, storedProgramSettings), planDraft));
  }

  async function runCloseout() {
    if (!(planDraft?.steps || []).length) {
      setMessage(messagePayload("error", translate(language, "message.createPlanBeforeCloseout")));
      return;
    }
    if ((planDraft.steps || []).some((step) => step.status !== "completed")) {
      setMessage(messagePayload("error", translate(language, "message.closeoutAfterAllSteps")));
      return;
    }
    if (!window.confirm(translate(language, "prompt.confirmCloseout"))) {
      return;
    }
    await startJob("run-closeout", buildProjectPayload(applyProgramSettingsToForm(projectForm, storedProgramSettings), planDraft));
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
          refresh_codex_status: false,
        },
        workspaceRoot || null,
      );
      applyProjectDetail(detail, { preserveSelectedStep: true });
      setMessage(messagePayload("info", translate(language, "message.stopRequested")));
    });
  }

  async function copyShareLink() {
    const shareUrl = projectDetail?.share?.active_session?.share_url || "";
    if (!shareUrl) {
      setMessage(messagePayload("error", translate(language, "message.noShareLinkAvailable")));
      return;
    }
    try {
      if (!navigator?.clipboard?.writeText) {
        throw new Error("Clipboard API is unavailable.");
      }
      await navigator.clipboard.writeText(shareUrl);
      setMessage(messagePayload("success", translate(language, "message.shareLinkCopied")));
    } catch (error) {
      setMessage(messagePayload("error", `${translate(language, "message.shareLinkCopyFailed")} ${String(error)}`.trim()));
    }
  }

  async function generateShareLink() {
    if (!projectForm.project_dir.trim()) {
      setMessage(messagePayload("error", translate(language, "message.openOrCreateProjectFirst")));
      return;
    }
    await withPending("create_share_session", async () => {
      const detail = await bridgeRequest(
        "create_share_session",
        {
          project_dir: projectForm.project_dir.trim(),
          created_by: "tauri-react-ui",
          bind_host: shareSettings.bind_host,
          public_base_url: shareSettings.public_base_url,
        },
        workspaceRoot || null,
      );
      lastAppliedDetailSignatureRef.current = "";
      setProjectDetail(detail);
      setModelCatalog(detail?.codex_status?.model_catalog || []);
      setShareSettings(shareSettingsFromDetail(detail));
      const shareUrl = detail?.created_share_session?.share_url || detail?.share?.active_session?.share_url || "";
      if (shareUrl && navigator?.clipboard?.writeText) {
        try {
          await navigator.clipboard.writeText(shareUrl);
        } catch {
          // Ignore clipboard failures here; the link is still generated and visible.
        }
      }
      setMessage(messagePayload("success", translate(language, "message.shareLinkReady")));
    });
  }

  async function revokeShareLink() {
    const sessionId = projectDetail?.share?.active_session?.session_id || "";
    if (!projectForm.project_dir.trim()) {
      setMessage(messagePayload("error", translate(language, "message.openOrCreateProjectFirst")));
      return;
    }
    if (!sessionId) {
      setMessage(messagePayload("error", translate(language, "message.noShareLinkAvailable")));
      return;
    }
    await withPending("revoke_share_session", async () => {
      const detail = await bridgeRequest(
        "revoke_share_session",
        {
          project_dir: projectForm.project_dir.trim(),
          session_id: sessionId,
        },
        workspaceRoot || null,
      );
      lastAppliedDetailSignatureRef.current = "";
      setProjectDetail(detail);
      setModelCatalog(detail?.codex_status?.model_catalog || []);
      setShareSettings(shareSettingsFromDetail(detail));
      setMessage(messagePayload("success", translate(language, "message.shareLinkRevoked")));
    });
  }

  async function approveCheckpoint() {
    if (!selectedProjectId) {
      setMessage(messagePayload("error", translate(language, "message.openProjectFirst")));
      return;
    }
    await withPending("approve-checkpoint", async () => {
      const detail = await bridgeRequest(
        "approve-checkpoint",
        {
          repo_id: selectedProjectId,
          push: true,
        },
        workspaceRoot || null,
      );
      lastAppliedDetailSignatureRef.current = "";
      setProjectDetail(detail);
      setModelCatalog(detail?.codex_status?.model_catalog || []);
      setShareSettings(shareSettingsFromDetail(detail));
      setMessage(messagePayload("success", translate(language, "message.checkpointApproved")));
    });
  }

  async function reloadProject() {
    if (!selectedProjectId) {
      setMessage(messagePayload("error", translate(language, "message.noProjectOpen")));
      return;
    }
    await loadProject(selectedProjectId, { refreshCodexStatus: true });
    setMessage(messagePayload("success", translate(language, "message.projectReloaded")));
  }

  function saveStepLocal() {
    if (!selectedStepId) {
      setMessage(messagePayload("error", translate(language, "message.selectPendingStepFirst")));
      return;
    }
    const step = (planDraft?.steps || []).find((item) => item.step_id === selectedStepId);
    if (!step || step.status !== "pending") {
      setMessage(messagePayload("error", translate(language, "message.onlyPendingEdit")));
      return;
    }
    setPlanDirty(true);
    setMessage(messagePayload("info", translate(language, "message.stepUpdatedLocally")));
  }

  function addStep() {
    const steps = cloneValue(planDraft?.steps || []);
    if (selectedStepId) {
      const selectedStep = steps.find((step) => step.step_id === selectedStepId);
      if (selectedStep && selectedStep.status !== "pending") {
        setMessage(messagePayload("error", translate(language, "message.insertAfterPending")));
        return;
      }
    }
    const insertAt = selectedStepId ? steps.findIndex((step) => step.step_id === selectedStepId) + 1 : steps.length;
    const newStep = {
      step_id: `TMP${steps.length + 1}`,
      title: translate(language, "run.newPendingStep"),
      display_description: translate(language, "run.stepCheckpointDescription"),
      codex_description: translate(language, "run.stepCodexDescription"),
      test_command: projectForm.runtime?.test_cmd || "python -m pytest",
      success_criteria: translate(language, "run.stepSuccessCriteria"),
      reasoning_effort: projectForm.runtime?.effort || "high",
      parallel_group: "",
      depends_on: [],
      owned_paths: [],
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
      setMessage(messagePayload("error", translate(language, "message.selectStepFirst")));
      return;
    }
    if (step.status !== "pending") {
      setMessage(messagePayload("error", translate(language, "message.onlyPendingDelete")));
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
      setMessage(messagePayload("error", translate(language, "message.selectPendingStepFirst")));
      return;
    }
    if (steps[index].status !== "pending") {
      setMessage(messagePayload("error", translate(language, "message.onlyPendingMove")));
      return;
    }
    const target = index + direction;
    if (target < 0 || target >= steps.length) {
      return;
    }
    if (steps[target].status !== "pending") {
      setMessage(messagePayload("error", translate(language, "message.pendingMoveRange")));
      return;
    }
    [steps[index], steps[target]] = [steps[target], steps[index]];
    syncPlan({
      ...(cloneValue(planDraft) || {}),
      steps,
    });
  }

  return {
    busy,
    workspaceRoot,
    defaultRuntime,
    programSettings,
    programSettingsDirty,
    modelPresets,
    modelCatalog,
    projects,
    filteredProjects,
    workspaceStats,
    selectedProjectId,
    projectForm,
    projectDetail,
    planDraft,
    selectedStepId,
    pendingAction,
    loadingProjectId,
    activeJob,
    activeJobId,
    message,
    shareSettings,
    centerTab,
    bottomTab,
    sidebarTab,
    bottomCollapsed,
    bottomHeight,
    projectFilter,
    workspaceFilter,
    planDirty,
    setMessage,
    setProjectForm: updateProjectForm,
    setPlanDraft,
    setSelectedStepId,
    setProgramSettings: updateProgramSettings,
    setCenterTab,
    setBottomTab,
    setSidebarTab,
    setBottomCollapsed,
    setBottomHeight,
    setProjectFilter,
    setWorkspaceFilter,
    setShareSettings,
    syncPlan,
    updateSelectedStep,
    chooseDirectory,
    forceRefresh,
    refreshProjects,
    loadProject,
    saveProject,
    deleteProject,
    deleteProjectById,
    deleteAllProjects,
    savePlan,
    resetPlan,
    startNewProject,
    saveProgramSettings,
    generatePlan,
    runPlan,
    runCloseout,
    requestStop,
    generateShareLink,
    revokeShareLink,
    copyShareLink,
    approveCheckpoint,
    reloadProject,
    saveStepLocal,
    addStep,
    deleteStep,
    moveStep,
    setSelectedProjectId,
  };
}
