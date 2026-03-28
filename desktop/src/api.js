import { invoke as tauriInvoke } from "@tauri-apps/api/core";
import { listen as tauriListen } from "@tauri-apps/api/event";

export function createBridgeClient(invoke = tauriInvoke, listen = tauriListen) {
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

    configureBridgeScheduler(maxConcurrentJobs, workspaceRoot = null) {
      return invoke("configure_bridge_scheduler", {
        maxConcurrentJobs,
        workspaceRoot,
      });
    },

    cancelBridgeJob(jobId) {
      return invoke("cancel_bridge_job", {
        jobId,
      });
    },

    subscribeBridgeEvents(handler) {
      return listen("jakal-flow://bridge-event", (event) => {
        handler(event?.payload || null);
      });
    },
  };
}

const bridgeClient = createBridgeClient();

export const {
  bridgeRequest,
  startBridgeJob,
  getBridgeJob,
  listBridgeJobs,
  configureBridgeScheduler,
  cancelBridgeJob,
  subscribeBridgeEvents,
} = bridgeClient;
