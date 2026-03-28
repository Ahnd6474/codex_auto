import { BRIDGE_COMMANDS } from "../bridgeProtocol.js";

function selectorPayload(selector = {}) {
  const payload = {};
  if (selector.repoId) {
    payload.repo_id = selector.repoId;
  }
  if (selector.projectDir) {
    payload.project_dir = selector.projectDir;
  }
  return payload;
}

export async function loadProjectCore(bridgeRequest, selector, workspaceRoot, options = {}) {
  return bridgeRequest(
    BRIDGE_COMMANDS.LOAD_PROJECT_CORE,
    {
      ...selectorPayload(selector),
      refresh_codex_status: options.refreshCodexStatus ?? false,
    },
    workspaceRoot || null,
  );
}

export async function loadProjectDetail(bridgeRequest, selector, workspaceRoot, options = {}) {
  return bridgeRequest(
    BRIDGE_COMMANDS.LOAD_PROJECT,
    {
      ...selectorPayload(selector),
      refresh_codex_status: options.refreshCodexStatus ?? false,
      detail_level: options.includeFull ? "full" : "core",
    },
    workspaceRoot || null,
  );
}

export async function loadProjectReports(bridgeRequest, selector, workspaceRoot) {
  const reports = await bridgeRequest(
    BRIDGE_COMMANDS.LOAD_PROJECT_REPORTS,
    selectorPayload(selector),
    workspaceRoot || null,
  );
  return {
    reports,
    loaded_sections: {
      reports: true,
    },
  };
}

export async function loadProjectWorkspace(bridgeRequest, selector, workspaceRoot) {
  const workspace = await bridgeRequest(
    BRIDGE_COMMANDS.LOAD_PROJECT_WORKSPACE,
    selectorPayload(selector),
    workspaceRoot || null,
  );
  return {
    workspace_tree: Array.isArray(workspace?.workspace_tree) ? workspace.workspace_tree : [],
    loaded_sections: {
      workspace: true,
    },
  };
}

export async function loadProjectCheckpoints(bridgeRequest, selector, workspaceRoot) {
  const checkpoints = await bridgeRequest(
    BRIDGE_COMMANDS.LOAD_PROJECT_CHECKPOINTS,
    selectorPayload(selector),
    workspaceRoot || null,
  );
  return {
    checkpoints,
    loaded_sections: {
      checkpoints: true,
    },
  };
}

export async function loadProjectHistory(bridgeRequest, selector, workspaceRoot) {
  const history = await bridgeRequest(
    BRIDGE_COMMANDS.LOAD_PROJECT_HISTORY,
    selectorPayload(selector),
    workspaceRoot || null,
  );
  return {
    history,
    loaded_sections: {
      history: true,
    },
  };
}

export async function loadHistoryDetail(bridgeRequest, archiveId, workspaceRoot, options = {}) {
  return bridgeRequest(
    BRIDGE_COMMANDS.LOAD_HISTORY_ENTRY,
    {
      archive_id: archiveId,
      detail_level: options.includeFull ? "full" : "core",
    },
    workspaceRoot || null,
  );
}
