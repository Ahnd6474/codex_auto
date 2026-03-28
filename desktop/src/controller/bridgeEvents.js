import { BRIDGE_EVENTS } from "../bridgeProtocol.js";

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
  const status = String(payload.status || payload.project_status || "").trim();
  if (!repoId && !projectDir && !status) {
    return null;
  }
  return {
    repo_id: repoId,
    project_dir: projectDir,
    status,
  };
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
