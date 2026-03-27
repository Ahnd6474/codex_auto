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
