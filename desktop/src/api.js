import { invoke } from "@tauri-apps/api/core";

export async function bridgeRequest(command, payload = null, workspaceRoot = null) {
  return invoke("bridge_request", {
    command,
    payload,
    workspaceRoot,
  });
}

export async function startBridgeJob(command, payload = null, workspaceRoot = null) {
  return invoke("start_bridge_job", {
    command,
    payload,
    workspaceRoot,
  });
}

export async function getBridgeJob(jobId) {
  return invoke("get_bridge_job", {
    jobId,
  });
}

export async function listBridgeJobs() {
  return invoke("list_bridge_jobs");
}
