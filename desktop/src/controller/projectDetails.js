import { BRIDGE_COMMANDS } from "../bridgeProtocol.js";
import { cloneValue } from "../utils.js";

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
  const core = await loadProjectCore(bridgeRequest, selector, workspaceRoot, {
    refreshCodexStatus: options.refreshCodexStatus ?? false,
  });
  if (!options.includeFull) {
    return core;
  }

  const [history, reports, config, workspace, checkpoints, share] = await Promise.all([
    bridgeRequest(BRIDGE_COMMANDS.LOAD_PROJECT_HISTORY, selectorPayload(selector), workspaceRoot || null),
    bridgeRequest(BRIDGE_COMMANDS.LOAD_PROJECT_REPORTS, selectorPayload(selector), workspaceRoot || null),
    bridgeRequest(BRIDGE_COMMANDS.LOAD_PROJECT_CONFIG, selectorPayload(selector), workspaceRoot || null),
    bridgeRequest(BRIDGE_COMMANDS.LOAD_PROJECT_WORKSPACE, selectorPayload(selector), workspaceRoot || null),
    bridgeRequest(BRIDGE_COMMANDS.LOAD_PROJECT_CHECKPOINTS, selectorPayload(selector), workspaceRoot || null),
    bridgeRequest(BRIDGE_COMMANDS.LOAD_PROJECT_SHARE, selectorPayload(selector), workspaceRoot || null),
  ]);

  const detail = cloneValue(core) || {};
  detail.history = history || { ui_events: [], blocks: [], passes: [], test_runs: [] };
  detail.reports = reports || {};
  detail.config = config || {};
  detail.workspace_tree = workspace?.workspace_tree || [];
  detail.checkpoints = checkpoints || { items: [], pending: null, timeline_markdown: "" };
  detail.share = share?.share || detail.share || {};
  detail.detail_level = "full";
  return detail;
}
