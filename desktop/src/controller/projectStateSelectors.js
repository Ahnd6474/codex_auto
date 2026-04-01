import { buildProjectStateTree } from "./projectStateTree.js";

const EMPTY_IDENTITY = Object.freeze({
  repo_id: "",
  project_dir: "",
  current_status: "",
  last_run_at: "",
});

const EMPTY_EXECUTION = Object.freeze({
  identity: EMPTY_IDENTITY,
  jobSource: null,
  jobs: [],
  selectedJob: null,
  activeJob: null,
  chatJob: null,
  queuedJobs: [],
  stoppableJob: null,
});

const EMPTY_UI = Object.freeze({
  busy: false,
  canRequestStop: false,
  canCancelReservation: false,
});

const EMPTY_WORKSPACE_STATS = Object.freeze({
  project_count: 0,
  ready_like: 0,
  running: 0,
  failed: 0,
});

export function selectProjectStateTree(input = {}) {
  return buildProjectStateTree(input);
}

export function selectProjectIdentity(tree = null) {
  return tree?.identity || EMPTY_IDENTITY;
}

export function selectProjectExecution(tree = null) {
  return tree?.execution || EMPTY_EXECUTION;
}

export function selectProjectUi(tree = null) {
  return tree?.ui || EMPTY_UI;
}

export function selectProjectLaneJob(tree = null, lane = "execution") {
  const execution = selectProjectExecution(tree);
  return String(lane || "").trim().toLowerCase() === "chat"
    ? execution.chatJob
    : execution.selectedJob;
}

export function selectQueuedExecutionJobs(tree = null) {
  return selectProjectExecution(tree).queuedJobs || [];
}

export function selectProjectDetail(tree = null) {
  return tree?.detail?.normalized ?? tree?.detail?.raw ?? null;
}

export function selectProjectListing(tree = null) {
  return tree?.listing?.normalized ?? tree?.listing?.raw ?? [];
}

export function selectProjectWorkspaceStats(tree = null) {
  return tree?.listing?.workspaceStats || EMPTY_WORKSPACE_STATS;
}
