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

export function planGenerationValidation({ projectDir, prompt, plan }) {
  const normalizedProjectDir = String(projectDir || "").trim();
  if (!normalizedProjectDir) {
    return "prepareProjectFirst";
  }
  const normalizedPrompt = String(prompt || "").trim();
  if (!normalizedPrompt) {
    return "promptRequired";
  }
  const normalizedPlan = plan && typeof plan === "object" ? plan : {};
  return {
    canGenerate: true,
    requiresReplacementConfirmation: Array.isArray(normalizedPlan.steps) && normalizedPlan.steps.length > 0,
  };
}

export function shouldPreserveProjectPrompt(plan) {
  const prompt = String(plan?.project_prompt || "").trim();
  if (!prompt) {
    return false;
  }
  return String(plan?.closeout_status || "not_started").trim().toLowerCase() !== "completed";
}

export function carryProjectPromptDraft(plan) {
  if (!shouldPreserveProjectPrompt(plan)) {
    return emptyPlanDraft();
  }
  const workflowMode = String(plan?.workflow_mode || "standard").trim().toLowerCase() || "standard";
  return {
    ...emptyPlanDraft(),
    project_prompt: String(plan?.project_prompt || ""),
    workflow_mode: workflowMode === "ml" ? "ml" : "standard",
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
  return false;
}

export function nextSidebarTab(currentTab, requestedTab) {
  const current = String(currentTab || "").trim();
  const requested = String(requestedTab || "").trim();
  if (!requested) {
    return "";
  }
  return current === requested ? "" : requested;
}

export function nextRightSidebarState(currentTab, requestedTab, collapsed = false) {
  const current = String(currentTab || "").trim();
  const requested = String(requestedTab || "").trim();
  if (!requested) {
    return {
      tab: current,
      collapsed: Boolean(collapsed),
    };
  }
  if (!collapsed && current === requested) {
    return {
      tab: current,
      collapsed: true,
    };
  }
  return {
    tab: requested,
    collapsed: false,
  };
}
