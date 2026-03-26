import { listBridgeJobs } from "../api";
import { BRIDGE_COMMANDS } from "../bridgeProtocol";
import { loadProjectDetail } from "./projectDetails";

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

export async function syncRunningJobSnapshot(preferredJobId = "") {
  const jobs = await listBridgeJobs();
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
  const bootstrap = await loadBootstrap(bridgeRequest);
  const listing = await loadProjectListing(bridgeRequest, bootstrap.workspace_root);
  const jobSnapshot = await syncRunningJobSnapshot(preferredJobId);
  return {
    bootstrap,
    listing,
    jobSnapshot,
  };
}

