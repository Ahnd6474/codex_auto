import { startTransition, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { bridgeRequest, startBridgeJob, subscribeBridgeEvents } from "../api";
import { BRIDGE_COMMANDS } from "../bridgeProtocol";
import { bridgeEventJob, bridgeEventProject, isJobUpdatedEvent, isProjectChangedEvent, isProjectUiEvent } from "../controller/bridgeEvents";
import { mergeRefreshRepoId, projectRefreshDebounceMs, shouldRefreshSelectedProject } from "../controller/projectRefresh";
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
  firstSelectableStepId,
  programSettingsFromRuntime,
  projectFormFromDetail,
  shouldReplaceVisibleProject,
} from "../utils";
import {
  fetchHistoryDetail,
  fetchProjectDetail,
  fetchProjectDetailBySelector,
  loadInitialDesktopState,
  loadProjectListing,
  refreshVisibleProjectState,
  syncRunningJobSnapshot,
} from "../controller/projectQueries";
import {
  applyActiveJobState,
  applyListingState,
  applyProjectDetailState,
  applyProjectDetailListingState,
  clearSelectedProjectState as clearProjectSelectionState,
} from "../controller/projectStore";
import { usePersistentState } from "./usePersistentState";

export function useDesktopController() {
  const { language } = useI18n();
  const [workspaceRoot, setWorkspaceRoot] = useState("");
  const [baseRuntime, setBaseRuntime] = useState(null);
  const [modelPresets, setModelPresets] = useState([]);
  const [modelCatalog, setModelCatalog] = useState([]);
  const [projects, setProjects] = useState([]);
  const [historyProjects, setHistoryProjects] = useState([]);
  const [workspaceStats, setWorkspaceStats] = useState(null);
  const [selectedProjectId, setSelectedProjectId] = usePersistentState("jakal-flow:selected-project", "");
  const [selectedHistoryId, setSelectedHistoryId] = usePersistentState("jakal-flow:selected-history", "");
  const [storedProgramSettings, setStoredProgramSettings] = usePersistentState("jakal-flow:program-settings", null);
  const [projectForm, setProjectForm] = useState(blankProjectForm(null));
  const [programSettings, setProgramSettings] = useState(programSettingsFromRuntime(null));
  const [projectDetail, setProjectDetail] = useState(null);
  const [historyDetail, setHistoryDetail] = useState(null);
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
  const bridgeRefreshInFlightRef = useRef(false);
  const bridgeRefreshTimerRef = useRef(null);
  const pendingBridgeRefreshRepoIdRef = useRef("");
  const pendingBridgeRefreshListingRef = useRef(false);
  const activeJobRef = useRef(null);
  const projectsRef = useRef([]);

  const [centerTab, setCenterTab] = usePersistentState("jakal-flow:center-tab", "run");
  const [bottomTab, setBottomTab] = usePersistentState("jakal-flow:bottom-tab", "json");
  const [sidebarTab, setSidebarTab] = usePersistentState("jakal-flow:sidebar-tab", "projects");
  const [bottomCollapsed, setBottomCollapsed] = usePersistentState("jakal-flow:bottom-collapsed", false);
  const [bottomHeight, setBottomHeight] = usePersistentState("jakal-flow:bottom-height", 250);
  const [projectFilter, setProjectFilter] = usePersistentState("jakal-flow:project-filter", "");
  const [workspaceFilter, setWorkspaceFilter] = usePersistentState("jakal-flow:workspace-filter", "");
  const deferredProjectFilter = useDeferredValue(projectFilter);
  const defaultRuntime = useMemo(() => applyProgramSettings(baseRuntime, storedProgramSettings), [baseRuntime, storedProgramSettings]);
  const wantsExpandedDetail = useMemo(
    () => needsExpandedProjectDetail({ centerTab, sidebarTab, bottomCollapsed, bottomTab }),
    [bottomCollapsed, bottomTab, centerTab, sidebarTab],
  );

  const busy = Boolean(pendingAction || (activeJob && activeJob.status === "running"));
  const shareBusy = pendingAction === "create_share_session" || pendingAction === "revoke_share_session";
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

  const filteredHistoryProjects = useMemo(() => {
    const query = deferredProjectFilter.trim().toLowerCase();
    if (!query) {
      return historyProjects;
    }
    return historyProjects.filter((project) =>
      [project.display_name, project.slug, project.status, project.detail, project.repo_path]
        .join(" ")
        .toLowerCase()
        .includes(query),
    );
  }, [deferredProjectFilter, historyProjects]);

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
      if (bridgeRefreshTimerRef.current) {
        window.clearTimeout(bridgeRefreshTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    activeJobRef.current = activeJob;
  }, [activeJob]);

  useEffect(() => {
    projectsRef.current = projects;
  }, [projects]);

  useEffect(() => {
    if (selectedHistoryId && !historyProjects.some((item) => item.archive_id === selectedHistoryId)) {
      setSelectedHistoryId("");
      setHistoryDetail(null);
    }
  }, [historyProjects, selectedHistoryId, setSelectedHistoryId]);

  function applyCurrentJobSnapshot(jobSnapshot) {
    return applyActiveJobState({
      jobSnapshot,
      setActiveJobId,
      setActiveJob,
      activeJobRef,
    });
  }

  function applyProjectDetail(detail, options = {}) {
    const applied = applyProjectDetailState({
      detail,
      options,
      refs: {
        lastAppliedDetailSignatureRef,
      },
      state: {
        projectDetail,
        modelCatalog,
        activeJob: activeJobRef.current,
        defaultRuntime,
        storedProgramSettings,
        planDirty,
      },
      setters: {
        transition: startTransition,
        setProjectDetail,
        setModelCatalog,
        setShareSettings,
        setLoadingProjectId,
        setProjectForm,
        setPlanDraft,
        setSelectedStepId,
        setPlanDirty,
      },
    });
    if (applied) {
      const nextProjects = applyProjectDetailListingState({
        projects: projectsRef.current,
        detail,
        runningJob: options.runningJob ?? activeJobRef.current,
        setProjects,
        setWorkspaceStats,
      });
      if (nextProjects) {
        projectsRef.current = nextProjects;
      }
    }
    return applied;
  }

  useEffect(() => {
    let cancelled = false;

    async function initialize() {
      try {
        const { bootstrap, listing, jobSnapshot } = await loadInitialDesktopState(bridgeRequest);
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
        const runningJob = applyCurrentJobSnapshot(jobSnapshot);
        if (cancelled) {
          return;
        }
        const nextProjects = applyListingState({
          listing,
          runningJob,
          setProjects,
          setWorkspaceStats,
        });
        setHistoryProjects(listing?.history || []);
        projectsRef.current = nextProjects;
        if (!nextProjects.some((item) => item.repo_id === selectedProjectId)) {
          setSelectedProjectId(nextProjects[0]?.repo_id || "");
        }
        if (!selectedHistoryId && (listing?.history || []).length) {
          setSelectedHistoryId(listing.history[0].archive_id || "");
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

    async function loadSelectedHistory() {
      try {
        const detail = await fetchHistoryDetail(bridgeRequest, selectedHistoryId, workspaceRoot, {
          detailLevel: centerTab === "history" ? "full" : "core",
        });
        if (cancelled) {
          return;
        }
        setHistoryDetail(detail);
      } catch (error) {
        if (!cancelled) {
          setMessage(messagePayload("error", String(error)));
        }
      }
    }

    if (!selectedHistoryId || !workspaceRoot || pendingAction) {
      return undefined;
    }
    if (
      historyDetail?.project?.archive_id === selectedHistoryId
      && (centerTab !== "history" || historyDetail?.detail_level === "full")
    ) {
      return undefined;
    }

    loadSelectedHistory();
    return () => {
      cancelled = true;
    };
  }, [
    centerTab,
    historyDetail?.detail_level,
    historyDetail?.project?.archive_id,
    pendingAction,
    selectedHistoryId,
    workspaceRoot,
  ]);

  useEffect(() => {
    let cancelled = false;

    async function loadSelectedProject() {
      try {
        setLoadingProjectId(selectedProjectId);
        const detail = await fetchProjectDetail(bridgeRequest, selectedProjectId, workspaceRoot, {
          refreshCodexStatus: false,
          detailLevel: wantsExpandedDetail ? "full" : "core",
        });
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

    if (!selectedProjectId || pendingAction || loadingProjectId) {
      return undefined;
    }
    if (
      projectDetail?.project?.repo_id === selectedProjectId &&
      (!wantsExpandedDetail || projectDetail?.detail_level === "full")
    ) {
      return undefined;
    }

    loadSelectedProject();
    return () => {
      cancelled = true;
    };
  }, [
    defaultRuntime,
    loadingProjectId,
    pendingAction,
    planDirty,
    projectDetail?.detail_level,
    projectDetail?.project?.repo_id,
    selectedProjectId,
    wantsExpandedDetail,
    workspaceRoot,
  ]);

  useEffect(() => {
    let cancelled = false;

    async function flushBridgeRefresh() {
      if (bridgeRefreshInFlightRef.current || !workspaceRoot) {
        return;
      }
      bridgeRefreshInFlightRef.current = true;
      const pendingRepoId = pendingBridgeRefreshRepoIdRef.current;
      const refreshListing = pendingBridgeRefreshListingRef.current;
      pendingBridgeRefreshRepoIdRef.current = "";
      pendingBridgeRefreshListingRef.current = false;
      try {
        const runningJob = activeJobRef.current?.status === "running" ? activeJobRef.current : null;
        const shouldLoadDetail = shouldRefreshSelectedProject(selectedProjectId, pendingRepoId);
        const { listing, detail } = await refreshVisibleProjectState(
          bridgeRequest,
          workspaceRoot,
          shouldLoadDetail ? selectedProjectId : "",
          {
            refreshCodexStatus: false,
            detailLevel: wantsExpandedDetail ? "full" : "core",
            refreshListing,
          },
        );
        if (cancelled) {
          return;
        }
        if (listing) {
          const nextProjects = applyListingState({
            listing,
            runningJob,
            setProjects,
            setWorkspaceStats,
          });
          setHistoryProjects(listing?.history || []);
          projectsRef.current = nextProjects;
        }
        if (detail && !cancelled) {
          applyProjectDetail(detail, {
            preserveSelectedStep: true,
            runningJob,
          });
        }
      } catch {
        // Keep event-driven refresh failures quiet; manual refresh still surfaces errors.
      } finally {
        bridgeRefreshInFlightRef.current = false;
        if (!cancelled && pendingBridgeRefreshRepoIdRef.current) {
          scheduleBridgeRefresh(pendingBridgeRefreshRepoIdRef.current);
        }
      }
    }

    function scheduleBridgeRefresh(eventRepoId = "", options = {}) {
      pendingBridgeRefreshRepoIdRef.current = mergeRefreshRepoId(pendingBridgeRefreshRepoIdRef.current, eventRepoId);
      pendingBridgeRefreshListingRef.current = pendingBridgeRefreshListingRef.current || options.refreshListing !== false;
      if (bridgeRefreshTimerRef.current) {
        window.clearTimeout(bridgeRefreshTimerRef.current);
      }
      bridgeRefreshTimerRef.current = window.setTimeout(() => {
        bridgeRefreshTimerRef.current = null;
        void flushBridgeRefresh();
      }, projectRefreshDebounceMs(activeJobRef.current));
    }

    async function handleBridgeEvent(eventPayload) {
      if (!workspaceRoot) {
        return;
      }
      if (isJobUpdatedEvent(eventPayload)) {
        const job = bridgeEventJob(eventPayload);
        if (!job) {
          return;
        }
        setActiveJob(job);
        if (job.status === "running") {
          activeJobRef.current = job;
          setActiveJobId(job.id || "");
        } else if (!cancelled) {
          activeJobRef.current = null;
          setActiveJobId("");
          if (job.result?.project && shouldReplaceVisibleProject(selectedProjectId, job.result.project.repo_id)) {
            applyProjectDetail(job.result, { preserveDirtyPlan: false, runningJob: null, force: true });
          }
          const listing = await loadProjectListing(bridgeRequest, workspaceRoot);
          if (cancelled) {
            return;
          }
          const nextProjects = applyListingState({
            listing,
            runningJob: null,
            setProjects,
            setWorkspaceStats,
          });
          projectsRef.current = nextProjects;
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
        return;
      }

      if (isProjectChangedEvent(eventPayload)) {
        const project = bridgeEventProject(eventPayload);
        const eventRepoId = String(project?.repo_id || "").trim();
        scheduleBridgeRefresh(eventRepoId, { refreshListing: true });
        return;
      }
      if (isProjectUiEvent(eventPayload)) {
        const project = bridgeEventProject(eventPayload);
        const eventRepoId = String(project?.repo_id || "").trim();
        if (shouldRefreshSelectedProject(selectedProjectId, eventRepoId)) {
          scheduleBridgeRefresh(eventRepoId, { refreshListing: false });
        }
      }
    }

    let unlisten = null;
    const subscription = subscribeBridgeEvents((eventPayload) => {
      void handleBridgeEvent(eventPayload);
    }).then((dispose) => {
      unlisten = dispose;
    });

    return () => {
      cancelled = true;
      if (bridgeRefreshTimerRef.current) {
        window.clearTimeout(bridgeRefreshTimerRef.current);
        bridgeRefreshTimerRef.current = null;
      }
      void subscription.then(() => {
        if (typeof unlisten === "function") {
          return unlisten();
        }
        return null;
      });
    };
  }, [
    language,
    selectedProjectId,
    wantsExpandedDetail,
    workspaceRoot,
  ]);

  async function refreshProjects() {
    const listing = await loadProjectListing(bridgeRequest, workspaceRoot);
    const nextProjects = applyListingState({
      listing,
      runningJob: activeJob?.status === "running" ? activeJob : null,
      setProjects,
      setWorkspaceStats,
    });
    setHistoryProjects(listing?.history || []);
    projectsRef.current = nextProjects;
    if (!selectedProjectId && nextProjects.length) {
      setSelectedProjectId(nextProjects[0].repo_id);
    }
  }

  async function forceRefresh() {
    try {
      const jobSnapshot = await syncRunningJobSnapshot(activeJobId);
      const runningJob = applyCurrentJobSnapshot(jobSnapshot);
      const listing = await loadProjectListing(bridgeRequest, workspaceRoot);
      const nextProjects = applyListingState({
        listing,
        runningJob,
        setProjects,
        setWorkspaceStats,
      });
      setHistoryProjects(listing?.history || []);
      projectsRef.current = nextProjects;

      if (selectedProjectId) {
        const detail = await fetchProjectDetail(bridgeRequest, selectedProjectId, workspaceRoot, {
          refreshCodexStatus: true,
          detailLevel: wantsExpandedDetail ? "full" : "core",
        });
        applyProjectDetail(detail, { preserveSelectedStep: true, runningJob });
      } else if (selectedHistoryId) {
        const detail = await fetchHistoryDetail(bridgeRequest, selectedHistoryId, workspaceRoot, {
          detailLevel: centerTab === "history" ? "full" : "core",
        });
        setHistoryDetail(detail);
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
      const detail = await fetchProjectDetail(bridgeRequest, repoId, workspaceRoot, {
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
    clearProjectSelectionState({
      defaultRuntime: nextRuntime,
      refs: {
        lastAppliedDetailSignatureRef,
      },
      setters: {
        setProjectDetail,
        setSelectedProjectId,
        setSelectedStepId,
        setPlanDirty,
        setLoadingProjectId,
        setProjectForm,
        setPlanDraft,
        setShareSettings,
      },
    });
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
        BRIDGE_COMMANDS.SAVE_PROJECT_SETUP,
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
    if (!window.confirm(translate(language, "prompt.confirmArchiveProject"))) {
      return;
    }
    const nextForm = applyProgramSettingsToForm(projectForm, storedProgramSettings);
    await withPending("delete-project", async () => {
      const result = await bridgeRequest(
        BRIDGE_COMMANDS.DELETE_PROJECT,
        {
          repo_id: selectedProjectId,
        },
        workspaceRoot || null,
      );
      setProjects(result.projects || []);
      setHistoryProjects(result.history || []);
      setWorkspaceStats(result.workspace || null);
      clearSelectedProjectState(defaultRuntime);
      setProjectForm({
        ...blankProjectForm(defaultRuntime),
        project_dir: nextForm.project_dir,
        display_name: nextForm.display_name,
        branch: nextForm.branch,
        origin_url: nextForm.origin_url,
        github_mode: nextForm.github_mode,
        runtime: nextForm.runtime,
      });
      setSelectedHistoryId(result.archived?.archive_id || "");
      setMessage(messagePayload("success", translate(language, "message.projectArchived")));
    });
  }

  async function deleteProjectById(repoId) {
    if (!repoId) {
      return;
    }
    if (!window.confirm(translate(language, "prompt.confirmArchiveProject"))) {
      return;
    }
    const nextForm = repoId === selectedProjectId ? applyProgramSettingsToForm(projectForm, storedProgramSettings) : null;
    await withPending("delete-project", async () => {
      const result = await bridgeRequest(
        BRIDGE_COMMANDS.DELETE_PROJECT,
        {
          repo_id: repoId,
        },
        workspaceRoot || null,
      );
      setProjects(result.projects || []);
      setHistoryProjects(result.history || []);
      setWorkspaceStats(result.workspace || null);
      if (repoId === selectedProjectId) {
        clearSelectedProjectState(defaultRuntime);
        if (nextForm) {
          setProjectForm({
            ...blankProjectForm(defaultRuntime),
            project_dir: nextForm.project_dir,
            display_name: nextForm.display_name,
            branch: nextForm.branch,
            origin_url: nextForm.origin_url,
            github_mode: nextForm.github_mode,
            runtime: nextForm.runtime,
          });
        }
      }
      setSelectedHistoryId(result.archived?.archive_id || selectedHistoryId);
      setMessage(messagePayload("success", translate(language, "message.projectArchived")));
    });
  }

  async function deleteAllProjects() {
    if (!projects.length) {
      return;
    }
    if (!window.confirm(translate(language, "prompt.confirmArchiveAllProjects"))) {
      return;
    }
    await withPending("delete-all-projects", async () => {
      const result = await bridgeRequest(BRIDGE_COMMANDS.DELETE_ALL_PROJECTS, {}, workspaceRoot || null);
      setProjects(result.projects || []);
      setHistoryProjects(result.history || []);
      setWorkspaceStats(result.workspace || null);
      clearSelectedProjectState(defaultRuntime);
      setSelectedHistoryId((result.history || [])[0]?.archive_id || "");
      setMessage(messagePayload("success", translate(language, "message.allProjectsArchived")));
    });
  }

  async function savePlan() {
    if (!projectForm.project_dir.trim()) {
      setMessage(messagePayload("error", translate(language, "message.openOrCreateProjectFirst")));
      return;
    }
    await withPending("save-plan", async () => {
      const detail = await bridgeRequest(
        BRIDGE_COMMANDS.SAVE_PLAN,
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
        BRIDGE_COMMANDS.RESET_PLAN,
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
      return job;
    } catch (error) {
      setMessage(messagePayload("error", String(error)));
      return null;
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
    await startJob(BRIDGE_COMMANDS.GENERATE_PLAN, {
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
    const job = await startJob(BRIDGE_COMMANDS.RUN_PLAN, buildProjectPayload(applyProgramSettingsToForm(projectForm, storedProgramSettings), planDraft));
    if (job) {
      setPlanDirty(false);
    }
  }

  async function requestStop() {
    if (!projectForm.project_dir.trim()) {
      return;
    }
    await withPending("request-stop", async () => {
      await bridgeRequest(
        BRIDGE_COMMANDS.REQUEST_STOP,
        {
          project_dir: projectForm.project_dir.trim(),
          source: "tauri-react-ui",
        },
        workspaceRoot || null,
      );
      const detail = await fetchProjectDetailBySelector(
        bridgeRequest,
        { projectDir: projectForm.project_dir.trim() },
        workspaceRoot,
        { refreshCodexStatus: false, detailLevel: wantsExpandedDetail ? "full" : "core" },
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
        BRIDGE_COMMANDS.CREATE_SHARE_SESSION,
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
        BRIDGE_COMMANDS.REVOKE_SHARE_SESSION,
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
        BRIDGE_COMMANDS.APPROVE_CHECKPOINT,
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
      metadata: {},
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
    shareBusy,
    workspaceRoot,
    defaultRuntime,
    programSettings,
    programSettingsDirty,
    modelPresets,
    modelCatalog,
    projects,
    filteredProjects,
    historyProjects,
    filteredHistoryProjects,
    workspaceStats,
    selectedProjectId,
    selectedHistoryId,
    projectForm,
    projectDetail,
    historyDetail,
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
    setSelectedHistoryId,
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
