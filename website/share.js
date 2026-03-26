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

function renderStatus(payload) {
  const project = payload.project || {};
  const task = payload.current_task || {};
  const step = task.step || {};
  const test = payload.latest_test_result || {};
  const logs = Array.isArray(payload.recent_logs) ? payload.recent_logs : [];
  setText("project-name", project.display_name || "Unnamed project");
  setText("project-slug", `Slug: ${project.slug || "-"}`);
  setText("last-updated", `Last updated: ${payload.last_updated_at || "-"}`);
  setText("expires-at", `Expires: ${payload.share_session?.expires_at || "-"}`);
  setText("run-status", payload.overall_run_status || "-");
  setText("current-phase", payload.current_phase ? `Phase: ${payload.current_phase}` : "Phase unavailable");
  setText("task-title", task.title || step.title || "No task reported");
  setText("task-summary", step.summary || "No current task summary");
  setText("test-status", test.status ? `${test.status} (${test.label || "test"})` : "No test result yet");
  setText("test-summary", test.summary || "No test result summary");
  setText("log-tail", logs.length ? logs.join("\n") : "No recent logs available.");
}

async function fetchStatus(session, token) {
  const url = new URL("/share/api/status", window.location.origin);
  url.searchParams.set("session", session);
  url.searchParams.set("token", token);
  const response = await fetch(url, { cache: "no-store" });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || `Request failed with ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return data;
}

async function bootstrap() {
  const session = queryValue("session");
  const token = queryValue("token");
  if (!session || !token) {
    setPollState("Missing link", "danger");
    showError("Missing share link data", "This URL does not include the required session and token.");
    return;
  }

  let inFlight = false;
  const tick = async () => {
    if (inFlight) {
      return;
    }
    inFlight = true;
    setPollState("Refreshing", "info");
    try {
      const payload = await fetchStatus(session, token);
      renderStatus(payload);
      hideError();
      setPollState("Live", "success");
    } catch (error) {
      setPollState("Access denied", "danger");
      showError("Unable to load share session", String(error.message || error));
    } finally {
      inFlight = false;
    }
  };

  await tick();
  window.setInterval(tick, 5000);
}

document.addEventListener("DOMContentLoaded", bootstrap);
