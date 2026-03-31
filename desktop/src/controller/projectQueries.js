import { listBridgeJobs } from "../api.js";
import { BRIDGE_COMMANDS } from "../bridgeProtocol.js";
import {
  loadProjectChat,
  loadHistoryDetail,
  loadProjectCheckpoints,
  loadProjectDetail,
  loadProjectHistory,
  loadProjectReports,
  loadProjectWorkspace,
} from "./projectDetails.js";

function listBridgeJobsRequest() {
  if (typeof globalThis.__JAKAL_FLOW_TEST_LIST_BRIDGE_JOBS__ === "function") {
    return globalThis.__JAKAL_FLOW_TEST_LIST_BRIDGE_JOBS__();
  }
  return listBridgeJobs();
}

export async function loadBootstrap(bridgeRequest) {
  return bridgeRequest(BRIDGE_COMMANDS.BOOTSTRAP);
}

export async function loadProjectListing(bridgeRequest, workspaceRoot) {
  return bridgeRequest(BRIDGE_COMMANDS.LIST_PROJECTS, null, workspaceRoot || null);
}

export async function loadWorkspaceShareDetail(bridgeRequest, workspaceRoot) {
  return bridgeRequest(BRIDGE_COMMANDS.LOAD_WORKSPACE_SHARE, {}, workspaceRoot || null);
}

export async function fetchProjectDetailBySelector(bridgeRequest, selector, workspaceRoot, options = {}) {
  return loadProjectDetail(bridgeRequest, selector, workspaceRoot || null, {
    refreshCodexStatus: options.refreshCodexStatus ?? false,
    includeFull: (options.detailLevel ?? "full") === "full",
    bypassDetailCache: options.bypassDetailCache ?? false,
  });
}

export async function fetchProjectDetail(bridgeRequest, repoId, workspaceRoot, options = {}) {
  return fetchProjectDetailBySelector(bridgeRequest, { repoId }, workspaceRoot, options);
}

export async function fetchHistoryDetail(bridgeRequest, archiveId, workspaceRoot, options = {}) {
  return loadHistoryDetail(bridgeRequest, archiveId, workspaceRoot || null, {
    includeFull: (options.detailLevel ?? "full") === "full",
  });
}

export async function fetchProjectReportsBySelector(bridgeRequest, selector, workspaceRoot) {
  return loadProjectReports(bridgeRequest, selector, workspaceRoot || null);
}

export async function fetchProjectReports(bridgeRequest, repoId, workspaceRoot) {
  return fetchProjectReportsBySelector(bridgeRequest, { repoId }, workspaceRoot);
}

export async function fetchProjectWorkspaceBySelector(bridgeRequest, selector, workspaceRoot) {
  return loadProjectWorkspace(bridgeRequest, selector, workspaceRoot || null);
}

export async function fetchProjectWorkspace(bridgeRequest, repoId, workspaceRoot) {
  return fetchProjectWorkspaceBySelector(bridgeRequest, { repoId }, workspaceRoot);
}

export async function fetchProjectCheckpointsBySelector(bridgeRequest, selector, workspaceRoot) {
  return loadProjectCheckpoints(bridgeRequest, selector, workspaceRoot || null);
}

export async function fetchProjectCheckpoints(bridgeRequest, repoId, workspaceRoot) {
  return fetchProjectCheckpointsBySelector(bridgeRequest, { repoId }, workspaceRoot);
}

export async function fetchProjectChatBySelector(bridgeRequest, selector, workspaceRoot, options = {}) {
  return loadProjectChat(bridgeRequest, selector, workspaceRoot || null, {
    sessionId: options.sessionId || "",
  });
}

export async function fetchProjectChat(bridgeRequest, repoId, workspaceRoot, options = {}) {
  return fetchProjectChatBySelector(bridgeRequest, { repoId }, workspaceRoot, options);
}

export async function fetchProjectHistoryBySelector(bridgeRequest, selector, workspaceRoot) {
  return loadProjectHistory(bridgeRequest, selector, workspaceRoot || null);
}

export async function fetchProjectHistory(bridgeRequest, repoId, workspaceRoot) {
  return fetchProjectHistoryBySelector(bridgeRequest, { repoId }, workspaceRoot);
}

export async function refreshVisibleProjectState(bridgeRequest, workspaceRoot, repoId, options = {}) {
  const result = await bridgeRequest(
    BRIDGE_COMMANDS.LOAD_VISIBLE_PROJECT_STATE,
    {
      ...(repoId ? { repo_id: repoId } : {}),
      refresh_codex_status: options.refreshCodexStatus ?? false,
      detail_level: options.detailLevel ?? "core",
      include_listing: options.refreshListing ?? true,
      bypass_detail_cache: options.bypassDetailCache ?? false,
      bypass_listing_cache: options.bypassListingCache ?? false,
    },
    workspaceRoot || null,
  );
  return {
    listing: result?.listing || null,
    detail: result?.detail || null,
  };
}

export async function syncRunningJobSnapshot(preferredJobId = "") {
  const jobs = await listBridgeJobsRequest();
  const preferredJob = preferredJobId ? jobs.find((job) => job.id === preferredJobId) || null : null;
  const runningJob = preferredJob?.status === "running" ? preferredJob : jobs.find((job) => job.status === "running") || null;
  const queuedJob = preferredJob?.status === "queued" ? preferredJob : jobs.find((job) => job.status === "queued") || null;
  return {
    jobs,
    runningJob,
    activeJob: runningJob || queuedJob || (preferredJob && !["running", "queued"].includes(preferredJob.status) ? preferredJob : null),
    activeJobId: (runningJob || queuedJob)?.id || "",
  };
}

export async function loadInitialDesktopState(bridgeRequest, preferredJobId = "") {
  const [bootstrap, jobSnapshot] = await Promise.all([
    loadBootstrap(bridgeRequest),
    syncRunningJobSnapshot(preferredJobId),
  ]);
  const listing = await loadProjectListing(bridgeRequest, bootstrap.workspace_root);
  return {
    bootstrap,
    listing,
    jobSnapshot,
  };
}
