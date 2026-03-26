const shareTranslations = Object.fromEntries(
  Array.from(
    new Set([
      ...Object.keys(window.JakalFlowGeneratedShareTranslations || { en: {} }),
      ...Object.keys(window.JakalFlowManualShareTranslations || {}),
    ]),
  ).map((language) => [
    language,
    {
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
  const template = shareTranslations[activeLanguage]?.[key] || shareTranslations.en?.[key] || key;
  return String(template).replace(/\{(\w+)\}/g, (_match, token) => String(params[token] ?? ""));
}

function queryValue(key) {
  const params = new URLSearchParams(window.location.search);
  return (params.get(key) || "").trim();
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

function applyStaticTranslations() {
  document.documentElement.lang = activeLanguage;
  document.title = t("page_title");
  setText("page-title", t("page_title"));
  setText("hero-eyebrow", t("hero_eyebrow"));
  setText("hero-title", t("hero_title"));
  setText("hero-copy", t("hero_copy"));
  setText("poll-state", t("poll_waiting"));
  setText("read-only-pill", t("read_only"));
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

async function fetchStatus(session, token) {
  const url = new URL("/share/api/status", window.location.origin);
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

function connectEventStream(session, token, onStatus, onFailure) {
  if (typeof window.EventSource !== "function") {
    return null;
  }
  const url = new URL("/share/api/events", window.location.origin);
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

  const tick = async () => {
    if (inFlight) {
      return;
    }
    inFlight = true;
    setPollState(t("refreshing"), "info");
    setRefreshNote(t("polling_every_5s"));
    try {
      const payload = await fetchStatus(session, token);
      renderStatus(payload);
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

  const stream = connectEventStream(
    session,
    token,
    (payload) => {
      renderStatus(payload);
      hideError();
      setPollState(t("live_stream"), "success");
      setRefreshNote(t("streaming_live_updates"));
    },
    fallbackToPolling,
  );
  if (!stream) {
    await fallbackToPolling();
  }
}

document.addEventListener("DOMContentLoaded", bootstrap);
