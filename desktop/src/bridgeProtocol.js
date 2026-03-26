export const BRIDGE_EVENT_NAME = "jakal-flow://bridge-event";

export const BRIDGE_COMMANDS = Object.freeze({
  BOOTSTRAP: "bootstrap",
  LIST_PROJECTS: "list-projects",
  LOAD_PROJECT: "load-project",
  LOAD_PROJECT_CORE: "load-project-core",
  LOAD_PROJECT_HISTORY: "load-project-history",
  LOAD_PROJECT_REPORTS: "load-project-reports",
  LOAD_PROJECT_CONFIG: "load-project-config",
  LOAD_PROJECT_WORKSPACE: "load-project-workspace",
  LOAD_PROJECT_CHECKPOINTS: "load-project-checkpoints",
  LOAD_PROJECT_SHARE: "load-project-share",
  SAVE_PROJECT_SETUP: "save-project-setup",
  SAVE_PLAN: "save-plan",
  RESET_PLAN: "reset-plan",
  DELETE_PROJECT: "delete-project",
  DELETE_ALL_PROJECTS: "delete-all-projects",
  GENERATE_PLAN: "generate-plan",
  RUN_PLAN: "run-plan",
  RUN_CLOSEOUT: "run-closeout",
  REQUEST_STOP: "request-stop",
  CREATE_SHARE_SESSION: "create_share_session",
  REVOKE_SHARE_SESSION: "revoke_share_session",
  APPROVE_CHECKPOINT: "approve-checkpoint",
});

export const BRIDGE_EVENTS = Object.freeze({
  JOB_UPDATED: "job.updated",
  PROJECT_CHANGED: "project.changed",
  PROJECT_UI_EVENT: "project.ui_event",
});

export function isBridgeMutationCommand(command) {
  return new Set([
    BRIDGE_COMMANDS.SAVE_PROJECT_SETUP,
    BRIDGE_COMMANDS.SAVE_PLAN,
    BRIDGE_COMMANDS.RESET_PLAN,
    BRIDGE_COMMANDS.DELETE_PROJECT,
    BRIDGE_COMMANDS.DELETE_ALL_PROJECTS,
    BRIDGE_COMMANDS.GENERATE_PLAN,
    BRIDGE_COMMANDS.RUN_PLAN,
    BRIDGE_COMMANDS.RUN_CLOSEOUT,
    BRIDGE_COMMANDS.REQUEST_STOP,
    BRIDGE_COMMANDS.CREATE_SHARE_SESSION,
    BRIDGE_COMMANDS.REVOKE_SHARE_SESSION,
    BRIDGE_COMMANDS.APPROVE_CHECKPOINT,
  ]).has(command);
}
