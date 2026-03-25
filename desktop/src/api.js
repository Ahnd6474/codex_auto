import { invoke as tauriInvoke } from "@tauri-apps/api/core";

export function createBridgeClient(invoke = tauriInvoke) {
  return {
    bridgeRequest(command, payload = null, workspaceRoot = null) {
      return invoke("bridge_request", {
        command,
        payload,
        workspaceRoot,
      });
    },

    startBridgeJob(command, payload = null, workspaceRoot = null) {
      return invoke("start_bridge_job", {
        command,
        payload,
        workspaceRoot,
      });
    },

    getBridgeJob(jobId) {
      return invoke("get_bridge_job", {
        jobId,
      });
    },

    listBridgeJobs() {
      return invoke("list_bridge_jobs");
    },
  };
}

const bridgeClient = createBridgeClient();

export const { bridgeRequest, startBridgeJob, getBridgeJob, listBridgeJobs } = bridgeClient;
