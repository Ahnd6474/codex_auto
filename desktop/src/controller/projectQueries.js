import { listBridgeJobs } from "../api.js";
import { BRIDGE_COMMANDS } from "../bridgeProtocol.js";
import { loadProjectDetail } from "./projectDetails.js";

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

export async function refreshVisibleProjectState(bridgeRequest, workspaceRoot, repoId, options = {}) {
  const listingPromise = loadProjectListing(bridgeRequest, workspaceRoot);
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
  return {
    jobs,
    runningJob,
    activeJob: runningJob || (preferredJob && preferredJob.status !== "running" ? preferredJob : null),
    activeJobId: runningJob?.id || "",
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
