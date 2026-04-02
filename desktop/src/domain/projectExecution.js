export function normalizeProjectPath(value = "") {
  const text = String(value || "").trim();
  if (!text) {
    return "";
  }
  const normalized = text.replace(/\\/g, "/").replace(/\/+/g, "/");
  return normalized.toLowerCase();
}

export function backgroundJobProjectKey(payload = null, workspaceRoot = "") {
  const repoId = String(payload?.repo_id || "").trim();
  const projectDir = normalizeProjectPath(payload?.project_dir || "");
  if (!repoId && !projectDir) {
    return "";
  }
  return [
    normalizeProjectPath(workspaceRoot),
    repoId,
    projectDir,
  ].join("|");
}

export function isDuplicateProjectJobError(error = null) {
  if (!error) {
    return false;
  }
  const rawReason = String(error?.reasonCode || error?.reason_code || error?.reason || "").trim().toLowerCase();
  return rawReason === "duplicate_job" || rawReason === "already_active_for_project";
}

export function normalizedChatMode(mode = "") {
  const normalized = String(mode || "").trim().toLowerCase();
  return ["conversation", "review", "debugger", "merger"].includes(normalized) ? normalized : "conversation";
}

export function jobLaneForRequest(command = "", payload = null) {
  const normalizedCommand = String(command || "").trim().toLowerCase();
  if (normalizedCommand === "send-chat-message" && ["conversation", "review"].includes(normalizedChatMode(payload?.chat_mode))) {
    return "chat";
  }
  return "execution";
}

export function jobLane(job = null) {
  const explicitLane = String(job?.job_lane || "").trim().toLowerCase();
  if (explicitLane === "chat" || explicitLane === "execution") {
    return explicitLane;
  }
  return jobLaneForRequest(job?.command, job);
}

export function isChatJob(job = null) {
  return jobLane(job) === "chat";
}

export function jobMatchesProject(job = null, project = {}) {
  if (!job || !project) {
    return false;
  }
  const jobRepoId = String(job?.repo_id || "").trim();
  const projectRepoId = String(project?.repo_id || "").trim();
  if (jobRepoId && projectRepoId && jobRepoId === projectRepoId) {
    return true;
  }
  const jobProjectDir = normalizeProjectPath(job?.project_dir || "");
  const projectDir = normalizeProjectPath(project?.project_dir || project?.repo_path || "");
  return Boolean(jobProjectDir) && Boolean(projectDir) && jobProjectDir === projectDir;
}

function jobStatusSortRank(job = null) {
  return ({
    running: 0,
    queued: 1,
  })[String(job?.status || "").trim().toLowerCase()] ?? 9;
}

function parseTimestampMs(value) {
  if (!value) {
    return null;
  }
  const parsed = Date.parse(String(value).trim());
  return Number.isFinite(parsed) ? parsed : null;
}

export function projectScopedJobFromJobs(jobs = [], project = {}, options = {}) {
  const jobItems = Array.isArray(jobs) ? jobs.filter(Boolean) : [];
  const lane = String(options?.lane || "execution").trim().toLowerCase();
  const ignoreSuperseded = options?.ignoreSuperseded ?? (lane !== "chat");
  const matches = jobItems.filter((job) => {
    if (!jobMatchesProject(job, project)) {
      return false;
    }
    if (lane === "chat") {
      return isChatJob(job);
    }
    if (lane === "execution") {
      return !isChatJob(job);
    }
    return true;
  });
  if (!matches.length) {
    return null;
  }
  const candidates = ignoreSuperseded
    ? matches.filter((job) => !jobIsSupersededByProject(job, project))
    : matches;
  if (!candidates.length) {
    return null;
  }
  return [...candidates].sort((left, right) => {
    const leftRank = jobStatusSortRank(left);
    const rightRank = jobStatusSortRank(right);
    if (leftRank !== rightRank) {
      return leftRank - rightRank;
    }
    return (Number(right?.updated_at_ms || 0) || 0) - (Number(left?.updated_at_ms || 0) || 0);
  })[0] || null;
}

export function projectJobFromJobs(jobs = [], project = {}) {
  return projectScopedJobFromJobs(jobs, project, {
    lane: "execution",
    ignoreSuperseded: true,
  });
}

export function projectChatJobFromJobs(jobs = [], project = {}) {
  return projectScopedJobFromJobs(jobs, project, {
    lane: "chat",
    ignoreSuperseded: false,
  });
}

export function jobHasNewerActiveReplacement(job = null, jobs = []) {
  const targetJobId = String(job?.id || "").trim();
  if (!targetJobId) {
    return false;
  }
  const replacement = (isChatJob(job) ? projectChatJobFromJobs : projectJobFromJobs)(jobs, {
    repo_id: job?.repo_id,
    project_dir: job?.project_dir,
  });
  if (!replacement || String(replacement?.id || "").trim() === targetJobId) {
    return false;
  }
  return ["queued", "running"].includes(String(replacement?.status || "").trim().toLowerCase());
}

export function jobIsSupersededByProject(job = null, project = null) {
  const jobStatus = String(job?.status || "").trim().toLowerCase();
  if (!["queued", "running"].includes(jobStatus)) {
    return false;
  }
  const currentStatus = String(project?.current_status || project?.status || "").trim().toLowerCase();
  if (!currentStatus || currentStatus.startsWith("running:") || currentStatus === "queued" || currentStatus.startsWith("queued:")) {
    return false;
  }
  const projectLastRunAtMs = parseTimestampMs(project?.last_run_at);
  const jobUpdatedAtMs = Number.isFinite(Number(job?.updated_at_ms)) ? Number(job.updated_at_ms) : null;
  if (projectLastRunAtMs !== null && jobUpdatedAtMs !== null && projectLastRunAtMs > jobUpdatedAtMs) {
    return true;
  }
  return false;
}

export function isChatCommand(command = "") {
  return String(command || "").trim().toLowerCase() === "send-chat-message";
}

export function visibleExecutionJob(job = null) {
  if (!job || isChatJob(job)) {
    return null;
  }
  return job;
}

export function isActiveExecutionStatus(status = "") {
  const normalized = String(status || "").trim().toLowerCase();
  return normalized === "running"
    || normalized.startsWith("running:")
    || normalized === "queued"
    || normalized.startsWith("queued:");
}

export function isPausedExecutionStatus(status = "") {
  const normalized = String(status || "").trim().toLowerCase();
  return normalized === "paused"
    || normalized.startsWith("paused:");
}

export function projectStatusWithJob(status = "", activeJob = null) {
  const job = visibleExecutionJob(activeJob);
  const currentStatus = String(status || "").trim();
  const jobStatus = String(job?.status || "").trim().toLowerCase();
  const command = String(job?.command || "").trim() || "background-job";
  if (jobStatus === "queued") {
    return `queued:${command}`;
  }
  if (jobStatus === "running" && !currentStatus.toLowerCase().startsWith("running:")) {
    return `running:${command}`;
  }
  return currentStatus;
}

export function sameQueuedJobs(previousJobs = [], nextJobs = []) {
  if (previousJobs === nextJobs) {
    return true;
  }
  if (!Array.isArray(previousJobs) || !Array.isArray(nextJobs) || previousJobs.length !== nextJobs.length) {
    return false;
  }
  for (let index = 0; index < previousJobs.length; index += 1) {
    const previousJob = previousJobs[index];
    const nextJob = nextJobs[index];
    if (
      previousJob?.id !== nextJob?.id
      || previousJob?.status !== nextJob?.status
      || previousJob?.queue_position !== nextJob?.queue_position
    ) {
      return false;
    }
  }
  return true;
}

export function detailApplySignature(detail = null, runningJob = null) {
  return [
    String(detail?.project?.repo_id || "").trim(),
    String(detail?.detail_level || "").trim(),
    String(detail?.detail_signature || detail?.content_signature || "").trim(),
    String(detail?.project?.current_status || "").trim(),
  ].join("|");
}
