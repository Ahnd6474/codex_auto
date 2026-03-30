const DEFAULT_IDLE_DEBOUNCE_MS = 150;
const DEFAULT_RUNNING_DEBOUNCE_MS = 900;

function normalizedRepoId(repoId) {
  return String(repoId || "").trim();
}

export function mergeRefreshRepoId(currentRepoId = "", nextRepoId = "") {
  const current = normalizedRepoId(currentRepoId);
  const next = normalizedRepoId(nextRepoId);
  return next || current;
}

export function projectRefreshDebounceMs(activeJob = null) {
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

export function shouldForceCodexRefreshForManualRefresh(centerTab = "") {
  const normalizedTab = String(centerTab || "").trim().toLowerCase();
  return normalizedTab === "config" || normalizedTab === "app-settings";
}
