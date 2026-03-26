import { BRIDGE_EVENTS } from "../bridgeProtocol";

export function bridgeEventType(eventPayload) {
  return String(eventPayload?.event || "").trim();
}

export function bridgeEventJob(eventPayload) {
  return eventPayload?.payload?.job || null;
}

export function bridgeEventProject(eventPayload) {
  return eventPayload?.payload?.project || null;
}

export function isJobUpdatedEvent(eventPayload) {
  return bridgeEventType(eventPayload) === BRIDGE_EVENTS.JOB_UPDATED;
}

export function isProjectChangedEvent(eventPayload) {
  const type = bridgeEventType(eventPayload);
  return type === BRIDGE_EVENTS.PROJECT_CHANGED || type === BRIDGE_EVENTS.PROJECT_UI_EVENT;
}
