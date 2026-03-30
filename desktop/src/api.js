import { invoke as tauriInvoke } from "@tauri-apps/api/core";
import { listen as tauriListen } from "@tauri-apps/api/event";
import { bridgeErrorMessage, parseBridgeError } from "./bridgeProtocol.js";

const DEFAULT_BRIDGE_LOGGER = {
  warn: (...args) => {
    if (globalThis.console && typeof globalThis.console.warn === "function") {
      globalThis.console.warn(...args);
    }
  },
  error: (...args) => {
    if (globalThis.console && typeof globalThis.console.error === "function") {
      globalThis.console.error(...args);
    }
  },
};

function resolveBridgeLogger(rawLogger = null) {
  return {
    warn: rawLogger && typeof rawLogger.warn === "function" ? rawLogger.warn : DEFAULT_BRIDGE_LOGGER.warn,
    error: rawLogger && typeof rawLogger.error === "function" ? rawLogger.error : DEFAULT_BRIDGE_LOGGER.error,
  };
}

function summarizeValue(value) {
  if (value === undefined || value === null) {
    return value;
  }
  if (
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean" ||
    typeof value === "bigint"
  ) {
    return value;
  }
  try {
    return JSON.parse(JSON.stringify(value));
  } catch {
    return String(value);
  }
}

function logBridgeError(logger, component, context = {}) {
  logger.error("[jakal-flow bridge]", component, summarizeValue(context));
}

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
    this.rawError = details.rawError || {};
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

function buildInvokeLogContext(method, command, context = {}, rawError = undefined) {
  return {
    method,
    command,
    reasonCode: String(context.reason_code || context.reasonCode || "").trim(),
    errorType: String(context.type || "").trim(),
    requestId: String(context.request_id || "").trim(),
    rawError: summarizeValue(rawError),
  };
}

async function safeInvoke(invokeFn, command = "", method = "", args = undefined, logger = DEFAULT_BRIDGE_LOGGER) {
  try {
    if (args === undefined) {
      return await invokeFn();
    }
    return await invokeFn(args);
  } catch (error) {
    const payload = parseBridgeError(error);
    const context = {
      ...payload,
      command: String(command || payload.command || "").trim(),
      method: String(method || payload.method || "").trim(),
    };
    const normalizedError = normalizeError(error || "Bridge request failed.", {
      rawError: summarizeValue(error),
      ...context,
    });
    logBridgeError(logger, "invoke_failed", buildInvokeLogContext(method, command, context, error));
    throw normalizedError;
  }
}

export function createBridgeClient(invoke = tauriInvoke, listen = tauriListen, options = {}) {
  const logger = resolveBridgeLogger(options.logger);
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
        logger,
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
        logger,
      );
    },

    getBridgeJob(jobId) {
      return safeInvoke(
        (invocation) => invoke("get_bridge_job", invocation),
        "",
        "get_bridge_job",
        { jobId },
        logger,
      );
    },

    listBridgeJobs() {
      return safeInvoke(() => invoke("list_bridge_jobs"), "", "list_bridge_jobs", undefined, logger);
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
        logger,
      );
    },

    cancelBridgeJob(jobId) {
      return safeInvoke(
        (invocation) => invoke("cancel_bridge_job", invocation),
        "",
        "cancel_bridge_job",
        { jobId },
        logger,
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
