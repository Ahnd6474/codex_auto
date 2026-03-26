export function messagePayload(tone, text) {
  return text ? { tone, text } : null;
}

export function defaultShareSettings() {
  return {
    bind_host: "0.0.0.0",
  };
}

export function shareSettingsFromDetail(detail) {
  return {
    bind_host: detail?.share?.server?.config?.bind_host || "0.0.0.0",
  };
}

export function emptyPlanDraft() {
  return {
    steps: [],
    project_prompt: "",
    workflow_mode: "standard",
    execution_mode: "parallel",
    closeout_status: "not_started",
  };
}

export async function resolveConfirmation(requestConfirmation, fallbackConfirmation, message) {
  if (typeof requestConfirmation === "function") {
    try {
      const result = await requestConfirmation(message);
      if (result === true || result === false) {
        return result;
      }
    } catch {
      // Fall back to the browser confirm when the native dialog is unavailable.
    }
  }
  if (typeof fallbackConfirmation === "function") {
    try {
      return fallbackConfirmation(message) === true;
    } catch {
      return false;
    }
  }
  return false;
}

export function needsExpandedProjectDetail({
  centerTab,
  sidebarTab,
  bottomCollapsed,
  bottomTab,
}) {
  if (centerTab === "dashboard" || centerTab === "reports" || centerTab === "history") {
    return true;
  }
  if (sidebarTab === "workspace" || sidebarTab === "plans") {
    return true;
  }
  return !bottomCollapsed && bottomTab === "tokens";
}
