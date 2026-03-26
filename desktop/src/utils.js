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

export const AUTO_REASONING_OPTION = "auto";
export const REASONING_OPTIONS = ["low", "medium", "high", "xhigh"];
export const MODEL_REASONING_OPTIONS = [AUTO_REASONING_OPTION, ...REASONING_OPTIONS];
export const PROGRAM_RUNTIME_KEYS = [
  "approval_mode",
  "sandbox_mode",
  "checkpoint_interval_blocks",
  "codex_path",
  "allow_push",
  "require_checkpoint_approval",
  "execution_mode",
  "parallel_workers",
];
export const PROGRAM_UI_KEYS = ["ui_theme"];

const DEFAULT_PROGRAM_RUNTIME = {
  approval_mode: "never",
  sandbox_mode: "danger-full-access",
  checkpoint_interval_blocks: 1,
  codex_path: "codex.cmd",
  allow_push: true,
  require_checkpoint_approval: false,
  execution_mode: "serial",
  parallel_workers: 2,
};
const DEFAULT_PROGRAM_UI = {
  ui_theme: "dark",
  developer_mode: false,
};

export function reasoningEffortLabel(value, language = "en") {
  const normalized = String(value || "").trim().toLowerCase();
  const locale = normalizeLanguage(language);
  if (normalized === AUTO_REASONING_OPTION) {
    return translate(locale, "reasoning.auto");
  }
  if (!normalized) {
    return translate(locale, "reasoning.high");
  }
  return translate(locale, `reasoning.${normalized}`);
}

export function autoRoutingPresetLabel(value, language = "en") {
  const normalized = String(value || "").trim().toLowerCase();
  const locale = normalizeLanguage(language);
  switch (normalized) {
    case AUTO_REASONING_OPTION:
      return translate(locale, "preset.auto");
    case "low":
      return translate(locale, "preset.lowOnly");
    case "medium":
      return translate(locale, "preset.mediumOnly");
    case "high":
      return translate(locale, "preset.highOnly");
    case "xhigh":
      return translate(locale, "preset.xhighOnly");
    default:
      return reasoningEffortLabel(normalized, locale);
  }
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

export function programSettingsFromRuntime(runtime) {
  const source = cloneValue(runtime) || {};
  const settings = { ...DEFAULT_PROGRAM_RUNTIME, ...DEFAULT_PROGRAM_UI };
  [...PROGRAM_RUNTIME_KEYS, ...PROGRAM_UI_KEYS].forEach((key) => {
    if (source[key] !== undefined) {
      settings[key] = source[key];
    }
  });
  return settings;
}

export function applyProgramSettings(runtime, programSettings) {
  const normalizedSettings = programSettingsFromRuntime(programSettings);
  const runtimeSettings = PROGRAM_RUNTIME_KEYS.reduce((settings, key) => {
    if (normalizedSettings[key] !== undefined) {
      settings[key] = normalizedSettings[key];
    }
    return settings;
  }, {});
  return {
    ...(cloneValue(runtime) || {}),
    ...runtimeSettings,
  };
}

export function applyProgramSettingsToForm(form, programSettings) {
  return {
    ...(cloneValue(form) || {}),
    runtime: applyProgramSettings(form?.runtime, programSettings),
  };
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

function normalizeModelCatalog(value, fallback = []) {
  return Array.isArray(value) ? value : fallback;
}

export function mergeProjectDetailCodexStatus(detail, fallbackCodexStatus = null, fallbackModelCatalog = []) {
  if (!detail) {
    return detail;
  }
  const nextCodexStatus =
    detail?.codex_status && Array.isArray(detail.codex_status.model_catalog)
      ? detail.codex_status
      : fallbackCodexStatus
        ? {
            ...fallbackCodexStatus,
            ...(detail?.codex_status || {}),
            model_catalog: normalizeModelCatalog(fallbackCodexStatus.model_catalog, fallbackModelCatalog),
          }
        : {
            ...(detail?.codex_status || {}),
            model_catalog: normalizeModelCatalog(detail?.codex_status?.model_catalog, fallbackModelCatalog),
          };
  return {
    ...detail,
    codex_status: nextCodexStatus,
    snapshot: detail?.snapshot
      ? {
          ...detail.snapshot,
          codex_status: nextCodexStatus,
        }
      : detail.snapshot,
    bottom_panels: detail?.bottom_panels
      ? {
          ...detail.bottom_panels,
          codex_status:
            detail.bottom_panels.codex_status && Array.isArray(detail.bottom_panels.codex_status.model_catalog)
              ? detail.bottom_panels.codex_status
              : nextCodexStatus,
        }
      : detail.bottom_panels,
  };
}

export function shouldKeepUnsavedPlan(currentProjectId, nextProjectId, planDirty) {
  if (!planDirty) {
    return false;
  }
  const current = String(currentProjectId || "").trim();
  const next = String(nextProjectId || "").trim();
  return Boolean(current) && current === next;
}

export function shouldReplaceVisibleProject(selectedProjectId, nextProjectId) {
  const selected = String(selectedProjectId || "").trim();
  const next = String(nextProjectId || "").trim();
  if (!next) {
    return false;
  }
  return !selected || selected === next;
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
    const nextPlan = cloneValue(plan) || {};
    const executionMode = String(payload.runtime?.execution_mode || nextPlan.execution_mode || "serial")
      .trim()
      .toLowerCase();
    nextPlan.execution_mode = executionMode === "parallel" ? "parallel" : "serial";
    nextPlan.default_test_command = nextPlan.default_test_command || payload.runtime?.test_cmd || "python -m pytest";
    payload.plan = nextPlan;
  }
  return payload;
}

export function findModelCatalogEntry(modelCatalog = [], model = "") {
  const target = String(model || "").trim().toLowerCase();
  return modelCatalog.find((item) => String(item?.model || "").trim().toLowerCase() === target) || null;
}

export function supportedReasoningOptions(modelCatalog = [], model = "", fallback = "medium") {
  const entry = findModelCatalogEntry(modelCatalog, model);
  const options = (entry?.supported_reasoning_efforts || []).filter((effort) => REASONING_OPTIONS.includes(effort));
  if (options.length) {
    return options;
  }
  return REASONING_OPTIONS.includes(fallback) ? [fallback] : ["medium"];
}

export function defaultReasoningOption(modelCatalog = [], model = "", fallback = "medium") {
  const entry = findModelCatalogEntry(modelCatalog, model);
  const preferred = String(entry?.default_reasoning_effort || fallback || "medium").trim().toLowerCase();
  const options = supportedReasoningOptions(modelCatalog, model, preferred);
  return options.includes(preferred) ? preferred : options[0] || "medium";
}

export function configReasoningOptions(modelCatalog = [], model = "", fallback = "medium") {
  const supported = supportedReasoningOptions(modelCatalog, model, fallback);
  return [AUTO_REASONING_OPTION, ...supported];
}

export function selectedConfigReasoning(modelCatalog = [], runtime = {}) {
  const model = String(runtime?.model || "").trim().toLowerCase() || "auto";
  const options = configReasoningOptions(modelCatalog, model, runtime?.effort || "medium");
  if (String(runtime?.effort_selection_mode || "").trim().toLowerCase() === AUTO_REASONING_OPTION && options.includes(AUTO_REASONING_OPTION)) {
    return AUTO_REASONING_OPTION;
  }
  if (model === "auto") {
    const preset = String(runtime?.model_preset || "").trim().toLowerCase();
    if (options.includes(preset)) {
      return preset;
    }
  }
  const preferred = String(runtime?.effort || "").trim().toLowerCase() || defaultReasoningOption(modelCatalog, model, "medium");
  if (options.includes(preferred)) {
    return preferred;
  }
  return options[0] || "medium";
}

export function modelDisplayName(modelCatalog = [], model = "") {
  const entry = findModelCatalogEntry(modelCatalog, model);
  return entry?.display_name || model || "auto";
}

function findRateLimitItem(rateLimits = [], matcher) {
  return (
    rateLimits.find((item) => {
      const haystack = `${item?.limit_id || ""} ${item?.limit_name || ""}`.trim().toLowerCase();
      return matcher(haystack, item);
    }) || null
  );
}

export function codexUsageBuckets(codexStatus = {}, language = "en") {
  const rateLimits = codexStatus?.rate_limits?.items || [];
  const defaultLimitId = String(codexStatus?.rate_limits?.default_limit_id || "").trim().toLowerCase();
  const defaultItem =
    findRateLimitItem(rateLimits, (_haystack, item) => String(item?.limit_id || "").trim().toLowerCase() === defaultLimitId) ||
    findRateLimitItem(rateLimits, (haystack) => haystack.includes("codex")) ||
    rateLimits[0] ||
    null;
  const sparkItem = findRateLimitItem(rateLimits, (haystack) => haystack.includes("spark"));
  return [
    {
      key: "window_5h",
      label: translate(language, "usage.window5h"),
      window: defaultItem?.primary || null,
    },
    {
      key: "window_7d",
      label: translate(language, "usage.window7d"),
      window: defaultItem?.secondary || null,
    },
    {
      key: "codex_spark",
      label: translate(language, "usage.codexSpark"),
      window: sparkItem?.primary || sparkItem?.secondary || null,
    },
  ];
}

export function rateLimitRemainingLabel(window, language = "en") {
  if (!window) {
    return translate(language, "common.unavailable");
  }
  return `${window.remaining_percent ?? 0}%`;
}

export function rateLimitWindowSummary(window, language = "en") {
  if (!window) {
    return translate(language, "common.unavailable");
  }
  return translate(language, "usage.windowSummary", {
    used: window.used_percent ?? 0,
    remaining: window.remaining_percent ?? 0,
    resetsAt: window.resets_at || translate(language, "common.unavailable"),
  });
}

export function firstSelectableStepId(plan) {
  const steps = plan?.steps || [];
  const pending = steps.find((step) => step.status !== "completed");
  return pending?.step_id || steps[0]?.step_id || "";
}

export function runtimeSummary(runtime, modelPresets = [], language = "en", modelCatalog = []) {
  const executionSuffix =
    String(runtime?.execution_mode || "serial").trim().toLowerCase() === "parallel"
      ? ` | parallel x${Math.max(1, Number.parseInt(String(runtime?.parallel_workers || 2), 10) || 1)}`
      : " | serial";
  const preset = modelPresets.find((item) => item.preset_id === runtime?.model_preset);
  if (preset) {
    const summary = `${preset.summary}${executionSuffix}`;
    return runtime?.use_fast_mode ? `${summary} | /fast` : summary;
  }
  if (runtime?.model) {
    const label = modelDisplayName(modelCatalog, runtime.model);
    const effortLabel =
      String(runtime?.effort_selection_mode || "").trim().toLowerCase() === AUTO_REASONING_OPTION
        ? reasoningEffortLabel(AUTO_REASONING_OPTION, language)
        : reasoningEffortLabel(runtime.effort || "high", language);
    if (normalizeLanguage(language) === "ko") {
      const summary = translate("ko", "runtime.modelSummary", {
        model: label,
        effort: effortLabel,
      });
      const nextSummary = `${summary}${executionSuffix}`;
      return runtime?.use_fast_mode ? `${nextSummary} | /fast` : nextSummary;
    }
    const summary = `${label} | reasoning ${effortLabel}${executionSuffix}`;
    return runtime?.use_fast_mode ? `${summary} | /fast` : summary;
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

export function executionProgressCaption(plan, language = "en") {
  const steps = plan?.steps || [];
  const completed = steps.filter((step) => step.status === "completed").length;
  const total = steps.length;
  const locale = normalizeLanguage(language);
  if (!total) {
    return locale === "ko" ? "아직 계획이 없습니다" : "No plan yet";
  }
  if (completed === total) {
    if (plan?.closeout_status === "completed") {
      return locale === "ko" ? `${completed}/${total}단계 완료, 마감 완료` : `Completed ${completed}/${total} steps, closeout completed`;
    }
    if (plan?.closeout_status === "running") {
      return locale === "ko" ? `${completed}/${total}단계 완료, 마감 진행 중` : `Completed ${completed}/${total} steps, closeout running`;
    }
    if (plan?.closeout_status === "failed") {
      return locale === "ko" ? `${completed}/${total}단계 완료, 마감 실패` : `Completed ${completed}/${total} steps, closeout failed`;
    }
    return locale === "ko" ? `${completed}/${total}단계 완료, 마감 대기` : `Completed ${completed}/${total} steps, closeout pending`;
  }
  const usesDag =
    String(plan?.execution_mode || "serial").trim().toLowerCase() === "parallel" &&
    steps.some((step) => (step?.depends_on || []).length || (step?.owned_paths || []).length);
  if (usesDag) {
    const completedIds = new Set(steps.filter((step) => step.status === "completed").map((step) => step.step_id));
    const readyIds = steps
      .filter(
        (step) =>
          step.status !== "completed" &&
          (step.depends_on || []).every((dependency) => completedIds.has(dependency)),
      )
      .map((step) => step.step_id);
    return locale === "ko"
      ? `${completed}/${total}단계 완료, 실행 가능: ${readyIds.join(", ") || "blocked"}`
      : `Completed ${completed}/${total} steps, ready: ${readyIds.join(", ") || "blocked"}`;
  }
  const nextStep = steps.find((step) => step.status !== "completed");
  return locale === "ko" ? `${completed}/${total}단계 완료, 다음: ${nextStep?.step_id || "완료"}` : `Completed ${completed}/${total} steps, next: ${nextStep?.step_id || "done"}`;
}

export function canEditStep(step, busy) {
  return Boolean(step) && step.status === "pending" && !busy;
}

export function toolbarProgressCaption(plan) {
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
  const usesDag =
    String(plan?.execution_mode || "serial").trim().toLowerCase() === "parallel" &&
    steps.some((step) => (step?.depends_on || []).length || (step?.owned_paths || []).length);
  if (usesDag) {
    const completedIds = new Set(steps.filter((step) => step.status === "completed").map((step) => step.step_id));
    const readyIds = steps
      .filter(
        (step) =>
          step.status !== "completed" &&
          (step.depends_on || []).every((dependency) => completedIds.has(dependency)),
      )
      .map((step) => step.step_id);
    return `Completed ${completed}/${total} steps, ready: ${readyIds.join(", ") || "blocked"}`;
  }
  const nextStep = steps.find((step) => step.status !== "completed");
  return `Completed ${completed}/${total} steps, next: ${nextStep?.step_id || "done"}`;
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
