const DEFAULT_IDLE_DEBOUNCE_MS = 400;
const DEFAULT_RUNNING_DEBOUNCE_MS = 1600;
const IMMEDIATE_REFRESH_DEBOUNCE_MS = 0;
const IMMEDIATE_JOB_COMMANDS = new Set([
  "generate-plan",
  "run-plan",
  "run-closeout",
  "run-manual-debugger",
  "run-manual-merger",
  "request-stop",
  "approve-checkpoint",
]);
const IMMEDIATE_PROJECT_STATUS_PREFIXES = [
  "running",
  "failed",
  "completed",
  "cancelled",
  "closed_out",
  "closeout_failed",
  "awaiting_checkpoint_approval",
];
const IMMEDIATE_UI_EVENT_TYPES = new Set([
  "step-finished",
  "batch-finished",
  "closeout-started",
  "closeout-finished",
  "run-paused",
  "checkpoint-approved",
  "project-state-synced",
]);

function normalizedRepoId(repoId) {
  return String(repoId || "").trim();
}

function normalizedStatus(status) {
  return String(status || "").trim().toLowerCase();
}

export function mergeRefreshRepoId(currentRepoId = "", nextRepoId = "") {
  const current = normalizedRepoId(currentRepoId);
  const next = normalizedRepoId(nextRepoId);
  return next || current;
}

export function projectRefreshDebounceMs(activeJob = null, options = {}) {
  if (options?.immediate) {
    return IMMEDIATE_REFRESH_DEBOUNCE_MS;
  }
  return activeJob?.status === "running" ? DEFAULT_RUNNING_DEBOUNCE_MS : DEFAULT_IDLE_DEBOUNCE_MS;
}

export function shouldRefreshSelectedProject(selectedProjectId = "", eventRepoId = "") {
  const selected = normalizedRepoId(selectedProjectId);
  if (!selected) {
    return false;
  }
  const eventRepo = normalizedRepoId(eventRepoId);
  return !eventRepo || eventRepo === selected;
}

export function shouldRefreshListingForProjectEvent(selectedProjectId = "", eventRepoId = "") {
  const selected = normalizedRepoId(selectedProjectId);
  const eventRepo = normalizedRepoId(eventRepoId);
  if (!eventRepo) {
    return true;
  }
  if (!selected) {
    return true;
  }
  return eventRepo !== selected;
}

export function shouldRefreshListingForManualRefresh(selectedProjectId = "") {
  return !normalizedRepoId(selectedProjectId);
}

export function shouldForceCodexRefreshForManualRefresh(centerTab = "") {
  const normalizedTab = String(centerTab || "").trim().toLowerCase();
  return normalizedTab === "config" || normalizedTab === "app-settings";
}

export function shouldImmediatelyRefreshProjectEvent(selectedProjectId = "", project = null) {
  if (!project || !shouldRefreshSelectedProject(selectedProjectId, project.repo_id || project.project_dir || "")) {
    return false;
  }
  const status = normalizedStatus(project.current_status || project.status || project.project_status);
  if (!status) {
    return false;
  }
  return IMMEDIATE_PROJECT_STATUS_PREFIXES.some((prefix) => status === prefix || status.startsWith(`${prefix}:`));
}

export function shouldImmediatelyRefreshProjectUiEvent(selectedProjectId = "", eventPayload = null) {
  const payload = eventPayload?.payload;
  const repoId = normalizedRepoId(payload?.repo_id || payload?.project?.repo_id || payload?.project_dir);
  if (!shouldRefreshSelectedProject(selectedProjectId, repoId)) {
    return false;
  }
  const event = payload?.event;
  const eventType = normalizedStatus(event?.event_type);
  const flow = normalizedStatus(event?.details?.flow);
  if (!eventType || flow === "planning") {
    return false;
  }
  return IMMEDIATE_UI_EVENT_TYPES.has(eventType);
}

export function shouldImmediatelyRefreshJobUpdate(selectedProjectId = "", job = null) {
  const repoId = normalizedRepoId(
    job?.repo_id
    || job?.result?.repo_id
    || job?.result?.project?.repo_id
    || job?.result?.detail?.project?.repo_id
    || job?.project_dir,
  );
  if (!shouldRefreshSelectedProject(selectedProjectId, repoId)) {
    return false;
  }
  const command = normalizedStatus(job?.command);
  if (!IMMEDIATE_JOB_COMMANDS.has(command)) {
    return false;
  }
  const status = normalizedStatus(job?.status);
  return ["queued", "running", "completed", "failed", "cancelled"].includes(status);
}
