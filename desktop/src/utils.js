export function cloneValue(value) {
  if (value === null || value === undefined) {
    return value;
  }
  return JSON.parse(JSON.stringify(value));
}

export function basename(path) {
  return String(path || "")
    .split(/[\\/]/)
    .filter(Boolean)
    .pop() || "";
}

export function deriveGithubMode(originUrl) {
  return originUrl ? "manual" : "existing";
}

export function blankProjectForm(defaultRuntime) {
  return {
    project_dir: "",
    display_name: "",
    branch: "main",
    origin_url: "",
    github_mode: "existing",
    runtime: {
      ...(cloneValue(defaultRuntime) || {}),
      max_blocks: defaultRuntime?.max_blocks || 5,
      test_cmd: defaultRuntime?.test_cmd || "python -m pytest",
    },
  };
}

export function projectFormFromDetail(detail, defaultRuntime) {
  return {
    project_dir: detail?.project?.repo_path || "",
    display_name: detail?.project?.display_name || detail?.project?.slug || "",
    branch: detail?.project?.branch || "main",
    origin_url: detail?.project?.origin_url || "",
    github_mode: deriveGithubMode(detail?.project?.origin_url),
    runtime: {
      ...(cloneValue(defaultRuntime) || {}),
      ...(cloneValue(detail?.runtime) || {}),
    },
  };
}

export function buildProjectPayload(form, plan = null) {
  const payload = {
    project_dir: form.project_dir.trim(),
    display_name: form.display_name.trim(),
    branch: form.branch.trim() || "main",
    origin_url: form.github_mode === "manual" ? form.origin_url.trim() : "",
    runtime: cloneValue(form.runtime) || {},
  };
  if (plan) {
    payload.plan = cloneValue(plan);
  }
  return payload;
}

export function firstSelectableStepId(plan) {
  const steps = plan?.steps || [];
  const pending = steps.find((step) => step.status !== "completed");
  return pending?.step_id || steps[0]?.step_id || "";
}

export function runtimeSummary(runtime, modelPresets) {
  const preset = modelPresets.find((item) => item.preset_id === runtime?.model_preset);
  if (preset) {
    return preset.summary;
  }
  if (runtime?.model) {
    return `Saved custom model ${runtime.model} | reasoning ${runtime.effort || "high"}`;
  }
  return "No model selected";
}

export function progressCaption(plan) {
  const steps = plan?.steps || [];
  const completed = steps.filter((step) => step.status === "completed").length;
  const total = steps.length;
  if (!total) {
    return "No plan yet";
  }
  if (completed === total) {
    if (plan?.closeout_status === "completed") {
      return `Completed ${completed}/${total} steps, closeout completed`;
    }
    if (plan?.closeout_status === "running") {
      return `Completed ${completed}/${total} steps, closeout running`;
    }
    if (plan?.closeout_status === "failed") {
      return `Completed ${completed}/${total} steps, closeout failed`;
    }
    return `Completed ${completed}/${total} steps, closeout pending`;
  }
  const nextStep = steps.find((step) => step.status !== "completed");
  return `Completed ${completed}/${total} steps, next: ${nextStep?.step_id || "done"}`;
}

export function canEditStep(step, busy) {
  return Boolean(step) && step.status === "pending" && !busy;
}

export function commandLabel(command) {
  switch (command) {
    case "generate-plan":
      return "Generate Plan";
    case "run-plan":
      return "Run Remaining Steps";
    case "run-closeout":
      return "Run Closeout";
    default:
      return String(command || "Background Job")
        .split("-")
        .join(" ");
  }
}

export function statusTone(status) {
  if (String(status || "").includes("failed")) {
    return "danger";
  }
  if (String(status || "").includes("running")) {
    return "info";
  }
  if (String(status || "") === "completed") {
    return "success";
  }
  if (String(status || "").includes("paused")) {
    return "warning";
  }
  return "neutral";
}
