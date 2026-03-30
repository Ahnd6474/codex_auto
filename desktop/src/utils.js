import { displayStatus, normalizeLanguage, translate } from "./locale.js";

export function defaultCodexPath(provider = "openai") {
  const normalizedProvider = String(provider || "").trim().toLowerCase();
  if (normalizedProvider === "claude" || normalizedProvider === "deepseek" || normalizedProvider === "minimax" || normalizedProvider === "glm") {
    const platform = String(globalThis.process?.platform || "").trim().toLowerCase();
    if (platform === "win32") {
      return "claude.cmd";
    }
    const userAgent = String(globalThis.navigator?.userAgent || "").toLowerCase();
    if (userAgent.includes("windows")) {
      return "claude.cmd";
    }
    return "claude";
  }
  if (normalizedProvider === "gemini") {
    const platform = String(globalThis.process?.platform || "").trim().toLowerCase();
    if (platform === "win32") {
      return "gemini.cmd";
    }
    const userAgent = String(globalThis.navigator?.userAgent || "").toLowerCase();
    if (userAgent.includes("windows")) {
      return "gemini.cmd";
    }
    return "gemini";
  }
  if (normalizedProvider === "qwen_code") {
    const platform = String(globalThis.process?.platform || "").trim().toLowerCase();
    if (platform === "win32") {
      return "qwen.cmd";
    }
    const userAgent = String(globalThis.navigator?.userAgent || "").toLowerCase();
    if (userAgent.includes("windows")) {
      return "qwen.cmd";
    }
    return "qwen";
  }
  const platform = String(globalThis.process?.platform || "").trim().toLowerCase();
  if (platform === "win32") {
    return "codex.cmd";
  }
  const userAgent = String(globalThis.navigator?.userAgent || "").toLowerCase();
  if (userAgent.includes("windows")) {
    return "codex.cmd";
  }
  return "codex";
}

export function cloneValue(value) {
  if (value === null || value === undefined) {
    return value;
  }
  if (typeof globalThis.structuredClone === "function") {
    return globalThis.structuredClone(value);
  }
  return JSON.parse(JSON.stringify(value));
}

export function normalizeProjectPath(value = "") {
  const text = String(value || "").trim();
  if (!text) {
    return "";
  }
  const normalized = text.replace(/\\/g, "/").replace(/\/+/g, "/");
  return normalized.toLowerCase();
}

export function backgroundJobProjectKey(payload = null, workspaceRoot = "") {
  const repoId = String(payload?.repo_id || "").trim();
  const projectDir = normalizeProjectPath(payload?.project_dir || "");
  if (!repoId && !projectDir) {
    return "";
  }
  return [
    normalizeProjectPath(workspaceRoot),
    repoId,
    projectDir,
  ].join("|");
}

export function isDuplicateProjectJobError(error = null) {
  return String(error || "").trim().toLowerCase().includes("already active for this project");
}

export function jobMatchesProject(job = null, project = {}) {
  if (!job || !project) {
    return false;
  }
  const jobRepoId = String(job?.repo_id || "").trim();
  const projectRepoId = String(project?.repo_id || "").trim();
  if (jobRepoId && projectRepoId && jobRepoId === projectRepoId) {
    return true;
  }
  const jobProjectDir = normalizeProjectPath(job?.project_dir || "");
  const projectDir = normalizeProjectPath(project?.project_dir || project?.repo_path || "");
  return Boolean(jobProjectDir) && Boolean(projectDir) && jobProjectDir === projectDir;
}

export function projectJobFromJobs(jobs = [], project = {}) {
  const jobItems = Array.isArray(jobs) ? jobs.filter(Boolean) : [];
  const statusRank = {
    running: 0,
    queued: 1,
  };
  const matches = jobItems.filter((job) => jobMatchesProject(job, project));
  if (!matches.length) {
    return null;
  }
  const candidates = matches.filter((job) => !jobIsSupersededByProject(job, project));
  if (!candidates.length) {
    return null;
  }
  return [...candidates].sort((left, right) => {
    const leftRank = statusRank[String(left?.status || "").trim().toLowerCase()] ?? 9;
    const rightRank = statusRank[String(right?.status || "").trim().toLowerCase()] ?? 9;
    if (leftRank !== rightRank) {
      return leftRank - rightRank;
    }
    return (Number(right?.updated_at_ms || 0) || 0) - (Number(left?.updated_at_ms || 0) || 0);
  })[0] || null;
}

export function jobHasNewerActiveReplacement(job = null, jobs = []) {
  const targetJobId = String(job?.id || "").trim();
  if (!targetJobId) {
    return false;
  }
  const replacement = projectJobFromJobs(jobs, {
    repo_id: job?.repo_id,
    project_dir: job?.project_dir,
  });
  if (!replacement || String(replacement?.id || "").trim() === targetJobId) {
    return false;
  }
  return ["queued", "running"].includes(String(replacement?.status || "").trim().toLowerCase());
}

export function isChatCommand(command = "") {
  return String(command || "").trim().toLowerCase() === "send-chat-message";
}

export function visibleExecutionJob(job = null) {
  if (!job || isChatCommand(job?.command)) {
    return null;
  }
  return job;
}

export function isActiveExecutionStatus(status = "") {
  const normalized = String(status || "").trim().toLowerCase();
  return normalized === "running"
    || normalized.startsWith("running:")
    || normalized === "queued"
    || normalized.startsWith("queued:");
}

export function projectStatusWithJob(status = "", activeJob = null) {
  const job = visibleExecutionJob(activeJob);
  const currentStatus = String(status || "").trim();
  const jobStatus = String(job?.status || "").trim().toLowerCase();
  const command = String(job?.command || "").trim() || "background-job";
  if (jobStatus === "queued") {
    return `queued:${command}`;
  }
  if (jobStatus === "running" && !currentStatus.toLowerCase().startsWith("running:")) {
    return `running:${command}`;
  }
  return currentStatus;
}

export function detailApplySignature(detail = null, runningJob = null) {
  return [
    String(detail?.project?.repo_id || "").trim(),
    String(detail?.detail_level || "").trim(),
    String(detail?.detail_signature || detail?.content_signature || "").trim(),
    String(detail?.project?.current_status || "").trim(),
    String(runningJob?.id || "").trim(),
    String(runningJob?.status || "").trim(),
  ].join("|");
}

export const AUTO_REASONING_OPTION = "auto";
export const REASONING_OPTIONS = ["low", "medium", "high", "xhigh"];
export const MODEL_REASONING_OPTIONS = [AUTO_REASONING_OPTION, ...REASONING_OPTIONS];
export const MODEL_PROVIDER_OPTIONS = ["openai", "ensemble", "claude", "gemini", "ollama", "qwen_code", "deepseek", "kimi", "minimax", "glm", "openrouter", "opencdk", "local_openai", "oss"];
export const PROGRAM_RUNTIME_KEYS = [
  "model_provider",
  "local_model_provider",
  "chat_model_provider",
  "chat_local_model_provider",
  "provider_base_url",
  "provider_api_key_env",
  "ensemble_openai_model",
  "ensemble_gemini_model",
  "ensemble_claude_model",
  "model",
  "chat_model",
  "chat_effort",
  "planning_effort",
  "model_preset",
  "model_selection_mode",
  "model_slug_input",
  "approval_mode",
  "sandbox_mode",
  "checkpoint_interval_blocks",
  "codex_path",
  "allow_push",
  "require_checkpoint_approval",
  "workflow_mode",
  "ml_max_cycles",
  "execution_mode",
  "parallel_worker_mode",
  "parallel_workers",
  "parallel_memory_per_worker_gib",
  "save_project_logs",
];
export const DEFAULT_DASHBOARD_VISIBILITY = Object.freeze({
  status: true,
  remaining_steps: true,
  checkpoint_pending: false,
  input_tokens: false,
  output_tokens: false,
  estimated_remaining: true,
  estimated_cost: false,
  actual_cost: false,
  codex_plan: false,
  rate_limit_window_5h: false,
  rate_limit_window_7d: true,
  rate_limit_codex_spark: false,
  runtime_card: false,
  codex_usage_card: false,
  word_report_card: true,
});
export const PROGRAM_UI_KEYS = ["ui_theme", "developer_mode", "dashboard_visibility", "background_concurrency_limit"];
export const CLAUDE_DEFAULT_MODEL = "claude-sonnet-4-6";
export const GEMINI_DEFAULT_MODEL = "gemini-3-flash-preview";
export const QWEN_CODE_DEFAULT_MODEL = "qwen3-coder-plus";
export const DEEPSEEK_DEFAULT_MODEL = "deepseek-chat";
export const KIMI_DEFAULT_MODEL = "kimi-k2.5";
export const MINIMAX_DEFAULT_MODEL = "MiniMax-M2.5";
export const GLM_DEFAULT_MODEL = "glm-4.7";

const LEGACY_DASHBOARD_VISIBILITY_ALIASES = Object.freeze({
  rate_limit_window_5h: "rate_limits",
  rate_limit_window_7d: "rate_limits",
  rate_limit_codex_spark: "rate_limits",
});

const DEFAULT_PROGRAM_RUNTIME = {
  model_provider: "openai",
  local_model_provider: "ollama",
  chat_model_provider: "",
  chat_local_model_provider: "",
  provider_base_url: "",
  provider_api_key_env: "OPENAI_API_KEY",
  ensemble_openai_model: "gpt-5.4",
  ensemble_gemini_model: GEMINI_DEFAULT_MODEL,
  ensemble_claude_model: CLAUDE_DEFAULT_MODEL,
  model: "gpt-5.4",
  chat_model: "",
  chat_effort: "",
  planning_effort: "medium",
  model_preset: "",
  model_selection_mode: "slug",
  model_slug_input: "gpt-5.4",
  approval_mode: "never",
  sandbox_mode: "danger-full-access",
  checkpoint_interval_blocks: 1,
  codex_path: defaultCodexPath(),
  allow_push: true,
  require_checkpoint_approval: false,
  workflow_mode: "standard",
  ml_max_cycles: 3,
  execution_mode: "parallel",
  parallel_worker_mode: "auto",
  parallel_workers: 0,
  parallel_memory_per_worker_gib: 3,
  save_project_logs: false,
};
const DEFAULT_PROGRAM_UI = {
  ui_theme: "dark",
  developer_mode: false,
  dashboard_visibility: DEFAULT_DASHBOARD_VISIBILITY,
  background_concurrency_limit: 2,
};

function normalizeProgramSettingsProviderSelection(settings = {}) {
  const provider = normalizedModelProvider(settings);
  const localProvider = normalizedLocalModelProvider(settings);
  const normalized = applyProviderDefaults(settings, provider, localProvider);
  return {
    ...normalized,
    model_provider: provider,
    local_model_provider: localProvider,
    provider_base_url: String(normalized?.provider_base_url || defaultProviderBaseUrl(provider)).trim(),
    provider_api_key_env: String(normalized?.provider_api_key_env || defaultProviderApiKeyEnv(provider)).trim(),
    ensemble_openai_model: String(normalized?.ensemble_openai_model || "gpt-5.4").trim().toLowerCase() || "gpt-5.4",
    ensemble_gemini_model: String(normalized?.ensemble_gemini_model || GEMINI_DEFAULT_MODEL).trim().toLowerCase() || GEMINI_DEFAULT_MODEL,
    ensemble_claude_model: String(normalized?.ensemble_claude_model || CLAUDE_DEFAULT_MODEL).trim().toLowerCase() || CLAUDE_DEFAULT_MODEL,
    model: String(normalized?.model || defaultModelForProvider(provider, normalized)).trim().toLowerCase(),
    model_preset: String(normalized?.model_preset || "").trim().toLowerCase(),
    model_selection_mode: String(normalized?.model_selection_mode || "slug").trim().toLowerCase() || "slug",
    model_slug_input: String(normalized?.model_slug_input || normalized?.model || defaultModelForProvider(provider, normalized)).trim(),
  };
}

export function normalizeDashboardVisibility(value) {
  const source = value && typeof value === "object" ? value : {};
  return Object.entries(DEFAULT_DASHBOARD_VISIBILITY).reduce((visibility, [key, fallback]) => {
    const legacyKey = LEGACY_DASHBOARD_VISIBILITY_ALIASES[key];
    const rawValue =
      source[key] !== undefined
        ? source[key]
        : legacyKey && source[legacyKey] !== undefined
          ? source[legacyKey]
          : fallback;
    visibility[key] = Boolean(rawValue);
    return visibility;
  }, {});
}

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
  const normalizedSettings = normalizeProgramSettingsProviderSelection(settings);
  Object.assign(settings, normalizedSettings);
  settings.execution_mode = "parallel";
  settings.dashboard_visibility = normalizeDashboardVisibility(settings.dashboard_visibility);
  settings.background_concurrency_limit = Math.max(1, Number.parseInt(String(settings.background_concurrency_limit || 2), 10) || 2);
  const fallbackModel = defaultModelForProvider(settings.model_provider, settings);
  if (!String(settings.model || "").trim() && fallbackModel) {
    settings.model = fallbackModel;
  }
  if (!String(settings.model_slug_input || "").trim() && fallbackModel) {
    settings.model_slug_input = fallbackModel;
  }
  return settings;
}

function dashboardVisibilityEqual(left = null, right = null) {
  const leftVisibility = normalizeDashboardVisibility(left);
  const rightVisibility = normalizeDashboardVisibility(right);
  return Object.keys(DEFAULT_DASHBOARD_VISIBILITY).every(
    (key) => leftVisibility[key] === rightVisibility[key],
  );
}

export function programSettingsEqual(left = null, right = null) {
  const leftSettings = left && typeof left === "object" ? left : {};
  const rightSettings = right && typeof right === "object" ? right : {};
  for (const key of PROGRAM_RUNTIME_KEYS) {
    if (!Object.is(leftSettings[key], rightSettings[key])) {
      return false;
    }
  }
  for (const key of PROGRAM_UI_KEYS) {
    if (key === "dashboard_visibility") {
      continue;
    }
    if (!Object.is(leftSettings[key], rightSettings[key])) {
      return false;
    }
  }
  return dashboardVisibilityEqual(leftSettings.dashboard_visibility, rightSettings.dashboard_visibility);
}

export function applyProgramSettings(runtime, programSettings) {
  const normalizedSettings = programSettingsFromRuntime(programSettings);
  const runtimeSettings = PROGRAM_RUNTIME_KEYS.reduce((settings, key) => {
    if (normalizedSettings[key] !== undefined) {
      settings[key] = normalizedSettings[key];
    }
    return settings;
  }, {});
  runtimeSettings.execution_mode = "parallel";
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

export function syncProgramSettingsModel(programSettings = {}, runtime = {}) {
  const base = programSettingsFromRuntime(cloneValue(programSettings) || {});
  return {
    ...base,
    model_provider: runtime?.model_provider ?? programSettings?.model_provider ?? base.model_provider,
    local_model_provider: runtime?.local_model_provider ?? programSettings?.local_model_provider ?? base.local_model_provider,
    ensemble_openai_model: runtime?.ensemble_openai_model ?? programSettings?.ensemble_openai_model ?? base.ensemble_openai_model,
    ensemble_gemini_model: runtime?.ensemble_gemini_model ?? programSettings?.ensemble_gemini_model ?? base.ensemble_gemini_model,
    ensemble_claude_model: runtime?.ensemble_claude_model ?? programSettings?.ensemble_claude_model ?? base.ensemble_claude_model,
    model: runtime?.model ?? programSettings?.model ?? base.model,
    model_preset: runtime?.model_preset ?? programSettings?.model_preset ?? base.model_preset,
    model_selection_mode: runtime?.model_selection_mode ?? programSettings?.model_selection_mode ?? base.model_selection_mode,
    model_slug_input: runtime?.model_slug_input ?? programSettings?.model_slug_input ?? base.model_slug_input,
  };
}

export function normalizeMemoryBudgetGiB(value, fallback = 3) {
  const parsed = Number.parseFloat(String(value ?? "").trim());
  const fallbackValue = Number.parseFloat(String(fallback ?? "").trim());
  const normalizedFallback = Number.isFinite(fallbackValue) ? Math.max(0.1, Math.round(fallbackValue * 10) / 10) : 0.1;
  if (!Number.isFinite(parsed)) {
    return normalizedFallback;
  }
  return Math.max(0.1, Math.round(parsed * 10) / 10);
}

function looksLikeClaudeModel(model = "") {
  const normalized = String(model || "").trim().toLowerCase();
  return normalized === "sonnet" || normalized === "opus" || normalized === "haiku" || normalized.startsWith("claude");
}

function providerDefaultModelSlug(provider = "openai") {
  switch (String(provider || "").trim().toLowerCase()) {
    case "qwen_code":
      return QWEN_CODE_DEFAULT_MODEL;
    case "deepseek":
      return DEEPSEEK_DEFAULT_MODEL;
    case "kimi":
      return KIMI_DEFAULT_MODEL;
    case "minimax":
      return MINIMAX_DEFAULT_MODEL;
    case "glm":
      return GLM_DEFAULT_MODEL;
    default:
      return "";
  }
}

function currentModelMatchesProvider(provider = "openai", model = "") {
  const normalizedProvider = String(provider || "").trim().toLowerCase();
  const normalizedModel = String(model || "").trim().toLowerCase();
  if (!normalizedModel) {
    return false;
  }
  if (normalizedProvider === "qwen_code") {
    return normalizedModel.startsWith("qwen");
  }
  if (normalizedProvider === "deepseek") {
    return normalizedModel.startsWith("deepseek");
  }
  if (normalizedProvider === "kimi") {
    return normalizedModel.startsWith("kimi");
  }
  if (normalizedProvider === "minimax") {
    return normalizedModel.includes("minimax");
  }
  if (normalizedProvider === "glm") {
    return normalizedModel.startsWith("glm");
  }
  return false;
}

export function defaultModelForProvider(provider = "openai", runtime = {}) {
  const normalizedProvider = String(provider || "").trim().toLowerCase();
  const currentModel = String(runtime?.model || runtime?.model_slug_input || "").trim().toLowerCase();
  if (normalizedProvider === "claude") {
    const ensembleClaudeModel = String(runtime?.ensemble_claude_model || "").trim().toLowerCase();
    if (normalizedModelProvider(runtime) === "ensemble" && ensembleClaudeModel) {
      return ensembleClaudeModel;
    }
    return looksLikeClaudeModel(currentModel) ? currentModel : CLAUDE_DEFAULT_MODEL;
  }
  if (normalizedProvider === "gemini") {
    const ensembleGeminiModel = String(runtime?.ensemble_gemini_model || "").trim().toLowerCase();
    if (normalizedModelProvider(runtime) === "ensemble" && ensembleGeminiModel) {
      return ensembleGeminiModel;
    }
    return currentModel.startsWith("gemini") ? currentModel : GEMINI_DEFAULT_MODEL;
  }
  if (providerDefaultModelSlug(normalizedProvider)) {
    return currentModelMatchesProvider(normalizedProvider, currentModel)
      ? currentModel
      : providerDefaultModelSlug(normalizedProvider);
  }
  if (normalizedProvider === "ensemble" || normalizedProvider === "openai") {
    const ensembleOpenAiModel = String(runtime?.ensemble_openai_model || "").trim().toLowerCase();
    if (normalizedModelProvider(runtime) === "ensemble" && ensembleOpenAiModel) {
      return ensembleOpenAiModel;
    }
    if (!currentModel) {
      return "gpt-5.4";
    }
    if (currentModel === "auto") {
      return "auto";
    }
    return looksLikeClaudeModel(currentModel) || currentModel.startsWith("gemini") ? "gpt-5.4" : currentModel;
  }
  if (normalizedProvider === "ollama" || normalizedProvider === "oss") {
    return currentModel;
  }
  return currentModel;
}

export function applyProviderDefaults(runtime = {}, nextProvider = "openai", nextLocalProvider = null) {
  const provider = MODEL_PROVIDER_OPTIONS.includes(String(nextProvider || "").trim().toLowerCase())
    ? String(nextProvider || "").trim().toLowerCase()
    : "openai";
  const previousProvider = normalizedModelProvider(runtime);
  const previousModel = String(runtime?.model_slug_input || runtime?.model || "").trim().toLowerCase();
  const nextEnsembleOpenAiModel =
    String(runtime?.ensemble_openai_model || "").trim().toLowerCase()
      || (previousProvider === "openai" && previousModel && previousModel !== "auto" ? previousModel : "gpt-5.4");
  const nextEnsembleGeminiModel =
    String(runtime?.ensemble_gemini_model || "").trim().toLowerCase()
      || (previousProvider === "gemini" && previousModel ? previousModel : GEMINI_DEFAULT_MODEL);
  const nextEnsembleClaudeModel =
    String(runtime?.ensemble_claude_model || "").trim().toLowerCase()
      || (previousProvider === "claude" && previousModel ? previousModel : CLAUDE_DEFAULT_MODEL);
  const previousLocalProvider = normalizedLocalModelProvider(runtime);
  const localProvider =
    provider === "ollama"
      ? "ollama"
      : provider === "oss"
        ? (String(nextLocalProvider || runtime?.local_model_provider || "ollama").trim().toLowerCase() === "lmstudio" ? "lmstudio" : "ollama")
        : "";
  const supportsAuto = providerSupportsAutoModel(provider);
  const currentModel = String(runtime?.model_slug_input || runtime?.model || "").trim().toLowerCase();
  const autoModelBase =
    previousProvider === provider
      ? (currentModel || "auto")
      : defaultModelForProvider(provider, { ...runtime, model: "", model_slug_input: "" });
  const ensembleDefaultModel = nextEnsembleOpenAiModel || "gpt-5.4";
  const keepExistingLocalModel =
    previousProvider === provider
    || (provider === "ollama" && previousProvider === "oss" && previousLocalProvider === "ollama")
    || (provider === "oss" && previousProvider === "ollama");
  const nextModel = supportsAuto
    ? autoModelBase
    : provider === "ensemble"
      ? ensembleDefaultModel
    : provider === "ollama" || provider === "oss"
      ? (currentModel === "auto" ? "" : (keepExistingLocalModel ? currentModel : ""))
    : provider === "claude" && !looksLikeClaudeModel(currentModel)
      ? CLAUDE_DEFAULT_MODEL
    : provider === "gemini" && !currentModel.startsWith("gemini")
      ? GEMINI_DEFAULT_MODEL
    : providerDefaultModelSlug(provider) && !currentModelMatchesProvider(provider, currentModel)
      ? providerDefaultModelSlug(provider)
      : currentModel === "auto"
        ? ""
        : currentModel || defaultModelForProvider(provider, runtime);
  return {
    ...(cloneValue(runtime) || {}),
    model_provider: provider,
    local_model_provider: localProvider,
    ensemble_openai_model: nextEnsembleOpenAiModel,
    ensemble_gemini_model: nextEnsembleGeminiModel,
    ensemble_claude_model: nextEnsembleClaudeModel,
    provider_base_url:
      previousProvider === provider
        ? String(runtime?.provider_base_url || "").trim() || defaultProviderBaseUrl(provider)
        : defaultProviderBaseUrl(provider),
    provider_api_key_env:
      previousProvider === provider
        ? String(runtime?.provider_api_key_env || "").trim() || defaultProviderApiKeyEnv(provider)
        : defaultProviderApiKeyEnv(provider),
    billing_mode:
      previousProvider === provider
        ? String(runtime?.billing_mode || "").trim() || defaultBillingMode(provider)
        : defaultBillingMode(provider),
    model: nextModel,
    model_preset: nextModel === "auto" && supportsAuto ? String(runtime?.model_preset || "auto").trim().toLowerCase() || "auto" : "",
    model_selection_mode: "slug",
    model_slug_input: nextModel,
    codex_path:
      previousProvider === provider
        ? String(runtime?.codex_path || "").trim() || defaultCodexPath(provider)
        : defaultCodexPath(provider),
  };
}

export function blankProjectForm(defaultRuntime) {
  const runtimeSource = cloneValue(defaultRuntime) || {};
  const runtimeDefaults = {
    ...DEFAULT_PROGRAM_RUNTIME,
    ...runtimeSource,
  };
  const defaultModel = defaultModelForProvider(runtimeDefaults.model_provider, runtimeDefaults) || "gpt-5.4";
  const defaultModelSlugInput = String(runtimeSource.model_slug_input ?? defaultModel).trim().toLowerCase() || defaultModel;
  const defaultModelPreset =
    runtimeSource.model_preset !== undefined
      ? String(runtimeSource.model_preset || "").trim().toLowerCase()
      : defaultModel === "auto"
        ? "auto"
        : "";
  return {
    project_dir: "",
    display_name: "",
    branch: "main",
    origin_url: "",
    github_mode: "existing",
    runtime: {
      ...runtimeDefaults,
      model: defaultModel,
      model_preset: defaultModelPreset,
      model_slug_input: defaultModelSlugInput,
      generate_word_report: runtimeDefaults.generate_word_report ?? true,
      max_blocks: runtimeDefaults.max_blocks || 5,
      optimization_mode: runtimeDefaults.optimization_mode || "light",
      test_cmd: runtimeDefaults.test_cmd || "python -m pytest",
      execution_mode: "parallel",
      allow_background_queue: runtimeDefaults.allow_background_queue ?? true,
      background_queue_priority: Number.parseInt(String(runtimeDefaults.background_queue_priority ?? 0), 10) || 0,
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
      execution_mode: "parallel",
      allow_background_queue:
        detail?.runtime?.allow_background_queue ?? defaultRuntime?.allow_background_queue ?? true,
      background_queue_priority:
        Number.parseInt(
          String(detail?.runtime?.background_queue_priority ?? defaultRuntime?.background_queue_priority ?? 0),
          10,
        ) || 0,
    },
  };
}

export function inheritProjectIdentityForm(form, defaultRuntime) {
  const nextForm = cloneValue(form) || {};
  return {
    ...blankProjectForm(defaultRuntime),
    project_dir: nextForm.project_dir || "",
    display_name: nextForm.display_name || "",
    branch: nextForm.branch || "main",
    origin_url: nextForm.origin_url || "",
    github_mode: nextForm.github_mode || deriveGithubMode(nextForm.origin_url),
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

export function computePlanStats(plan = {}) {
  const steps = Array.isArray(plan?.steps) ? plan.steps : [];
  const completed = steps.filter((step) => step.status === "completed").length;
  const failed = steps.filter((step) => step.status === "failed").length;
  const running = steps.filter((step) => ["running", "integrating"].includes(String(step?.status || "").trim().toLowerCase())).length;
  return {
    total_steps: steps.length,
    completed_steps: completed,
    failed_steps: failed,
    running_steps: running,
    remaining_steps: Math.max(0, steps.length - completed),
  };
}

const RUN_STATE_STALE_AFTER_MS = 30 * 1000;

function parseTimestampMs(value) {
  if (!value) {
    return null;
  }
  const parsed = Date.parse(String(value).trim());
  return Number.isFinite(parsed) ? parsed : null;
}

function jobIsSupersededByProject(job = null, project = null) {
  const jobStatus = String(job?.status || "").trim().toLowerCase();
  if (!["queued", "running"].includes(jobStatus)) {
    return false;
  }
  const currentStatus = String(project?.current_status || project?.status || "").trim().toLowerCase();
  if (!currentStatus || currentStatus.startsWith("running:") || currentStatus === "queued" || currentStatus.startsWith("queued:")) {
    return false;
  }
  const projectLastRunAtMs = parseTimestampMs(project?.last_run_at);
  const jobUpdatedAtMs = Number.isFinite(Number(job?.updated_at_ms)) ? Number(job.updated_at_ms) : null;
  if (projectLastRunAtMs !== null && jobUpdatedAtMs !== null && projectLastRunAtMs > jobUpdatedAtMs) {
    return true;
  }
  return false;
}

const ACTIVE_ACTIVITY_EVENT_TYPES = new Set([
  "batch-started",
  "closeout-started",
  "plan-finalizing",
  "plan-started",
  "planner-agent-started",
  "run-started",
  "step-started",
]);

function activeActivityTimestampMs(line) {
  const text = String(line || "").trim();
  if (!text.includes("|")) {
    return null;
  }
  const parts = text.split("|").map((item) => item.trim());
  if (parts.length < 2) {
    return null;
  }
  const timestampMs = parseTimestampMs(parts[0]);
  if (timestampMs === null) {
    return null;
  }
  const eventType = String(parts[1] || "").split(" ")[0].trim().toLowerCase();
  return ACTIVE_ACTIVITY_EVENT_TYPES.has(eventType) ? timestampMs : null;
}

function latestRunningSignalMs({
  plan = null,
  activity = [],
}) {
  const candidates = [
    parseTimestampMs(plan?.closeout_started_at),
    ...((Array.isArray(plan?.steps) ? plan.steps : [])
      .filter((step) => ["running", "integrating"].includes(String(step?.status || "").trim().toLowerCase()))
      .map((step) => parseTimestampMs(step?.started_at))),
    ...((Array.isArray(activity) ? activity : [])
      .map((line) => activeActivityTimestampMs(line))),
  ].filter((value) => Number.isFinite(value));
  if (!candidates.length) {
    return null;
  }
  return Math.max(...candidates);
}

function shouldPreserveRecentRunningState({
  plan = null,
  activity = [],
  pendingCheckpoint = false,
  nowMs = Date.now(),
  staleAfterMs = RUN_STATE_STALE_AFTER_MS,
}) {
  if (pendingCheckpoint) {
    return true;
  }
  const latestSignal = latestRunningSignalMs({ plan, activity });
  if (latestSignal === null) {
    return false;
  }
  return Math.max(0, nowMs - latestSignal) < staleAfterMs;
}

function readyExecutionNodeIds(plan = {}) {
  const steps = Array.isArray(plan?.steps) ? plan.steps : [];
  const completedIds = new Set(steps.filter((step) => step.status === "completed").map((step) => step.step_id));
  return steps
    .filter(
      (step) =>
        step.status !== "completed" &&
        (step.depends_on || []).every((dependency) => completedIds.has(dependency)),
    )
    .map((step) => step.step_id);
}

function executionStepsByStatus(plan = {}, statuses = []) {
  const allowed = new Set(statuses.map((status) => String(status || "").trim().toLowerCase()));
  const steps = Array.isArray(plan?.steps) ? plan.steps : [];
  return steps.filter((step) => allowed.has(String(step?.status || "").trim().toLowerCase()));
}

function runningExecutionSteps(plan = {}) {
  return executionStepsByStatus(plan, ["running", "integrating"]);
}

function activeExecutionStepIds(plan = {}) {
  return {
    runningIds: summarizeStepIds(executionStepsByStatus(plan, ["running"])),
    integratingIds: summarizeStepIds(executionStepsByStatus(plan, ["integrating"])),
  };
}

function progressActiveStatusCaption(plan, language = "en", completed = 0, total = 0) {
  const locale = normalizeLanguage(language);
  const { runningIds, integratingIds } = activeExecutionStepIds(plan);
  if (runningIds && integratingIds) {
    return translate(locale, "progress.runningAndIntegratingIds", {
      completed,
      total,
      runningIds,
      integratingIds,
    });
  }
  if (runningIds) {
    return translate(locale, "progress.runningIds", {
      completed,
      total,
      ids: runningIds,
    });
  }
  if (integratingIds) {
    return translate(locale, "progress.integratingIds", {
      completed,
      total,
      ids: integratingIds,
    });
  }
  return "";
}

export function planDependencyValidationMessage(plan = {}) {
  const steps = Array.isArray(plan?.steps) ? plan.steps : [];
  const stepById = new Map();
  steps.forEach((step) => {
    const stepId = String(step?.step_id || "").trim();
    if (stepId) {
      stepById.set(stepId, step);
    }
  });

  for (const step of steps) {
    const stepId = String(step?.step_id || "").trim();
    if (!stepId) {
      continue;
    }
    for (const dependency of step?.depends_on || []) {
      const dependencyId = String(dependency || "").trim();
      if (!dependencyId) {
        continue;
      }
      if (!stepById.has(dependencyId)) {
        return `Unknown dependency reference: ${dependencyId}`;
      }
      if (dependencyId === stepId) {
        return `${stepId} cannot depend on itself.`;
      }
    }
  }

  const visitState = new Map();
  const path = [];

  function visit(stepId) {
    const state = visitState.get(stepId) || 0;
    if (state === 1) {
      const cycleStart = path.indexOf(stepId);
      const cycle = cycleStart >= 0 ? path.slice(cycleStart).concat(stepId) : [stepId, stepId];
      return `Parallel execution plan contains a dependency cycle: ${cycle.join(" -> ")}.`;
    }
    if (state === 2) {
      return "";
    }
    visitState.set(stepId, 1);
    path.push(stepId);
    const step = stepById.get(stepId);
    for (const dependency of step?.depends_on || []) {
      const dependencyId = String(dependency || "").trim();
      if (!dependencyId || !stepById.has(dependencyId)) {
        continue;
      }
      const message = visit(dependencyId);
      if (message) {
        return message;
      }
    }
    path.pop();
    visitState.set(stepId, 2);
    return "";
  }

  for (const stepId of stepById.keys()) {
    const message = visit(stepId);
    if (message) {
      return message;
    }
  }
  return "";
}

function summarizeStepIds(steps = [], maxVisible = 4) {
  const stepIds = steps
    .map((step) => String(step?.step_id || "").trim())
    .filter(Boolean);
  if (!stepIds.length) {
    return "";
  }
  if (stepIds.length <= maxVisible) {
    return stepIds.join(", ");
  }
  return `${stepIds.slice(0, maxVisible).join(", ")} +${stepIds.length - maxVisible}`;
}

export function activityLineSummary(line = "") {
  const parts = String(line || "")
    .split("|")
    .map((part) => part.trim())
    .filter(Boolean);
  if (!parts.length) {
    return "";
  }
  if (parts.length >= 3) {
    return parts.slice(2).join(" | ");
  }
  return parts[parts.length - 1];
}

export function isDebuggingStatus(status = "") {
  const normalized = String(status || "").trim().toLowerCase();
  return normalized === "debugging" || normalized === "running:debugging" || normalized === "running:parallel-debugging";
}

export function effectiveStepStatus(step = null, projectStatus = "") {
  const rawStepStatus = String(step?.status || "").trim().toLowerCase();
  if (!rawStepStatus) {
    return "";
  }
  if (isDebuggingStatus(projectStatus) && rawStepStatus === "running") {
    return "running:debugging";
  }
  return String(step?.status || "").trim();
}

function normalizedCloseoutStatus(plan = null) {
  return String(plan?.closeout_status || "not_started").trim().toLowerCase();
}

function planProgressCounts(plan = null) {
  const steps = Array.isArray(plan?.steps) ? plan.steps : [];
  const completedStepCount = steps.filter((step) => String(step?.status || "").trim().toLowerCase() === "completed").length;
  const totalStepCount = steps.length;
  const closeoutStatus = normalizedCloseoutStatus(plan);
  const includesCloseout = totalStepCount > 0 || closeoutStatus !== "not_started";
  const totalCount = includesCloseout ? totalStepCount + 1 : 0;
  const completedCount = Math.min(totalCount, completedStepCount + (closeoutStatus === "completed" ? 1 : 0));
  return {
    steps,
    completedStepCount,
    totalStepCount,
    completedCount,
    totalCount,
    closeoutStatus,
  };
}

function normalizePlanningProgress(raw = null) {
  if (!raw || typeof raw !== "object") {
    return null;
  }
  const stageCount = Math.max(0, Number.parseInt(String(raw.stage_count || 0), 10) || 0);
  const currentStageIndex = Math.max(0, Number.parseInt(String(raw.current_stage_index || 0), 10) || 0);
  const percent = Math.max(0, Math.min(100, Number.parseInt(String(raw.percent || 0), 10) || 0));
  const stages = Array.isArray(raw.stages)
    ? raw.stages
        .filter((stage) => stage && typeof stage === "object")
        .map((stage, index) => ({
          key: String(stage.key || "").trim(),
          index: Math.max(1, Number.parseInt(String(stage.index || index + 1), 10) || index + 1),
          label: String(stage.label || "").trim(),
          status: String(stage.status || "pending").trim().toLowerCase() || "pending",
          agentLabel: String(stage.agent_label || "").trim(),
        }))
    : [];
  const currentStage =
    stages.find((stage) => stage.index === currentStageIndex)
    || stages.find((stage) => stage.status === "running" || stage.status === "failed")
    || null;
  return {
    stageCount,
    completedStages: Math.max(0, Number.parseInt(String(raw.completed_stages || 0), 10) || 0),
    percent,
    stages,
    currentStageIndex,
    currentStageKey: String(raw.current_stage_key || "").trim(),
    currentStageLabel: String(raw.current_stage_label || currentStage?.label || "").trim(),
    currentStageStatus: String(raw.current_stage_status || currentStage?.status || "").trim().toLowerCase() || "pending",
    currentAgentLabel: String(raw.current_agent_label || currentStage?.agentLabel || "").trim(),
    message: String(raw.message || "").trim(),
    eventType: String(raw.event_type || "").trim(),
  };
}

function planningProgressStatusValue(progress = null) {
  if (!progress || typeof progress !== "object") {
    return "";
  }
  return String(progress?.currentStageStatus ?? progress?.current_stage_status ?? "").trim().toLowerCase();
}

export function isPlanningProgressRunning(progress = null) {
  return planningProgressStatusValue(progress) === "running";
}

function planningProgressSummary(progress = null) {
  if (!progress || typeof progress !== "object") {
    return {
      currentStageIndex: 0,
      currentStageStatus: "",
      stageCount: 0,
    };
  }
  const currentStage = progress?.planningCurrentStage && typeof progress.planningCurrentStage === "object"
    ? progress.planningCurrentStage
    : null;
  return {
    currentStageIndex: Math.max(
      0,
      Number.parseInt(
        String(currentStage?.index ?? progress?.currentStageIndex ?? progress?.current_stage_index ?? 0),
        10,
      ) || 0,
    ),
    currentStageStatus: String(
      currentStage?.status ?? progress?.currentStageStatus ?? progress?.current_stage_status ?? "",
    )
      .trim()
      .toLowerCase(),
    stageCount: Math.max(
      0,
      Number.parseInt(
        String(progress?.planningStageCount ?? progress?.stageCount ?? progress?.stage_count ?? 0),
        10,
      ) || 0,
    ),
  };
}

export function planningProgressCaptionDisplay(progress = null, language = "en") {
  const locale = normalizeLanguage(language);
  const summary = planningProgressSummary(progress);
  if (summary.currentStageIndex && summary.stageCount) {
    if (summary.currentStageStatus) {
      return translate(locale, "run.planningStageWithStatus", {
        current: summary.currentStageIndex,
        status: displayStatus(summary.currentStageStatus, locale),
        total: summary.stageCount,
      });
    }
    return translate(locale, "run.planningStage", {
      current: summary.currentStageIndex,
      total: summary.stageCount,
    });
  }
  return translate(locale, "run.planGeneration");
}

export function deriveExecutionProgress(detail = null, planDraft = null, activeJob = null) {
  const progressJob = visibleExecutionJob(activeJob);
  const detailPlan = detail?.plan && typeof detail.plan === "object" ? detail.plan : null;
  const fallbackPlan = planDraft && typeof planDraft === "object" ? planDraft : {};
  const plan = cloneValue(detailPlan || fallbackPlan) || {};
  const { steps, completedCount, totalCount, closeoutStatus } = planProgressCounts(plan);
  const stats = detail?.stats || computePlanStats(plan);
  const command = progressJob?.status === "running" ? String(progressJob?.command || "").trim() : "";
  const runningStepList = runningExecutionSteps(plan);
  const runningStep = runningStepList[0] || null;
  const nextStep = steps.find((step) => step.status !== "completed") || null;
  const readyIds = readyExecutionNodeIds(plan);
  const closeoutRunning = closeoutStatus === "running";
  const currentStatus = String(detail?.project?.current_status || "").trim();
  const status = currentStatus.toLowerCase();
  const debugging = isDebuggingStatus(currentStatus);
  const planningProgress = normalizePlanningProgress(detail?.planning_progress);
  const planningRunning = isPlanningProgressRunning(planningProgress);
  const recentActivity = (Array.isArray(detail?.activity) ? detail.activity : [])
    .map((line) => activityLineSummary(line))
    .filter(Boolean)
    .slice(0, 3);
  const isActive =
    progressJob?.status === "running" ||
    runningStepList.length > 0 ||
    closeoutRunning ||
    status.startsWith("running:") ||
    planningRunning;

  let phase = "idle";
  if (command === "generate-plan" || planningRunning) {
    phase = "planning";
  } else if (command === "run-closeout" || closeoutRunning) {
    phase = "closeout";
  } else if (debugging) {
    phase = "debugging";
  } else if (command || runningStepList.length > 0 || nextStep) {
    phase = "step";
  }

  let percent = null;
  let visualPercent = 0;
  let indeterminate = false;
  if (isActive) {
    if (phase === "planning" && planningProgress?.stageCount) {
      percent = planningProgress.percent;
      visualPercent = percent > 0 ? percent : 6;
    } else if (phase === "planning" && !steps.length) {
      indeterminate = true;
    } else if (totalCount) {
      percent = Math.round((completedCount / totalCount) * 100);
      visualPercent = percent > 0 ? percent : 6;
      if ((phase === "closeout" || runningStepList.length > 0 || command === "run-plan") && percent < 95) {
        visualPercent = Math.max(visualPercent, 10);
        visualPercent = Math.min(95, visualPercent);
      }
    } else {
      indeterminate = true;
    }
  }

  return {
    isActive,
    phase,
    command,
    status: currentStatus,
    debugging,
    plan,
    totalSteps: steps.length,
    completedSteps: Math.max(0, Number(stats?.completed_steps || 0)),
    totalProgressUnits: totalCount,
    completedProgressUnits: completedCount,
    failedSteps: Math.max(0, Number(stats?.failed_steps || 0)),
    runningSteps: Math.max(0, Number(stats?.running_steps || 0)),
    remainingSteps: Math.max(0, Number(stats?.remaining_steps || 0)),
    runningStepList,
    runningStep,
    nextStep,
    readyIds,
    planningProgress,
    planningStages: planningProgress?.stages || [],
    planningStageCount: planningProgress?.stageCount || 0,
    planningCurrentStage: planningProgress?.currentStageLabel
      ? {
          index: planningProgress.currentStageIndex,
          key: planningProgress.currentStageKey,
          label: planningProgress.currentStageLabel,
          status: planningProgress.currentStageStatus,
        }
      : null,
    planningCurrentAgentLabel: planningProgress?.currentAgentLabel || "",
    recentActivity,
    headlineActivity: planningProgress?.message || recentActivity[0] || "",
    closeoutRunning,
    percent,
    visualPercent,
    indeterminate,
  };
}

export function workspaceStatsFromProjects(projects = []) {
  let running = 0;
  let readyLike = 0;
  let failed = 0;
  for (const project of projects || []) {
    const status = String(project?.status || "").trim();
    if (status.startsWith("running:")) {
      running += 1;
    } else if (["setup_ready", "plan_ready", "plan_completed", "closed_out", "ready"].includes(status)) {
      readyLike += 1;
    } else if (status.endsWith("failed") || status === "failed" || status === "closeout_failed") {
      failed += 1;
    }
  }
  return {
    project_count: (projects || []).length,
    ready_like: readyLike,
    running,
    failed,
  };
}

export function deriveIdleProjectStatus(plan = null, stats = null, currentStatus = "") {
  const normalizedCurrentStatus = String(currentStatus || "").trim().toLowerCase();
  const closeoutStatus = String(plan?.closeout_status || stats?.closeout_status || "").trim().toLowerCase();
  const effectiveStats = plan ? computePlanStats(plan) : stats || {};
  const totalSteps = Math.max(0, Number(effectiveStats?.total_steps || 0));
  const completedSteps = Math.max(0, Number(effectiveStats?.completed_steps || 0));
  const failedSteps = Math.max(0, Number(effectiveStats?.failed_steps || 0));

  if (closeoutStatus === "completed") {
    return "closed_out";
  }
  if (closeoutStatus === "failed") {
    return "closeout_failed";
  }
  if (normalizedCurrentStatus.endsWith("failed") || failedSteps > 0) {
    return "failed";
  }
  if (totalSteps <= 0) {
    return "setup_ready";
  }
  if (completedSteps >= totalSteps) {
    return "plan_completed";
  }
  return "plan_ready";
}

export function normalizeInterruptedPlan(plan = null) {
  const nextPlan = cloneValue(plan) || {};
  const rawSteps = Array.isArray(nextPlan.steps) ? nextPlan.steps : [];
  nextPlan.steps = rawSteps.map((step) =>
    ["running", "integrating"].includes(String(step?.status || "").trim().toLowerCase())
      ? {
          ...step,
          status: "pending",
        }
      : step,
  );
  if (String(nextPlan.closeout_status || "").trim().toLowerCase() === "running") {
    nextPlan.closeout_status = "not_started";
  }
  return nextPlan;
}

export function sanitizeProjectListForJobState(projects = [], activeJob = null, options = {}) {
  if (
    activeJob &&
    !Array.isArray(activeJob) &&
    ["queued", "running"].includes(String(activeJob?.status || "").trim().toLowerCase()) &&
    !String(activeJob?.repo_id || "").trim() &&
    !String(activeJob?.project_dir || "").trim()
  ) {
    return projects;
  }
  const jobItems = Array.isArray(activeJob) ? activeJob.filter(Boolean) : activeJob ? [activeJob] : [];
  const nowMs = Number.isFinite(options?.nowMs) ? options.nowMs : Date.now();
  return (projects || []).map((project) => {
    const matchedJob = projectJobFromJobs(jobItems, project);
    if (matchedJob && ["queued", "running"].includes(String(matchedJob?.status || "").trim().toLowerCase())) {
      return {
        ...project,
        status: projectStatusWithJob(project?.status, matchedJob),
      };
    }
    const currentStatus = String(project?.status || "").trim();
    const normalizedStatus = currentStatus.toLowerCase();
    if (!normalizedStatus.startsWith("running:") && normalizedStatus !== "queued" && !normalizedStatus.startsWith("queued:")) {
      return project;
    }
    if (
      shouldPreserveRecentRunningState({
        plan: {
          closeout_started_at: null,
        },
        nowMs,
      })
    ) {
      return project;
    }
    return {
      ...project,
      status: deriveIdleProjectStatus(null, { ...(project?.stats || {}), closeout_status: project?.closeout_status }, currentStatus),
    };
  });
}

export function sanitizeProjectDetailForJobState(detail, activeJob = null, options = {}) {
  let matchedJob = Array.isArray(activeJob)
    ? projectJobFromJobs(activeJob, detail?.project || {})
    : activeJob;
  if (jobIsSupersededByProject(matchedJob, detail?.project || {})) {
    matchedJob = null;
  }
  if (!detail || ["queued", "running"].includes(String(matchedJob?.status || "").trim().toLowerCase())) {
    return detail;
  }
  const currentStatus = String(detail?.project?.current_status || "").trim();
  if (isPlanningProgressRunning(detail?.planning_progress) && !currentStatus.toLowerCase().startsWith("running:")) {
    const nextStatus = "running:generate-plan";
    return {
      ...detail,
      project: detail?.project
        ? {
            ...detail.project,
            current_status: nextStatus,
          }
        : detail?.project,
      snapshot: detail?.snapshot
        ? {
            ...detail.snapshot,
            project: detail.snapshot.project
              ? {
                  ...detail.snapshot.project,
                  current_status: nextStatus,
                }
              : detail.snapshot.project,
          }
        : detail?.snapshot,
      bottom_panels: detail?.bottom_panels
        ? {
            ...detail.bottom_panels,
            git_status: detail.bottom_panels.git_status
              ? {
                  ...detail.bottom_panels.git_status,
                  current_status: nextStatus,
                }
              : detail.bottom_panels.git_status,
          }
        : detail?.bottom_panels,
    };
  }
  const planSteps = Array.isArray(detail?.plan?.steps) ? detail.plan.steps : [];
  const planHasRunningStep = planSteps.some((step) => step.status === "running");
  const closeoutStatus = String(detail?.plan?.closeout_status || "").trim().toLowerCase();
  const closeoutRunning = closeoutStatus === "running";
  const terminalPlanState =
    closeoutStatus === "completed"
    || closeoutStatus === "failed"
    || planSteps.some((step) => String(step?.status || "").trim().toLowerCase() === "failed")
    || (planSteps.length > 0 && planSteps.every((step) => String(step?.status || "").trim().toLowerCase() === "completed"));
  if (!currentStatus.toLowerCase().startsWith("running:") && !planHasRunningStep && !closeoutRunning) {
    return detail;
  }
  const nowMs = Number.isFinite(options?.nowMs) ? options.nowMs : Date.now();
  if (
    !terminalPlanState
    && shouldPreserveRecentRunningState({
      plan: detail?.plan,
      activity: detail?.activity,
      pendingCheckpoint:
        Boolean(detail?.checkpoints?.pending) ||
        Boolean(detail?.loop_state?.pending_checkpoint_approval) ||
        Boolean(detail?.bottom_panels?.git_status?.pending_checkpoint_approval),
      nowMs,
    })
  ) {
    return detail;
  }

  const nextPlan = normalizeInterruptedPlan(detail.plan);
  const nextStats = computePlanStats(nextPlan);
  const nextStatus = deriveIdleProjectStatus(nextPlan, nextStats, currentStatus);
  const nextSnapshot = detail?.snapshot
    ? {
        ...detail.snapshot,
        project: detail.snapshot.project
          ? {
              ...detail.snapshot.project,
              current_status: nextStatus,
            }
          : detail.snapshot.project,
        plan: nextPlan,
      }
    : detail.snapshot;
  const nextBottomPanels = detail?.bottom_panels
    ? {
        ...detail.bottom_panels,
        git_status: detail.bottom_panels.git_status
          ? {
              ...detail.bottom_panels.git_status,
              current_status: nextStatus,
            }
          : detail.bottom_panels.git_status,
      }
    : detail.bottom_panels;

  return {
    ...detail,
    project: detail.project
      ? {
          ...detail.project,
          current_status: nextStatus,
        }
      : detail.project,
    plan: nextPlan,
    stats: nextStats,
    progress: toolbarProgressCaptionDisplay(nextPlan),
    snapshot: nextSnapshot,
    bottom_panels: nextBottomPanels,
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
    const nextPlan = cloneValue(plan) || {};
    const workflowMode = String(payload.runtime?.workflow_mode || nextPlan.workflow_mode || "standard")
      .trim()
      .toLowerCase();
    nextPlan.workflow_mode = workflowMode === "ml" ? "ml" : "standard";
    nextPlan.execution_mode = "parallel";
    nextPlan.default_test_command = nextPlan.default_test_command || payload.runtime?.test_cmd || "python -m pytest";
    payload.plan = nextPlan;
  }
  return payload;
}

export function buildRunPlanPayloadFromDetail(detail, defaultRuntime = null) {
  const projectDir = String(detail?.project?.repo_path || "").trim();
  const steps = Array.isArray(detail?.plan?.steps) ? detail.plan.steps : [];
  if (!projectDir || !steps.length) {
    return null;
  }
  return buildProjectPayload(projectFormFromDetail(detail, defaultRuntime), detail.plan);
}

export function findModelCatalogEntry(modelCatalog = [], model = "") {
  const target = String(model || "").trim().toLowerCase();
  return modelCatalog.find((item) => String(item?.model || "").trim().toLowerCase() === target) || null;
}

export function defaultProviderBaseUrl(provider = "openai") {
  switch (String(provider || "").trim().toLowerCase()) {
    case "deepseek":
      return "https://api.deepseek.com/anthropic";
    case "kimi":
      return "https://api.moonshot.cn/v1";
    case "minimax":
      return "https://api.minimax.io/anthropic/v1";
    case "glm":
      return "https://open.bigmodel.cn/api/anthropic";
    case "qwen_code":
      return "https://dashscope.aliyuncs.com/compatible-mode/v1";
    case "openrouter":
      return "https://openrouter.ai/api/v1";
    case "local_openai":
      return "http://127.0.0.1:1234/v1";
    default:
      return "";
  }
}

export function defaultProviderApiKeyEnv(provider = "openai") {
  switch (String(provider || "").trim().toLowerCase()) {
    case "ensemble":
      return "OPENAI_API_KEY";
    case "claude":
      return "ANTHROPIC_API_KEY";
    case "gemini":
      return "GEMINI_API_KEY";
    case "qwen_code":
      return "DASHSCOPE_API_KEY";
    case "deepseek":
      return "DEEPSEEK_API_KEY";
    case "kimi":
      return "MOONSHOT_API_KEY";
    case "minimax":
      return "MINIMAX_API_KEY";
    case "glm":
      return "ZHIPUAI_API_KEY";
    case "openrouter":
      return "OPENROUTER_API_KEY";
    case "opencdk":
      return "OPENCDK_API_KEY";
    case "openai":
      return "OPENAI_API_KEY";
    default:
      return "";
  }
}

export function defaultBillingMode(provider = "openai") {
  switch (String(provider || "").trim().toLowerCase()) {
    case "deepseek":
    case "kimi":
    case "minimax":
    case "glm":
    case "qwen_code":
    case "openrouter":
    case "opencdk":
      return "token";
    case "ollama":
    case "oss":
      return "per_pass";
    default:
      return "included";
  }
}

export function providerSupportsAutoModel(provider = "openai") {
  const normalized = String(provider || "").trim().toLowerCase();
  return normalized === "openai" || normalized === "ensemble";
}

export function providerSupportsCatalog(provider = "openai") {
  const normalized = String(provider || "").trim().toLowerCase();
  return [
    "openai",
    "ensemble",
    "claude",
    "gemini",
    "ollama",
    "qwen_code",
    "deepseek",
    "kimi",
    "minimax",
    "glm",
    "oss",
  ].includes(normalized);
}

export function providerStatusMap(codexStatus = {}) {
  const providerStatuses = codexStatus?.provider_statuses;
  return providerStatuses && typeof providerStatuses === "object" ? providerStatuses : {};
}

export function providerAvailable(provider = "openai", codexStatus = {}) {
  const status = providerStatusMap(codexStatus)[String(provider || "").trim().toLowerCase()];
  if (!status) {
    return true;
  }
  return Boolean(status.available);
}

export function providerUsable(provider = "openai", codexStatus = {}) {
  const status = providerStatusMap(codexStatus)[String(provider || "").trim().toLowerCase()];
  if (!status) {
    return true;
  }
  return Boolean(status.usable);
}

export function providerStatusReason(provider = "openai", codexStatus = {}) {
  const status = providerStatusMap(codexStatus)[String(provider || "").trim().toLowerCase()];
  return String(status?.reason || "").trim();
}

export function programSettingsAllowsModelSlugInput(provider = "openai") {
  const normalized = String(provider || "").trim().toLowerCase();
  return normalized === "openrouter" || normalized === "opencdk";
}

export function providerDisplayName(provider = "openai", localProvider = "") {
  const normalized = String(provider || "").trim().toLowerCase();
  if (normalized === "ensemble") {
    return "GPT+Gemini+Claude Ensemble";
  }
  if (normalized === "claude") {
    return "Claude Code";
  }
  if (normalized === "gemini") {
    return "Gemini CLI";
  }
  if (normalized === "ollama") {
    return "Ollama";
  }
  if (normalized === "qwen_code") {
    return "Qwen Code";
  }
  if (normalized === "deepseek") {
    return "DeepSeek via Claude Code";
  }
  if (normalized === "kimi") {
    return "Kimi";
  }
  if (normalized === "minimax") {
    return "MiniMax via Claude Code";
  }
  if (normalized === "glm") {
    return "GLM via Claude Code";
  }
  if (normalized === "oss") {
    const local = String(localProvider || "").trim().toLowerCase();
    if (local === "lmstudio") {
      return "Local/LM Studio";
    }
    return "Local/Ollama";
  }
  if (normalized === "openrouter") {
    return "OpenRouter";
  }
  if (normalized === "opencdk") {
    return "OpenCDK";
  }
  if (normalized === "local_openai") {
    return "Local OpenAI-Compatible";
  }
  return "OpenAI/Codex";
}

export function normalizedModelProvider(runtime = {}) {
  const normalized = String(runtime?.model_provider || "openai").trim().toLowerCase();
  if (normalized === "oss" && normalizedLocalModelProvider(runtime) === "ollama") {
    return "ollama";
  }
  return MODEL_PROVIDER_OPTIONS.includes(normalized) ? normalized : "openai";
}

export function normalizedBillingMode(runtime = {}, fallback = "") {
  const normalized = String(runtime?.billing_mode || fallback || "").trim().toLowerCase();
  if (normalized === "token" || normalized === "per_pass" || normalized === "included") {
    return normalized;
  }
  return "";
}

export function normalizedLocalModelProvider(runtime = {}) {
  return String(runtime?.local_model_provider || "ollama").trim().toLowerCase() === "lmstudio" ? "lmstudio" : "ollama";
}

export function filterModelCatalogByProvider(modelCatalog = [], runtime = {}) {
  const provider = normalizedModelProvider(runtime);
  const localProvider = normalizedLocalModelProvider(runtime);
  if (!providerSupportsCatalog(provider)) {
    const currentModel = String(runtime?.model_slug_input || runtime?.model || "").trim();
    if (!currentModel) {
      return [];
    }
    return [
      {
        model: currentModel,
        display_name: currentModel,
        hidden: false,
        provider,
      },
    ];
  }
  return (modelCatalog || []).filter((item) => {
    const itemProvider = String(item?.provider || "openai").trim().toLowerCase() || "openai";
    const matchesProvider =
      provider === "ensemble"
        ? itemProvider === "openai"
        : provider === "ollama"
          ? itemProvider === "oss"
          : itemProvider === provider;
    if (!matchesProvider) {
      return false;
    }
    if (provider === "ollama") {
      return String(item?.local_provider || "").trim().toLowerCase() === "ollama";
    }
    if (provider !== "oss") {
      return true;
    }
    const itemLocalProvider = String(item?.local_provider || "").trim().toLowerCase();
    return !itemLocalProvider || itemLocalProvider === localProvider;
  });
}

export function defaultModelForRuntime(modelCatalog = [], runtime = {}) {
  const provider = normalizedModelProvider(runtime);
  if (!providerSupportsCatalog(provider)) {
    return defaultModelForProvider(provider, runtime);
  }
  const scopedCatalog = filterModelCatalogByProvider(modelCatalog, runtime);
  const visible = scopedCatalog.filter((item) => !item?.hidden);
  const preferred = visible[0] || scopedCatalog[0] || null;
  if (preferred?.model) {
    return preferred.model;
  }
  return provider === "oss" || provider === "ollama" ? "" : "auto";
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

export function clampReasoningEffort(modelCatalog = [], model = "", requestedEffort = "", fallback = "medium") {
  const normalizedRequested = String(requestedEffort || "").trim().toLowerCase();
  const options = supportedReasoningOptions(modelCatalog, model, fallback);
  if (options.includes(normalizedRequested)) {
    return normalizedRequested;
  }
  return defaultReasoningOption(modelCatalog, model, fallback);
}

export function applyConfigRuntimeModelSelection(currentRuntime = {}, modelCatalog = [], nextModel = "", nextEffort = null) {
  const providerAllowsAuto = providerSupportsAutoModel(currentRuntime?.model_provider || "openai");
  const model = String(nextModel || "").trim() || (providerAllowsAuto ? "auto" : "");
  const normalizedModel = model.toLowerCase();
  const supported = configReasoningOptions(modelCatalog, model, currentRuntime?.effort || "medium");
  const preferred = nextEffort || selectedConfigReasoning(modelCatalog, { ...currentRuntime, model });
  const selection = supported.includes(preferred) ? preferred : supported[0] || "medium";
  const effort = selection === AUTO_REASONING_OPTION ? defaultReasoningOption(modelCatalog, model, currentRuntime?.effort || "medium") : selection;
  const planningEffort = clampReasoningEffort(modelCatalog, model, currentRuntime?.planning_effort || effort, effort);
  return {
    ...currentRuntime,
    model,
    effort,
    planning_effort: planningEffort,
    effort_selection_mode: selection === AUTO_REASONING_OPTION ? AUTO_REASONING_OPTION : "explicit",
    model_preset: normalizedModel === "auto" ? (selection === AUTO_REASONING_OPTION ? "auto" : selection) : "",
    model_selection_mode: "slug",
    model_slug_input: model,
  };
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

export function formatDurationCompact(seconds, language = "en") {
  const total = Math.max(0, Math.round(Number(seconds || 0)));
  if (!Number.isFinite(total) || total <= 0) {
    return normalizeLanguage(language) === "ko" ? "0초" : "0s";
  }
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remainingSeconds = total % 60;
  if (normalizeLanguage(language) === "ko") {
    if (hours > 0) {
      return `${hours}시간 ${minutes}분`;
    }
    if (minutes > 0) {
      return `${minutes}분 ${remainingSeconds}초`;
    }
    return `${remainingSeconds}초`;
  }
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  if (minutes > 0) {
    return `${minutes}m ${remainingSeconds}s`;
  }
  return `${remainingSeconds}s`;
}

export function formatUsd(value, language = "en") {
  const amount = Number(value || 0);
  if (!Number.isFinite(amount)) {
    return normalizeLanguage(language) === "ko" ? "알 수 없음" : "Unavailable";
  }
  return new Intl.NumberFormat(normalizeLanguage(language) === "ko" ? "ko-KR" : "en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: amount > 0 && amount < 1 ? 4 : 2,
    maximumFractionDigits: amount > 0 && amount < 1 ? 4 : 2,
  }).format(amount);
}

export function formatBinaryGiB(value, language = "en") {
  const bytes = Number(value || 0);
  const locale = normalizeLanguage(language);
  if (!Number.isFinite(bytes) || bytes <= 0) {
    return translate(locale, "common.unavailable");
  }
  const gib = bytes / 1024 ** 3;
  const fractionDigits = gib >= 10 ? 0 : 1;
  return `${new Intl.NumberFormat(locale === "ko" ? "ko-KR" : "en-US", {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(gib)} GiB`;
}

export function shouldShowEstimatedCost(runtime = {}, costEstimate = {}) {
  const recentMode = normalizedBillingMode(costEstimate?.recent, "");
  const remainingMode = normalizedBillingMode(costEstimate?.remaining, "");
  const fallbackMode = normalizedBillingMode(runtime, defaultBillingMode(normalizedModelProvider(runtime)));
  const billingMode = recentMode || remainingMode || fallbackMode;
  if (billingMode === "included" || !billingMode) {
    return false;
  }
  if (billingMode === "token") {
    return Boolean(costEstimate?.recent?.configured || costEstimate?.remaining?.configured);
  }
  if (billingMode === "per_pass") {
    return Boolean(costEstimate?.recent?.configured || costEstimate?.remaining?.configured);
  }
  return false;
}

export function parallelWorkerLabel(count, language = "en") {
  const safeCount = Math.max(1, Number.parseInt(String(count || 1), 10) || 1);
  return normalizeLanguage(language) === "ko" ? `${safeCount}개 워커` : `${safeCount} worker${safeCount === 1 ? "" : "s"}`;
}

export function parallelLimitDescription(parallel = {}, language = "en") {
  const locale = normalizeLanguage(language);
  const cpuCap = Math.max(1, Number.parseInt(String(parallel?.cpu_parallel_limit || 1), 10) || 1);
  const logicalCpuCount = Math.max(1, Number.parseInt(String(parallel?.cpu_logical_count || cpuCap), 10) || cpuCap);
  const recommended = Math.max(1, Number.parseInt(String(parallel?.recommended_workers || 1), 10) || 1);
  const requested = Math.max(0, Number.parseInt(String(parallel?.requested_workers || 0), 10) || 0);
  const rawMemoryCap = Number.parseInt(String(parallel?.memory_parallel_limit || 0), 10);
  const memoryCap = Number.isFinite(rawMemoryCap) && rawMemoryCap > 0 ? rawMemoryCap : null;
  const freeMemory = formatBinaryGiB(parallel?.memory_available_bytes, language);

  if (String(parallel?.worker_mode || "").trim().toLowerCase() === "manual" && requested > recommended) {
    return translate(locale, "run.parallelLimitRequestedCap", {
      requested,
      recommended,
      cpuCap,
      memoryCap: memoryCap ?? translate(locale, "common.unavailable"),
    });
  }
  if (memoryCap !== null && memoryCap < cpuCap) {
    return translate(locale, "run.parallelLimitMemoryCap", {
      memoryCap,
      cpuCap,
      freeMemory,
    });
  }
  if (cpuCap <= recommended) {
    return translate(locale, "run.parallelLimitCpuCap", {
      cpuCap,
      logicalCpuCount,
    });
  }
  return translate(locale, "run.parallelLimitAutoCap", {
    cpuCap,
    memoryCap: memoryCap ?? translate(locale, "common.unavailable"),
  });
}

export function parallelLimitTone(parallel = {}) {
  const cpuCap = Math.max(1, Number.parseInt(String(parallel?.cpu_parallel_limit || 1), 10) || 1);
  const recommended = Math.max(1, Number.parseInt(String(parallel?.recommended_workers || 1), 10) || 1);
  const rawMemoryCap = Number.parseInt(String(parallel?.memory_parallel_limit || 0), 10);
  const memoryCap = Number.isFinite(rawMemoryCap) && rawMemoryCap > 0 ? rawMemoryCap : null;
  if (recommended <= 1 || (memoryCap !== null && memoryCap < cpuCap)) {
    return "warning";
  }
  return "info";
}

export function firstSelectableStepId(plan) {
  const steps = plan?.steps || [];
  const pending = steps.find((step) => step.status !== "completed");
  return pending?.step_id || "";
}

export function toggleStepSelection(currentStepId = "", nextStepId = "") {
  const current = String(currentStepId || "").trim();
  const next = String(nextStepId || "").trim();
  if (!next || current === next) {
    return "";
  }
  return next;
}

export const CLOSEOUT_STEP_ID = "CO1";

export function isSystemStep(step) {
  return Boolean(step?.metadata?.system_step);
}

export function planStepsWithCloseout(plan, labels = {}) {
  const steps = Array.isArray(plan?.steps) ? plan.steps.map((step) => cloneValue(step)) : [];
  if (!steps.length) {
    return steps;
  }
  const stepIds = steps
    .map((step) => String(step?.step_id || "").trim())
    .filter((stepId) => stepId && stepId !== CLOSEOUT_STEP_ID);
  const dependedOnStepIds = new Set();
  steps.forEach((step) => {
    (step?.depends_on || []).forEach((dependency) => {
      const dependencyId = String(dependency || "").trim();
      if (dependencyId && dependencyId !== CLOSEOUT_STEP_ID) {
        dependedOnStepIds.add(dependencyId);
      }
    });
  });
  const closeoutDependsOn = stepIds.filter((stepId) => !dependedOnStepIds.has(stepId));
  const closeoutStatus = String(plan?.closeout_status || "not_started").trim().toLowerCase();
  let status = "pending";
  if (closeoutStatus === "running") {
    status = "running";
  } else if (closeoutStatus === "completed") {
    status = "completed";
  } else if (closeoutStatus === "failed") {
    status = "failed";
  }
  steps.push({
    step_id: CLOSEOUT_STEP_ID,
    title: labels.title || "Closeout",
    display_description: labels.description || labels.title || "Closeout",
    codex_description: labels.description || labels.title || "Closeout",
    success_criteria: labels.successCriteria || labels.description || labels.title || "Closeout",
    deadline_at: "",
    reasoning_effort: "high",
    parallel_group: "",
    // Closeout should attach to terminal steps, otherwise the DAG renders redundant
    // shortcut edges like ST2 -> CO1 alongside ST2 -> ... -> CO1.
    depends_on: closeoutDependsOn.length ? closeoutDependsOn : stepIds,
    owned_paths: ["README.md", "docs/CLOSEOUT_REPORT.md"],
    status,
    notes: String(plan?.closeout_notes || "").trim(),
    metadata: {
      system_step: true,
      system_step_kind: "closeout",
      ...(status === "failed" ? { failure_reason_code: "closeout_failed" } : {}),
    },
  });
  return steps;
}

export function runtimeSummary(runtime, modelPresets = [], language = "en", modelCatalog = []) {
  const provider = normalizedModelProvider(runtime);
  const providerPrefix = providerDisplayName(provider, normalizedLocalModelProvider(runtime));
  const compactPlanningSuffix = runtime?.use_fast_mode ? ` | ${translate(language, "runtime.compactPlanning")}` : "";
  const workflowSuffix =
    String(runtime?.workflow_mode || "standard").trim().toLowerCase() === "ml"
      ? ` | ${translate(language, "option.workflowML")}`
      : ` | ${translate(language, "option.workflowStandard")}`;
  const autoParallelWorkers = String(runtime?.parallel_worker_mode || "auto").trim().toLowerCase() !== "manual";
  const executionSuffix = autoParallelWorkers
    ? ` | parallel ${String(translate(language, "preset.auto") || "auto").trim().toLowerCase() || "auto"}`
    : ` | parallel x${Math.max(1, Number.parseInt(String(runtime?.parallel_workers || 4), 10) || 1)}`;
  const preset = modelPresets.find((item) => item.preset_id === runtime?.model_preset);
  if (preset && providerSupportsAutoModel(provider)) {
    const summary = `${providerPrefix}${workflowSuffix} | ${preset.summary}${executionSuffix}`;
    return `${summary}${compactPlanningSuffix}`;
  }
  if (runtime?.model) {
    const label = modelDisplayName(modelCatalog, runtime.model);
    const effortLabel =
      String(runtime?.effort_selection_mode || "").trim().toLowerCase() === AUTO_REASONING_OPTION
        ? reasoningEffortLabel(AUTO_REASONING_OPTION, language)
        : reasoningEffortLabel(runtime.effort || "high", language);
    if (normalizeLanguage(language) === "ko") {
      const summary = translate("ko", "runtime.modelSummary", {
        model: `${providerPrefix}${workflowSuffix} | ${label}`,
        effort: effortLabel,
      });
      const nextSummary = `${summary}${executionSuffix}`;
      return `${nextSummary}${compactPlanningSuffix}`;
    }
    const summary = `${providerPrefix}${workflowSuffix} | ${label} | reasoning ${effortLabel}${executionSuffix}`;
    return `${summary}${compactPlanningSuffix}`;
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
  const usesDag = steps.some((step) => (step?.depends_on || []).length || (step?.owned_paths || []).length);
  if (usesDag) {
    const activeCaption = progressActiveStatusCaption(plan, language, completed, total);
    if (activeCaption) {
      return activeCaption;
    }
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
  const normalizedStatus = String(step?.status || "").trim().toLowerCase();
  return Boolean(step) && !isSystemStep(step) && ["pending", "failed"].includes(normalizedStatus) && !busy;
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
  const usesDag = steps.some((step) => (step?.depends_on || []).length || (step?.owned_paths || []).length);
  if (usesDag) {
    const activeCaption = progressActiveStatusCaption(plan, "en", completed, total);
    if (activeCaption) {
      return activeCaption;
    }
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

function progressDisplayCaption(plan, language = "en", dagAware = false) {
  const { steps, completedStepCount, totalStepCount, completedCount, totalCount, closeoutStatus } = planProgressCounts(plan);
  const locale = normalizeLanguage(language);
  if (!totalCount) {
    return translate(locale, "progress.noPlanYet");
  }
  if (completedStepCount === totalStepCount) {
    if (closeoutStatus === "completed") {
      return translate(locale, "progress.closeoutCompleted", { completed: completedCount, total: totalCount });
    }
    if (closeoutStatus === "running") {
      return translate(locale, "progress.closeoutRunning", { completed: completedCount, total: totalCount });
    }
    if (closeoutStatus === "failed") {
      return translate(locale, "progress.closeoutFailed", { completed: completedCount, total: totalCount });
    }
    return translate(locale, "progress.closeoutPending", { completed: completedCount, total: totalCount });
  }
  if (dagAware) {
    const activeCaption = progressActiveStatusCaption(plan, locale, completedCount, totalCount);
    if (activeCaption) {
      return activeCaption;
    }
    const completedIds = new Set(steps.filter((step) => step.status === "completed").map((step) => step.step_id));
    const readyIds = steps
      .filter(
        (step) =>
          step.status !== "completed" &&
          (step.depends_on || []).every((dependency) => completedIds.has(dependency)),
      )
      .map((step) => step.step_id);
    return translate(locale, "progress.readyIds", {
      completed: completedCount,
      total: totalCount,
      ids: readyIds.join(", ") || "blocked",
    });
  }
  const nextStep = steps.find((step) => step.status !== "completed");
  return translate(locale, "progress.doneNext", {
    completed: completedCount,
    total: totalCount,
    next: nextStep?.step_id || "done",
  });
}

export function progressCaptionDisplay(plan, language = "en") {
  return progressDisplayCaption(plan, language, false);
}

export function executionProgressCaptionDisplay(plan, language = "en") {
  return progressDisplayCaption(plan, language, true);
}

export function toolbarProgressCaptionDisplay(plan, language = "en", options = {}) {
  const command = String(options?.activeJob?.command || "").trim().toLowerCase();
  const jobStatus = String(options?.activeJob?.status || "").trim().toLowerCase();
  if ((jobStatus === "running" && command === "generate-plan") || isPlanningProgressRunning(options?.planningProgress)) {
    return planningProgressCaptionDisplay(options?.planningProgress, language);
  }
  return progressDisplayCaption(plan, language, true);
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
    case "run-manual-debugger":
      return locale === "ko" ? "수동 디버거" : "Manual Debugger";
    case "run-manual-merger":
      return locale === "ko" ? "수동 머저" : "Manual Merger";
    default:
      return String(command || (locale === "ko" ? "백그라운드 작업" : "Background Job"))
        .split("-")
        .join(" ");
  }
}

export function statusTone(status) {
  const normalized = String(status || "").trim().toLowerCase();
  if (isDebuggingStatus(status)) {
    return "warning";
  }
  if (normalized === "awaiting_review" || normalized === "awaiting_checkpoint_approval") {
    return "warning";
  }
  if (normalized.startsWith("queued")) {
    return "info";
  }
  if (normalized.includes("cancelled")) {
    return "neutral";
  }
  if (normalized.includes("failed")) {
    return "danger";
  }
  if (normalized === "integrating") {
    return "info";
  }
  if (normalized.includes("running")) {
    return "info";
  }
  if (normalized === "completed") {
    return "success";
  }
  if (normalized.includes("paused")) {
    return "warning";
  }
  return "neutral";
}

const FAILURE_REASON_LABELS = {
  preflight_failed: {
    en: "Preflight failed",
    ko: "실행 준비 실패",
  },
  agent_pass_failed: {
    en: "Agent pass failed",
    ko: "에이전트 실행 실패",
  },
  verification_test_failed: {
    en: "Verification tests failed",
    ko: "검증 테스트 실패",
  },
  parallel_execution_failed: {
    en: "Parallel execution failed",
    ko: "병렬 실행 실패",
  },
  parallel_merge_conflict: {
    en: "Parallel merge conflict",
    ko: "병렬 병합 충돌",
  },
  recovery_artifacts_missing: {
    en: "Recovery artifacts missing",
    ko: "복구 아티팩트 없음",
  },
  merge_conflict_state_invalid: {
    en: "No active merge conflict",
    ko: "활성 병합 충돌 없음",
  },
  closeout_failed: {
    en: "Closeout failed",
    ko: "클로즈아웃 실패",
  },
};

function failureReasonLabelForCode(reasonCode, language = "en") {
  const normalized = String(reasonCode || "").trim().toLowerCase();
  if (!normalized) {
    return "";
  }
  const labels = FAILURE_REASON_LABELS[normalized];
  if (labels) {
    return language === "ko" ? labels.ko : labels.en;
  }
  return normalized
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function failureReasonCode(value = null) {
  if (!value || typeof value !== "object") {
    return "";
  }
  if (typeof value.failure_reason_code === "string") {
    return value.failure_reason_code.trim().toLowerCase();
  }
  if (typeof value?.metadata?.failure_reason_code === "string") {
    return value.metadata.failure_reason_code.trim().toLowerCase();
  }
  return "";
}

export function failureReasonLabel(value = null, language = "en") {
  return failureReasonLabelForCode(failureReasonCode(value), language);
}
