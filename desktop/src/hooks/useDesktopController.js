import { startTransition, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { confirm as confirmDialog, open } from "@tauri-apps/plugin-dialog";
import { bridgeRequest, cancelBridgeJob, configureBridgeScheduler, startBridgeJob, subscribeBridgeEvents } from "../api";
import { BRIDGE_COMMANDS } from "../bridgeProtocol";
import { bridgeEventJob, bridgeEventProject, isJobUpdatedEvent, isProjectChangedEvent, isProjectUiEvent } from "../controller/bridgeEvents";
import {
  mergeRefreshRepoId,
  projectRefreshDebounceMs,
  shouldRefreshListingForProjectEvent,
  shouldRefreshSelectedProject,
} from "../controller/projectRefresh";
import {
  carryProjectPromptDraft,
  defaultShareSettings,
  emptyPlanDraft,
  messagePayload,
  needsExpandedProjectDetail,
  planGenerationValidation,
  resolveConfirmation,
  shareSettingsFromDetail,
  shouldPreserveProjectPrompt,
} from "../controllerHelpers";
import { useI18n } from "../i18n";
import { translate } from "../locale";
import {
  applyProgramSettings,
  backgroundJobProjectKey,
  applyProgramSettingsToForm,
  basename,
  blankProjectForm,
  buildProjectPayload,
  buildRunPlanPayloadFromDetail,
  cloneValue,
  commandLabel,
  firstSelectableStepId,
  inheritProjectIdentityForm,
  isDuplicateProjectJobError,
  planDependencyValidationMessage,
  projectJobFromJobs,
  programSettingsFromRuntime,
  projectFormFromDetail,
  sanitizeProjectListForJobState,
  shouldReplaceVisibleProject,
  workspaceStatsFromProjects,
} from "../utils";
import {
  fetchHistoryDetail,
  fetchProjectCheckpoints,
  fetchProjectDetail,
  fetchProjectDetailBySelector,
  fetchProjectHistory,
  fetchProjectReports,
  fetchProjectWorkspace,
  loadInitialDesktopState,
  loadProjectListing,
  refreshVisibleProjectState,
  syncRunningJobSnapshot,
} from "../controller/projectQueries";
import {
  applyListingState,
  applyProjectDetailState,
  applyProjectDetailListingState,
  clearSelectedProjectState as clearProjectSelectionState,
  mergeProjectDetailSupplement,
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
  const [workspaceShareDetail, setWorkspaceShareDetail] = useState(null);
  const [historyDetail, setHistoryDetail] = useState(null);
  const [planDraft, setPlanDraft] = useState(() => emptyPlanDraft());
  const [selectedStepId, setSelectedStepId] = usePersistentState("jakal-flow:selected-step", "");
  const [planDirty, setPlanDirty] = useState(false);
  const [pendingAction, setPendingAction] = useState("");
  const [startingJobCount, setStartingJobCount] = useState(0);
  const [loadingProjectId, setLoadingProjectId] = useState("");
  const [jobs, setJobs] = useState([]);
  const [message, setMessage] = useState(null);
  const [shareSettings, setShareSettings] = useState(() => defaultShareSettings());
  const [autoRunAfterPlan, setAutoRunAfterPlan] = usePersistentState("jakal-flow:auto-run-after-plan", false);
  const projectAutosaveTimerRef = useRef(null);
  const lastAppliedDetailSignatureRef = useRef("");
  const bridgeRefreshInFlightRef = useRef(false);
  const bridgeRefreshTimerRef = useRef(null);
  const pendingBridgeRefreshRepoIdRef = useRef("");
  const pendingBridgeRefreshListingRef = useRef(false);
  const startingProjectJobsRef = useRef(new Set());
  const activeJobRef = useRef(null);
  const appliedSchedulerLimitRef = useRef(0);
  const autoRunAfterPlanRef = useRef(false);
  const defaultRuntimeRef = useRef(null);
  const jobsRef = useRef([]);
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
  const activeJob = useMemo(
    () =>
      projectJobFromJobs(jobs, {
        repo_id: selectedProjectId,
        project_dir: projectDetail?.project?.repo_path || projectForm?.project_dir || "",
        current_status: projectDetail?.project?.current_status || "",
        last_run_at: projectDetail?.project?.last_run_at || "",
      }),
    [jobs, projectDetail?.project?.current_status, projectDetail?.project?.last_run_at, projectDetail?.project?.repo_path, projectForm?.project_dir, selectedProjectId],
  );
  const activeJobId = activeJob?.id || "";
  const queuedJobs = useMemo(
    () =>
      [...jobs]
        .filter((job) => String(job?.status || "").trim().toLowerCase() === "queued")
        .sort((left, right) => {
          const leftPosition = Number.parseInt(String(left?.queue_position || 0), 10) || Number.MAX_SAFE_INTEGER;
          const rightPosition = Number.parseInt(String(right?.queue_position || 0), 10) || Number.MAX_SAFE_INTEGER;
          if (leftPosition !== rightPosition) {
            return leftPosition - rightPosition;
          }
          return (Number(left?.updated_at_ms || 0) || 0) - (Number(right?.updated_at_ms || 0) || 0);
        }),
    [jobs],
  );

  const busy = Boolean(pendingAction || startingJobCount > 0 || ["queued", "running"].includes(String(activeJob?.status || "").trim().toLowerCase()));
  const canRequestStop = String(activeJob?.status || "").trim().toLowerCase() === "running";
  const canCancelReservation = String(activeJob?.status || "").trim().toLowerCase() === "queued";
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
    autoRunAfterPlanRef.current = Boolean(autoRunAfterPlan);
  }, [autoRunAfterPlan]);

  useEffect(() => {
    defaultRuntimeRef.current = defaultRuntime;
  }, [defaultRuntime]);

  useEffect(() => {
    projectsRef.current = projects;
  }, [projects]);

  useEffect(() => {
    jobsRef.current = jobs;
  }, [jobs]);

  useEffect(() => {
    let cancelled = false;
    const nextLimit = Math.max(1, Number.parseInt(String(programSettings?.background_concurrency_limit || 2), 10) || 2);
    if (!workspaceRoot || appliedSchedulerLimitRef.current === nextLimit) {
      return undefined;
    }

    async function syncSchedulerLimit() {
      try {
        await configureBridgeScheduler(nextLimit, workspaceRoot || null);
        if (!cancelled) {
          appliedSchedulerLimitRef.current = nextLimit;
        }
      } catch (error) {
        if (!cancelled) {
          setMessage(messagePayload("error", String(error)));
        }
      }
    }

    void syncSchedulerLimit();
    return () => {
      cancelled = true;
    };
  }, [programSettings?.background_concurrency_limit, workspaceRoot]);

  useEffect(() => {
    if (selectedHistoryId && !historyProjects.some((item) => item.archive_id === selectedHistoryId)) {
      setSelectedHistoryId("");
      setHistoryDetail(null);
    }
  }, [historyProjects, selectedHistoryId, setSelectedHistoryId]);

  function reapplyProjectJobState(jobItems = jobsRef.current) {
    const nextProjects = sanitizeProjectListForJobState(projectsRef.current, jobItems);
    setProjects(nextProjects);
    setWorkspaceStats(workspaceStatsFromProjects(nextProjects));
    projectsRef.current = nextProjects;
  }

  function syncJobs(jobItems = []) {
    const nextJobs = Array.isArray(jobItems) ? jobItems.filter(Boolean) : [];
    jobsRef.current = nextJobs;
    setJobs(nextJobs);
    const nextActiveJob = projectJobFromJobs(nextJobs, {
      repo_id: selectedProjectId,
      project_dir: projectDetail?.project?.repo_path || projectForm?.project_dir || "",
      current_status: projectDetail?.project?.current_status || "",
      last_run_at: projectDetail?.project?.last_run_at || "",
    });
    activeJobRef.current = nextActiveJob;
    return nextActiveJob;
  }

  function mergeJobUpdate(job) {
    const nextJobs = [...jobsRef.current];
    const index = nextJobs.findIndex((item) => item?.id === job?.id);
    if (index >= 0) {
      nextJobs[index] = job;
    } else {
      nextJobs.unshift(job);
    }
    nextJobs.sort((left, right) => (Number(right?.updated_at_ms || 0) || 0) - (Number(left?.updated_at_ms || 0) || 0));
    return syncJobs(nextJobs);
  }

  function applyCurrentJobSnapshot(jobSnapshot) {
    const selectedJob = syncJobs(jobSnapshot?.jobs || []);
    return String(selectedJob?.status || "").trim().toLowerCase() === "running" ? selectedJob : null;
  }

  function applyProjectDetail(detail, options = {}) {
    const normalizedDetail = applyProjectDetailState({
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
    if (detail?.share) {
      setWorkspaceShareDetail(detail.share);
    }
    if (normalizedDetail) {
      const nextProjects = applyProjectDetailListingState({
        projects: projectsRef.current,
        detail: normalizedDetail,
        runningJob: options.runningJob ?? jobsRef.current,
        setProjects,
        setWorkspaceStats,
      });
      if (nextProjects) {
        projectsRef.current = nextProjects;
      }
    }
    return normalizedDetail;
  }

  function mergeSelectedProjectSupplement(repoId, supplement) {
    if (!repoId || !supplement) {
      return;
    }
    startTransition(() => {
      setProjectDetail((current) => {
        if (String(current?.project?.repo_id || "").trim() !== String(repoId || "").trim()) {
          return current;
        }
        return mergeProjectDetailSupplement(current, supplement);
      });
    });
  }

  function projectSectionLoaded(sectionKey) {
    return Boolean(projectDetail?.loaded_sections?.[sectionKey]);
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
        const workspaceShare = await bridgeRequest(BRIDGE_COMMANDS.LOAD_WORKSPACE_SHARE, {}, bootstrap.workspace_root);
        if (cancelled) {
          return;
        }
        setWorkspaceShareDetail(workspaceShare?.share || null);
        setBaseRuntime(bootstrap.default_runtime);
        setModelPresets(bootstrap.model_presets || []);
        setModelCatalog(bootstrap.model_catalog || []);
        const nextProgramSettings = programSettingsFromRuntime(storedProgramSettings || bootstrap.default_runtime);
        setStoredProgramSettings(nextProgramSettings);
        setProgramSettings(nextProgramSettings);
        setProjectForm(blankProjectForm(applyProgramSettings(bootstrap.default_runtime, nextProgramSettings)));
        applyCurrentJobSnapshot(jobSnapshot);
        if (cancelled) {
          return;
        }
        const nextProjects = applyListingState({
          listing,
          runningJob: jobsRef.current,
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

    async function loadProjectSupplements() {
      const repoId = String(selectedProjectId || "").trim();
      if (!repoId || !workspaceRoot || pendingAction || loadingProjectId) {
        return;
      }
      if (String(projectDetail?.project?.repo_id || "").trim() !== repoId) {
        return;
      }
      const supplementRequests = [];
      if (Boolean(programSettings?.developer_mode) && centerTab === "reports" && !projectSectionLoaded("reports")) {
        supplementRequests.push(fetchProjectReports(bridgeRequest, repoId, workspaceRoot));
      }
      if (sidebarTab === "workspace" && !projectSectionLoaded("workspace")) {
        supplementRequests.push(fetchProjectWorkspace(bridgeRequest, repoId, workspaceRoot));
      }
      if (sidebarTab === "plans" && !projectSectionLoaded("checkpoints")) {
        supplementRequests.push(fetchProjectCheckpoints(bridgeRequest, repoId, workspaceRoot));
      }
      if (centerTab === "history" && !selectedHistoryId && !projectSectionLoaded("history")) {
        supplementRequests.push(fetchProjectHistory(bridgeRequest, repoId, workspaceRoot));
      }
      if (!supplementRequests.length) {
        return;
      }
      try {
        const supplements = await Promise.all(supplementRequests);
        if (cancelled) {
          return;
        }
        const mergedSupplement = supplements.reduce(
          (combined, supplement) => ({
            ...combined,
            ...supplement,
            loaded_sections: {
              ...(combined?.loaded_sections || {}),
              ...(supplement?.loaded_sections || {}),
            },
          }),
          {},
        );
        mergeSelectedProjectSupplement(repoId, mergedSupplement);
      } catch (error) {
        if (!cancelled && !pendingAction) {
          setMessage(messagePayload("error", String(error)));
        }
      }
    }

    void loadProjectSupplements();
    return () => {
      cancelled = true;
    };
  }, [
    centerTab,
    loadingProjectId,
    pendingAction,
    programSettings?.developer_mode,
    projectDetail?.loaded_sections?.checkpoints,
    projectDetail?.loaded_sections?.history,
    projectDetail?.loaded_sections?.reports,
    projectDetail?.loaded_sections?.workspace,
    projectDetail?.project?.repo_id,
    selectedHistoryId,
    selectedProjectId,
    sidebarTab,
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
        const selectedJob = projectJobFromJobs(jobsRef.current, {
          repo_id: selectedProjectId,
          project_dir: projectDetail?.project?.repo_path || projectForm?.project_dir || "",
          current_status: projectDetail?.project?.current_status || "",
          last_run_at: projectDetail?.project?.last_run_at || "",
        });
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
            runningJob: jobsRef.current,
            setProjects,
            setWorkspaceStats,
          });
          setHistoryProjects(listing?.history || []);
          projectsRef.current = nextProjects;
        }
        if (detail && !cancelled) {
          applyProjectDetail(detail, {
            preserveSelectedStep: true,
            runningJob: selectedJob,
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
      }, projectRefreshDebounceMs(jobsRef.current.find((job) => String(job?.status || "").trim().toLowerCase() === "running") || null));
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
        const nextSelectedJob = mergeJobUpdate(job);
        reapplyProjectJobState(jobsRef.current);
        const jobStatus = String(job.status || "").trim().toLowerCase();
        if (!["queued", "running"].includes(jobStatus) && !cancelled) {
          if (job.result?.project && shouldReplaceVisibleProject(selectedProjectId, job.result.project.repo_id)) {
            applyProjectDetail(job.result, { preserveDirtyPlan: false, runningJob: nextSelectedJob, force: true });
          }
          if (
            jobStatus === "completed"
            && job.command === BRIDGE_COMMANDS.GENERATE_PLAN
            && autoRunAfterPlanRef.current
          ) {
            const chainedRun = await startAutoRunFromGeneratedPlan(job.result);
            if (cancelled) {
              return;
            }
            if (chainedRun.attempted) {
              return;
            }
          }
          const listing = await loadProjectListing(bridgeRequest, workspaceRoot);
          if (cancelled) {
            return;
          }
          const nextProjects = applyListingState({
            listing,
            runningJob: jobsRef.current,
            setProjects,
            setWorkspaceStats,
          });
          projectsRef.current = nextProjects;
          setMessage(
            job.status === "completed"
              ? messagePayload(
                  "success",
                  completedJobMessage(job),
                )
              : jobStatus === "cancelled"
                ? messagePayload(
                    "info",
                    translate(language, "message.commandCancelled", {
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
        scheduleBridgeRefresh(eventRepoId, {
          refreshListing: shouldRefreshListingForProjectEvent(selectedProjectId, eventRepoId),
        });
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
      runningJob: jobsRef.current,
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
      applyCurrentJobSnapshot(jobSnapshot);
      const selectedJob = projectJobFromJobs(jobsRef.current, {
        repo_id: selectedProjectId,
        project_dir: projectDetail?.project?.repo_path || projectForm?.project_dir || "",
        current_status: projectDetail?.project?.current_status || "",
        last_run_at: projectDetail?.project?.last_run_at || "",
      });
      const listing = await loadProjectListing(bridgeRequest, workspaceRoot);
      const nextProjects = applyListingState({
        listing,
        runningJob: jobsRef.current,
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
        applyProjectDetail(detail, { preserveSelectedStep: true, runningJob: selectedJob });
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
        applyProjectDetail(
          detail,
          {
            runningJob: projectJobFromJobs(jobsRef.current, {
              repo_id: repoId,
              project_dir: detail?.project?.repo_path || "",
              current_status: detail?.project?.current_status || "",
              last_run_at: detail?.project?.last_run_at || "",
            }),
          },
        );
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
    const formToSave = cloneValue(formOverride || projectForm);
    const preserveLocalPlan = Boolean(planDirty);
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
      setProjectForm(projectFormFromDetail(detail, defaultRuntime));
      if (preserveLocalPlan) {
        setPlanDraft(cloneValue(planDraft));
      } else {
        setPlanDraft(cloneValue(detail.plan));
        setSelectedStepId(firstSelectableStepId(detail.plan));
      }
      setPlanDirty(preserveLocalPlan);
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

  function restoreProjectForm(nextForm) {
    setProjectForm(inheritProjectIdentityForm(nextForm, defaultRuntime));
  }

  function restoreProjectPrompt(nextPlan) {
    if (!shouldPreserveProjectPrompt(nextPlan)) {
      return;
    }
    setPlanDraft(carryProjectPromptDraft(nextPlan));
    setSelectedStepId("");
    setPlanDirty(true);
  }

  async function requestConfirmation(messageKey, { kind = "warning", okLabel = undefined } = {}) {
    return resolveConfirmation(
      (message) =>
        confirmDialog(message, {
          title: "jakal-flow",
          kind,
          okLabel,
          cancelLabel: translate(language, "common.no"),
        }),
      (message) => globalThis.window?.confirm?.(message),
      translate(language, messageKey),
    );
  }

  function completedJobMessage(job) {
    const command = commandLabel(job?.command, language);
    const normalizedCommand = String(job?.command || "").trim().toLowerCase();
    const closeoutCompleted = String(job?.result?.plan?.closeout_status || "").trim().toLowerCase() === "completed";
    const wordReportPath = String(job?.result?.reports?.word_report_path || "").trim();
    if (["run-plan", "run-closeout"].includes(normalizedCommand) && closeoutCompleted && wordReportPath) {
      return translate(language, "message.commandCompletedWithWordReport", {
        command,
        path: wordReportPath,
      });
    }
    return translate(language, "message.commandCompleted", { command });
  }

  async function archiveProject() {
    if (!selectedProjectId) {
      setMessage(messagePayload("error", translate(language, "message.openProjectFirst")));
      return;
    }
    if (!(await requestConfirmation("prompt.confirmArchiveProject", { okLabel: translate(language, "action.archiveProject") }))) {
      return;
    }
    const nextForm = cloneValue(projectForm);
    await withPending("archive-project", async () => {
      const result = await bridgeRequest(
        BRIDGE_COMMANDS.ARCHIVE_PROJECT,
        {
          repo_id: selectedProjectId,
        },
        workspaceRoot || null,
      );
      setProjects(result.projects || []);
      setHistoryProjects(result.history || []);
      setWorkspaceStats(result.workspace || null);
      clearSelectedProjectState(defaultRuntime);
      restoreProjectForm(nextForm);
      restoreProjectPrompt(planDraft);
      setSelectedHistoryId(result.archived?.archive_id || "");
      setMessage(messagePayload("success", translate(language, "message.projectArchived")));
    });
  }

  async function archiveProjectById(repoId) {
    if (!repoId) {
      return;
    }
    if (!(await requestConfirmation("prompt.confirmArchiveProject", { okLabel: translate(language, "action.archiveProject") }))) {
      return;
    }
    const nextForm = repoId === selectedProjectId ? cloneValue(projectForm) : null;
    await withPending("archive-project", async () => {
      const result = await bridgeRequest(
        BRIDGE_COMMANDS.ARCHIVE_PROJECT,
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
          restoreProjectForm(nextForm);
          restoreProjectPrompt(planDraft);
        }
      }
      setSelectedHistoryId(result.archived?.archive_id || selectedHistoryId);
      setMessage(messagePayload("success", translate(language, "message.projectArchived")));
    });
  }

  async function deleteProject() {
    if (!selectedProjectId) {
      setMessage(messagePayload("error", translate(language, "message.openProjectFirst")));
      return;
    }
    if (!(await requestConfirmation("prompt.confirmDeleteProject", { okLabel: translate(language, "action.deleteProject") }))) {
      return;
    }
    const nextForm = cloneValue(projectForm);
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
      restoreProjectForm(nextForm);
      restoreProjectPrompt(planDraft);
      setMessage(messagePayload("success", translate(language, "message.projectDeleted")));
    });
  }

  async function deleteProjectById(repoId) {
    if (!repoId) {
      return;
    }
    if (!(await requestConfirmation("prompt.confirmDeleteProject", { okLabel: translate(language, "action.deleteProject") }))) {
      return;
    }
    const nextForm = repoId === selectedProjectId ? cloneValue(projectForm) : null;
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
          restoreProjectForm(nextForm);
          restoreProjectPrompt(planDraft);
        }
      }
      setMessage(messagePayload("success", translate(language, "message.projectDeleted")));
    });
  }

  async function archiveAllProjects() {
    if (!projects.length) {
      return;
    }
    if (!(await requestConfirmation("prompt.confirmArchiveAllProjects", { okLabel: translate(language, "action.archiveAllProjects") }))) {
      return;
    }
    await withPending("archive-all-projects", async () => {
      const result = await bridgeRequest(BRIDGE_COMMANDS.ARCHIVE_ALL_PROJECTS, {}, workspaceRoot || null);
      setProjects(result.projects || []);
      setHistoryProjects(result.history || []);
      setWorkspaceStats(result.workspace || null);
      clearSelectedProjectState(defaultRuntime);
      setSelectedHistoryId((result.history || [])[0]?.archive_id || "");
      setMessage(messagePayload("success", translate(language, "message.allProjectsArchived")));
    });
  }

  async function deleteAllProjects() {
    if (!projects.length) {
      return;
    }
    if (!(await requestConfirmation("prompt.confirmDeleteAllProjects", { okLabel: translate(language, "action.deleteAllProjects") }))) {
      return;
    }
    await withPending("delete-all-projects", async () => {
      const result = await bridgeRequest(BRIDGE_COMMANDS.DELETE_ALL_PROJECTS, {}, workspaceRoot || null);
      setProjects(result.projects || []);
      setHistoryProjects(result.history || []);
      setWorkspaceStats(result.workspace || null);
      clearSelectedProjectState(defaultRuntime);
      setMessage(messagePayload("success", translate(language, "message.allProjectsDeleted")));
    });
  }

  async function deleteHistoryEntry(archiveId) {
    if (!archiveId) {
      return;
    }
    if (!(await requestConfirmation("prompt.confirmDeleteHistoryEntry", { okLabel: translate(language, "action.deleteArchivedRun") }))) {
      return;
    }
    await withPending("delete-history-entry", async () => {
      const result = await bridgeRequest(
        BRIDGE_COMMANDS.DELETE_HISTORY_ENTRY,
        {
          archive_id: archiveId,
        },
        workspaceRoot || null,
      );
      setProjects(result.projects || []);
      setHistoryProjects(result.history || []);
      setWorkspaceStats(result.workspace || null);
      const nextHistoryId = (result.history || [])[0]?.archive_id || "";
      if (archiveId === selectedHistoryId) {
        setSelectedHistoryId(nextHistoryId);
        if (!nextHistoryId) {
          setHistoryDetail(null);
        }
      }
      setMessage(messagePayload("success", translate(language, "message.historyEntryDeleted")));
    });
  }

  async function savePlan() {
    if (!projectForm.project_dir.trim()) {
      setMessage(messagePayload("error", translate(language, "message.openOrCreateProjectFirst")));
      return;
    }
    const dependencyValidationError = planDependencyValidationMessage(planDraft);
    if (dependencyValidationError) {
      setMessage(messagePayload("error", dependencyValidationError));
      return;
    }
    await withPending("save-plan", async () => {
      const detail = await bridgeRequest(
        BRIDGE_COMMANDS.SAVE_PLAN,
        buildProjectPayload(projectForm, planDraft),
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
    if (!(await requestConfirmation("prompt.confirmResetPlan", { okLabel: translate(language, "action.reset") }))) {
      return;
    }
    await withPending("reset-plan", async () => {
      const detail = await bridgeRequest(
        BRIDGE_COMMANDS.RESET_PLAN,
        buildProjectPayload(projectForm),
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
    const targetProject = {
      repo_id: String(payload?.repo_id || "").trim(),
      project_dir: String(payload?.project_dir || "").trim(),
    };
    const currentProjectJob = () => projectJobFromJobs(jobsRef.current, targetProject);
    const projectJobKey = backgroundJobProjectKey(payload, workspaceRoot || "");
    const existingJob = currentProjectJob();
    if (["queued", "running"].includes(String(existingJob?.status || "").trim().toLowerCase())) {
      return existingJob;
    }
    if (projectJobKey && startingProjectJobsRef.current.has(projectJobKey)) {
      return currentProjectJob() || null;
    }
    if (projectJobKey) {
      startingProjectJobsRef.current.add(projectJobKey);
    }
    setStartingJobCount((count) => count + 1);
    try {
      setMessage(null);
      const job = await startBridgeJob(command, payload, workspaceRoot || null);
      mergeJobUpdate(job);
      reapplyProjectJobState(jobsRef.current);
      setCenterTab("run");
      setBottomTab("json");
      setMessage(
        messagePayload(
          "info",
          String(job?.status || "").trim().toLowerCase() === "queued"
            ? translate(language, "message.commandQueued", {
                command: commandLabel(command, language),
                position: Math.max(1, Number.parseInt(String(job?.queue_position || 1), 10) || 1),
              })
            : translate(language, "message.commandStarted", {
                command: commandLabel(command, language),
              }),
        ),
      );
      return job;
    } catch (error) {
      if (isDuplicateProjectJobError(error)) {
        try {
          const jobSnapshot = await syncRunningJobSnapshot(activeJobRef.current?.id || "");
          applyCurrentJobSnapshot(jobSnapshot);
          reapplyProjectJobState(jobSnapshot?.jobs || []);
          const recoveredJob = projectJobFromJobs(jobSnapshot?.jobs || [], targetProject);
          if (["queued", "running"].includes(String(recoveredJob?.status || "").trim().toLowerCase())) {
            return recoveredJob;
          }
        } catch {
          // Fall through to the original bridge error when the recovery snapshot is unavailable.
        }
      }
      setMessage(messagePayload("error", String(error)));
      return null;
    } finally {
      if (projectJobKey) {
        startingProjectJobsRef.current.delete(projectJobKey);
      }
      setStartingJobCount((count) => Math.max(0, count - 1));
    }
  }

  async function startAutoRunFromGeneratedPlan(detail) {
    const payload = buildRunPlanPayloadFromDetail(detail, defaultRuntimeRef.current);
    if (!payload) {
      return { attempted: false, job: null };
    }
    const job = await startJob(BRIDGE_COMMANDS.RUN_PLAN, payload);
    if (job) {
      setPlanDirty(false);
    }
    return {
      attempted: true,
      job,
    };
  }

  async function generatePlan() {
    const prompt = planDraft?.project_prompt?.trim() || "";
    const generationValidation = planGenerationValidation({
      projectDir: projectForm.project_dir,
      prompt,
      plan: planDraft,
    });
    if (generationValidation === "prepareProjectFirst") {
      setMessage(messagePayload("error", translate(language, "message.prepareProjectFirst")));
      return;
    }
    if (generationValidation === "promptRequired") {
      setMessage(messagePayload("error", translate(language, "message.promptRequired")));
      return;
    }
    if (
      generationValidation?.requiresReplacementConfirmation
      && !(await requestConfirmation("prompt.confirmRegeneratePlan", { kind: "info", okLabel: translate(language, "action.generatePlan") }))
    ) {
      return;
    }
    await startJob(BRIDGE_COMMANDS.GENERATE_PLAN, {
      ...buildProjectPayload(projectForm),
      prompt,
      max_steps: Math.max(1, Number.parseInt(String(projectForm.runtime?.max_blocks || 5), 10) || 1),
    });
  }

  async function runPlan() {
    if (!(planDraft?.steps || []).length) {
      setMessage(messagePayload("error", translate(language, "message.createStepBeforeRun")));
      return;
    }
    const dependencyValidationError = planDependencyValidationMessage(planDraft);
    if (dependencyValidationError) {
      setMessage(messagePayload("error", dependencyValidationError));
      return;
    }
    const job = await startJob(BRIDGE_COMMANDS.RUN_PLAN, buildProjectPayload(projectForm, planDraft));
    if (job) {
      setPlanDirty(false);
    }
  }

  async function requestStop() {
    if (!projectForm.project_dir.trim() || String(activeJob?.status || "").trim().toLowerCase() !== "running") {
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

  async function cancelQueuedReservation(jobId = activeJob?.id || "") {
    const targetJob = jobsRef.current.find((item) => item?.id === jobId) || null;
    if (!targetJob || String(targetJob?.status || "").trim().toLowerCase() !== "queued") {
      return;
    }
    if (!(await requestConfirmation("prompt.confirmCancelReservation", { okLabel: translate(language, "action.cancelReservation") }))) {
      return;
    }
    await withPending("cancel-reservation", async () => {
      const job = await cancelBridgeJob(jobId);
      mergeJobUpdate(job);
      reapplyProjectJobState(jobsRef.current);
      setMessage(
        messagePayload(
          "info",
          translate(language, "message.commandCancelled", {
            command: commandLabel(job?.command, language),
          }),
        ),
      );
    });
  }

  async function copyShareLink() {
    const shareUrl = workspaceShareDetail?.active_session?.share_url || "";
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
    await withPending("create_share_session", async () => {
      const shareResult = await bridgeRequest(
        BRIDGE_COMMANDS.CREATE_SHARE_SESSION,
        {
          created_by: "tauri-react-ui",
          bind_host: shareSettings.bind_host,
          public_base_url: shareSettings.public_base_url,
        },
        workspaceRoot || null,
      );
      setWorkspaceShareDetail(shareResult?.share || null);
      setShareSettings(shareSettingsFromDetail(shareResult));
      const shareUrl = shareResult?.created_share_session?.share_url || shareResult?.share?.active_session?.share_url || "";
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
    const sessionId = workspaceShareDetail?.active_session?.session_id || "";
    if (!sessionId) {
      setMessage(messagePayload("error", translate(language, "message.noShareLinkAvailable")));
      return;
    }
    await withPending("revoke_share_session", async () => {
      const shareResult = await bridgeRequest(
        BRIDGE_COMMANDS.REVOKE_SHARE_SESSION,
        {
          session_id: sessionId,
        },
        workspaceRoot || null,
      );
      setWorkspaceShareDetail(shareResult?.share || null);
      setShareSettings(shareSettingsFromDetail(shareResult));
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
      model_provider: "",
      model: "",
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
    workspaceShareDetail,
    historyDetail,
    planDraft,
    selectedStepId,
    pendingAction,
    loadingProjectId,
    activeJob,
    activeJobId,
    queuedJobs,
    canRequestStop,
    canCancelReservation,
    message,
    shareSettings,
    autoRunAfterPlan,
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
    setAutoRunAfterPlan,
    syncPlan,
    updateSelectedStep,
    chooseDirectory,
    forceRefresh,
    refreshProjects,
    loadProject,
    archiveProject,
    archiveProjectById,
    saveProject,
    deleteProject,
    deleteProjectById,
    deleteHistoryEntry,
    archiveAllProjects,
    deleteAllProjects,
    savePlan,
    resetPlan,
    startNewProject,
    saveProgramSettings,
    generatePlan,
    runPlan,
    requestStop,
    cancelQueuedReservation,
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
