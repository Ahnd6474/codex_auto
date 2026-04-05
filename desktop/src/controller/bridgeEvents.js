import { BRIDGE_EVENTS } from "../bridgeProtocol.js";

function normalizedText(value = "") {
  return String(value || "").trim();
}

export function bridgeEventType(eventPayload) {
  return String(eventPayload?.event || "").trim();
}

export function bridgeEventJob(eventPayload) {
  return eventPayload?.payload?.job || null;
}

export function bridgeEventProject(eventPayload) {
  const payload = eventPayload?.payload;
  if (!payload || typeof payload !== "object") {
    return null;
  }
  if (payload.project && typeof payload.project === "object") {
    return payload.project;
  }
  const repoId = String(payload.repo_id || "").trim();
  const projectDir = String(payload.project_dir || "").trim();
  const projectDirHint = String(payload.project_dir_hint || "").trim();
  const status = String(payload.status || payload.project_status || "").trim();
  if (!repoId && !projectDir && !projectDirHint && !status) {
    return null;
  }
  return {
    repo_id: repoId,
    ...(Object.prototype.hasOwnProperty.call(payload, "project_dir")
      ? { project_dir: projectDir }
      : {}),
    ...(Object.prototype.hasOwnProperty.call(payload, "project_dir_hint")
      ? { project_dir_hint: projectDirHint }
      : {}),
    ...(Object.prototype.hasOwnProperty.call(payload, "repo_available")
      ? { repo_available: Boolean(payload.repo_available) }
      : {}),
    ...(String(payload.repo_binding || "").trim()
      ? { repo_binding: String(payload.repo_binding || "").trim() }
      : {}),
    ...(String(payload.project_root_relative || "").trim()
      ? { project_root_relative: String(payload.project_root_relative || "").trim() }
      : {}),
    status,
  };
}

function bridgeEventProjectKey(eventPayload) {
  const project = bridgeEventProject(eventPayload);
  const eventType = bridgeEventType(eventPayload);
  if (!project || !eventType) {
    return "";
  }
  const payload = eventPayload?.payload;
  const event = payload?.event;
  let detailKey = "";
  if (eventType === BRIDGE_EVENTS.PROJECT_UI_EVENT && event && typeof event === "object") {
    const uiEventType = normalizedText(event.event_type);
    const details = event.details && typeof event.details === "object" ? event.details : {};
    const stepId = normalizedText(details.step_id);
    const stepIds = Array.isArray(details.step_ids)
      ? details.step_ids.map((value) => normalizedText(value)).filter(Boolean).sort()
      : [];
    const statusStepIds = details.statuses && typeof details.statuses === "object"
      ? Object.keys(details.statuses).map((value) => normalizedText(value)).filter(Boolean).sort()
      : [];
    detailKey = [
      uiEventType,
      stepId,
      stepIds.join(","),
      statusStepIds.join(","),
    ].join("|");
  }
  return [
    eventType,
    String(project.repo_id || "").trim(),
    String(project.project_dir || project.project_dir_hint || "").trim(),
    detailKey,
  ].join("|");
}

export function isJobUpdatedEvent(eventPayload) {
  return bridgeEventType(eventPayload) === BRIDGE_EVENTS.JOB_UPDATED;
}

export function isProjectChangedEvent(eventPayload) {
  return bridgeEventType(eventPayload) === BRIDGE_EVENTS.PROJECT_CHANGED;
}

export function isProjectUiEvent(eventPayload) {
  return bridgeEventType(eventPayload) === BRIDGE_EVENTS.PROJECT_UI_EVENT;
}

export function compactBridgeEventQueue(events = []) {
  const items = Array.isArray(events) ? events.filter(Boolean) : [];
  if (items.length < 2) {
    return items;
  }
  const compacted = [];
  const projectEventIndexByKey = new Map();
  items.forEach((eventPayload) => {
    if (isProjectChangedEvent(eventPayload) || isProjectUiEvent(eventPayload)) {
      const key = bridgeEventProjectKey(eventPayload);
      if (key) {
        const existingIndex = projectEventIndexByKey.get(key);
        if (existingIndex !== undefined) {
          compacted[existingIndex] = eventPayload;
          return;
        }
        projectEventIndexByKey.set(key, compacted.length);
      }
    }
    compacted.push(eventPayload);
  });
  return compacted;
}
