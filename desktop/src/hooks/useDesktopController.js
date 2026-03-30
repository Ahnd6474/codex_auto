import { startTransition, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { confirm as confirmDialog, open } from "@tauri-apps/plugin-dialog";
import { bridgeRequest, cancelBridgeJob, configureBridgeScheduler, openInSystem, openInVsCode, startBridgeJob, subscribeBridgeEvents } from "../api";
import { BRIDGE_COMMANDS } from "../bridgeProtocol";
import { bridgeEventJob, bridgeEventProject, compactBridgeEventQueue, isJobUpdatedEvent, isProjectChangedEvent, isProjectUiEvent } from "../controller/bridgeEvents";
import {
  mergeRefreshRepoId,
  projectRefreshDebounceMs,
  shouldForceCodexRefreshForManualRefresh,
  shouldRefreshListingForProjectEvent,
  shouldRefreshSelectedProject,
} from "../controller/projectRefresh";
import { applyProjectUiEvent, shouldRefreshProjectDetailForUiEvent } from "../controller/projectUiEvents";
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
  inheritProjectIdentityForm,
  isDuplicateProjectJobError,
  isChatCommand,
  jobHasNewerActiveReplacement,
  planDependencyValidationMessage,
  projectJobFromJobs,
  programSettingsEqual,
  programSettingsFromRuntime,
  sanitizeProjectListForJobState,
  shouldReplaceVisibleProject,
  visibleExecutionJob,
  workspaceStatsFromProjects,
} from "../utils";
import {
  fetchHistoryDetail,
  fetchProjectChat,
  fetchProjectCheckpoints,
  fetchProjectDetail,
  fetchProjectDetailBySelector,
  fetchProjectHistory,
  fetchProjectReports,
  fetchProjectWorkspace,
  loadInitialDesktopState,
  loadProjectListing,
  loadWorkspaceShareDetail,
  refreshVisibleProjectState,
  syncRunningJobSnapshot,
} from "../controller/projectQueries";
import {
  applyListingState,
  applyProjectEventDetailState,
  applyProjectDetailState,
  applyProjectDetailListingState,
  applyProjectEventListingState,
  clearSelectedProjectState as clearProjectSelectionState,
  mergeProjectDetailSupplement,
} from "../controller/projectStore";
import { createRequestDeduper } from "../controller/requestDeduper";
import { usePersistentState } from "./usePersistentState";

const LISTING_RELOAD_COMMANDS = new Set([
  BRIDGE_COMMANDS.ARCHIVE_PROJECT,
  BRIDGE_COMMANDS.ARCHIVE_ALL_PROJECTS,
  BRIDGE_COMMANDS.DELETE_PROJECT,
  BRIDGE_COMMANDS.DELETE_ALL_PROJECTS,
  BRIDGE_COMMANDS.DELETE_HISTORY_ENTRY,
]);

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
  const lastAppliedDetailSignatureRef = useRef("");
  const bridgeRefreshInFlightRef = useRef(false);
  const bridgeRefreshTimerRef = useRef(null);
  const pendingBridgeRefreshRepoIdRef = useRef("");
  const pendingBridgeRefreshListingRef = useRef(false);
  const pendingBridgeRefreshDetailRef = useRef(false);
  const pendingBridgeEventsRef = useRef([]);
  const bridgeEventFlushScheduledRef = useRef(false);
  const bridgeEventFlushInFlightRef = useRef(false);
  const startingProjectJobsRef = useRef(new Set());
  const activeJobRef = useRef(null);
  const blockingJobRef = useRef(null);
  const appliedSchedulerLimitRef = useRef(0);
  const autoRunAfterPlanRef = useRef(false);
  const defaultRuntimeRef = useRef(null);
  const planDirtyRef = useRef(false);
  const jobsRef = useRef([]);
  const projectsRef = useRef([]);
  const projectDetailRequestDeduperRef = useRef(createRequestDeduper());
  const historyDetailRequestDeduperRef = useRef(createRequestDeduper());
  const projectSupplementRequestDeduperRef = useRef(createRequestDeduper());
  const workspaceShareRequestDeduperRef = useRef(createRequestDeduper());

  const [centerTab, setCenterTab] = usePersistentState("jakal-flow:center-tab", "run");
  const [bottomTab, setBottomTab] = usePersistentState("jakal-flow:bottom-tab", "json");
  const [sidebarTab, setSidebarTab] = usePersistentState("jakal-flow:sidebar-tab-v2", "workspace");
  const [bottomCollapsed, setBottomCollapsed] = usePersistentState("jakal-flow:bottom-collapsed", false);
  const [bottomHeight, setBottomHeight] = usePersistentState("jakal-flow:bottom-height", 250);
  const [rightCollapsed, setRightCollapsed] = usePersistentState("jakal-flow:right-panel-v2", false);
  const [rightWidth, setRightWidth] = usePersistentState("jakal-flow:right-width", 320);
  const [sidebarWidth, setSidebarWidth] = usePersistentState("jakal-flow:sidebar-width", 312);
  const [projectFilter, setProjectFilter] = usePersistentState("jakal-flow:project-filter", "");
  const [workspaceFilter, setWorkspaceFilter] = usePersistentState("jakal-flow:workspace-filter", "");
  const [selectedChatSessionId, setSelectedChatSessionId] = useState("");
  const [chatDraftSession, setChatDraftSession] = useState(false);
  const deferredProjectFilter = useDeferredValue(projectFilter);
  const defaultRuntime = useMemo(() => applyProgramSettings(baseRuntime, storedProgramSettings), [baseRuntime, storedProgramSettings]);
  const wantsExpandedDetail = useMemo(
    () => needsExpandedProjectDetail({ centerTab, sidebarTab, bottomCollapsed, bottomTab }),
    [bottomCollapsed, bottomTab, centerTab, sidebarTab],
  );
  const projectJob = useMemo(
    () =>
      projectJobFromJobs(jobs, {
        repo_id: selectedProjectId,
        project_dir: projectDetail?.project?.repo_path || projectForm?.project_dir || "",
        current_status: projectDetail?.project?.current_status || "",
        last_run_at: projectDetail?.project?.last_run_at || "",
      }),
    [jobs, projectDetail?.project?.current_status, projectDetail?.project?.last_run_at, projectDetail?.project?.repo_path, projectForm?.project_dir, selectedProjectId],
  );
  const activeJob = useMemo(() => visibleExecutionJob(projectJob), [projectJob]);
  const activeJobId = activeJob?.id || "";
  const queuedJobs = useMemo(
    () =>
      [...jobs]
        .filter((job) => String(job?.status || "").trim().toLowerCase() === "queued" && !isChatCommand(job?.command))
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

  const busy = Boolean(pendingAction || startingJobCount > 0 || ["queued", "running"].includes(String(projectJob?.status || "").trim().toLowerCase()));
  const canRequestStop = String(activeJob?.status || "").trim().toLowerCase() === "running";
  const canCancelReservation = String(activeJob?.status || "").trim().toLowerCase() === "queued";
  const shareBusy = pendingAction === "create_share_session" || pendingAction === "revoke_share_session";
  const savedProgramSettings = useMemo(
    () => programSettingsFromRuntime(storedProgramSettings),
    [storedProgramSettings],
  );
  const programSettingsDirty = useMemo(
    () => !programSettingsEqual(programSettings, savedProgramSettings),
    [programSettings, savedProgramSettings],
  );

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
    if (["github", "projects", "history", "chat"].includes(sidebarTab)) {
      setSidebarTab("workspace");
    }
  }, [sidebarTab, setSidebarTab]);

  useEffect(() => {
    return () => {
      if (bridgeRefreshTimerRef.current) {
        window.clearTimeout(bridgeRefreshTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    activeJobRef.current = activeJob;
  }, [activeJob]);

  useEffect(() => {
    blockingJobRef.current = projectJob;
  }, [projectJob]);

  useEffect(() => {
    autoRunAfterPlanRef.current = Boolean(autoRunAfterPlan);
  }, [autoRunAfterPlan]);

  useEffect(() => {
    defaultRuntimeRef.current = defaultRuntime;
  }, [defaultRuntime]);

  useEffect(() => {
    planDirtyRef.current = planDirty;
  }, [planDirty]);

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

  useEffect(() => {
    const detailRepoId = String(projectDetail?.project?.repo_id || "").trim();
    const currentSelection = String(selectedChatSessionId || "").trim();
    const activeSessionId = String(projectDetail?.chat?.active_session_id || "").trim();
    if (!detailRepoId || detailRepoId !== String(selectedProjectId || "").trim()) {
      if (currentSelection) {
        setSelectedChatSessionId("");
      }
      if (chatDraftSession) {
        setChatDraftSession(false);
      }
      return;
    }
    if (chatDraftSession) {
      return;
    }
    if (activeSessionId && currentSelection !== activeSessionId) {
      setSelectedChatSessionId(activeSessionId);
      return;
    }
    if (!activeSessionId && currentSelection) {
      setSelectedChatSessionId("");
    }
  }, [
    chatDraftSession,
    projectDetail?.chat?.active_session_id,
    projectDetail?.project?.repo_id,
    selectedChatSessionId,
    selectedProjectId,
  ]);

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
    activeJobRef.current = visibleExecutionJob(nextActiveJob);
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

  function applyProjectListingDelta(projectLike, runningJob = jobsRef.current) {
    const nextProjects = applyProjectEventListingState({
      projects: projectsRef.current,
      project: projectLike,
      runningJob,
      setProjects,
      setWorkspaceStats,
    });
    if (nextProjects) {
      projectsRef.current = nextProjects;
    }
    return nextProjects;
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
        defaultRuntime: defaultRuntimeRef.current,
        planDirty: planDirtyRef.current,
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
      setWorkspaceShareDetail(normalizeWorkspaceShareDetail(detail.share));
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

  function applySelectedProjectDelta(projectLike) {
    const currentRepoId = String(projectDetail?.project?.repo_id || "").trim();
    const nextRepoId = String(projectLike?.repo_id || "").trim();
    const currentRepoPath = String(projectDetail?.project?.repo_path || "").trim();
    const nextRepoPath = String(projectLike?.project_dir || "").trim();
    if (
      (!currentRepoId || !nextRepoId || currentRepoId !== nextRepoId)
      && (!currentRepoPath || !nextRepoPath || currentRepoPath !== nextRepoPath)
    ) {
      return false;
    }
    startTransition(() => {
      setProjectDetail((current) => applyProjectEventDetailState(current, projectLike) || current);
    });
    return true;
  }

  function fetchProjectDetailOnce(repoId, options = {}) {
    const requestKey = [
      workspaceRoot || "",
      repoId || "",
      options.detailLevel ?? "core",
      options.refreshCodexStatus ? "refresh" : "cached",
    ].join("|");
    return projectDetailRequestDeduperRef.current.run(requestKey, () =>
      fetchProjectDetail(bridgeRequest, repoId, workspaceRoot, options)
    );
  }

  function fetchHistoryDetailOnce(archiveId, options = {}) {
    const requestKey = [
      workspaceRoot || "",
      archiveId || "",
      options.detailLevel ?? "core",
    ].join("|");
    return historyDetailRequestDeduperRef.current.run(requestKey, () =>
      fetchHistoryDetail(bridgeRequest, archiveId, workspaceRoot, options)
    );
  }

  function fetchProjectSupplementOnce(requestKey, loader) {
    return projectSupplementRequestDeduperRef.current.run(requestKey, loader);
  }

  function loadWorkspaceShareOnce() {
    return workspaceShareRequestDeduperRef.current.run(workspaceRoot || "workspace-share", () =>
      loadWorkspaceShareDetail(bridgeRequest, workspaceRoot)
    );
  }

  function projectSectionLoaded(sectionKey) {
    return Boolean(projectDetail?.loaded_sections?.[sectionKey]);
  }

  function normalizeWorkspaceShareDetail(shareDetail, fallbackSession = null) {
    if (!shareDetail || typeof shareDetail !== "object") {
      return null;
    }
    const resolvedSession =
      shareDetail.active_session
      || shareDetail.project_active_session
      || fallbackSession
      || null;
    return {
      ...shareDetail,
      active_session: resolvedSession,
      project_active_session: shareDetail.project_active_session || resolvedSession,
    };
  }

  async function ensureWorkspaceShareLoaded(options = {}) {
    const force = options.force === true;
    if (!workspaceRoot) {
      return null;
    }
    if (!force && workspaceShareDetail) {
      return workspaceShareDetail;
    }
    const shareDetail = await loadWorkspaceShareOnce();
    const normalizedShareDetail = normalizeWorkspaceShareDetail(shareDetail?.share || null);
    setWorkspaceShareDetail(normalizedShareDetail);
    return normalizedShareDetail;
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
        const detail = await fetchHistoryDetailOnce(selectedHistoryId, {
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
        const detail = await fetchProjectDetailOnce(selectedProjectId, {
          refreshCodexStatus: false,
          detailLevel: wantsExpandedDetail ? "full" : "core",
        });
        if (cancelled) {
          return;
        }
        applyProjectDetail(detail);
      } catch (error) {
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
    loadingProjectId,
    pendingAction,
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
        supplementRequests.push(
          fetchProjectSupplementOnce(
            `${workspaceRoot || ""}|${repoId}|reports`,
            () => fetchProjectReports(bridgeRequest, repoId, workspaceRoot),
          ),
        );
      }
      if (sidebarTab === "workspace" && !projectSectionLoaded("workspace")) {
        supplementRequests.push(
          fetchProjectSupplementOnce(
            `${workspaceRoot || ""}|${repoId}|workspace`,
            () => fetchProjectWorkspace(bridgeRequest, repoId, workspaceRoot),
          ),
        );
      }
      if (sidebarTab === "chat" && !projectSectionLoaded("chat")) {
        const sessionId = selectedChatSessionId || projectDetail?.chat?.active_session_id || "";
        supplementRequests.push(
          fetchProjectSupplementOnce(
            `${workspaceRoot || ""}|${repoId}|chat|${sessionId}`,
            () => fetchProjectChat(bridgeRequest, repoId, workspaceRoot, { sessionId }),
          ),
        );
      }
      if (sidebarTab === "plans" && !projectSectionLoaded("checkpoints")) {
        supplementRequests.push(
          fetchProjectSupplementOnce(
            `${workspaceRoot || ""}|${repoId}|checkpoints`,
            () => fetchProjectCheckpoints(bridgeRequest, repoId, workspaceRoot),
          ),
        );
      }
      if (centerTab === "history" && !selectedHistoryId && !projectSectionLoaded("history")) {
        supplementRequests.push(
          fetchProjectSupplementOnce(
            `${workspaceRoot || ""}|${repoId}|history`,
            () => fetchProjectHistory(bridgeRequest, repoId, workspaceRoot),
          ),
        );
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
    projectDetail?.chat?.active_session_id,
    projectDetail?.loaded_sections?.chat,
    projectDetail?.loaded_sections?.checkpoints,
    projectDetail?.loaded_sections?.history,
    projectDetail?.loaded_sections?.reports,
    projectDetail?.loaded_sections?.workspace,
    projectDetail?.project?.repo_id,
    selectedChatSessionId,
    selectedHistoryId,
    selectedProjectId,
    sidebarTab,
    workspaceRoot,
  ]);

  useEffect(() => {
    let cancelled = false;

    async function loadWorkspaceShare() {
      if (!workspaceRoot || pendingAction) {
        return;
      }
      if (centerTab !== "app-settings" || workspaceShareDetail) {
        return;
      }
      try {
        const shareDetail = await ensureWorkspaceShareLoaded();
        if (cancelled || !shareDetail) {
          return;
        }
      } catch (error) {
        if (!cancelled) {
          setMessage(messagePayload("error", String(error)));
        }
      }
    }

    void loadWorkspaceShare();
    return () => {
      cancelled = true;
    };
  }, [centerTab, pendingAction, workspaceRoot, workspaceShareDetail]);

  useEffect(() => {
    let cancelled = false;

    async function flushBridgeRefresh() {
      if (bridgeRefreshInFlightRef.current || !workspaceRoot) {
        return;
      }
      bridgeRefreshInFlightRef.current = true;
      const pendingRepoId = pendingBridgeRefreshRepoIdRef.current;
      const refreshListing = pendingBridgeRefreshListingRef.current;
      const refreshDetail = pendingBridgeRefreshDetailRef.current;
      pendingBridgeRefreshRepoIdRef.current = "";
      pendingBridgeRefreshListingRef.current = false;
      pendingBridgeRefreshDetailRef.current = false;
      try {
        const selectedJob = projectJobFromJobs(jobsRef.current, {
          repo_id: selectedProjectId,
          project_dir: projectDetail?.project?.repo_path || projectForm?.project_dir || "",
          current_status: projectDetail?.project?.current_status || "",
          last_run_at: projectDetail?.project?.last_run_at || "",
        });
        const shouldLoadDetail = refreshDetail && shouldRefreshSelectedProject(selectedProjectId, pendingRepoId);
        const { listing, detail } = await refreshVisibleProjectState(
          bridgeRequest,
          workspaceRoot,
          shouldLoadDetail ? selectedProjectId : "",
          {
            refreshCodexStatus: false,
            // Keep event-driven refreshes on the lean core payload. Heavy sections
            // stay loaded from the existing detail state and on-demand supplements.
            detailLevel: "core",
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
      pendingBridgeRefreshDetailRef.current = pendingBridgeRefreshDetailRef.current || options.refreshDetail !== false;
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
        const normalizedCommand = String(job.command || "").trim().toLowerCase();
        const supersededByActiveJob = jobHasNewerActiveReplacement(job, jobsRef.current);
        if (normalizedCommand === BRIDGE_COMMANDS.SEND_CHAT_MESSAGE) {
          const resultProjectId = String(job?.result?.project?.repo_id || "").trim();
          if (
            job?.result?.chat
            && !supersededByActiveJob
            && shouldReplaceVisibleProject(selectedProjectId, resultProjectId)
          ) {
            mergeSelectedProjectSupplement(resultProjectId, {
              chat: job.result.chat,
              loaded_sections: {
                chat: true,
              },
            });
            setSelectedChatSessionId(String(job.result.chat.active_session_id || "").trim());
            setChatDraftSession(Boolean(job.result.chat.draft_session));
          }
          if (
            job?.result?.detail
            && !supersededByActiveJob
            && shouldReplaceVisibleProject(selectedProjectId, resultProjectId)
          ) {
            applyProjectDetail(job.result.detail, {
              preserveDirtyPlan: false,
              runningJob: nextSelectedJob,
              force: true,
            });
          }
          return;
        }
        if (!["queued", "running"].includes(jobStatus) && !cancelled) {
          if (
            !supersededByActiveJob
            && job.result?.project
            && shouldReplaceVisibleProject(selectedProjectId, job.result.project.repo_id)
          ) {
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
          const hasProjectDelta = Boolean(
            job?.result?.project
            || job?.result?.detail?.project
            || job?.result?.repo_id
            || job?.result?.project_dir,
          );
          if (job?.result?.detail?.project) {
            applyProjectListingDelta(job.result.detail.project, jobsRef.current);
          }
          if (job?.result?.project) {
            applyProjectListingDelta(job.result.project, jobsRef.current);
          }
          if (!hasProjectDelta || LISTING_RELOAD_COMMANDS.has(normalizedCommand)) {
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
          }
          if (supersededByActiveJob) {
            return;
          }
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
        const detailPatched = project ? applySelectedProjectDelta(project) : false;
        if (project) {
          applyProjectListingDelta(project, jobsRef.current);
        }
        scheduleBridgeRefresh(eventRepoId, {
          refreshListing: shouldRefreshListingForProjectEvent(selectedProjectId, eventRepoId),
          refreshDetail: !detailPatched,
        });
        return;
      }
      if (isProjectUiEvent(eventPayload)) {
        const project = bridgeEventProject(eventPayload);
        const eventRepoId = String(project?.repo_id || "").trim();
        const detailPatched = project ? applySelectedProjectDelta(project) : false;
        if (project) {
          applyProjectListingDelta(project, jobsRef.current);
        }
        const shouldPatchSelectedProject = shouldRefreshSelectedProject(selectedProjectId, eventRepoId);
        if (shouldPatchSelectedProject) {
          startTransition(() => {
            setProjectDetail((current) => applyProjectUiEvent(current, eventPayload));
          });
        }
        if (shouldPatchSelectedProject && shouldRefreshProjectDetailForUiEvent(eventPayload)) {
          scheduleBridgeRefresh(eventRepoId, { refreshListing: false, refreshDetail: !detailPatched });
        }
      }
    }

    async function flushPendingBridgeEvents() {
      if (bridgeEventFlushInFlightRef.current) {
        return;
      }
      bridgeEventFlushInFlightRef.current = true;
      try {
        while (!cancelled) {
          const nextQueue = compactBridgeEventQueue(pendingBridgeEventsRef.current);
          pendingBridgeEventsRef.current = [];
          if (!nextQueue.length) {
            break;
          }
          for (const eventPayload of nextQueue) {
            if (cancelled) {
              break;
            }
            await handleBridgeEvent(eventPayload);
          }
        }
      } finally {
        bridgeEventFlushInFlightRef.current = false;
      }
    }

    function scheduleBridgeEventFlush() {
      if (bridgeEventFlushScheduledRef.current) {
        return;
      }
      bridgeEventFlushScheduledRef.current = true;
      window.setTimeout(() => {
        bridgeEventFlushScheduledRef.current = false;
        void flushPendingBridgeEvents();
      }, 16);
    }

    let unlisten = null;
    const subscription = subscribeBridgeEvents((eventPayload) => {
      pendingBridgeEventsRef.current.push(eventPayload);
      scheduleBridgeEventFlush();
    }).then((dispose) => {
      unlisten = dispose;
    });

    return () => {
      cancelled = true;
      if (bridgeRefreshTimerRef.current) {
        window.clearTimeout(bridgeRefreshTimerRef.current);
        bridgeRefreshTimerRef.current = null;
      }
      pendingBridgeEventsRef.current = [];
      bridgeEventFlushScheduledRef.current = false;
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
      const refreshCodexStatus = shouldForceCodexRefreshForManualRefresh(centerTab);
      const jobSnapshotPromise = syncRunningJobSnapshot(activeJobId);
      const projectStatePromise = selectedProjectId
        ? refreshVisibleProjectState(
            bridgeRequest,
            workspaceRoot,
            selectedProjectId,
            {
              refreshCodexStatus,
              detailLevel: wantsExpandedDetail ? "full" : "core",
              refreshListing: true,
            },
          )
        : loadProjectListing(bridgeRequest, workspaceRoot);
      const [jobSnapshot, refreshedState] = await Promise.all([jobSnapshotPromise, projectStatePromise]);
      applyCurrentJobSnapshot(jobSnapshot);
      const selectedJob = projectJobFromJobs(jobsRef.current, {
        repo_id: selectedProjectId,
        project_dir: projectDetail?.project?.repo_path || projectForm?.project_dir || "",
        current_status: projectDetail?.project?.current_status || "",
        last_run_at: projectDetail?.project?.last_run_at || "",
      });
      if (selectedProjectId) {
        const { listing, detail } = refreshedState || {};
        const nextProjects = applyListingState({
          listing,
          runningJob: jobsRef.current,
          setProjects,
          setWorkspaceStats,
        });
        startTransition(() => {
          setHistoryProjects(listing?.history || []);
          projectsRef.current = nextProjects;
          if (detail) {
            applyProjectDetail(detail, { preserveSelectedStep: true, runningJob: selectedJob });
          }
        });
      } else {
        const listing = refreshedState;
        const nextProjects = applyListingState({
          listing,
          runningJob: jobsRef.current,
          setProjects,
          setWorkspaceStats,
        });
        const historyDetail = selectedHistoryId
          ? await fetchHistoryDetailOnce(selectedHistoryId, {
            detailLevel: centerTab === "history" ? "full" : "core",
          })
          : null;
        startTransition(() => {
          setHistoryProjects(listing?.history || []);
          projectsRef.current = nextProjects;
          if (selectedHistoryId && historyDetail) {
            setHistoryDetail(historyDetail);
          } else if (!selectedHistoryId && nextProjects.length) {
            setSelectedProjectId(nextProjects[0].repo_id);
          }
        });
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
    const previousProjectId = selectedProjectId;
    setLoadingProjectId(repoId);
    setSelectedProjectId(repoId);
    try {
      const detail = await fetchProjectDetailOnce(repoId, {
        refreshCodexStatus: options.refreshCodexStatus ?? false,
        detailLevel: options.detailLevel ?? (wantsExpandedDetail ? "full" : "core"),
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
    setMessage(null);
    clearSelectedProjectState(defaultRuntime);
    setCenterTab("config");
    setSidebarTab("workspace");
  }

  function applyProgramSettingsNow(nextSettings) {
    setStoredProgramSettings(nextSettings);
    setProgramSettings(nextSettings);
    startTransition(() => {
      setProjectForm((current) => applyProgramSettingsToForm(current, nextSettings));
    });
  }

  function updateProgramSettings(updater) {
    startTransition(() => {
      setProgramSettings((current) => {
        const draft = typeof updater === "function" ? updater(current) : updater;
        return programSettingsFromRuntime(draft);
      });
    });
  }

  function setChatModelSelection(selection = null) {
    const nextSettings = programSettingsFromRuntime({
      ...programSettings,
      chat_model_provider: String(selection?.provider || "").trim().toLowerCase(),
      chat_local_model_provider: String(selection?.localProvider || "").trim().toLowerCase(),
      chat_model: String(selection?.model || "").trim().toLowerCase(),
    });
    setStoredProgramSettings(nextSettings);
    setProgramSettings(nextSettings);
    setProjectForm((current) => ({
      ...(current || {}),
      runtime: {
        ...(current?.runtime || {}),
        chat_model_provider: nextSettings.chat_model_provider,
        chat_local_model_provider: nextSettings.chat_local_model_provider,
        chat_model: nextSettings.chat_model,
      },
    }));
  }

  function saveProgramSettings(settingsOverride = null) {
    const nextSettings = programSettingsFromRuntime(settingsOverride || programSettings);
    applyProgramSettingsNow(nextSettings);
    setMessage(messagePayload("success", translate(language, "message.programSettingsSaved")));
  }

  async function saveProject(options = {}) {
    const { formOverride = null, silent = false } = options;
    const formToSave = cloneValue(formOverride || projectForm);
    const preserveLocalPlan = Boolean(planDirty);
    const preservedStepId = selectedStepId;
    await withPending("save-project-setup", async () => {
      const detail = await bridgeRequest(
        BRIDGE_COMMANDS.SAVE_PROJECT_SETUP,
        buildProjectPayload(formToSave),
        workspaceRoot || null,
      );
      lastAppliedDetailSignatureRef.current = "";
      setSelectedProjectId(detail.project.repo_id);
      applyProjectDetail(detail, {
        force: true,
        preserveDirtyPlan: false,
      });
      if (preserveLocalPlan) {
        setPlanDraft(cloneValue(planDraft));
        setSelectedStepId(preservedStepId);
        setPlanDirty(true);
      } else {
        setSelectedStepId("");
      }
      if (!silent) {
        setMessage(messagePayload("success", translate(language, "message.projectConfigurationSaved")));
      }
    });
  }

  function updateProjectForm(updater) {
    setProjectForm((current) => {
      return typeof updater === "function" ? updater(current) : updater;
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
      applyProjectDetail(detail, { force: true, preserveDirtyPlan: false });
      setSelectedStepId("");
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
      applyProjectDetail(detail, { force: true, preserveDirtyPlan: false });
      setSelectedStepId("");
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
      const selectedRepoId = String(projectDetail?.project?.repo_id || "").trim();
      const selectedProjectDir = String(projectDetail?.project?.repo_path || "").trim();
      if (
        selectedRepoId
        && (
          (targetProject.repo_id && selectedRepoId === targetProject.repo_id)
          || (targetProject.project_dir && selectedProjectDir === targetProject.project_dir)
        )
      ) {
        mergeSelectedProjectSupplement(selectedRepoId, { reports: { latest_failure: {} } });
      }
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
          const jobSnapshot = await syncRunningJobSnapshot(blockingJobRef.current?.id || "");
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

  async function runManualDebugger() {
    if (!projectForm.project_dir.trim()) {
      setMessage(messagePayload("error", translate(language, "message.openProjectFirst")));
      return;
    }
    const latestFailure = projectDetail?.reports?.latest_failure || {};
    if (!latestFailure.summary && !latestFailure.report_markdown_file && !latestFailure.report_json_file) {
      setMessage(
        messagePayload(
          "error",
          language === "ko"
            ? "최근 실패 로그가 없어 수동 디버거를 실행할 수 없습니다."
            : "Manual debugger requires a recent failure log.",
        ),
      );
      return;
    }
    const job = await startJob(BRIDGE_COMMANDS.RUN_MANUAL_DEBUGGER, buildProjectPayload(projectForm, planDraft));
    if (job) {
      setPlanDirty(false);
    }
  }

  async function runManualMerger() {
    if (!projectForm.project_dir.trim()) {
      setMessage(messagePayload("error", translate(language, "message.openProjectFirst")));
      return;
    }
    const job = await startJob(BRIDGE_COMMANDS.RUN_MANUAL_MERGER, buildProjectPayload(projectForm, planDraft));
    if (job) {
      setPlanDirty(false);
    }
  }

  async function loadChatSession(sessionId = "") {
    if (!selectedProjectId || !workspaceRoot) {
      return null;
    }
    try {
      const supplement = await fetchProjectChat(bridgeRequest, selectedProjectId, workspaceRoot, {
        sessionId,
      });
      mergeSelectedProjectSupplement(selectedProjectId, supplement);
      const activeSessionId = String(supplement?.chat?.active_session_id || "").trim();
      setSelectedChatSessionId(activeSessionId);
      setChatDraftSession(Boolean(supplement?.chat?.draft_session));
      return supplement;
    } catch (error) {
      setMessage(messagePayload("error", String(error)));
      return null;
    }
  }

  function startNewChatSession() {
    setSelectedChatSessionId("");
    setChatDraftSession(true);
    if (!selectedProjectId) {
      return;
    }
    mergeSelectedProjectSupplement(selectedProjectId, {
      chat: {
        ...(projectDetail?.chat || {}),
        active_session_id: "",
        active_session: null,
        messages: [],
        summary_text: "",
        summary_file: "",
        transcript_file: "",
        draft_session: true,
      },
      loaded_sections: {
        chat: true,
      },
    });
  }

  async function sendChatMessage(text, mode = "conversation") {
    const messageText = String(text || "").trim();
    if (!projectForm.project_dir.trim()) {
      setMessage(messagePayload("error", translate(language, "message.openProjectFirst")));
      return null;
    }
    if (!messageText) {
      return null;
    }
    if (["queued", "running"].includes(String(projectJob?.status || "").trim().toLowerCase())) {
      setMessage(
        messagePayload(
          "error",
          language === "ko"
            ? "현재 프로젝트에서 다른 백그라운드 작업이 진행 중이라 채팅 요청을 시작할 수 없습니다."
            : "Another background task is already active for this project.",
        ),
      );
      return null;
    }
    const activeSessionId = String(
      chatDraftSession
        ? ""
        : (selectedChatSessionId || projectDetail?.chat?.active_session_id || ""),
    ).trim();
    const basePayload = buildProjectPayload(projectForm, planDraft);
    return startJob(
      BRIDGE_COMMANDS.SEND_CHAT_MESSAGE,
      {
        ...basePayload,
        runtime: {
          ...(basePayload.runtime || {}),
          chat_model_provider: String(programSettings?.chat_model_provider || "").trim().toLowerCase(),
          chat_local_model_provider: String(programSettings?.chat_local_model_provider || "").trim().toLowerCase(),
          chat_model: String(programSettings?.chat_model || "").trim().toLowerCase(),
        },
        message: messageText,
        chat_mode: String(mode || "conversation").trim().toLowerCase() || "conversation",
        session_id: activeSessionId,
        create_new_session: chatDraftSession || !activeSessionId,
      },
    );
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
    const detail = await ensureWorkspaceShareLoaded({ force: true });
    const shareUrl = detail?.active_session?.share_url || detail?.project_active_session?.share_url || "";
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
      const normalizedShareDetail = normalizeWorkspaceShareDetail(
        shareResult?.share || null,
        shareResult?.created_share_session || null,
      );
      setWorkspaceShareDetail(normalizedShareDetail);
      setShareSettings(shareSettingsFromDetail(shareResult));
      const refreshedShareDetail = await ensureWorkspaceShareLoaded({ force: true }).catch(() => normalizedShareDetail);
      if (refreshedShareDetail) {
        setWorkspaceShareDetail(refreshedShareDetail);
      }
      const shareUrl =
        shareResult?.created_share_session?.share_url
        || refreshedShareDetail?.active_session?.share_url
        || refreshedShareDetail?.project_active_session?.share_url
        || normalizedShareDetail?.active_session?.share_url
        || "";
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
    const detail = await ensureWorkspaceShareLoaded({ force: true });
    const sessionId = detail?.active_session?.session_id || detail?.project_active_session?.session_id || "";
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
      setWorkspaceShareDetail(normalizeWorkspaceShareDetail(shareResult?.share || null));
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
      applyProjectDetail(detail, { force: true, preserveDirtyPlan: true, preserveSelectedStep: true });
      setMessage(messagePayload("success", translate(language, "message.checkpointApproved")));
    });
  }

  function normalizeOperatorList(value) {
    if (Array.isArray(value)) {
      return value
        .map((item) => String(item || "").trim())
        .filter(Boolean);
    }
    return String(value || "")
      .replace(/\r/g, "\n")
      .split(/[\n,]/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  async function resolveCommonRequirement(requestId, note = "") {
    if (!selectedProjectId) {
      setMessage(messagePayload("error", translate(language, "message.openProjectFirst")));
      return false;
    }
    const detail = await withPending("resolve-common-requirement", async () =>
      bridgeRequest(
        BRIDGE_COMMANDS.RESOLVE_COMMON_REQUIREMENT,
        {
          repo_id: selectedProjectId,
          request_id: String(requestId || "").trim(),
          note: String(note || "").trim(),
        },
        workspaceRoot || null,
      )
    );
    if (!detail) {
      return false;
    }
    lastAppliedDetailSignatureRef.current = "";
    applyProjectDetail(detail, { force: true, preserveDirtyPlan: true });
    setMessage(messagePayload("success", "Marked the CRR as resolved."));
    return true;
  }

  async function reopenCommonRequirement(requestId, note = "") {
    if (!selectedProjectId) {
      setMessage(messagePayload("error", translate(language, "message.openProjectFirst")));
      return false;
    }
    const detail = await withPending("reopen-common-requirement", async () =>
      bridgeRequest(
        BRIDGE_COMMANDS.REOPEN_COMMON_REQUIREMENT,
        {
          repo_id: selectedProjectId,
          request_id: String(requestId || "").trim(),
          note: String(note || "").trim(),
        },
        workspaceRoot || null,
      )
    );
    if (!detail) {
      return false;
    }
    lastAppliedDetailSignatureRef.current = "";
    applyProjectDetail(detail, { force: true, preserveDirtyPlan: true });
    setMessage(messagePayload("success", "Reopened the CRR."));
    return true;
  }

  async function recordSpineCheckpoint(options = {}) {
    if (!selectedProjectId) {
      setMessage(messagePayload("error", translate(language, "message.openProjectFirst")));
      return false;
    }
    const selectedStep = (planDraft?.steps || []).find((step) => step?.step_id === selectedStepId) || null;
    const payload = {
      repo_id: selectedProjectId,
      version: String(options?.version || "").trim(),
      notes: String(options?.notes || "").trim(),
      shared_contracts: normalizeOperatorList(
        options?.sharedContracts ?? selectedStep?.shared_contracts ?? [],
      ),
      touched_files: normalizeOperatorList(
        options?.touchedFiles
          ?? selectedStep?.primary_scope_paths
          ?? selectedStep?.owned_paths
          ?? [],
      ),
      step_id: String(options?.stepId || selectedStep?.step_id || "").trim(),
      lineage_id: String(options?.lineageId || selectedStep?.metadata?.lineage_id || "").trim(),
      commit_hash: String(options?.commitHash || "").trim(),
    };
    const detail = await withPending("record-spine-checkpoint", async () =>
      bridgeRequest(BRIDGE_COMMANDS.RECORD_SPINE_CHECKPOINT, payload, workspaceRoot || null)
    );
    if (!detail) {
      return false;
    }
    lastAppliedDetailSignatureRef.current = "";
    applyProjectDetail(detail, { force: true, preserveDirtyPlan: true });
    setMessage(messagePayload("success", "Recorded the spine checkpoint."));
    return true;
  }

  async function updateCommonRequirement(requestId, updates = {}) {
    if (!selectedProjectId) {
      setMessage(messagePayload("error", translate(language, "message.openProjectFirst")));
      return false;
    }
    const detail = await withPending("update-common-requirement", async () =>
      bridgeRequest(
        BRIDGE_COMMANDS.UPDATE_COMMON_REQUIREMENT,
        {
          repo_id: selectedProjectId,
          request_id: String(requestId || "").trim(),
          title: String(updates?.title || "").trim(),
          reason: String(updates?.reason || "").trim(),
          notes: String(updates?.notes || "").trim(),
          affected_paths: normalizeOperatorList(updates?.affectedPaths ?? []),
          shared_contracts: normalizeOperatorList(updates?.sharedContracts ?? []),
          promotion_class: String(updates?.promotionClass || "").trim(),
          step_id: String(updates?.stepId || "").trim(),
          lineage_id: String(updates?.lineageId || "").trim(),
          spine_version: String(updates?.spineVersion || "").trim(),
        },
        workspaceRoot || null,
      )
    );
    if (!detail) {
      return false;
    }
    lastAppliedDetailSignatureRef.current = "";
    applyProjectDetail(detail, { force: true, preserveDirtyPlan: true });
    setMessage(messagePayload("success", "Updated the CRR."));
    return true;
  }

  async function deleteCommonRequirement(requestId, note = "") {
    if (!selectedProjectId) {
      setMessage(messagePayload("error", translate(language, "message.openProjectFirst")));
      return false;
    }
    const detail = await withPending("delete-common-requirement", async () =>
      bridgeRequest(
        BRIDGE_COMMANDS.DELETE_COMMON_REQUIREMENT,
        {
          repo_id: selectedProjectId,
          request_id: String(requestId || "").trim(),
          note: String(note || "").trim(),
        },
        workspaceRoot || null,
      )
    );
    if (!detail) {
      return false;
    }
    lastAppliedDetailSignatureRef.current = "";
    applyProjectDetail(detail, { force: true, preserveDirtyPlan: true });
    setMessage(messagePayload("success", "Removed the CRR and recorded it in the audit log."));
    return true;
  }

  async function updateSpineCheckpoint(checkpointId, updates = {}) {
    if (!selectedProjectId) {
      setMessage(messagePayload("error", translate(language, "message.openProjectFirst")));
      return false;
    }
    const detail = await withPending("update-spine-checkpoint", async () =>
      bridgeRequest(
        BRIDGE_COMMANDS.UPDATE_SPINE_CHECKPOINT,
        {
          repo_id: selectedProjectId,
          checkpoint_id: String(checkpointId || "").trim(),
          version: String(updates?.version || "").trim(),
          notes: String(updates?.notes || "").trim(),
          shared_contracts: normalizeOperatorList(updates?.sharedContracts ?? []),
          touched_files: normalizeOperatorList(updates?.touchedFiles ?? []),
          step_id: String(updates?.stepId || "").trim(),
          lineage_id: String(updates?.lineageId || "").trim(),
          commit_hash: String(updates?.commitHash || "").trim(),
        },
        workspaceRoot || null,
      )
    );
    if (!detail) {
      return false;
    }
    lastAppliedDetailSignatureRef.current = "";
    applyProjectDetail(detail, { force: true, preserveDirtyPlan: true });
    setMessage(messagePayload("success", "Updated the spine checkpoint."));
    return true;
  }

  async function deleteSpineCheckpoint(checkpointId, note = "") {
    if (!selectedProjectId) {
      setMessage(messagePayload("error", translate(language, "message.openProjectFirst")));
      return false;
    }
    const detail = await withPending("delete-spine-checkpoint", async () =>
      bridgeRequest(
        BRIDGE_COMMANDS.DELETE_SPINE_CHECKPOINT,
        {
          repo_id: selectedProjectId,
          checkpoint_id: String(checkpointId || "").trim(),
          note: String(note || "").trim(),
        },
        workspaceRoot || null,
      )
    );
    if (!detail) {
      return false;
    }
    lastAppliedDetailSignatureRef.current = "";
    applyProjectDetail(detail, { force: true, preserveDirtyPlan: true });
    setMessage(messagePayload("success", "Removed the spine checkpoint and recorded it in the audit log."));
    return true;
  }

  async function reloadProject() {
    if (!selectedProjectId) {
      setMessage(messagePayload("error", translate(language, "message.noProjectOpen")));
      return;
    }
    await loadProject(selectedProjectId, {
      refreshCodexStatus: shouldForceCodexRefreshForManualRefresh(centerTab),
    });
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
    rightCollapsed,
    rightWidth,
    sidebarWidth,
    projectFilter,
    workspaceFilter,
    selectedChatSessionId,
    chatDraftSession,
    planDirty,
    setMessage,
    setProjectForm: updateProjectForm,
    setPlanDraft,
    setSelectedStepId,
    setSelectedHistoryId,
    setProgramSettings: updateProgramSettings,
    setChatModelSelection,
    setCenterTab,
    setBottomTab,
    setSidebarTab,
    setBottomCollapsed,
    setBottomHeight,
    setRightCollapsed,
    setRightWidth,
    setSidebarWidth,
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
    runManualDebugger,
    runManualMerger,
    loadChatSession,
    startNewChatSession,
    sendChatMessage,
    requestStop,
    cancelQueuedReservation,
    generateShareLink,
    revokeShareLink,
    copyShareLink,
    approveCheckpoint,
    resolveCommonRequirement,
    reopenCommonRequirement,
    recordSpineCheckpoint,
    updateCommonRequirement,
    deleteCommonRequirement,
    updateSpineCheckpoint,
    deleteSpineCheckpoint,
    reloadProject,
    saveStepLocal,
    addStep,
    deleteStep,
    moveStep,
    setSelectedProjectId,
    openRepoInFolder: () => {
      const path = projectDetail?.project?.repo_path || projectForm?.project_dir || "";
      if (path) openInSystem(path).catch(() => {});
    },
    openRepoInVsCode: () => {
      const path = projectDetail?.project?.repo_path || projectForm?.project_dir || "";
      if (path) openInVsCode(path).catch(() => {});
    },
    openRepoOnGithub: () => {
      const url = projectDetail?.github?.origin_url || projectDetail?.github?.repo_url || projectForm?.origin_url || "";
      if (!url) {
        return;
      }
      const normalizedUrl = url.startsWith("http")
        ? url.replace(/\.git$/i, "")
        : `https://github.com/${url.replace(/^git@github\.com:/i, "").replace(/\.git$/i, "")}`;
      openInSystem(normalizedUrl).catch(() => {});
    },
    smartShareLink: async () => {
      const currentShareDetail = await ensureWorkspaceShareLoaded({ force: true }).catch(() => workspaceShareDetail);
      const existingUrl =
        currentShareDetail?.active_session?.share_url
        || currentShareDetail?.project_active_session?.share_url
        || "";
      if (existingUrl) {
        await copyShareLink();
      } else {
        await generateShareLink();
      }
    },
  };
}
