export const BRIDGE_EVENT_NAME = "jakal-flow://bridge-event";

export const BRIDGE_COMMANDS = Object.freeze({
  BOOTSTRAP: "bootstrap",
  LIST_PROJECTS: "list-projects",
  LOAD_PROJECT: "load-project",
  LOAD_PROJECT_CORE: "load-project-core",
  LOAD_VISIBLE_PROJECT_STATE: "load-visible-project-state",
  LOAD_PROJECT_HISTORY: "load-project-history",
  LOAD_HISTORY_ENTRY: "load-history-entry",
  LOAD_PROJECT_REPORTS: "load-project-reports",
  LOAD_PROJECT_CONFIG: "load-project-config",
  LOAD_PROJECT_WORKSPACE: "load-project-workspace",
  LOAD_PROJECT_CHECKPOINTS: "load-project-checkpoints",
  LOAD_PROJECT_SHARE: "load-project-share",
  LOAD_PROJECT_CHAT: "load-project-chat",
  LOAD_WORKSPACE_SHARE: "load-workspace-share",
  SAVE_PROJECT_SETUP: "save-project-setup",
  SAVE_PLAN: "save-plan",
  RESET_PLAN: "reset-plan",
  ARCHIVE_PROJECT: "archive-project",
  ARCHIVE_ALL_PROJECTS: "archive-all-projects",
  DELETE_PROJECT: "delete-project",
  DELETE_ALL_PROJECTS: "delete-all-projects",
  DELETE_HISTORY_ENTRY: "delete-history-entry",
  GENERATE_PLAN: "generate-plan",
  RUN_PLAN: "run-plan",
  RUN_CLOSEOUT: "run-closeout",
  RUN_MANUAL_DEBUGGER: "run-manual-debugger",
  RUN_MANUAL_MERGER: "run-manual-merger",
  SEND_CHAT_MESSAGE: "send-chat-message",
  REQUEST_STOP: "request-stop",
  CREATE_SHARE_SESSION: "create_share_session",
  REVOKE_SHARE_SESSION: "revoke_share_session",
  APPROVE_CHECKPOINT: "approve-checkpoint",
  RESOLVE_COMMON_REQUIREMENT: "resolve-common-requirement",
  REOPEN_COMMON_REQUIREMENT: "reopen-common-requirement",
  RECORD_SPINE_CHECKPOINT: "record-spine-checkpoint",
  UPDATE_COMMON_REQUIREMENT: "update-common-requirement",
  DELETE_COMMON_REQUIREMENT: "delete-common-requirement",
  UPDATE_SPINE_CHECKPOINT: "update-spine-checkpoint",
  DELETE_SPINE_CHECKPOINT: "delete-spine-checkpoint",
});

export const BRIDGE_EVENTS = Object.freeze({
  JOB_UPDATED: "job.updated",
  PROJECT_CHANGED: "project.changed",
  PROJECT_UI_EVENT: "project.ui_event",
});

export const BRIDGE_ERROR_PREFIX = "BRIDGE_ERROR_JSON:";

export const BRIDGE_ERROR_CODES = Object.freeze({
  BRIDGE_ERROR: "bridge_server_error",
  INVALID_REQUEST: "invalid_request",
  REQUEST_REJECTED: "request_rejected",
  NOT_FOUND: "not_found",
  DUPLICATE_JOB: "duplicate_job",
  INVALID_COMMAND: "unsupported_command",
  METHOD_UNSUPPORTED: "unsupported_method",
  TIMEOUT: "timeout",
  BRIDGE_UNAVAILABLE: "bridge_unavailable",
  PRECONDITION_FAILED: "precondition_failed",
});

export function parseBridgeError(rawError) {
  const rawMessage = String(
    (rawError && typeof rawError === "object" && (rawError.message || rawError.error))
      || rawError
      || "",
  ).trim();
  if (typeof rawError === "object" && rawError !== null) {
    if (typeof rawError.reason_code === "string" || typeof rawError.reasonCode === "string") {
      return {
        message: String(rawError.message || rawMessage || "Bridge request failed."),
        reason_code: String(rawError.reason_code || rawError.reasonCode || "").trim(),
        type: String(rawError.type || rawError.error_type || "").trim(),
        details: rawError.details || {},
        recoverable: rawError.recoverable,
        command: String(rawError.command || "").trim(),
        method: String(rawError.method || "").trim(),
        request_id: String(rawError.request_id || "").trim(),
      };
    }
    const text = rawMessage.startsWith(BRIDGE_ERROR_PREFIX)
      ? rawMessage.slice(BRIDGE_ERROR_PREFIX.length).trim()
      : rawMessage;
    if (text.startsWith("{") && text.endsWith("}")) {
      try {
        const parsed = JSON.parse(text);
        if (parsed && typeof parsed === "object") {
          return {
            message: String(parsed.message || rawMessage || "Bridge request failed."),
            reason_code: String(parsed.reason_code || parsed.reasonCode || "").trim(),
            type: String(parsed.type || "").trim(),
            details: parsed.details || {},
            recoverable: parsed.recoverable,
            command: String(parsed.command || "").trim(),
            method: String(parsed.method || "").trim(),
            request_id: String(parsed.request_id || "").trim(),
          };
        }
      } catch {
        // Fall back to the raw message.
      }
    }
  } else if (rawMessage.startsWith(BRIDGE_ERROR_PREFIX)) {
    const text = rawMessage.slice(BRIDGE_ERROR_PREFIX.length).trim();
    if (text.startsWith("{") && text.endsWith("}")) {
      try {
        const parsed = JSON.parse(text);
        if (parsed && typeof parsed === "object") {
          return {
            message: String(parsed.message || rawMessage || "Bridge request failed."),
            reason_code: String(parsed.reason_code || parsed.reasonCode || "").trim(),
            type: String(parsed.type || "").trim(),
            details: parsed.details || {},
            recoverable: parsed.recoverable,
            command: String(parsed.command || "").trim(),
            method: String(parsed.method || "").trim(),
            request_id: String(parsed.request_id || "").trim(),
          };
        }
      } catch {
        // Fall back to the raw message.
      }
    }
  }
  return {
    message: rawMessage || "Bridge request failed.",
    reason_code: "",
    type: "",
    details: {},
    recoverable: null,
    command: "",
    method: "",
    request_id: "",
  };
}

export function bridgeErrorMessage(rawError, fallback = "Bridge request failed.") {
  const parsed = parseBridgeError(rawError);
  return String(parsed.message || "").trim() || String(fallback || "Bridge request failed.");
}

export function isBridgeMutationCommand(command) {
  return new Set([
    BRIDGE_COMMANDS.SAVE_PROJECT_SETUP,
    BRIDGE_COMMANDS.SAVE_PLAN,
    BRIDGE_COMMANDS.RESET_PLAN,
    BRIDGE_COMMANDS.ARCHIVE_PROJECT,
    BRIDGE_COMMANDS.ARCHIVE_ALL_PROJECTS,
    BRIDGE_COMMANDS.DELETE_PROJECT,
    BRIDGE_COMMANDS.DELETE_ALL_PROJECTS,
    BRIDGE_COMMANDS.DELETE_HISTORY_ENTRY,
    BRIDGE_COMMANDS.GENERATE_PLAN,
    BRIDGE_COMMANDS.RUN_PLAN,
    BRIDGE_COMMANDS.RUN_CLOSEOUT,
    BRIDGE_COMMANDS.RUN_MANUAL_DEBUGGER,
    BRIDGE_COMMANDS.RUN_MANUAL_MERGER,
    BRIDGE_COMMANDS.SEND_CHAT_MESSAGE,
    BRIDGE_COMMANDS.REQUEST_STOP,
    BRIDGE_COMMANDS.CREATE_SHARE_SESSION,
    BRIDGE_COMMANDS.REVOKE_SHARE_SESSION,
    BRIDGE_COMMANDS.APPROVE_CHECKPOINT,
    BRIDGE_COMMANDS.RESOLVE_COMMON_REQUIREMENT,
    BRIDGE_COMMANDS.REOPEN_COMMON_REQUIREMENT,
    BRIDGE_COMMANDS.RECORD_SPINE_CHECKPOINT,
    BRIDGE_COMMANDS.UPDATE_COMMON_REQUIREMENT,
    BRIDGE_COMMANDS.DELETE_COMMON_REQUIREMENT,
    BRIDGE_COMMANDS.UPDATE_SPINE_CHECKPOINT,
    BRIDGE_COMMANDS.DELETE_SPINE_CHECKPOINT,
  ]).has(command);
}
