import { normalizeLanguage, translate } from "./locale.js";

export function cloneValue(value) {
  if (value === null || value === undefined) {
    return value;
  }
  if (typeof globalThis.structuredClone === "function") {
    return globalThis.structuredClone(value);
  }
  return JSON.parse(JSON.stringify(value));
}

export const REASONING_OPTIONS = ["low", "medium", "high", "xhigh"];

export function reasoningEffortLabel(value, language = "en") {
  const normalized = String(value || "").trim().toLowerCase();
  const locale = normalizeLanguage(language);
  if (!normalized) {
    return translate(locale, "reasoning.high");
  }
  return translate(locale, `reasoning.${normalized}`);
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

export function runtimeSummary(runtime, modelPresets = [], language = "en") {
  const preset = modelPresets.find((item) => item.preset_id === runtime?.model_preset);
  if (preset) {
    return preset.summary;
  }
  if (runtime?.model) {
    if (normalizeLanguage(language) === "ko") {
      return translate("ko", "runtime.modelSummary", {
        model: runtime.model,
        effort: reasoningEffortLabel(runtime.effort || "high", "ko"),
      });
    }
    return `${runtime.model} | reasoning ${runtime.effort || "high"}`;
  }
  return translate(language, "runtime.noModelSelected");
}

export function progressCaption(plan, language = "en") {
  const steps = plan?.steps || [];
  const completed = steps.filter((step) => step.status === "completed").length;
  const total = steps.length;
  const locale = normalizeLanguage(language);
  if (!total) {
    return locale === "ko" ? "아직 계획이 없습니다" : "No plan yet";
  }
  if (completed === total) {
    if (plan?.closeout_status === "completed") {
      return locale === "ko"
        ? `${completed}/${total}단계 완료, 마감 완료`
        : `Completed ${completed}/${total} steps, closeout completed`;
    }
    if (plan?.closeout_status === "running") {
      return locale === "ko"
        ? `${completed}/${total}단계 완료, 마감 실행 중`
        : `Completed ${completed}/${total} steps, closeout running`;
    }
    if (plan?.closeout_status === "failed") {
      return locale === "ko"
        ? `${completed}/${total}단계 완료, 마감 실패`
        : `Completed ${completed}/${total} steps, closeout failed`;
    }
    return locale === "ko"
      ? `${completed}/${total}단계 완료, 마감 대기`
      : `Completed ${completed}/${total} steps, closeout pending`;
  }
  const nextStep = steps.find((step) => step.status !== "completed");
  return locale === "ko"
    ? `${completed}/${total}단계 완료, 다음: ${nextStep?.step_id || "완료"}`
    : `Completed ${completed}/${total} steps, next: ${nextStep?.step_id || "done"}`;
}

export function canEditStep(step, busy) {
  return Boolean(step) && step.status === "pending" && !busy;
}

export function commandLabel(command, language = "en") {
  const locale = normalizeLanguage(language);
  switch (command) {
    case "generate-plan":
      return translate(locale, "action.generatePlan");
    case "run-plan":
      return translate(locale, "action.runRemaining");
    case "run-closeout":
      return translate(locale, "action.closeout");
    default:
      return String(command || (locale === "ko" ? "백그라운드 작업" : "Background Job"))
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
