const builtInEnglishShareTranslations = {
  page_title: "jakal-flow | Remote Monitor",
  hero_eyebrow: "jakal-flow remote monitor",
  hero_title: "Remote monitor and control",
  hero_copy: "One signed link shows every in-progress project in this workspace and lets you pause after the current step or resume remaining work.",
  poll_waiting: "Waiting",
  remote_control_pill: "Signed workspace control link",
  workspace_label: "Workspace",
  workspace_title: "In-progress projects",
  workspace_updated_prefix: "Workspace updated: {value}",
  projects_visible_label: "Projects visible",
  running_now_label: "Running now",
  resume_ready_label: "Resume ready",
  pause_queued_label: "Pause queued",
  projects_label: "Projects",
  projects_title: "Active remote control surface",
  projects_loading: "Loading projects...",
  no_visible_projects: "No in-progress projects are visible right now.",
  project_label: "Project",
  run_status_label: "Run status",
  current_task_label: "Current task",
  latest_test_label: "Latest test",
  recent_logs_label: "Recent logs",
  masked_activity_tail: "Masked activity tail",
  refresh_connecting: "Connecting live stream",
  access_label: "Access",
  error_unable_load: "Unable to load share session",
  unnamed_project: "Unnamed project",
  slug_prefix: "Slug: {value}",
  last_updated_prefix: "Last updated: {value}",
  expires_prefix: "Expires: {value}",
  phase_prefix: "Phase: {value}",
  phase_unavailable: "Phase unavailable",
  no_task_reported: "No task reported",
  no_current_task_summary: "No current task summary",
  test_label_default: "test",
  no_test_result_yet: "No test result yet",
  no_test_result_summary: "No test result summary",
  no_recent_logs: "No recent logs available.",
  request_failed_with: "Request failed with {status}",
  live_stream: "Live stream",
  streaming_live_updates: "Streaming live updates",
  live_connection_lost: "Live connection lost.",
  missing_link: "Missing link",
  missing_share_link_data: "This URL does not include the required session and token.",
  missing_share_link_title: "Missing share link data",
  refreshing: "Refreshing",
  polling_every_5s: "Polling every 5s",
  polling: "Polling",
  access_denied: "Access denied",
  link_unavailable: "Link unavailable",
  link_expired: "Link expired",
  link_revoked: "Link revoked",
  invalid_link: "Invalid link",
  share_link_not_found_title: "Share link is no longer active",
  share_link_not_found: "This share link no longer matches an active session. Generate a new share link and try again.",
  share_link_expired_title: "Share link expired",
  share_link_expired: "This share link has expired. Generate a new share link to continue.",
  share_link_revoked_title: "Share link revoked",
  share_link_revoked: "This share link was revoked, usually because a newer share link replaced it.",
  share_link_invalid_title: "Share link looks incomplete",
  share_link_invalid: "The token in this link is invalid. Recopy the full URL and make sure no extra characters were added.",
  unable_keep_live_connection: "Unable to keep live connection",
  live_stream_unavailable: "Live stream unavailable",
  falling_back_to_polling: "{message} Falling back to polling.",
  control_label: "Remote control",
  control_title: "Pause after the current step or resume the remaining work.",
  control_help_idle: "Controls become available when the shared project is running or can resume.",
  control_help_pause: "Pause is requested after the current step because in-flight work is left to finish safely.",
  control_help_pause_requested: "Pause has already been requested. The run will stop after the current step.",
  control_help_resume: "Resume starts the saved plan again from the next remaining step.",
  control_help_unavailable: "No remote action is currently available for this project.",
  control_state_running: "Run active",
  control_state_pause_requested: "Pause requested",
  control_state_resume_ready: "Resume ready",
  control_state_resume_starting: "Starting resume",
  control_state_unavailable: "No action available",
  control_action_pausing: "Requesting pause",
  control_action_resuming: "Starting resume",
  pause_after_step: "Pause after step",
  resume_run: "Resume run",
  flow_label: "Execution flow",
  flow_title: "Live execution map",
  flow_state_unavailable: "Flow unavailable",
  flow_empty: "Waiting for the latest flow chart...",
  flow_alt: "Execution flow chart",
};

const shareTranslations = Object.fromEntries(
  Array.from(
    new Set([
      "en",
      ...Object.keys(window.JakalFlowGeneratedShareTranslations || { en: {} }),
      ...Object.keys(window.JakalFlowManualShareTranslations || {}),
    ]),
  ).map((language) => [
    language,
    {
      ...(language === "en" ? builtInEnglishShareTranslations : {}),
      ...((window.JakalFlowGeneratedShareTranslations || { en: {} })[language] || {}),
      ...((window.JakalFlowManualShareTranslations || {})[language] || {}),
    },
  ]),
);

const shareLanguageAliases = {
  zh: "zh-CN",
  "zh-cn": "zh-CN",
  "zh-hans": "zh-CN",
  "zh-tw": "zh-TW",
  "zh-hant": "zh-TW",
  "zh-hk": "zh-TW",
  "zh-mo": "zh-TW",
  pt: "pt-PT",
  "pt-br": "pt-BR",
  "pt-pt": "pt-PT",
  fil: "tl",
  iw: "he",
  nb: "no",
  nn: "no",
};

function normalizeLanguage(value) {
  const normalized = String(value || "").trim();
  if (!normalized) {
    return "en";
  }
  const lower = normalized.toLowerCase();
  const aliased = shareLanguageAliases[lower] || normalized;
  if (shareTranslations[aliased]) {
    return aliased;
  }
  const base = lower.split("-")[0];
  const baseAliased = shareLanguageAliases[base] || base;
  return shareTranslations[baseAliased] ? baseAliased : "en";
}

const activeLanguage = normalizeLanguage(window.navigator?.language || "en");

function t(key, params = {}) {
  const template = shareTranslations[activeLanguage]?.[key]
    || shareTranslations.en?.[key]
    || builtInEnglishShareTranslations[key]
    || key;
  return String(template).replace(/\{(\w+)\}/g, (_match, token) => String(params[token] ?? ""));
}

function queryValue(key) {
  const params = new URLSearchParams(window.location.search);
  return (params.get(key) || "").trim();
}

function shareEndpoint(path) {
  const current = new URL(window.location.href);
  const pathname = current.pathname.replace(/\/+$/, "");
  const basePath = pathname.endsWith("/share/view")
    ? pathname.slice(0, -"/view".length)
    : pathname.endsWith("/view")
      ? pathname.slice(0, -"/view".length)
      : pathname.replace(/\/[^/]*$/, "");
  return new URL(`${basePath}/${String(path).replace(/^\/+/, "")}`, current.origin);
}

function setText(id, value) {
  const node = document.getElementById(id);
  if (node) {
    node.textContent = value || "-";
  }
}

function setPollState(label, tone = "neutral") {
  const node = document.getElementById("poll-state");
  if (!node) {
    return;
  }
  node.textContent = label;
  node.className = `pill pill--${tone}`;
}

function setRefreshNote(value) {
  const node = document.getElementById("refresh-note");
  if (node) {
    node.textContent = value || "-";
  }
}

function showError(title, message) {
  const card = document.getElementById("error-card");
  if (!card) {
    return;
  }
  card.hidden = false;
  setText("error-title", title);
  setText("error-message", message);
}

function hideError() {
  const card = document.getElementById("error-card");
  if (card) {
    card.hidden = true;
  }
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function projectControlDescriptor(remote = {}) {
  if (remote.resume_starting) {
    return {
      label: t("control_state_resume_starting"),
      tone: "info",
      help: t("control_help_resume"),
    };
  }
  if (remote.pause_requested) {
    return {
      label: t("control_state_pause_requested"),
      tone: "info",
      help: t("control_help_pause_requested"),
    };
  }
  if (remote.can_pause) {
    return {
      label: t("control_state_running"),
      tone: "success",
      help: t("control_help_pause"),
    };
  }
  if (remote.can_resume) {
    return {
      label: t("control_state_resume_ready"),
      tone: "success",
      help: t("control_help_resume"),
    };
  }
  return {
    label: t("control_state_unavailable"),
    tone: "neutral",
    help: t("control_help_unavailable"),
  };
}

function flowImageUrl(session, token, projectPayload) {
  const url = shareEndpoint("api/flow.svg");
  const project = projectPayload.project || {};
  const flow = projectPayload.flow || {};
  const revision = `${projectPayload.last_updated_at || ""}:${projectPayload.current_phase || ""}:${flow.step_count || 0}`;
  url.searchParams.set("session", session);
  url.searchParams.set("token", token);
  url.searchParams.set("repo_id", project.repo_id || "");
  url.searchParams.set("rev", revision || "0");
  return url.toString();
}

function renderWorkspaceSummary(payload) {
  const workspace = payload.workspace || {};
  setText("workspace-label", t("workspace_label"));
  setText("workspace-title", t("workspace_title"));
  setText("workspace-last-updated", t("workspace_updated_prefix", { value: payload.last_updated_at || "-" }));
  setText("expires-at", t("expires_prefix", { value: payload.share_session?.expires_at || "-" }));
  setText("projects-visible-label", t("projects_visible_label"));
  setText("running-now-label", t("running_now_label"));
  setText("resume-ready-label", t("resume_ready_label"));
  setText("pause-queued-label", t("pause_queued_label"));
  setText("projects-visible-count", String(workspace.project_count || 0));
  setText("running-now-count", String(workspace.running_count || 0));
  setText("resume-ready-count", String(workspace.resume_ready_count || 0));
  setText("pause-queued-count", String(workspace.pause_requested_count || 0));
}

function projectCardHtml(session, token, projectPayload, controlBusyByRepoId) {
  const project = projectPayload.project || {};
  const task = projectPayload.current_task || {};
  const step = task.step || {};
  const test = projectPayload.latest_test_result || {};
  const remote = projectPayload.remote_control || {};
  const logs = Array.isArray(projectPayload.recent_logs) ? projectPayload.recent_logs : [];
  const flow = projectPayload.flow || {};
  const repoId = String(project.repo_id || "").trim();
  const busyAction = controlBusyByRepoId[repoId] || "";
  const descriptor = projectControlDescriptor(remote);
  const canPause = Boolean(remote.can_pause) && !busyAction;
  const canResume = Boolean(remote.can_resume) && !busyAction;
  const pauseLabel = busyAction === "pause" ? t("control_action_pausing") : t("pause_after_step");
  const resumeLabel = busyAction === "resume" ? t("control_action_resuming") : t("resume_run");
  const testStatus = test.status
    ? `${test.status} (${test.label || t("test_label_default")})`
    : t("no_test_result_yet");
  const flowAvailable = Boolean(flow.available);

  return `
    <article class="project-card" data-repo-id="${escapeHtml(repoId)}">
      <div class="project-card__top">
        <div>
          <p class="card-label">${escapeHtml(t("project_label"))}</p>
          <h2>${escapeHtml(project.display_name || t("unnamed_project"))}</h2>
          <div class="project-card__status-row">
            <span class="pill pill--info">${escapeHtml(projectPayload.overall_run_status || "-")}</span>
            <span class="pill">${escapeHtml(projectPayload.current_phase ? t("phase_prefix", { value: projectPayload.current_phase }) : t("phase_unavailable"))}</span>
          </div>
          <div class="meta-list">
            <span>${escapeHtml(t("slug_prefix", { value: project.slug || "-" }))}</span>
            <span>${escapeHtml(t("last_updated_prefix", { value: projectPayload.last_updated_at || "-" }))}</span>
          </div>
        </div>
      </div>

      <div class="project-card__grid">
        <section class="mini-panel">
          <div class="mini-panel__head">
            <div>
              <p class="card-label">${escapeHtml(t("current_task_label"))}</p>
              <strong>${escapeHtml(task.title || step.title || t("no_task_reported"))}</strong>
            </div>
          </div>
          <p class="muted">${escapeHtml(step.summary || t("no_current_task_summary"))}</p>
        </section>

        <section class="mini-panel">
          <div class="mini-panel__head">
            <div>
              <p class="card-label">${escapeHtml(t("latest_test_label"))}</p>
              <strong>${escapeHtml(testStatus)}</strong>
            </div>
          </div>
          <p class="muted">${escapeHtml(test.summary || t("no_test_result_summary"))}</p>
        </section>

        <section class="mini-panel">
          <div class="mini-panel__head">
            <div>
              <p class="card-label">${escapeHtml(t("control_label"))}</p>
              <strong>${escapeHtml(t("control_title"))}</strong>
            </div>
            <span class="pill pill--${escapeHtml(descriptor.tone)}">${escapeHtml(descriptor.label)}</span>
          </div>
          <div class="control-actions">
            <button class="control-button" type="button" data-action="pause" data-repo-id="${escapeHtml(repoId)}"${canPause ? "" : " disabled"}>${escapeHtml(pauseLabel)}</button>
            <button class="control-button control-button--secondary" type="button" data-action="resume" data-repo-id="${escapeHtml(repoId)}"${canResume ? "" : " disabled"}>${escapeHtml(resumeLabel)}</button>
          </div>
          <p class="muted">${escapeHtml(descriptor.help)}</p>
        </section>

        <section class="mini-panel">
          <div class="mini-panel__head">
            <div>
              <p class="card-label">${escapeHtml(t("recent_logs_label"))}</p>
              <strong>${escapeHtml(t("masked_activity_tail"))}</strong>
            </div>
          </div>
          <pre>${escapeHtml(logs.length ? logs.join("\n") : t("no_recent_logs"))}</pre>
        </section>

        <section class="mini-panel mini-panel--wide">
          <div class="mini-panel__head">
            <div>
              <p class="card-label">${escapeHtml(t("flow_label"))}</p>
              <strong>${escapeHtml(t("flow_title"))}</strong>
            </div>
          </div>
          <div class="project-flow">
            <img
              class="project-flow__image"
              alt="${escapeHtml(t("flow_alt"))}"
              src="${flowAvailable ? escapeHtml(flowImageUrl(session, token, projectPayload)) : ""}"
              ${flowAvailable ? "" : "hidden"}
            >
            <p class="muted project-flow__empty"${flowAvailable ? " hidden" : ""}>${escapeHtml(t("flow_empty"))}</p>
          </div>
        </section>
      </div>
    </article>
  `;
}

function renderProjects(session, token, payload, controlBusyByRepoId) {
  const container = document.getElementById("projects-list");
  const emptyNode = document.getElementById("projects-empty");
  if (!container || !emptyNode) {
    return;
  }
  const projects = Array.isArray(payload.projects) ? payload.projects : [];
  if (!projects.length) {
    container.innerHTML = "";
    emptyNode.hidden = false;
    emptyNode.className = "muted empty-block";
    emptyNode.textContent = t("no_visible_projects");
    return;
  }
  emptyNode.hidden = true;
  container.innerHTML = projects.map((item) => projectCardHtml(session, token, item, controlBusyByRepoId)).join("");
  container.querySelectorAll(".project-flow__image").forEach((image) => {
    image.addEventListener(
      "error",
      () => {
        image.hidden = true;
        const parent = image.parentElement;
        const empty = parent?.querySelector(".project-flow__empty");
        if (empty) {
          empty.hidden = false;
          empty.textContent = t("flow_state_unavailable");
        }
      },
      { once: true },
    );
  });
}

async function fetchStatus(session, token) {
  const url = shareEndpoint("api/status");
  url.searchParams.set("session", session);
  url.searchParams.set("token", token);
  const response = await fetch(url, { cache: "no-store" });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || t("request_failed_with", { status: response.status }));
    error.status = response.status;
    throw error;
  }
  return data;
}

async function sendControlAction(session, token, repoId, action) {
  const url = shareEndpoint("api/control");
  url.searchParams.set("session", session);
  url.searchParams.set("token", token);
  const response = await fetch(url, {
    method: "POST",
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ action, repo_id: repoId }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || t("request_failed_with", { status: response.status }));
    error.status = response.status;
    throw error;
  }
  return data;
}

function shareErrorDescriptor(error) {
  const status = Number(error?.status || 0);
  const message = String(error?.message || error || "").trim();
  const normalized = message.toLowerCase();

  if (status === 404 || normalized === "unknown share session.") {
    return {
      pill: t("link_unavailable"),
      title: t("share_link_not_found_title"),
      message: t("share_link_not_found"),
    };
  }
  if (normalized.includes("expired")) {
    return {
      pill: t("link_expired"),
      title: t("share_link_expired_title"),
      message: t("share_link_expired"),
    };
  }
  if (normalized.includes("revoked")) {
    return {
      pill: t("link_revoked"),
      title: t("share_link_revoked_title"),
      message: t("share_link_revoked"),
    };
  }
  if (normalized.includes("invalid share token")) {
    return {
      pill: t("invalid_link"),
      title: t("share_link_invalid_title"),
      message: t("share_link_invalid"),
    };
  }
  return {
    pill: t("access_denied"),
    title: t("error_unable_load"),
    message: message || t("request_failed_with", { status: status || "?" }),
  };
}

function showShareError(error) {
  const descriptor = shareErrorDescriptor(error);
  setPollState(descriptor.pill, "danger");
  showError(descriptor.title, descriptor.message);
}

function connectEventStream(session, token, onStatus, onFailure) {
  if (typeof window.EventSource !== "function") {
    return null;
  }
  const url = shareEndpoint("api/events");
  url.searchParams.set("session", session);
  url.searchParams.set("token", token);
  const source = new window.EventSource(url);

  source.addEventListener("open", () => {
    setPollState(t("live_stream"), "success");
    setRefreshNote(t("streaming_live_updates"));
  });

  source.addEventListener("status", (event) => {
    const payload = JSON.parse(event.data || "{}");
    onStatus(payload);
  });

  source.addEventListener("error", (event) => {
    let message = t("live_connection_lost");
    if (event?.data) {
      try {
        const payload = JSON.parse(event.data);
        message = payload.error || message;
      } catch {
        message = String(event.data || message);
      }
    }
    source.close();
    onFailure(new Error(message));
  });

  source.onerror = () => {
    source.close();
    onFailure(new Error(t("live_connection_lost")));
  };

  return source;
}

function applyStaticTranslations() {
  document.documentElement.lang = activeLanguage;
  document.title = t("page_title");
  setText("page-title", t("page_title"));
  setText("hero-eyebrow", t("hero_eyebrow"));
  setText("hero-title", t("hero_title"));
  setText("hero-copy", t("hero_copy"));
  setText("poll-state", t("poll_waiting"));
  setText("read-only-pill", t("remote_control_pill"));
  setText("workspace-label", t("workspace_label"));
  setText("workspace-title", t("workspace_title"));
  setText("workspace-last-updated", t("workspace_updated_prefix", { value: "-" }));
  setText("projects-visible-label", t("projects_visible_label"));
  setText("running-now-label", t("running_now_label"));
  setText("resume-ready-label", t("resume_ready_label"));
  setText("pause-queued-label", t("pause_queued_label"));
  setText("projects-label", t("projects_label"));
  setText("projects-title", t("projects_title"));
  setText("projects-empty", t("projects_loading"));
  setText("refresh-note", t("refresh_connecting"));
  setText("access-label", t("access_label"));
  setText("error-title", t("error_unable_load"));
}

async function bootstrap() {
  applyStaticTranslations();
  const session = queryValue("session");
  const token = queryValue("token");
  if (!session || !token) {
    setPollState(t("missing_link"), "danger");
    showError(t("missing_share_link_title"), t("missing_share_link_data"));
    return;
  }

  let inFlight = false;
  let usingPolling = false;
  const controlBusyByRepoId = {};
  let latestPayload = null;

  const applyPayload = (payload) => {
    latestPayload = payload;
    renderWorkspaceSummary(payload);
    renderProjects(session, token, payload, controlBusyByRepoId);
  };

  const reconcileStatus = async () => {
    if (inFlight) {
      return;
    }
    inFlight = true;
    try {
      const payload = await fetchStatus(session, token);
      applyPayload(payload);
      hideError();
    } finally {
      inFlight = false;
    }
  };

  const tick = async () => {
    if (inFlight) {
      return;
    }
    inFlight = true;
    setPollState(t("refreshing"), "info");
    setRefreshNote(t("polling_every_5s"));
    try {
      const payload = await fetchStatus(session, token);
      applyPayload(payload);
      hideError();
      setPollState(t("polling"), "success");
    } catch (error) {
      showShareError(error);
    } finally {
      inFlight = false;
    }
  };

  const fallbackToPolling = async (error) => {
    if (usingPolling) {
      if (error) {
        showError(t("unable_keep_live_connection"), String(error.message || error));
      }
      return;
    }
    usingPolling = true;
    setRefreshNote(t("polling_every_5s"));
    if (error) {
      showError(t("live_stream_unavailable"), t("falling_back_to_polling", { message: String(error.message || error) }));
    }
    await tick();
    window.setInterval(tick, 5000);
  };

  const postControl = async (repoId, action) => {
    if (!repoId || controlBusyByRepoId[repoId]) {
      return;
    }
    controlBusyByRepoId[repoId] = action;
    renderProjects(session, token, latestPayload || { projects: [] }, controlBusyByRepoId);
    setPollState(action === "pause" ? t("control_action_pausing") : t("control_action_resuming"), "info");
    try {
      const payload = await sendControlAction(session, token, repoId, action);
      applyPayload(payload);
      hideError();
      if (usingPolling) {
        setPollState(t("polling"), "success");
      }
    } catch (error) {
      showError(t("error_unable_load"), String(error.message || error));
    } finally {
      delete controlBusyByRepoId[repoId];
      renderProjects(session, token, latestPayload || { projects: [] }, controlBusyByRepoId);
    }
  };

  const projectsList = document.getElementById("projects-list");
  if (projectsList) {
    projectsList.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof Element)) {
        return;
      }
      const button = target.closest("button[data-action][data-repo-id]");
      if (!button) {
        return;
      }
      void postControl(button.dataset.repoId || "", button.dataset.action || "");
    });
  }

  try {
    await reconcileStatus();
  } catch (error) {
    showShareError(error);
  }

  const stream = connectEventStream(
    session,
    token,
    (payload) => {
      applyPayload(payload);
      hideError();
      setPollState(t("live_stream"), "success");
      setRefreshNote(t("streaming_live_updates"));
    },
    fallbackToPolling,
  );
  if (!stream) {
    await fallbackToPolling();
    return;
  }

  window.setInterval(() => {
    if (usingPolling) {
      return;
    }
    void reconcileStatus().catch(() => {
      // Let the live stream remain primary; polling fallback handles stream failures.
    });
  }, 4000);
}

document.addEventListener("DOMContentLoaded", bootstrap);
