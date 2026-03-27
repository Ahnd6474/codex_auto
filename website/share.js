const builtInEnglishShareTranslations = {
  page_title: "jakal-flow | Remote Monitor",
  hero_eyebrow: "jakal-flow remote monitor",
  hero_title: "Remote monitor and control",
  hero_copy: "This page streams masked progress updates in near real time and can request a pause after the current step or resume the saved plan.",
  poll_waiting: "Waiting",
  remote_control_pill: "Signed control link",
  project_label: "Project",
  project_loading: "Loading...",
  run_status_label: "Run status",
  current_task_label: "Current task",
  latest_test_label: "Latest test",
  recent_logs_label: "Recent logs",
  masked_activity_tail: "Masked activity tail",
  refresh_connecting: "Connecting live stream",
  log_waiting: "Waiting for status...",
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
  unable_keep_live_connection: "Unable to keep live connection",
  live_stream_unavailable: "Live stream unavailable",
  falling_back_to_polling: "{message} Falling back to polling.",
  control_label: "Remote control",
  control_title: "Pause after the current step or resume the remaining work.",
  control_idle: "Control idle",
  pause_after_step: "Pause after step",
  resume_run: "Resume run",
  control_help_idle: "Controls become available when the shared project is running or can resume.",
  control_help_pause: "Pause is requested after the current step because in-flight work is left to finish safely.",
  control_help_pause_requested: "Pause has already been requested. The run will stop after the current step.",
  control_help_resume: "Resume starts the saved plan again from the next remaining step.",
  control_help_unavailable: "No remote action is currently available for this session.",
  control_state_running: "Run active",
  control_state_pause_requested: "Pause requested",
  control_state_resume_ready: "Resume ready",
  control_state_resume_starting: "Starting resume",
  control_state_unavailable: "No action available",
  control_action_pausing: "Requesting pause",
  control_action_resuming: "Starting resume",
  flow_label: "Execution flow",
  flow_title: "Live execution map",
  flow_state_loading: "Loading flow",
  flow_state_ready: "Flow ready",
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
  const template = shareTranslations[activeLanguage]?.[key] || shareTranslations.en?.[key] || builtInEnglishShareTranslations[key] || key;
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

function setFlowState(label, tone = "neutral") {
  const node = document.getElementById("flow-state");
  if (!node) {
    return;
  }
  node.textContent = label;
  node.className = `pill pill--${tone}`;
}

function setControlState(label, tone = "neutral") {
  const node = document.getElementById("control-state");
  if (!node) {
    return;
  }
  node.textContent = label;
  node.className = `pill pill--${tone}`;
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

function applyStaticTranslations() {
  document.documentElement.lang = activeLanguage;
  document.title = t("page_title");
  setText("page-title", t("page_title"));
  setText("hero-eyebrow", t("hero_eyebrow"));
  setText("hero-title", t("hero_title"));
  setText("hero-copy", t("hero_copy"));
  setText("poll-state", t("poll_waiting"));
  setText("read-only-pill", t("remote_control_pill"));
  setText("project-label", t("project_label"));
  setText("project-name", t("project_loading"));
  setText("run-status-label", t("run_status_label"));
  setText("current-task-label", t("current_task_label"));
  setText("latest-test-label", t("latest_test_label"));
  setText("recent-logs-label", t("recent_logs_label"));
  setText("masked-activity-tail", t("masked_activity_tail"));
  setText("refresh-note", t("refresh_connecting"));
  setText("log-tail", t("log_waiting"));
  setText("access-label", t("access_label"));
  setText("error-title", t("error_unable_load"));
  setText("flow-label", t("flow_label"));
  setText("flow-title", t("flow_title"));
  setText("flow-state", t("flow_state_loading"));
  setText("flow-empty", t("flow_empty"));
  setText("control-label", t("control_label"));
  setText("control-title", t("control_title"));
  setText("control-state", t("control_idle"));
  setText("control-help", t("control_help_idle"));

  const pauseButton = document.getElementById("pause-button");
  if (pauseButton) {
    pauseButton.textContent = t("pause_after_step");
  }
  const resumeButton = document.getElementById("resume-button");
  if (resumeButton) {
    resumeButton.textContent = t("resume_run");
  }
  const flowChart = document.getElementById("flow-chart");
  if (flowChart) {
    flowChart.alt = t("flow_alt");
  }
}

function renderStatus(payload) {
  const project = payload.project || {};
  const task = payload.current_task || {};
  const step = task.step || {};
  const test = payload.latest_test_result || {};
  const logs = Array.isArray(payload.recent_logs) ? payload.recent_logs : [];
  setText("project-name", project.display_name || t("unnamed_project"));
  setText("project-slug", t("slug_prefix", { value: project.slug || "-" }));
  setText("last-updated", t("last_updated_prefix", { value: payload.last_updated_at || "-" }));
  setText("expires-at", t("expires_prefix", { value: payload.share_session?.expires_at || "-" }));
  setText("run-status", payload.overall_run_status || "-");
  setText("current-phase", payload.current_phase ? t("phase_prefix", { value: payload.current_phase }) : t("phase_unavailable"));
  setText("task-title", task.title || step.title || t("no_task_reported"));
  setText("task-summary", step.summary || t("no_current_task_summary"));
  setText("test-status", test.status ? `${test.status} (${test.label || t("test_label_default")})` : t("no_test_result_yet"));
  setText("test-summary", test.summary || t("no_test_result_summary"));
  setText("log-tail", logs.length ? logs.join("\n") : t("no_recent_logs"));
}

function renderControls(payload, controlBusy = false, busyAction = "") {
  const remote = payload.remote_control || {};
  const pauseButton = document.getElementById("pause-button");
  const resumeButton = document.getElementById("resume-button");
  const canPause = Boolean(remote.can_pause) && !controlBusy;
  const canResume = Boolean(remote.can_resume) && !controlBusy;
  const pauseRequested = Boolean(remote.pause_requested);
  const resumeStarting = Boolean(remote.resume_starting);

  if (pauseButton) {
    pauseButton.disabled = !canPause;
    pauseButton.textContent = controlBusy && busyAction === "pause" ? t("control_action_pausing") : t("pause_after_step");
  }
  if (resumeButton) {
    resumeButton.disabled = !canResume;
    resumeButton.textContent = controlBusy && busyAction === "resume" ? t("control_action_resuming") : t("resume_run");
  }

  if (resumeStarting) {
    setControlState(t("control_state_resume_starting"), "info");
    setText("control-help", t("control_help_resume"));
    return;
  }
  if (pauseRequested) {
    setControlState(t("control_state_pause_requested"), "info");
    setText("control-help", t("control_help_pause_requested"));
    return;
  }
  if (remote.can_pause) {
    setControlState(t("control_state_running"), "success");
    setText("control-help", t("control_help_pause"));
    return;
  }
  if (remote.can_resume) {
    setControlState(t("control_state_resume_ready"), "success");
    setText("control-help", t("control_help_resume"));
    return;
  }
  setControlState(t("control_state_unavailable"), "neutral");
  setText("control-help", t("control_help_unavailable"));
}

function renderFlow(session, token, payload, state) {
  const flowChart = document.getElementById("flow-chart");
  const flowEmpty = document.getElementById("flow-empty");
  if (!flowChart || !flowEmpty) {
    return;
  }
  const flow = payload.flow || {};
  if (!flow.available) {
    flowChart.hidden = true;
    flowEmpty.hidden = false;
    flowEmpty.textContent = t("flow_empty");
    setFlowState(t("flow_state_unavailable"), "neutral");
    return;
  }
  const revision = `${payload.last_updated_at || ""}:${payload.current_phase || ""}:${flow.step_count || 0}`;
  if (state.lastFlowRevision !== revision) {
    const url = shareEndpoint("api/flow.svg");
    url.searchParams.set("session", session);
    url.searchParams.set("token", token);
    url.searchParams.set("rev", revision || "0");
    flowChart.src = url.toString();
    state.lastFlowRevision = revision;
  }
  flowChart.hidden = false;
  flowEmpty.hidden = true;
  setFlowState(t("flow_state_ready"), "success");
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

async function sendControlAction(session, token, action) {
  const url = shareEndpoint("api/control");
  url.searchParams.set("session", session);
  url.searchParams.set("token", token);
  const response = await fetch(url, {
    method: "POST",
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ action }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || t("request_failed_with", { status: response.status }));
    error.status = response.status;
    throw error;
  }
  return data;
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
  let controlBusy = false;
  let currentControlAction = "";
  let latestPayload = null;
  const flowState = {
    lastFlowRevision: "",
  };

  const applyPayload = (payload) => {
    latestPayload = payload;
    renderStatus(payload);
    renderFlow(session, token, payload, flowState);
    renderControls(payload, controlBusy, currentControlAction);
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
      setPollState(t("access_denied"), "danger");
      showError(t("error_unable_load"), String(error.message || error));
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

  const postControl = async (action) => {
    if (controlBusy) {
      return;
    }
    controlBusy = true;
    currentControlAction = action;
    renderControls(latestPayload || {}, true, currentControlAction);
    setControlState(action === "pause" ? t("control_action_pausing") : t("control_action_resuming"), "info");
    try {
      const payload = await sendControlAction(session, token, action);
      applyPayload(payload);
      hideError();
      if (usingPolling) {
        setPollState(t("polling"), "success");
      }
    } catch (error) {
      renderControls(latestPayload || {}, false, "");
      showError(t("error_unable_load"), String(error.message || error));
    } finally {
      controlBusy = false;
      currentControlAction = "";
      renderControls(latestPayload || {}, false, "");
    }
  };

  const pauseButton = document.getElementById("pause-button");
  if (pauseButton) {
    pauseButton.addEventListener("click", () => {
      void postControl("pause");
    });
  }
  const resumeButton = document.getElementById("resume-button");
  if (resumeButton) {
    resumeButton.addEventListener("click", () => {
      void postControl("resume");
    });
  }
  const flowChart = document.getElementById("flow-chart");
  if (flowChart) {
    flowChart.addEventListener("error", () => {
      flowChart.hidden = true;
      setText("flow-empty", t("flow_empty"));
      const flowEmpty = document.getElementById("flow-empty");
      if (flowEmpty) {
        flowEmpty.hidden = false;
      }
      setFlowState(t("flow_state_unavailable"), "neutral");
    });
  }

  try {
    await reconcileStatus();
  } catch (error) {
    showError(t("error_unable_load"), String(error.message || error));
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
