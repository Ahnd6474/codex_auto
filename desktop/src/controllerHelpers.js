export function messagePayload(tone, text) {
  return text ? { tone, text } : null;
}

export function defaultShareSettings() {
  return {
    bind_host: "127.0.0.1",
    public_base_url: "",
  };
}

export function shareSettingsFromDetail(detail) {
  return {
    bind_host: detail?.share?.server?.config?.bind_host || "127.0.0.1",
    public_base_url: detail?.share?.server?.config?.public_base_url || "",
  };
}

export function emptyPlanDraft() {
  return {
    steps: [],
    project_prompt: "",
    workflow_mode: "standard",
    execution_mode: "serial",
    closeout_status: "not_started",
  };
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
