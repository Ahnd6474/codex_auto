import { defaultShareSettings, emptyPlanDraft, shareSettingsFromDetail } from "../controllerHelpers.js";
import {
  blankProjectForm,
  cloneValue,
  detailApplySignature,
  mergeProjectDetailCodexStatus,
  projectFormFromDetail,
  sanitizeProjectDetailForJobState,
  sanitizeProjectListForJobState,
  shouldKeepUnsavedPlan,
  workspaceStatsFromProjects,
} from "../utils.js";

const PROJECT_DETAIL_SECTION_KEYS = ["reports", "workspace", "checkpoints", "history", "config", "chat"];

function hasOwnValue(value, key) {
  return Boolean(value) && Object.prototype.hasOwnProperty.call(value, key);
}

function sameProjectDetail(left, right) {
  const leftRepoId = String(left?.project?.repo_id || "").trim();
  const rightRepoId = String(right?.project?.repo_id || "").trim();
  return Boolean(leftRepoId) && leftRepoId === rightRepoId;
}

function projectEventMatchesDetail(detail = null, project = null) {
  const detailRepoId = String(detail?.project?.repo_id || "").trim();
  const eventRepoId = String(project?.repo_id || "").trim();
  if (detailRepoId && eventRepoId) {
    return detailRepoId === eventRepoId;
  }
  const detailProjectDir = String(detail?.project?.repo_path || "").trim();
  const eventProjectDir = String(project?.project_dir || "").trim();
  return Boolean(detailProjectDir) && Boolean(eventProjectDir) && detailProjectDir === eventProjectDir;
}

function workspaceTreeNodesEqual(leftNodes = [], rightNodes = []) {
  if (leftNodes === rightNodes) {
    return true;
  }
  if (!Array.isArray(leftNodes) || !Array.isArray(rightNodes) || leftNodes.length !== rightNodes.length) {
    return false;
  }
  return leftNodes.every((leftNode, index) => {
    const rightNode = rightNodes[index];
    if (!leftNode || !rightNode) {
      return leftNode === rightNode;
    }
    return (
      leftNode.label === rightNode.label
      && leftNode.path === rightNode.path
      && leftNode.kind === rightNode.kind
      && workspaceTreeNodesEqual(leftNode.children || [], rightNode.children || [])
    );
  });
}

function resolveWorkspaceTree(nextWorkspaceTree, previousWorkspaceTree = []) {
  const previousTree = Array.isArray(previousWorkspaceTree) ? previousWorkspaceTree : [];
  const incomingTree = Array.isArray(nextWorkspaceTree) ? nextWorkspaceTree : [];
  if (!incomingTree.length) {
    return previousTree;
  }
  if (previousTree.length && workspaceTreeNodesEqual(incomingTree, previousTree)) {
    return previousTree;
  }
  return cloneValue(incomingTree);
}

function projectListingKey(project = {}) {
  return String(project?.repo_id || project?.archive_id || project?.repo_path || "").trim();
}

function sameProjectStats(leftStats = {}, rightStats = {}) {
  const left = leftStats && typeof leftStats === "object" ? leftStats : {};
  const right = rightStats && typeof rightStats === "object" ? rightStats : {};
  const keys = new Set([...Object.keys(left), ...Object.keys(right)]);
  for (const key of keys) {
    if (left[key] !== right[key]) {
      return false;
    }
  }
  return true;
}

function sameProjectListItem(left, right) {
  if (left === right) {
    return true;
  }
  if (!left || !right) {
    return false;
  }
  return (
    left.repo_id === right.repo_id
    && left.archive_id === right.archive_id
    && left.slug === right.slug
    && left.display_name === right.display_name
    && left.repo_path === right.repo_path
    && left.origin_url === right.origin_url
    && left.branch === right.branch
    && left.status === right.status
    && left.detail === right.detail
    && left.created_at === right.created_at
    && left.last_run_at === right.last_run_at
    && left.summary === right.summary
    && left.progress === right.progress
    && left.closeout_status === right.closeout_status
    && sameProjectStats(left.stats, right.stats)
  );
}

function reuseProjectListingItems(previousProjects = [], nextProjects = []) {
  const previousByKey = new Map(
    (Array.isArray(previousProjects) ? previousProjects : [])
      .map((project) => [projectListingKey(project), project])
      .filter(([key]) => Boolean(key)),
  );
  const reusedProjects = (Array.isArray(nextProjects) ? nextProjects : []).map((project) => {
    const key = projectListingKey(project);
    const previousProject = key ? previousByKey.get(key) : null;
    return previousProject && sameProjectListItem(previousProject, project) ? previousProject : project;
  });
  if (
    reusedProjects.length === (Array.isArray(previousProjects) ? previousProjects.length : 0)
    && reusedProjects.every((project, index) => project === previousProjects[index])
  ) {
    return previousProjects;
  }
  return reusedProjects;
}

function mergeLoadedSections(currentSections = null, fallbackSections = null, detailLevel = "") {
  const nextSections = {
    ...(fallbackSections && typeof fallbackSections === "object" ? fallbackSections : {}),
    ...(currentSections && typeof currentSections === "object" ? currentSections : {}),
  };
  if (String(detailLevel || "").trim().toLowerCase() === "full") {
    PROJECT_DETAIL_SECTION_KEYS.forEach((key) => {
      nextSections[key] = true;
    });
  }
  return nextSections;
}

function preserveProjectIdentityForm(currentForm = null, nextForm = null) {
  const current = currentForm && typeof currentForm === "object" ? currentForm : {};
  const next = nextForm && typeof nextForm === "object" ? nextForm : {};
  if (String(next.project_dir || "").trim() || !String(current.project_dir || "").trim()) {
    return next;
  }
  return {
    ...next,
    project_dir: current.project_dir,
    display_name: next.display_name || current.display_name || "",
    branch: next.branch || current.branch || "main",
    origin_url: next.origin_url || current.origin_url || "",
    github_mode: next.github_mode || current.github_mode || "",
  };
}

function mergeReportsSection(primary = null, fallback = null, preserveSparse = false) {
  if (!primary && !fallback) {
    return primary ?? fallback;
  }
  const primaryReports = primary && typeof primary === "object" ? primary : {};
  const fallbackReports = fallback && typeof fallback === "object" ? fallback : {};
  const nextReports = {
    ...fallbackReports,
    ...primaryReports,
  };
  const textKeys = [
    "closeout_report_text",
    "ml_experiment_report_text",
    "attempt_history_text",
    "word_report_path",
    "ml_results_svg_path",
  ];
  textKeys.forEach((key) => {
    if (!hasOwnValue(primaryReports, key)) {
      nextReports[key] = fallbackReports?.[key] || "";
      return;
    }
    const primaryText = String(primaryReports?.[key] || "");
    const fallbackText = String(fallbackReports?.[key] || "");
    nextReports[key] = preserveSparse && !primaryText.trim() && fallbackText.trim() ? fallbackText : primaryText;
  });
  nextReports.word_report_enabled =
    primaryReports?.word_report_enabled ?? fallbackReports?.word_report_enabled ?? false;
  if (!hasOwnValue(primaryReports, "latest_failure")) {
    nextReports.latest_failure = fallbackReports?.latest_failure || {};
  } else {
    const primaryFailure = primaryReports?.latest_failure;
    nextReports.latest_failure = cloneValue(primaryFailure || {});
  }
  return nextReports;
}

function mergeCheckpointsSection(primary = null, fallback = null, preserveSparse = false) {
  if (!primary && !fallback) {
    return primary ?? fallback;
  }
  const primaryCheckpoints = primary && typeof primary === "object" ? primary : {};
  const fallbackCheckpoints = fallback && typeof fallback === "object" ? fallback : {};
  const nextCheckpoints = {
    ...fallbackCheckpoints,
    ...primaryCheckpoints,
  };
  if (!hasOwnValue(primaryCheckpoints, "items")) {
    nextCheckpoints.items = fallbackCheckpoints?.items || [];
  } else {
    const primaryItems = Array.isArray(primaryCheckpoints?.items) ? primaryCheckpoints.items : [];
    const fallbackItems = Array.isArray(fallbackCheckpoints?.items) ? fallbackCheckpoints.items : [];
    nextCheckpoints.items =
      preserveSparse && primaryItems.length === 0 && fallbackItems.length > 0
        ? fallbackItems
        : cloneValue(primaryItems);
  }
  if (!hasOwnValue(primaryCheckpoints, "pending")) {
    nextCheckpoints.pending = fallbackCheckpoints?.pending ?? null;
  } else {
    const primaryPending = primaryCheckpoints?.pending ?? null;
    nextCheckpoints.pending =
      preserveSparse && primaryPending == null && fallbackCheckpoints?.pending != null
        ? fallbackCheckpoints.pending
        : cloneValue(primaryPending);
  }
  if (!hasOwnValue(primaryCheckpoints, "timeline_markdown")) {
    nextCheckpoints.timeline_markdown = String(fallbackCheckpoints?.timeline_markdown || "");
  } else {
    const primaryTimeline = String(primaryCheckpoints?.timeline_markdown || "");
    const fallbackTimeline = String(fallbackCheckpoints?.timeline_markdown || "");
    nextCheckpoints.timeline_markdown =
      preserveSparse && !primaryTimeline.trim() && fallbackTimeline.trim() ? fallbackTimeline : primaryTimeline;
  }
  return nextCheckpoints;
}

function mergeHistorySection(primary = null, fallback = null, preserveSparse = false) {
  if (!primary && !fallback) {
    return primary ?? fallback;
  }
  const primaryHistory = primary && typeof primary === "object" ? primary : {};
  const fallbackHistory = fallback && typeof fallback === "object" ? fallback : {};
  const nextHistory = {
    ...fallbackHistory,
    ...primaryHistory,
  };
  ["ui_events", "blocks", "passes", "test_runs"].forEach((key) => {
    if (!hasOwnValue(primaryHistory, key)) {
      nextHistory[key] = fallbackHistory?.[key] || [];
      return;
    }
    const primaryItems = Array.isArray(primaryHistory?.[key]) ? primaryHistory[key] : [];
    const fallbackItems = Array.isArray(fallbackHistory?.[key]) ? fallbackHistory[key] : [];
    nextHistory[key] =
      preserveSparse && primaryItems.length === 0 && fallbackItems.length > 0
        ? fallbackItems
        : cloneValue(primaryItems);
  });
  ["flow_svg_path", "flow_svg_text"].forEach((key) => {
    if (!hasOwnValue(primaryHistory, key)) {
      nextHistory[key] = String(fallbackHistory?.[key] || "");
      return;
    }
    const primaryText = String(primaryHistory?.[key] || "");
    const fallbackText = String(fallbackHistory?.[key] || "");
    nextHistory[key] = preserveSparse && !primaryText.trim() && fallbackText.trim() ? fallbackText : primaryText;
  });
  return nextHistory;
}

function mergeConfigSection(primary = null, fallback = null, preserveSparse = false) {
  if (!primary && !fallback) {
    return primary ?? fallback;
  }
  const primaryConfig = primary && typeof primary === "object" ? primary : {};
  const fallbackConfig = fallback && typeof fallback === "object" ? fallback : {};
  const primaryHasEntries = Object.keys(primaryConfig).length > 0;
  if (preserveSparse && !primaryHasEntries && Object.keys(fallbackConfig).length > 0) {
    return fallbackConfig;
  }
  return {
    ...fallbackConfig,
    ...primaryConfig,
  };
}

function mergeChatSection(primary = null, fallback = null, preserveSparse = false) {
  if (!primary && !fallback) {
    return primary ?? fallback;
  }
  const primaryChat = primary && typeof primary === "object" ? primary : {};
  const fallbackChat = fallback && typeof fallback === "object" ? fallback : {};
  const nextChat = {
    ...fallbackChat,
    ...primaryChat,
  };
  ["sessions", "messages"].forEach((key) => {
    if (!hasOwnValue(primaryChat, key)) {
      nextChat[key] = fallbackChat?.[key] || [];
      return;
    }
    const primaryItems = Array.isArray(primaryChat?.[key]) ? primaryChat[key] : [];
    const fallbackItems = Array.isArray(fallbackChat?.[key]) ? fallbackChat[key] : [];
    nextChat[key] =
      preserveSparse && primaryItems.length === 0 && fallbackItems.length > 0
        ? fallbackItems
        : cloneValue(primaryItems);
  });
  ["active_session_id", "summary_text", "summary_file", "transcript_file"].forEach((key) => {
    if (!hasOwnValue(primaryChat, key)) {
      nextChat[key] = String(fallbackChat?.[key] || "");
      return;
    }
    const primaryText = String(primaryChat?.[key] || "");
    const fallbackText = String(fallbackChat?.[key] || "");
    nextChat[key] = preserveSparse && !primaryText.trim() && fallbackText.trim() ? fallbackText : primaryText;
  });
  if (!hasOwnValue(primaryChat, "active_session")) {
    nextChat.active_session = fallbackChat?.active_session ?? null;
  } else {
    nextChat.active_session = cloneValue(primaryChat?.active_session ?? null);
  }
  nextChat.draft_session = primaryChat?.draft_session ?? fallbackChat?.draft_session ?? false;
  return nextChat;
}

export function preserveProjectDetailSupplement(detail, previousDetail = null) {
  if (!detail) {
    return detail;
  }
  const sameProject = sameProjectDetail(detail, previousDetail);
  const loadedSections = mergeLoadedSections(
    detail?.loaded_sections,
    sameProject ? previousDetail?.loaded_sections : null,
    detail?.detail_level,
  );
  const resolvedWorkspaceTree = loadedSections.workspace
    ? resolveWorkspaceTree(detail?.workspace_tree, sameProject ? previousDetail?.workspace_tree : [])
    : detail?.workspace_tree;
  if (!sameProject || String(detail?.detail_level || "").trim().toLowerCase() === "full") {
    return {
      ...detail,
      workspace_tree: resolvedWorkspaceTree,
      loaded_sections: loadedSections,
    };
  }
  return {
    ...detail,
    workspace_tree: resolvedWorkspaceTree,
    reports: loadedSections.reports
      ? mergeReportsSection(detail?.reports, previousDetail?.reports, true)
      : detail?.reports,
    checkpoints: loadedSections.checkpoints
      ? mergeCheckpointsSection(detail?.checkpoints, previousDetail?.checkpoints, true)
      : detail?.checkpoints,
    history: loadedSections.history
      ? mergeHistorySection(detail?.history, previousDetail?.history, true)
      : detail?.history,
    config: loadedSections.config
      ? mergeConfigSection(detail?.config, previousDetail?.config, true)
      : detail?.config,
    chat: loadedSections.chat
      ? mergeChatSection(detail?.chat, previousDetail?.chat, true)
      : detail?.chat,
    loaded_sections: loadedSections,
  };
}

export function mergeProjectDetailSupplement(detail, supplement = {}) {
  if (!detail) {
    return detail;
  }
  return {
    ...detail,
    ...(hasOwnValue(supplement, "workspace_tree")
      ? { workspace_tree: resolveWorkspaceTree(supplement.workspace_tree, detail?.workspace_tree) }
      : {}),
    ...(hasOwnValue(supplement, "reports")
      ? { reports: mergeReportsSection(supplement.reports, detail?.reports, false) }
      : {}),
    ...(hasOwnValue(supplement, "checkpoints")
      ? { checkpoints: mergeCheckpointsSection(supplement.checkpoints, detail?.checkpoints, false) }
      : {}),
    ...(hasOwnValue(supplement, "history")
      ? { history: mergeHistorySection(supplement.history, detail?.history, false) }
      : {}),
    ...(hasOwnValue(supplement, "config")
      ? { config: mergeConfigSection(supplement.config, detail?.config, false) }
      : {}),
    ...(hasOwnValue(supplement, "chat")
      ? { chat: mergeChatSection(supplement.chat, detail?.chat, false) }
      : {}),
    loaded_sections: mergeLoadedSections(
      supplement?.loaded_sections,
      detail?.loaded_sections,
      detail?.detail_level,
    ),
  };
}

export function applyListingState({ listing, runningJob = null, setProjects, setWorkspaceStats }) {
  const nextProjects = sanitizeProjectListForJobState(
    reuseProjectListingItems([], listing?.projects || []),
    runningJob,
  );
  setProjects(nextProjects);
  setWorkspaceStats(workspaceStatsFromProjects(nextProjects));
  return nextProjects;
}

function projectListItemFromDetail(detail, fallbackProject = null) {
  const project = detail?.project || {};
  const branch = project.branch || fallbackProject?.branch || "";
  return {
    ...fallbackProject,
    repo_id: project.repo_id || fallbackProject?.repo_id || "",
    slug: project.slug || fallbackProject?.slug || "",
    display_name: project.display_name || project.slug || fallbackProject?.display_name || "",
    repo_path: project.repo_path || fallbackProject?.repo_path || "",
    origin_url: project.origin_url || fallbackProject?.origin_url || "",
    branch,
    status: project.current_status || fallbackProject?.status || "",
    detail: project.origin_url || `Branch ${branch}`,
    created_at: project.created_at || fallbackProject?.created_at || "",
    last_run_at: project.last_run_at || fallbackProject?.last_run_at || "",
    summary: detail?.summary || fallbackProject?.summary || "",
    progress: detail?.progress || fallbackProject?.progress || "",
    stats: cloneValue(detail?.stats || fallbackProject?.stats || {}),
    closeout_status: detail?.plan?.closeout_status || fallbackProject?.closeout_status || "",
  };
}

export function applyProjectDetailListingState({
  projects,
  detail,
  runningJob = null,
  setProjects,
  setWorkspaceStats,
}) {
  const repoId = String(detail?.project?.repo_id || "").trim();
  if (!repoId) {
    return null;
  }
  let matched = false;
  const nextProjects = (projects || []).map((project) => {
    if (String(project?.repo_id || "").trim() !== repoId) {
      return project;
    }
    matched = true;
    return projectListItemFromDetail(detail, project);
  });
  const mergedProjects = matched ? nextProjects : [projectListItemFromDetail(detail), ...(projects || [])];
  const sanitizedProjects = sanitizeProjectListForJobState(
    reuseProjectListingItems(projects || [], mergedProjects),
    runningJob,
  );
  setProjects(sanitizedProjects);
  setWorkspaceStats(workspaceStatsFromProjects(sanitizedProjects));
  return sanitizedProjects;
}

export function applyProjectEventListingState({
  projects,
  project,
  runningJob = null,
  setProjects,
  setWorkspaceStats,
}) {
  const repoId = String(project?.repo_id || "").trim();
  const projectDir = String(project?.project_dir || "").trim();
  const status = String(project?.status || project?.project_status || "").trim();
  if (!repoId && !projectDir && !status) {
    return null;
  }

  let changed = false;
  const nextProjects = (projects || []).map((item) => {
    const sameRepoId = repoId && String(item?.repo_id || "").trim() === repoId;
    const sameProjectDir = projectDir && String(item?.repo_path || "").trim() === projectDir;
    if (!sameRepoId && !sameProjectDir) {
      return item;
    }
    changed = true;
    return {
      ...item,
      repo_id: repoId || item?.repo_id || "",
      repo_path: projectDir || item?.repo_path || "",
      status: status || item?.status || "",
      detail: item?.detail || (projectDir ? `Path ${projectDir}` : ""),
    };
  });

  if (!changed) {
    return null;
  }

  const sanitizedProjects = sanitizeProjectListForJobState(
    reuseProjectListingItems(projects || [], nextProjects),
    runningJob,
  );
  setProjects(sanitizedProjects);
  setWorkspaceStats(workspaceStatsFromProjects(sanitizedProjects));
  return sanitizedProjects;
}

export function applyProjectEventDetailState(detail, project) {
  if (!detail || !projectEventMatchesDetail(detail, project)) {
    return null;
  }
  const nextStatus = String(project?.status || project?.project_status || "").trim();
  const nextRepoPath = String(project?.project_dir || "").trim();
  const currentStatus = String(detail?.project?.current_status || "").trim();
  const currentRepoPath = String(detail?.project?.repo_path || "").trim();
  if (!nextStatus && !nextRepoPath) {
    return null;
  }
  if (nextStatus === currentStatus && (!nextRepoPath || nextRepoPath === currentRepoPath)) {
    return detail;
  }

  const nextProject = {
    ...(detail?.project || {}),
    ...(nextStatus ? { current_status: nextStatus } : {}),
    ...(nextRepoPath ? { repo_path: nextRepoPath } : {}),
  };
  const nextSnapshotProject = detail?.snapshot?.project
    ? {
        ...detail.snapshot.project,
        ...(nextStatus ? { current_status: nextStatus } : {}),
        ...(nextRepoPath ? { repo_path: nextRepoPath } : {}),
      }
    : detail?.snapshot?.project;
  return {
    ...detail,
    project: nextProject,
    snapshot: detail?.snapshot
      ? {
          ...detail.snapshot,
          project: nextSnapshotProject,
        }
      : detail?.snapshot,
  };
}

export function applyActiveJobState({
  jobSnapshot,
  setActiveJobId,
  setActiveJob,
  activeJobRef,
}) {
  const nextActiveJob = jobSnapshot?.activeJob || null;
  const nextActiveJobId = jobSnapshot?.activeJobId || "";
  setActiveJobId(nextActiveJobId);
  setActiveJob(nextActiveJob);
  activeJobRef.current = nextActiveJob;
  return jobSnapshot?.runningJob || null;
}

export function applyProjectDetailState({
  detail,
  options = {},
  refs,
  state,
  setters,
}) {
  const preservedDetail = preserveProjectDetailSupplement(detail, state.projectDetail);
  const mergedDetail = mergeProjectDetailCodexStatus(preservedDetail, state.projectDetail?.codex_status, state.modelCatalog);
  const normalizedDetail = sanitizeProjectDetailForJobState(mergedDetail, options.runningJob ?? state.activeJob);
  const applySignature = detailApplySignature(normalizedDetail, options.runningJob ?? state.activeJob);
  if (
    !options.force &&
    applySignature &&
    refs.lastAppliedDetailSignatureRef.current === applySignature &&
    normalizedDetail?.project?.repo_id === state.projectDetail?.project?.repo_id
  ) {
    setters.setLoadingProjectId("");
    return null;
  }
  const preserveDirtyPlan = shouldKeepUnsavedPlan(
    state.projectDetail?.project?.repo_id,
    normalizedDetail?.project?.repo_id,
    options.preserveDirtyPlan ?? state.planDirty,
  );
  const sameProject = sameProjectDetail(normalizedDetail, state.projectDetail);
  refs.lastAppliedDetailSignatureRef.current = applySignature;
  setters.transition(() => {
    setters.setProjectDetail(normalizedDetail);
    setters.setModelCatalog(normalizedDetail?.codex_status?.model_catalog || state.modelCatalog);
    setters.setShareSettings(shareSettingsFromDetail(normalizedDetail));
    setters.setLoadingProjectId("");
    setters.setProjectForm((current) => {
      if (current.project_dir && preserveDirtyPlan) {
        return current;
      }
      return preserveProjectIdentityForm(
        current,
        projectFormFromDetail(normalizedDetail, state.defaultRuntime),
      );
    });
    if (!preserveDirtyPlan) {
      setters.setPlanDraft(cloneValue(normalizedDetail.plan));
      setters.setSelectedStepId((current) => {
        const currentStepId = String(current || "").trim();
        const currentStep = (normalizedDetail?.plan?.steps || []).find((step) => step?.step_id === currentStepId);
        if (currentStep && currentStep.status !== "completed") {
          return currentStepId;
        }
        return "";
      });
      setters.setPlanDirty(false);
    }
  });
  return normalizedDetail;
}

export function clearSelectedProjectState({
  defaultRuntime,
  refs,
  setters,
}) {
  refs.lastAppliedDetailSignatureRef.current = "";
  setters.setProjectDetail(null);
  setters.setSelectedProjectId("");
  setters.setSelectedStepId("");
  setters.setPlanDirty(false);
  setters.setLoadingProjectId("");
  setters.setProjectForm(blankProjectForm(defaultRuntime));
  setters.setPlanDraft(emptyPlanDraft());
  setters.setShareSettings(defaultShareSettings());
}
