import { listBridgeJobs } from "../api.js";
import { BRIDGE_COMMANDS } from "../bridgeProtocol.js";
import { loadHistoryDetail, loadProjectDetail } from "./projectDetails.js";

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

export async function fetchProjectDetailBySelector(bridgeRequest, selector, workspaceRoot, options = {}) {
  return loadProjectDetail(bridgeRequest, selector, workspaceRoot || null, {
    refreshCodexStatus: options.refreshCodexStatus ?? false,
    includeFull: (options.detailLevel ?? "full") === "full",
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

export async function refreshVisibleProjectState(bridgeRequest, workspaceRoot, repoId, options = {}) {
  const refreshListing = options.refreshListing ?? true;
  const listingPromise = refreshListing ? loadProjectListing(bridgeRequest, workspaceRoot) : Promise.resolve(null);
  if (!repoId) {
    return {
      listing: await listingPromise,
      detail: null,
    };
  }

  const detailPromise = fetchProjectDetail(bridgeRequest, repoId, workspaceRoot, options);
  const [listing, detail] = await Promise.all([listingPromise, detailPromise]);
  return {
    listing,
    detail,
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
