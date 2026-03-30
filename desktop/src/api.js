import { invoke as tauriInvoke } from "@tauri-apps/api/core";
import { listen as tauriListen } from "@tauri-apps/api/event";
import { bridgeErrorMessage, parseBridgeError } from "./bridgeProtocol.js";

export class BridgeApiError extends Error {
  constructor(message, details = {}) {
    super(message);
    this.name = "BridgeApiError";
    this.reasonCode = String(details.reason_code || details.reasonCode || "").trim() || null;
    this.errorType = String(details.type || "").trim() || null;
    this.command = String(details.command || "").trim() || null;
    this.method = String(details.method || "").trim() || null;
    this.requestId = String(details.request_id || "").trim() || null;
    this.recoverable = Object.prototype.hasOwnProperty.call(details, "recoverable")
      ? details.recoverable
      : null;
    this.errorDetails = details.details || {};
  }
}

function normalizeError(error, context = {}) {
  const payload = parseBridgeError(error);
  return new BridgeApiError(
    bridgeErrorMessage(error, "Bridge request failed."),
    {
      ...payload,
      ...context,
    },
  );
}

async function safeInvoke(invokeFn, command = "", method = "", args = {}) {
  try {
    return await invokeFn(args);
  } catch (error) {
    const payload = parseBridgeError(error);
    const context = {
      ...payload,
      command: String(command || payload.command || "").trim(),
      method: String(method || payload.method || "").trim(),
    };
    throw normalizeError(error || "Bridge request failed.", context);
  }
}

export function createBridgeClient(invoke = tauriInvoke, listen = tauriListen) {
  return {
    bridgeRequest(command, payload = null, workspaceRoot = null) {
      return safeInvoke(
        (invocation) => invoke("bridge_request", invocation),
        command,
        "bridge_request",
        {
          command,
          payload,
          workspaceRoot,
        },
      );
    },

    startBridgeJob(command, payload = null, workspaceRoot = null) {
      return safeInvoke(
        (invocation) => invoke("start_bridge_job", invocation),
        command,
        "start_bridge_job",
        {
          command,
          payload,
          workspaceRoot,
        },
      );
    },

    getBridgeJob(jobId) {
      return safeInvoke(
        (invocation) => invoke("get_bridge_job", invocation),
        "",
        "get_bridge_job",
        { jobId },
      );
    },

    listBridgeJobs() {
      return safeInvoke((invocation) => invoke("list_bridge_jobs", invocation), "", "list_bridge_jobs", {});
    },

    configureBridgeScheduler(maxConcurrentJobs, workspaceRoot = null) {
      return safeInvoke(
        (invocation) => invoke("configure_bridge_scheduler", invocation),
        "",
        "configure_bridge_scheduler",
        {
          maxConcurrentJobs,
          workspaceRoot,
        },
      );
    },

    cancelBridgeJob(jobId) {
      return safeInvoke(
        (invocation) => invoke("cancel_bridge_job", invocation),
        "",
        "cancel_bridge_job",
        { jobId },
      );
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

export async function openInSystem(path) {
  return tauriInvoke("open_in_system", { path });
}

export async function openInVsCode(path) {
  return tauriInvoke("open_in_vscode", { path });
}

export function openUrl(url) {
  if (url) window.open(url, "_blank", "noopener");
}
