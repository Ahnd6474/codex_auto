import assert from "node:assert/strict";
import test from "node:test";

import {
  activityLineSummary,
  applyConfigRuntimeModelSelection,
  applyProviderDefaults,
  applyProgramSettings,
  applyProgramSettingsToForm,
  autoRoutingPresetLabel,
  backgroundJobProjectKey,
  configReasoningOptions,
  basename,
  blankProjectForm,
  buildProjectPayload,
  buildRunPlanPayloadFromDetail,
  canEditStep,
  codexUsageBuckets,
  cloneValue,
  commandLabel,
  detailApplySignature,
  computePlanStats,
  CLAUDE_DEFAULT_MODEL,
  DEEPSEEK_DEFAULT_MODEL,
  defaultCodexPath,
  planStepsWithCloseout,
  deriveExecutionProgress,
  reasoningEffortLabel,
  deriveIdleProjectStatus,
  deriveGithubMode,
  effectiveStepStatus,
  executionProgressCaptionDisplay,
  firstSelectableStepId,
  GEMINI_DEFAULT_MODEL,
  GLM_DEFAULT_MODEL,
  inheritProjectIdentityForm,
  isDuplicateProjectJobError,
  isPlanningProgressRunning,
  KIMI_DEFAULT_MODEL,
  mergeProjectDetailCodexStatus,
  MINIMAX_DEFAULT_MODEL,
  normalizeMemoryBudgetGiB,
  normalizeInterruptedPlan,
  planDependencyValidationMessage,
  planningProgressCaptionDisplay,
  progressCaption,
  programSettingsFromRuntime,
  providerSupportsCatalog,
  projectJobFromJobs,
  projectFormFromDetail,
  projectStatusWithJob,
  runtimeSummary,
  QWEN_CODE_DEFAULT_MODEL,
  sanitizeProjectDetailForJobState,
  sanitizeProjectListForJobState,
  selectedConfigReasoning,
  shouldKeepUnsavedPlan,
  shouldShowEstimatedCost,
  shouldReplaceVisibleProject,
  statusTone,
  syncProgramSettingsModel,
  toolbarProgressCaptionDisplay,
  workspaceStatsFromProjects,
} from "../src/utils.js";

test("cloneValue deep-clones plain data and preserves nullish values", () => {
  const original = {
    runtime: {
      model: "gpt-5.4",
      tags: ["desktop", "tests"],
    },
  };

  const cloned = cloneValue(original);
  cloned.runtime.tags.push("changed");

  assert.deepEqual(original.runtime.tags, ["desktop", "tests"]);
  assert.deepEqual(cloned.runtime.tags, ["desktop", "tests", "changed"]);
  assert.equal(cloneValue(null), null);
  assert.equal(cloneValue(undefined), undefined);
});

test("basename handles Windows, POSIX, and empty paths", () => {
  assert.equal(basename("C:\\work\\repo"), "repo");
  assert.equal(basename("/tmp/demo/"), "demo");
  assert.equal(basename(""), "");
});

test("detailApplySignature tracks payload identity and running job state", () => {
  const detail = {
    detail_level: "core",
    detail_signature: "sig-123",
    project: {
      repo_id: "repo-1",
      current_status: "running:block:2",
    },
  };

  assert.equal(
    detailApplySignature(detail, { id: "job-1", status: "running" }),
    "repo-1|core|sig-123|running:block:2|job-1|running",
  );
  assert.notEqual(
    detailApplySignature(detail, { id: "job-1", status: "running" }),
    detailApplySignature(detail, { id: "job-2", status: "running" }),
  );
});

test("project job helpers match jobs by repo id or project path and derive display status", () => {
  const jobs = [
    {
      id: "job-queued",
      status: "queued",
      command: "run-plan",
      project_dir: "C:\\Work\\Repo",
      updated_at_ms: 20,
    },
    {
      id: "job-running",
      status: "running",
      command: "generate-plan",
      repo_id: "repo-1",
      updated_at_ms: 10,
    },
  ];

  assert.equal(projectJobFromJobs(jobs, { repo_id: "repo-1" })?.id, "job-running");
  assert.equal(projectJobFromJobs(jobs, { repo_path: "c:/work/repo" })?.id, "job-queued");
  assert.equal(projectStatusWithJob("plan_ready", jobs[0]), "queued:run-plan");
  assert.equal(projectStatusWithJob("setup_ready", jobs[1]), "running:generate-plan");
});

test("backgroundJobProjectKey normalizes workspace and project paths for deduping", () => {
  assert.equal(
    backgroundJobProjectKey(
      {
        project_dir: "C:\\Work\\Repo",
      },
      "C:\\Users\\alber\\Workspace",
    ),
    "c:/users/alber/workspace||c:/work/repo",
  );
  assert.equal(
    backgroundJobProjectKey(
      {
        repo_id: "repo-1",
      },
      "/tmp/workspace",
    ),
    "/tmp/workspace|repo-1|",
  );
  assert.equal(backgroundJobProjectKey({}, "/tmp/workspace"), "");
});

test("isDuplicateProjectJobError detects bridge rejections for already-active jobs", () => {
  assert.equal(isDuplicateProjectJobError("Another background task is already active for this project."), true);
  assert.equal(isDuplicateProjectJobError(new Error("another background task is already active for this project.")), true);
  assert.equal(isDuplicateProjectJobError("The requested background job was not found."), false);
});

test("planDependencyValidationMessage reports dependency cycles with step ids", () => {
  assert.equal(
    planDependencyValidationMessage({
      steps: [
        { step_id: "ST1", depends_on: ["ST2"] },
        { step_id: "ST2", depends_on: ["ST1"] },
      ],
    }),
    "Parallel execution plan contains a dependency cycle: ST1 -> ST2 -> ST1.",
  );
});

test("planDependencyValidationMessage reports unknown dependency references", () => {
  assert.equal(
    planDependencyValidationMessage({
      steps: [{ step_id: "ST1", depends_on: ["ST9"] }],
    }),
    "Unknown dependency reference: ST9",
  );
});

test("project job helpers ignore stale running jobs when the project has a newer saved state", () => {
  const jobs = [
    {
      id: "job-running",
      status: "running",
      command: "run-plan",
      repo_id: "repo-1",
      updated_at_ms: Date.parse("2026-03-27T03:00:00Z"),
    },
  ];

  assert.equal(
    projectJobFromJobs(jobs, {
      repo_id: "repo-1",
      current_status: "closed_out",
      last_run_at: "2026-03-27T03:25:31Z",
    }),
    null,
  );
  assert.equal(
    projectJobFromJobs(jobs, {
      repo_id: "repo-1",
      current_status: "plan_ready",
      last_run_at: "2026-03-27T02:59:59Z",
    })?.id,
    "job-running",
  );
});

test("deriveGithubMode distinguishes manual and existing projects", () => {
  assert.equal(deriveGithubMode("https://github.com/openai/jakal-flow"), "manual");
  assert.equal(deriveGithubMode(""), "existing");
  assert.equal(deriveGithubMode(null), "existing");
});

test("defaultCodexPath follows the current platform", () => {
  assert.equal(defaultCodexPath(), process.platform === "win32" ? "codex.cmd" : "codex");
  assert.equal(defaultCodexPath("claude"), process.platform === "win32" ? "claude.cmd" : "claude");
  assert.equal(defaultCodexPath("gemini"), process.platform === "win32" ? "gemini.cmd" : "gemini");
  assert.equal(defaultCodexPath("qwen_code"), process.platform === "win32" ? "qwen.cmd" : "qwen");
  assert.equal(defaultCodexPath("deepseek"), process.platform === "win32" ? "claude.cmd" : "claude");
});

test("program settings helpers keep global runtime controls separate from project-specific values", () => {
  const settings = programSettingsFromRuntime({
    approval_mode: "untrusted",
    sandbox_mode: "workspace-write",
    allow_push: false,
  });

  assert.deepEqual(settings, {
    model_provider: "openai",
    local_model_provider: "ollama",
    provider_base_url: "",
    provider_api_key_env: "OPENAI_API_KEY",
    ensemble_openai_model: "gpt-5.4",
    ensemble_gemini_model: GEMINI_DEFAULT_MODEL,
    ensemble_claude_model: CLAUDE_DEFAULT_MODEL,
    model: "gpt-5.4",
    planning_effort: "medium",
    model_preset: "",
    model_selection_mode: "slug",
    model_slug_input: "gpt-5.4",
    approval_mode: "untrusted",
    sandbox_mode: "workspace-write",
    checkpoint_interval_blocks: 1,
    codex_path: defaultCodexPath(),
    allow_push: false,
    require_checkpoint_approval: false,
    workflow_mode: "standard",
    ml_max_cycles: 3,
    execution_mode: "parallel",
    parallel_worker_mode: "auto",
    parallel_workers: 0,
    parallel_memory_per_worker_gib: 3,
    save_project_logs: false,
    developer_mode: false,
    ui_theme: "dark",
    dashboard_visibility: {
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
    },
    background_concurrency_limit: 2,
  });

  assert.deepEqual(
    applyProgramSettings(
      {
        test_cmd: "pytest -q",
      },
      settings,
    ),
    {
      test_cmd: "pytest -q",
      model_provider: "openai",
      local_model_provider: "ollama",
      provider_base_url: "",
      provider_api_key_env: "OPENAI_API_KEY",
      ensemble_openai_model: "gpt-5.4",
      ensemble_gemini_model: GEMINI_DEFAULT_MODEL,
      ensemble_claude_model: CLAUDE_DEFAULT_MODEL,
      model: "gpt-5.4",
      planning_effort: "medium",
      model_preset: "",
      model_selection_mode: "slug",
      model_slug_input: "gpt-5.4",
      approval_mode: "untrusted",
      sandbox_mode: "workspace-write",
      checkpoint_interval_blocks: 1,
      codex_path: defaultCodexPath(),
      allow_push: false,
      require_checkpoint_approval: false,
      workflow_mode: "standard",
      ml_max_cycles: 3,
      execution_mode: "parallel",
      parallel_worker_mode: "auto",
      parallel_workers: 0,
      parallel_memory_per_worker_gib: 3,
      save_project_logs: false,
    },
  );

  assert.deepEqual(
    applyProgramSettingsToForm(
      {
        project_dir: "demo",
        runtime: {
          model: "gpt-5.4",
          test_cmd: "pytest -q",
          approval_mode: "never",
        },
      },
      settings,
    ),
    {
      project_dir: "demo",
      runtime: {
        model: "gpt-5.4",
        model_preset: "",
        model_selection_mode: "slug",
        model_slug_input: "gpt-5.4",
        test_cmd: "pytest -q",
        model_provider: "openai",
        local_model_provider: "ollama",
        provider_base_url: "",
        provider_api_key_env: "OPENAI_API_KEY",
        ensemble_openai_model: "gpt-5.4",
        ensemble_gemini_model: GEMINI_DEFAULT_MODEL,
        ensemble_claude_model: CLAUDE_DEFAULT_MODEL,
        planning_effort: "medium",
        approval_mode: "untrusted",
        sandbox_mode: "workspace-write",
        checkpoint_interval_blocks: 1,
        codex_path: defaultCodexPath(),
        allow_push: false,
        require_checkpoint_approval: false,
        workflow_mode: "standard",
        ml_max_cycles: 3,
        execution_mode: "parallel",
        parallel_worker_mode: "auto",
        parallel_workers: 0,
        parallel_memory_per_worker_gib: 3,
        save_project_logs: false,
      },
    },
  );
});

test("blankProjectForm seeds runtime defaults without mutating the source runtime", () => {
  const defaultRuntime = {
    model_preset: "default",
    generate_word_report: false,
    max_blocks: 9,
    test_cmd: "pytest -q",
  };

  const form = blankProjectForm(defaultRuntime);
  form.runtime.test_cmd = "npm test";

  assert.deepEqual(defaultRuntime, {
    model_preset: "default",
    generate_word_report: false,
    max_blocks: 9,
    test_cmd: "pytest -q",
  });
  assert.equal(form.branch, "main");
  assert.equal(form.github_mode, "existing");
  assert.equal(form.runtime.model, "gpt-5.4");
  assert.equal(form.runtime.max_blocks, 9);
  assert.equal(form.runtime.generate_word_report, false);
  assert.equal(form.runtime.allow_background_queue, true);
  assert.equal(form.runtime.background_queue_priority, 0);
});

test("blankProjectForm falls back to repository defaults when runtime is missing", () => {
  const form = blankProjectForm(null);

  assert.equal(form.runtime.model, "gpt-5.4");
  assert.equal(form.runtime.model_preset, "");
  assert.equal(form.runtime.model_slug_input, "gpt-5.4");
  assert.equal(form.runtime.generate_word_report, true);
  assert.equal(form.runtime.max_blocks, 5);
  assert.equal(form.runtime.optimization_mode, "light");
  assert.equal(form.runtime.test_cmd, "python -m pytest");
  assert.equal(form.runtime.allow_background_queue, true);
  assert.equal(form.runtime.background_queue_priority, 0);
});

test("providerSupportsCatalog enables curated catalogs for first-party provider presets", () => {
  assert.equal(providerSupportsCatalog("openai"), true);
  assert.equal(providerSupportsCatalog("gemini"), true);
  assert.equal(providerSupportsCatalog("claude"), true);
  assert.equal(providerSupportsCatalog("deepseek"), true);
  assert.equal(providerSupportsCatalog("openrouter"), false);
  assert.equal(providerSupportsCatalog("local_openai"), false);
});

test("applyProviderDefaults drops the auto sentinel for providers without auto routing", () => {
  const runtime = applyProviderDefaults(
    {
      model_provider: "openai",
      model: "auto",
      model_slug_input: "auto",
      model_preset: "auto",
    },
    "openrouter",
  );

  assert.equal(runtime.model_provider, "openrouter");
  assert.equal(runtime.model, "");
  assert.equal(runtime.model_slug_input, "");
  assert.equal(runtime.model_preset, "");
});

test("applyProviderDefaults switches the runtime path for Gemini CLI and clears OpenAI-only defaults", () => {
  const runtime = applyProviderDefaults(
    {
      model_provider: "openai",
      model: "gpt-5.4",
      model_slug_input: "gpt-5.4",
      codex_path: defaultCodexPath(),
    },
    "gemini",
  );

  assert.equal(runtime.model_provider, "gemini");
  assert.equal(runtime.codex_path, defaultCodexPath("gemini"));
  assert.equal(runtime.model, GEMINI_DEFAULT_MODEL);
  assert.equal(runtime.model_slug_input, GEMINI_DEFAULT_MODEL);
  assert.equal(runtime.provider_api_key_env, "GEMINI_API_KEY");
});

test("applyProviderDefaults switches the runtime path for Claude Code and applies Anthropic defaults", () => {
  const runtime = applyProviderDefaults(
    {
      model_provider: "openai",
      model: "gpt-5.4",
      model_slug_input: "gpt-5.4",
      codex_path: defaultCodexPath(),
    },
    "claude",
  );

  assert.equal(runtime.model_provider, "claude");
  assert.equal(runtime.codex_path, defaultCodexPath("claude"));
  assert.equal(runtime.model, CLAUDE_DEFAULT_MODEL);
  assert.equal(runtime.model_slug_input, CLAUDE_DEFAULT_MODEL);
  assert.equal(runtime.provider_api_key_env, "ANTHROPIC_API_KEY");
});

test("applyProviderDefaults switches the runtime path for Qwen Code and applies DashScope defaults", () => {
  const runtime = applyProviderDefaults(
    {
      model_provider: "openai",
      model: "gpt-5.4",
      model_slug_input: "gpt-5.4",
      codex_path: defaultCodexPath(),
    },
    "qwen_code",
  );

  assert.equal(runtime.model_provider, "qwen_code");
  assert.equal(runtime.codex_path, defaultCodexPath("qwen_code"));
  assert.equal(runtime.model, QWEN_CODE_DEFAULT_MODEL);
  assert.equal(runtime.model_slug_input, QWEN_CODE_DEFAULT_MODEL);
  assert.equal(runtime.provider_base_url, "https://dashscope.aliyuncs.com/compatible-mode/v1");
  assert.equal(runtime.provider_api_key_env, "DASHSCOPE_API_KEY");
});

test("applyProviderDefaults seeds Claude-compatible vendor defaults", () => {
  const deepseek = applyProviderDefaults(
    {
      model_provider: "openai",
      model: "gpt-5.4",
      model_slug_input: "gpt-5.4",
      codex_path: defaultCodexPath(),
    },
    "deepseek",
  );
  const minimax = applyProviderDefaults(
    {
      model_provider: "openai",
      model: "gpt-5.4",
      model_slug_input: "gpt-5.4",
      codex_path: defaultCodexPath(),
    },
    "minimax",
  );
  const glm = applyProviderDefaults(
    {
      model_provider: "openai",
      model: "gpt-5.4",
      model_slug_input: "gpt-5.4",
      codex_path: defaultCodexPath(),
    },
    "glm",
  );

  assert.equal(deepseek.codex_path, defaultCodexPath("deepseek"));
  assert.equal(deepseek.model, DEEPSEEK_DEFAULT_MODEL);
  assert.equal(deepseek.provider_api_key_env, "DEEPSEEK_API_KEY");
  assert.equal(deepseek.provider_base_url, "https://api.deepseek.com/anthropic");
  assert.equal(minimax.model, MINIMAX_DEFAULT_MODEL);
  assert.equal(minimax.provider_base_url, "https://api.minimax.io/anthropic/v1");
  assert.equal(glm.model, GLM_DEFAULT_MODEL);
  assert.equal(glm.provider_base_url, "https://open.bigmodel.cn/api/anthropic");
});

test("applyProviderDefaults seeds Kimi defaults on the Codex/OpenAI-compatible path", () => {
  const runtime = applyProviderDefaults(
    {
      model_provider: "openai",
      model: "gpt-5.4",
      model_slug_input: "gpt-5.4",
      codex_path: defaultCodexPath(),
    },
    "kimi",
  );

  assert.equal(runtime.model_provider, "kimi");
  assert.equal(runtime.codex_path, defaultCodexPath());
  assert.equal(runtime.model, KIMI_DEFAULT_MODEL);
  assert.equal(runtime.provider_base_url, "https://api.moonshot.cn/v1");
  assert.equal(runtime.provider_api_key_env, "MOONSHOT_API_KEY");
});

test("applyProviderDefaults switches the runtime path for the ensemble provider and keeps Codex defaults", () => {
  const runtime = applyProviderDefaults(
    {
      model_provider: "openai",
      model: "gpt-5.4",
      model_slug_input: "gpt-5.4",
      codex_path: defaultCodexPath(),
    },
    "ensemble",
  );

  assert.equal(runtime.model_provider, "ensemble");
  assert.equal(runtime.codex_path, defaultCodexPath());
  assert.equal(runtime.model, "gpt-5.4");
  assert.equal(runtime.model_slug_input, "gpt-5.4");
  assert.equal(runtime.provider_api_key_env, "OPENAI_API_KEY");
  assert.equal(runtime.ensemble_openai_model, "gpt-5.4");
  assert.equal(runtime.ensemble_gemini_model, GEMINI_DEFAULT_MODEL);
  assert.equal(runtime.ensemble_claude_model, CLAUDE_DEFAULT_MODEL);
});

test("blankProjectForm keeps Gemini CLI projects on the Gemini default model", () => {
  const form = blankProjectForm({
    model_provider: "gemini",
    provider_api_key_env: "GEMINI_API_KEY",
    codex_path: defaultCodexPath("gemini"),
  });

  assert.equal(form.runtime.model_provider, "gemini");
  assert.equal(form.runtime.model, GEMINI_DEFAULT_MODEL);
  assert.equal(form.runtime.model_slug_input, GEMINI_DEFAULT_MODEL);
});

test("blankProjectForm keeps Claude Code projects on the Claude default model", () => {
  const form = blankProjectForm({
    model_provider: "claude",
    provider_api_key_env: "ANTHROPIC_API_KEY",
    codex_path: defaultCodexPath("claude"),
  });

  assert.equal(form.runtime.model_provider, "claude");
  assert.equal(form.runtime.model, CLAUDE_DEFAULT_MODEL);
  assert.equal(form.runtime.model_slug_input, CLAUDE_DEFAULT_MODEL);
});

test("blankProjectForm keeps Qwen Code projects on the Qwen default model", () => {
  const form = blankProjectForm({
    model_provider: "qwen_code",
    provider_api_key_env: "DASHSCOPE_API_KEY",
    codex_path: defaultCodexPath("qwen_code"),
  });

  assert.equal(form.runtime.model_provider, "qwen_code");
  assert.equal(form.runtime.model, QWEN_CODE_DEFAULT_MODEL);
  assert.equal(form.runtime.model_slug_input, QWEN_CODE_DEFAULT_MODEL);
});

test("blankProjectForm keeps ensemble projects on the Codex default model", () => {
  const form = blankProjectForm({
    model_provider: "ensemble",
    provider_api_key_env: "OPENAI_API_KEY",
    codex_path: defaultCodexPath(),
  });

  assert.equal(form.runtime.model_provider, "ensemble");
  assert.equal(form.runtime.model, "gpt-5.4");
  assert.equal(form.runtime.model_slug_input, "gpt-5.4");
  assert.equal(form.runtime.ensemble_openai_model, "gpt-5.4");
  assert.equal(form.runtime.ensemble_gemini_model, GEMINI_DEFAULT_MODEL);
  assert.equal(form.runtime.ensemble_claude_model, CLAUDE_DEFAULT_MODEL);
});

test("normalizeMemoryBudgetGiB keeps one decimal place for UI memory budgets", () => {
  assert.equal(normalizeMemoryBudgetGiB("1.54", 3), 1.5);
  assert.equal(normalizeMemoryBudgetGiB("1.55", 3), 1.6);
  assert.equal(normalizeMemoryBudgetGiB("0", 3), 0.1);
  assert.equal(normalizeMemoryBudgetGiB("bogus", 1.5), 1.5);
});

test("projectFormFromDetail merges persisted runtime and derives GitHub mode", () => {
  const detail = {
    project: {
      repo_path: "C:/work/demo",
      display_name: "Demo App",
      slug: "demo-app",
      branch: "release",
      origin_url: "https://github.com/openai/demo-app",
    },
    runtime: {
      test_cmd: "npm run check",
      model: "gpt-5.4",
    },
  };
  const defaultRuntime = {
    max_blocks: 7,
    effort: "high",
    optimization_mode: "refactor",
  };

  const form = projectFormFromDetail(detail, defaultRuntime);

  assert.deepEqual(form, {
    project_dir: "C:/work/demo",
    display_name: "Demo App",
    branch: "release",
    origin_url: "https://github.com/openai/demo-app",
    github_mode: "manual",
    runtime: {
      max_blocks: 7,
      effort: "high",
      optimization_mode: "refactor",
      execution_mode: "parallel",
      allow_background_queue: true,
      background_queue_priority: 0,
      test_cmd: "npm run check",
      model: "gpt-5.4",
    },
  });
});

test("inheritProjectIdentityForm keeps project links but resets runtime to app defaults", () => {
  const form = inheritProjectIdentityForm(
    {
      project_dir: "C:/work/demo",
      display_name: "Demo App",
      branch: "release",
      origin_url: "https://github.com/openai/demo-app",
      github_mode: "manual",
      runtime: {
        model: "gpt-5.4-mini",
        effort: "high",
        parallel_memory_per_worker_gib: 7,
        test_cmd: "npm test",
      },
    },
    {
      model: "auto",
      effort: "medium",
      parallel_memory_per_worker_gib: 3,
      test_cmd: "python -m pytest",
      optimization_mode: "light",
    },
  );

  assert.deepEqual(
    {
      project_dir: form.project_dir,
      display_name: form.display_name,
      branch: form.branch,
      origin_url: form.origin_url,
      github_mode: form.github_mode,
    },
    {
      project_dir: "C:/work/demo",
      display_name: "Demo App",
      branch: "release",
      origin_url: "https://github.com/openai/demo-app",
      github_mode: "manual",
    },
  );
  assert.equal(form.runtime.model, "auto");
  assert.equal(form.runtime.effort, "medium");
  assert.equal(form.runtime.parallel_memory_per_worker_gib, 3);
  assert.equal(form.runtime.test_cmd, "python -m pytest");
  assert.equal(form.runtime.optimization_mode, "light");
  assert.equal(form.runtime.generate_word_report, true);
  assert.equal(form.runtime.max_blocks, 5);
  assert.equal(form.runtime.execution_mode, "parallel");
  assert.equal(form.runtime.model_slug_input, "auto");
  assert.equal(form.runtime.model_provider, "openai");
  assert.equal(form.runtime.local_model_provider, "ollama");
  assert.equal(form.runtime.approval_mode, "never");
  assert.equal(form.runtime.sandbox_mode, "danger-full-access");
  assert.equal(form.runtime.allow_push, true);
  assert.equal(form.runtime.workflow_mode, "standard");
  assert.equal(form.runtime.parallel_worker_mode, "auto");
  assert.equal(form.runtime.parallel_workers, 0);
  assert.equal(form.runtime.ml_max_cycles, 3);
  assert.equal(form.runtime.checkpoint_interval_blocks, 1);
  assert.equal(form.runtime.require_checkpoint_approval, false);
  assert.equal(form.runtime.model_preset, "auto");
  assert.equal(form.runtime.model_selection_mode, "slug");
  assert.equal(form.runtime.planning_effort, "medium");
  assert.equal(form.runtime.provider_base_url, "");
  assert.equal(form.runtime.provider_api_key_env, "OPENAI_API_KEY");
  assert.equal(form.runtime.codex_path, defaultCodexPath());
});

test("mergeProjectDetailCodexStatus preserves the last known catalog when a lightweight detail omits it", () => {
  const fallbackStatus = {
    available: true,
    model_catalog: [{ model: "auto", display_name: "Auto" }],
    account: { email: "demo@example.com" },
  };
  const merged = mergeProjectDetailCodexStatus(
    {
      project: { repo_id: "repo-a" },
      codex_status: {},
      snapshot: {},
      bottom_panels: {},
    },
    fallbackStatus,
    fallbackStatus.model_catalog,
  );

  assert.deepEqual(merged.codex_status, fallbackStatus);
  assert.deepEqual(merged.snapshot.codex_status, fallbackStatus);
  assert.deepEqual(merged.bottom_panels.codex_status, fallbackStatus);
});

test("shouldKeepUnsavedPlan only preserves local edits for the same project", () => {
  assert.equal(shouldKeepUnsavedPlan("repo-a", "repo-a", true), true);
  assert.equal(shouldKeepUnsavedPlan("repo-a", "repo-b", true), false);
  assert.equal(shouldKeepUnsavedPlan("repo-a", "", true), false);
  assert.equal(shouldKeepUnsavedPlan("repo-a", "repo-a", false), false);
});

test("shouldReplaceVisibleProject only accepts a completed job for the visible project", () => {
  assert.equal(shouldReplaceVisibleProject("", "repo-a"), true);
  assert.equal(shouldReplaceVisibleProject("repo-a", "repo-a"), true);
  assert.equal(shouldReplaceVisibleProject("repo-a", "repo-b"), false);
  assert.equal(shouldReplaceVisibleProject("repo-a", ""), false);
});

test("running-state helpers fall back to idle project status when no job is active", () => {
  const plan = {
    closeout_status: "running",
    steps: [
      { step_id: "ST1", status: "completed" },
      { step_id: "ST2", status: "integrating" },
    ],
  };
  const normalizedPlan = normalizeInterruptedPlan(plan);

  assert.deepEqual(computePlanStats(plan), {
    total_steps: 2,
    completed_steps: 1,
    failed_steps: 0,
    running_steps: 1,
    remaining_steps: 1,
  });
  assert.deepEqual(normalizedPlan, {
    closeout_status: "not_started",
    steps: [
      { step_id: "ST1", status: "completed" },
      { step_id: "ST2", status: "pending" },
    ],
  });
  assert.equal(deriveIdleProjectStatus(normalizedPlan, null, "running:block:2"), "plan_ready");
  assert.deepEqual(
    workspaceStatsFromProjects([
      { status: "plan_ready" },
      { status: "failed" },
      { status: "running:block:3" },
    ]),
    {
      project_count: 3,
      ready_like: 1,
      running: 1,
      failed: 1,
    },
  );
});

test("job-aware sanitizers clear stale running status without touching active jobs", () => {
  const runningDetail = {
    project: {
      repo_id: "repo-a",
      current_status: "running:block:2",
    },
    plan: {
      closeout_status: "running",
      steps: [
        { step_id: "ST1", status: "completed" },
        { step_id: "ST2", status: "running" },
      ],
    },
    stats: {
      total_steps: 2,
      completed_steps: 1,
      failed_steps: 0,
      running_steps: 1,
      remaining_steps: 1,
    },
    snapshot: {
      project: {
        current_status: "running:block:2",
      },
      plan: {
        closeout_status: "running",
        steps: [
          { step_id: "ST1", status: "completed" },
          { step_id: "ST2", status: "running" },
        ],
      },
    },
    bottom_panels: {
      git_status: {
        current_status: "running:block:2",
      },
    },
  };
  const runningList = [
    {
      repo_id: "repo-a",
      status: "running:block:2",
      stats: { total_steps: 2, completed_steps: 1, failed_steps: 0, running_steps: 1, remaining_steps: 1 },
      closeout_status: "not_started",
    },
  ];

  const sanitizedDetail = sanitizeProjectDetailForJobState(runningDetail, null);
  const activeDetail = sanitizeProjectDetailForJobState(runningDetail, { id: "job-1", status: "running" });
  const sanitizedList = sanitizeProjectListForJobState(runningList, null);

  assert.equal(sanitizedDetail.project.current_status, "plan_ready");
  assert.equal(sanitizedDetail.plan.closeout_status, "not_started");
  assert.equal(sanitizedDetail.plan.steps[1].status, "pending");
  assert.equal(sanitizedDetail.bottom_panels.git_status.current_status, "plan_ready");
  assert.equal(activeDetail.project.current_status, "running:block:2");
  assert.equal(sanitizedList[0].status, "plan_ready");
});

test("job-aware detail sanitizer ignores a stale running bridge job when saved project state is newer", () => {
  const detail = {
    project: {
      repo_id: "repo-a",
      current_status: "closed_out",
      last_run_at: "2026-03-27T03:25:31Z",
    },
    plan: {
      closeout_status: "completed",
      steps: [
        { step_id: "ST1", status: "completed" },
      ],
    },
    stats: {
      total_steps: 1,
      completed_steps: 1,
      failed_steps: 0,
      running_steps: 0,
      remaining_steps: 0,
    },
  };

  const sanitizedDetail = sanitizeProjectDetailForJobState(detail, {
    id: "job-1",
    status: "running",
    repo_id: "repo-a",
    updated_at_ms: Date.parse("2026-03-27T03:00:00Z"),
  });

  assert.equal(sanitizedDetail.project.current_status, "closed_out");
  assert.equal(sanitizedDetail.plan.closeout_status, "completed");
});

test("job-aware detail sanitizer prefers terminal plan state over recent running activity", () => {
  const nowMs = Date.parse("2026-03-26T10:00:00Z");
  const failedDetail = {
    project: {
      repo_id: "repo-a",
      current_status: "running:block:2",
      last_run_at: "2026-03-26T09:59:58Z",
    },
    activity: ["2026-03-26T09:59:59Z | step-started [ST2] | Running ST2: Build the screen"],
    plan: {
      closeout_status: "not_started",
      steps: [
        { step_id: "ST1", status: "completed" },
        { step_id: "ST2", status: "failed" },
      ],
    },
    stats: {
      total_steps: 2,
      completed_steps: 1,
      failed_steps: 1,
      running_steps: 0,
      remaining_steps: 1,
    },
    bottom_panels: {
      git_status: {
        current_status: "running:block:2",
      },
    },
  };
  const completedDetail = {
    project: {
      repo_id: "repo-b",
      current_status: "running:closeout",
      last_run_at: "2026-03-26T09:59:58Z",
    },
    activity: ["2026-03-26T09:59:59Z | closeout-started | Started project closeout."],
    plan: {
      closeout_status: "completed",
      steps: [
        { step_id: "ST1", status: "completed" },
        { step_id: "ST2", status: "completed" },
      ],
    },
    stats: {
      total_steps: 2,
      completed_steps: 2,
      failed_steps: 0,
      running_steps: 0,
      remaining_steps: 0,
    },
    bottom_panels: {
      git_status: {
        current_status: "running:closeout",
      },
    },
  };

  const sanitizedFailedDetail = sanitizeProjectDetailForJobState(failedDetail, null, { nowMs });
  const sanitizedCompletedDetail = sanitizeProjectDetailForJobState(completedDetail, null, { nowMs });

  assert.equal(sanitizedFailedDetail.project.current_status, "failed");
  assert.equal(sanitizedFailedDetail.bottom_panels.git_status.current_status, "failed");
  assert.equal(sanitizedCompletedDetail.project.current_status, "closed_out");
  assert.equal(sanitizedCompletedDetail.bottom_panels.git_status.current_status, "closed_out");
});

test("job-aware detail sanitizer marks planning progress as generate-plan when the job snapshot is missing", () => {
  const detail = {
    project: {
      repo_id: "repo-plan",
      current_status: "setup_ready",
    },
    planning_progress: {
      stage_count: 4,
      current_stage_index: 2,
      current_stage_status: "running",
    },
    bottom_panels: {
      git_status: {
        current_status: "setup_ready",
      },
    },
  };

  const sanitizedDetail = sanitizeProjectDetailForJobState(detail, null);

  assert.equal(sanitizedDetail.project.current_status, "running:generate-plan");
  assert.equal(sanitizedDetail.bottom_panels.git_status.current_status, "running:generate-plan");
});

test("job-aware detail sanitizer preserves a very recent active run signal while the job snapshot catches up", () => {
  const nowMs = Date.parse("2026-03-26T10:00:00Z");
  const runningDetail = {
    project: {
      repo_id: "repo-a",
      current_status: "running:block:2",
      last_run_at: "2026-03-26T09:59:40Z",
    },
    activity: ["2026-03-26T09:59:42Z | step-started [ST2] | Running ST2: Build the screen"],
    checkpoints: {
      pending: {
        checkpoint_id: "CP2",
        status: "awaiting_review",
      },
    },
    plan: {
      closeout_status: "not_started",
      steps: [
        { step_id: "ST1", status: "completed" },
        { step_id: "ST2", status: "running", started_at: "2026-03-26T09:59:35Z" },
      ],
    },
  };
  const runningList = [
    {
      repo_id: "repo-a",
      status: "running:block:2",
      last_run_at: "2026-03-26T09:59:40Z",
      stats: { total_steps: 2, completed_steps: 1, failed_steps: 0, running_steps: 1, remaining_steps: 1 },
      closeout_status: "not_started",
    },
  ];

  const preservedDetail = sanitizeProjectDetailForJobState(runningDetail, null, { nowMs });
  const sanitizedList = sanitizeProjectListForJobState(runningList, null, { nowMs });

  assert.equal(preservedDetail.project.current_status, "running:block:2");
  assert.equal(preservedDetail.plan.steps[1].status, "running");
  assert.equal(sanitizedList[0].status, "plan_ready");
});

test("job-aware sanitizers overlay queued and running status from multiple active jobs", () => {
  const projects = [
    {
      repo_id: "repo-a",
      repo_path: "C:/work/repo-a",
      status: "plan_ready",
      stats: { total_steps: 1, completed_steps: 0, failed_steps: 0, running_steps: 0, remaining_steps: 1 },
      closeout_status: "not_started",
    },
    {
      repo_id: "repo-b",
      repo_path: "C:/work/repo-b",
      status: "setup_ready",
      stats: { total_steps: 0, completed_steps: 0, failed_steps: 0, running_steps: 0, remaining_steps: 0 },
      closeout_status: "not_started",
    },
  ];
  const jobs = [
    { id: "job-1", status: "queued", command: "run-plan", project_dir: "C:\\work\\repo-a", updated_at_ms: 20 },
    { id: "job-2", status: "running", command: "generate-plan", repo_id: "repo-b", updated_at_ms: 10 },
  ];

  const nextProjects = sanitizeProjectListForJobState(projects, jobs);

  assert.equal(nextProjects[0].status, "queued:run-plan");
  assert.equal(nextProjects[1].status, "running:generate-plan");
});

test("job-aware sanitizers clear stale queued overlays when reservations disappear", () => {
  const projects = [
    {
      repo_id: "repo-a",
      repo_path: "C:/work/repo-a",
      status: "queued:run-plan",
      stats: { total_steps: 1, completed_steps: 0, failed_steps: 0, running_steps: 0, remaining_steps: 1 },
      closeout_status: "not_started",
    },
  ];

  const nextProjects = sanitizeProjectListForJobState(projects, []);

  assert.equal(nextProjects[0].status, "plan_ready");
});

test("activityLineSummary strips the timestamp and event prefix", () => {
  assert.equal(
    activityLineSummary("2026-03-26T09:00:00Z | step-started [ST2] | Running ST2: Build the screen"),
    "Running ST2: Build the screen",
  );
  assert.equal(activityLineSummary("single message"), "single message");
  assert.equal(activityLineSummary(""), "");
});

test("deriveExecutionProgress summarizes active step progress and recent activity", () => {
  const progress = deriveExecutionProgress(
    {
      project: {
        current_status: "running:block:2",
      },
      stats: {
        total_steps: 3,
        completed_steps: 1,
        failed_steps: 0,
        running_steps: 1,
        remaining_steps: 2,
      },
      activity: [
        "2026-03-26T09:01:00Z | step-started [ST2] | Running ST2: Build the screen",
        "2026-03-26T09:00:00Z | batch-started | Running parallel batch: ST2, ST3",
      ],
      plan: {
        execution_mode: "parallel",
        closeout_status: "not_started",
        steps: [
          { step_id: "ST1", title: "Plan", status: "completed" },
          { step_id: "ST2", title: "Build", status: "running", depends_on: ["ST1"], owned_paths: ["desktop/src"] },
          { step_id: "ST3", title: "Backend", status: "pending", depends_on: ["ST1"], owned_paths: ["src/jakal_flow"] },
        ],
      },
    },
    null,
    {
      status: "running",
      command: "run-plan",
    },
  );

  assert.equal(progress.isActive, true);
  assert.equal(progress.phase, "step");
  assert.equal(progress.runningStep.step_id, "ST2");
  assert.deepEqual(progress.readyIds, ["ST2", "ST3"]);
  assert.equal(progress.completedProgressUnits, 1);
  assert.equal(progress.totalProgressUnits, 4);
  assert.equal(progress.percent, 25);
  assert.equal(progress.headlineActivity, "Running ST2: Build the screen");
});

test("deriveExecutionProgress falls back to an indeterminate planning state", () => {
  const progress = deriveExecutionProgress(
    {
      project: {
        current_status: "running:generate-plan",
      },
      activity: ["2026-03-26T09:02:00Z | plan-generated | Drafting execution plan"],
      plan: {
        execution_mode: "serial",
        closeout_status: "not_started",
        steps: [],
      },
    },
    null,
    {
      status: "running",
      command: "generate-plan",
    },
  );

  assert.equal(progress.isActive, true);
  assert.equal(progress.phase, "planning");
  assert.equal(progress.indeterminate, true);
  assert.equal(progress.totalSteps, 0);
});

test("deriveExecutionProgress uses structured planning progress when available", () => {
  const progress = deriveExecutionProgress(
    {
      project: {
        current_status: "setup_ready",
      },
      activity: [
        "2026-03-26T09:02:00Z | planner-agent-started | Planner Agent A is decomposing the work into implementation blocks.",
      ],
      planning_progress: {
        stage_count: 4,
        completed_stages: 1,
        percent: 38,
        current_stage_key: "planner_a",
        current_stage_index: 2,
        current_stage_label: "Planner Agent A",
        current_stage_status: "running",
        current_agent_label: "Planner Agent A",
        message: "Planner Agent A is decomposing the work into implementation blocks.",
        stages: [
          { key: "context_scan", index: 1, label: "Scan repository context", status: "completed" },
          { key: "planner_a", index: 2, label: "Planner Agent A", status: "running", agent_label: "Planner Agent A" },
          { key: "planner_b", index: 3, label: "Planner Agent B", status: "pending" },
          { key: "finalize", index: 4, label: "Validate and save plan", status: "pending" },
        ],
      },
      plan: {
        execution_mode: "serial",
        closeout_status: "not_started",
        steps: [],
      },
    },
    null,
    {
      status: "running",
      command: "generate-plan",
    },
  );

  assert.equal(progress.isActive, true);
  assert.equal(progress.phase, "planning");
  assert.equal(progress.indeterminate, false);
  assert.equal(progress.percent, 38);
  assert.equal(progress.planningStageCount, 4);
  assert.equal(progress.planningCurrentStage.label, "Planner Agent A");
  assert.equal(progress.planningCurrentAgentLabel, "Planner Agent A");
  assert.equal(progress.headlineActivity, "Planner Agent A is decomposing the work into implementation blocks.");
});

test("deriveExecutionProgress treats running planning progress as active even without a bridge job", () => {
  const progress = deriveExecutionProgress(
    {
      project: {
        current_status: "setup_ready",
      },
      planning_progress: {
        stage_count: 4,
        current_stage_index: 2,
        current_stage_status: "running",
        current_stage_label: "Planner Agent A",
      },
      plan: {
        execution_mode: "serial",
        closeout_status: "not_started",
        steps: [],
      },
    },
    null,
    null,
  );

  assert.equal(progress.isActive, true);
  assert.equal(progress.phase, "planning");
  assert.equal(progress.indeterminate, false);
  assert.equal(progress.planningCurrentStage.label, "Planner Agent A");
});

test("planningProgressCaptionDisplay reports the active planning stage and status", () => {
  assert.equal(isPlanningProgressRunning({ current_stage_status: "running" }), true);
  assert.equal(isPlanningProgressRunning({ currentStageStatus: "completed" }), false);
  assert.equal(
    planningProgressCaptionDisplay({
      stage_count: 4,
      current_stage_index: 2,
      current_stage_status: "running",
    }),
    "Planning stage 2/4, Running",
  );
  assert.equal(
    planningProgressCaptionDisplay(null),
    "Generating execution plan",
  );
});

test("syncProgramSettingsModel mirrors project model changes back into program defaults", () => {
  const nextSettings = syncProgramSettingsModel(
    {
      model_provider: "openai",
      model: "gpt-5.4",
      model_preset: "",
      model_selection_mode: "slug",
      model_slug_input: "gpt-5.4",
      ensemble_openai_model: "gpt-5.4",
      ensemble_gemini_model: GEMINI_DEFAULT_MODEL,
      ensemble_claude_model: CLAUDE_DEFAULT_MODEL,
    },
    {
      model_provider: "gemini",
      model: "gemini-2.5-pro",
      model_preset: "",
      model_selection_mode: "slug",
      model_slug_input: "gemini-2.5-pro",
      ensemble_openai_model: "gpt-5.4-mini",
      ensemble_gemini_model: "gemini-2.5-pro",
      ensemble_claude_model: "claude-3.7-sonnet",
    },
  );

  assert.equal(nextSettings.model_provider, "gemini");
  assert.equal(nextSettings.model, "gemini-2.5-pro");
  assert.equal(nextSettings.model_slug_input, "gemini-2.5-pro");
  assert.equal(nextSettings.ensemble_openai_model, "gpt-5.4-mini");
  assert.equal(nextSettings.ensemble_gemini_model, "gemini-2.5-pro");
  assert.equal(nextSettings.ensemble_claude_model, "claude-3.7-sonnet");
});

test("deriveExecutionProgress marks debugger recovery as an active debugging phase", () => {
  const progress = deriveExecutionProgress(
    {
      project: {
        current_status: "running:debugging",
      },
      activity: [
        "debugger | debugger_invoked | Debugging ST2 - Build | python -m pytest exited with 1",
      ],
      plan: {
        execution_mode: "serial",
        closeout_status: "not_started",
        steps: [
          { step_id: "ST1", title: "Plan", status: "completed" },
          { step_id: "ST2", title: "Build", status: "running" },
        ],
      },
      stats: {
        total_steps: 2,
        completed_steps: 1,
        failed_steps: 0,
        running_steps: 1,
        remaining_steps: 1,
      },
    },
    null,
    {
      status: "running",
      command: "run-plan",
    },
  );

  assert.equal(progress.isActive, true);
  assert.equal(progress.phase, "debugging");
  assert.equal(progress.debugging, true);
  assert.equal(progress.status, "running:debugging");
  assert.equal(progress.headlineActivity, "Debugging ST2 - Build | python -m pytest exited with 1");
});

test("deriveExecutionProgress keeps integrating steps in the active execution set", () => {
  const progress = deriveExecutionProgress(
    {
      project: {
        current_status: "running:parallel",
      },
      activity: [
        "2026-03-26T09:02:00Z | batch-started | Integrating ST2 while ST3 keeps running",
      ],
      plan: {
        execution_mode: "parallel",
        closeout_status: "not_started",
        steps: [
          { step_id: "ST1", title: "Plan", status: "completed" },
          { step_id: "ST2", title: "Integrate", status: "integrating", depends_on: ["ST1"] },
          { step_id: "ST3", title: "Backend", status: "running", depends_on: ["ST1"] },
        ],
      },
      stats: {
        total_steps: 3,
        completed_steps: 1,
        failed_steps: 0,
        running_steps: 2,
        remaining_steps: 2,
      },
    },
    null,
    {
      status: "running",
      command: "run-plan",
    },
  );

  assert.equal(progress.isActive, true);
  assert.deepEqual(progress.runningStepList.map((step) => step.step_id), ["ST2", "ST3"]);
  assert.equal(progress.runningStep?.status, "integrating");
});

test("buildProjectPayload trims fields, blanks origin_url for existing repos, and clones plan data", () => {
  const form = {
    project_dir: "  C:/work/demo  ",
    display_name: "  Demo App  ",
    branch: "  ",
    origin_url: "  https://github.com/openai/demo-app.git  ",
    github_mode: "existing",
    runtime: {
      test_cmd: "pytest -q",
    },
  };
  const plan = {
    steps: [{ step_id: "S1", status: "pending" }],
  };

  const payload = buildProjectPayload(form, plan);
  payload.runtime.test_cmd = "changed";
  payload.plan.steps[0].status = "completed";

  assert.deepEqual(form.runtime, { test_cmd: "pytest -q" });
  assert.deepEqual(plan.steps, [{ step_id: "S1", status: "pending" }]);
  assert.deepEqual(payload, {
    project_dir: "C:/work/demo",
    display_name: "Demo App",
    branch: "main",
    origin_url: "",
    runtime: {
      test_cmd: "changed",
    },
    plan: {
      workflow_mode: "standard",
      execution_mode: "parallel",
      default_test_command: "pytest -q",
      steps: [{ step_id: "S1", status: "completed" }],
    },
  });
});

test("buildProjectPayload keeps a manually entered origin URL", () => {
  const payload = buildProjectPayload({
    project_dir: "demo",
    display_name: "demo",
    branch: "main",
    origin_url: "  https://github.com/openai/demo-app.git  ",
    github_mode: "manual",
    runtime: {},
  });

  assert.equal(payload.origin_url, "https://github.com/openai/demo-app.git");
});

test("buildRunPlanPayloadFromDetail reuses the generated plan and persisted runtime", () => {
  const detail = {
    project: {
      repo_path: "C:/work/demo",
      display_name: "Demo App",
      slug: "demo-app",
      branch: "release",
      origin_url: "https://github.com/openai/demo-app",
    },
    runtime: {
      model: "gpt-5.4",
      test_cmd: "npm run check",
    },
    plan: {
      workflow_mode: "standard",
      steps: [{ step_id: "ST1", status: "pending" }],
    },
  };

  const payload = buildRunPlanPayloadFromDetail(detail, {
    max_blocks: 7,
    effort: "high",
  });

  assert.deepEqual(payload, {
    project_dir: "C:/work/demo",
    display_name: "Demo App",
    branch: "release",
    origin_url: "https://github.com/openai/demo-app",
    runtime: {
      max_blocks: 7,
      effort: "high",
      execution_mode: "parallel",
      allow_background_queue: true,
      background_queue_priority: 0,
      model: "gpt-5.4",
      test_cmd: "npm run check",
    },
    plan: {
      workflow_mode: "standard",
      execution_mode: "parallel",
      default_test_command: "npm run check",
      steps: [{ step_id: "ST1", status: "pending" }],
    },
  });
  assert.equal(buildRunPlanPayloadFromDetail({ project: { repo_path: "C:/work/demo" }, plan: { steps: [] } }, null), null);
});

test("firstSelectableStepId prefers the first incomplete step", () => {
  assert.equal(
    firstSelectableStepId({
      steps: [
        { step_id: "S1", status: "completed" },
        { step_id: "S2", status: "running" },
        { step_id: "S3", status: "pending" },
      ],
    }),
    "S2",
  );
  assert.equal(firstSelectableStepId({ steps: [{ step_id: "S1", status: "completed" }] }), "");
  assert.equal(firstSelectableStepId({ steps: [] }), "");
});

test("planStepsWithCloseout appends a synthetic final closeout node", () => {
  const steps = planStepsWithCloseout(
    {
      closeout_status: "not_started",
      closeout_notes: "",
      steps: [
        { step_id: "ST1", status: "completed" },
        { step_id: "ST2", status: "pending" },
      ],
    },
    {
      title: "Closeout",
      description: "Closeout report",
      successCriteria: "Closeout report",
    },
  );

  assert.equal(steps.length, 3);
  assert.equal(steps[2].step_id, "CO1");
  assert.equal(steps[2].status, "pending");
  assert.deepEqual(steps[2].depends_on, ["ST1", "ST2"]);
  assert.equal(canEditStep(steps[2], false), false);
});

/*
  assert.equal(
    runtimeSummary(
      { model_preset: "balanced" },
      [{ preset_id: "balanced", summary: "Balanced preset" }],
    ),
    "Balanced preset",
  );
  assert.equal(runtimeSummary({ model: "gpt-5.4", effort: "low" }, []), "gpt-5.4 | reasoning Low");
  assert.equal(runtimeSummary({ model: "gpt-5.4", effort: "medium", effort_selection_mode: "auto" }, []), "gpt-5.4 | reasoning Auto");
  assert.equal(runtimeSummary({ model: "gpt-5.4", effort: "low", use_fast_mode: true }, []), "gpt-5.4 | reasoning Low | /fast");
  assert.equal(runtimeSummary({ model: "gpt-5.4" }), "gpt-5.4 | reasoning High");
  assert.equal(runtimeSummary({}, undefined), "No model selected");
  assert.equal(runtimeSummary({ model: "gpt-5.4", effort: "high" }, [], "ko"), "gpt-5.4 | 추론 높음");
*/

test("runtimeSummary reflects execution mode in preset and direct model summaries", () => {
  assert.equal(
    runtimeSummary(
      { model_preset: "balanced" },
      [{ preset_id: "balanced", summary: "Balanced preset" }],
    ),
    "OpenAI/Codex | Standard Mode | Balanced preset | parallel auto",
  );
  assert.equal(runtimeSummary({ model: "gpt-5.4", effort: "low" }, []), "OpenAI/Codex | Standard Mode | gpt-5.4 | reasoning Low | parallel auto");
  assert.equal(
    runtimeSummary({ model: "gpt-5.4", effort: "medium", effort_selection_mode: "auto" }, []),
    "OpenAI/Codex | Standard Mode | gpt-5.4 | reasoning Auto | parallel auto",
  );
  assert.equal(
    runtimeSummary({ model: "gpt-5.4", effort: "low", use_fast_mode: true }, []),
    "OpenAI/Codex | Standard Mode | gpt-5.4 | reasoning Low | parallel auto | /fast",
  );
  assert.equal(runtimeSummary({ model: "gpt-5.4" }), "OpenAI/Codex | Standard Mode | gpt-5.4 | reasoning High | parallel auto");
  assert.equal(
    runtimeSummary({ model: "gpt-5.4", effort: "high", execution_mode: "parallel", parallel_worker_mode: "auto" }, []),
    "OpenAI/Codex | Standard Mode | gpt-5.4 | reasoning High | parallel auto",
  );
  assert.equal(runtimeSummary({}, undefined), "No model selected");
  assert.match(runtimeSummary({ model: "gpt-5.4", effort: "high" }, [], "ko"), /^OpenAI\/Codex \| .* \| gpt-5\.4 .* parallel .*$/);
});

test("runtimeSummary includes the selected local provider for OSS models", () => {
  assert.equal(
    runtimeSummary(
      {
        model_provider: "oss",
        local_model_provider: "ollama",
        model: "qwen2.5-coder:0.5b",
        effort: "medium",
      },
      [],
    ),
    "Local/Ollama | Standard Mode | qwen2.5-coder:0.5b | reasoning Medium | parallel auto",
  );
});

test("runtimeSummary shows Gemini CLI as a first-class backend", () => {
  assert.equal(
    runtimeSummary(
      {
        model_provider: "gemini",
        model: "gemini-2.5-flash",
        effort: "medium",
      },
      [],
    ),
    "Gemini CLI | Standard Mode | gemini-2.5-flash | reasoning Medium | parallel auto",
  );
});

test("runtimeSummary shows Claude Code as a first-class backend", () => {
  assert.equal(
    runtimeSummary(
      {
        model_provider: "claude",
        model: CLAUDE_DEFAULT_MODEL,
        effort: "medium",
      },
      [],
    ),
    "Claude Code | Standard Mode | claude-sonnet-4-6 | reasoning Medium | parallel auto",
  );
});

test("runtimeSummary shows the ensemble provider as a first-class backend", () => {
  assert.equal(
    runtimeSummary(
      {
        model_provider: "ensemble",
        model: "gpt-5.4",
        effort: "medium",
      },
      [],
    ),
    "GPT+Gemini+Claude Ensemble | Standard Mode | gpt-5.4 | reasoning Medium | parallel auto",
  );
});

test("config reasoning helpers keep auto separate from explicit efforts", () => {
  const modelCatalog = [
    {
      model: "auto",
      default_reasoning_effort: "medium",
      supported_reasoning_efforts: ["low", "medium", "high", "xhigh"],
    },
    {
      model: "gpt-5.4",
      default_reasoning_effort: "medium",
      supported_reasoning_efforts: ["medium"],
    },
  ];

  assert.deepEqual(configReasoningOptions(modelCatalog, "auto", "medium"), ["auto", "low", "medium", "high", "xhigh"]);
  assert.deepEqual(configReasoningOptions(modelCatalog, "gpt-5.4", "medium"), ["auto", "medium"]);
  assert.equal(selectedConfigReasoning(modelCatalog, { model: "auto", model_preset: "auto", effort: "medium" }), "auto");
  assert.equal(selectedConfigReasoning(modelCatalog, { model: "auto", model_preset: "medium", effort: "medium" }), "medium");
  assert.equal(selectedConfigReasoning(modelCatalog, { model: "gpt-5.4", effort: "medium", effort_selection_mode: "auto" }), "auto");
  assert.equal(reasoningEffortLabel("auto"), "Auto");
  assert.equal(autoRoutingPresetLabel("low"), "Low Only");
  assert.equal(autoRoutingPresetLabel("xhigh", "ko"), "매우 높음만");
});

test("applyConfigRuntimeModelSelection updates reasoning for models with stricter defaults", () => {
  const nextRuntime = applyConfigRuntimeModelSelection(
    {
      model_provider: "deepseek",
      model: "deepseek-chat",
      model_slug_input: "deepseek-chat",
      effort: "low",
      effort_selection_mode: "explicit",
    },
    [
      {
        model: "deepseek-chat",
        default_reasoning_effort: "medium",
        supported_reasoning_efforts: ["low", "medium", "high", "xhigh"],
      },
      {
        model: "deepseek-reasoner",
        default_reasoning_effort: "high",
        supported_reasoning_efforts: ["medium", "high", "xhigh"],
      },
    ],
    "deepseek-reasoner",
  );

  assert.equal(nextRuntime.model, "deepseek-reasoner");
  assert.equal(nextRuntime.model_slug_input, "deepseek-reasoner");
  assert.equal(nextRuntime.effort, "high");
  assert.equal(nextRuntime.effort_selection_mode, "auto");
});

test("codexUsageBuckets separates 5h, 7d, and spark usage windows", () => {
  const buckets = codexUsageBuckets({
    rate_limits: {
      default_limit_id: "codex",
      items: [
        {
          limit_id: "codex",
          primary: { remaining_percent: 70, used_percent: 30, resets_at: "2026-03-26T05:00:00+00:00" },
          secondary: { remaining_percent: 55, used_percent: 45, resets_at: "2026-04-02T00:00:00+00:00" },
        },
        {
          limit_id: "codex-spark",
          primary: { remaining_percent: 20, used_percent: 80, resets_at: "2026-03-26T02:00:00+00:00" },
        },
      ],
    },
  });

  assert.equal(buckets[0].label, "5h Usage");
  assert.equal(buckets[0].window.remaining_percent, 70);
  assert.equal(buckets[1].label, "7d Usage");
  assert.equal(buckets[1].window.remaining_percent, 55);
  assert.equal(buckets[2].label, "Codex Spark");
  assert.equal(buckets[2].window.remaining_percent, 20);
});

test("progressCaption summarizes empty, partial, and completed plans", () => {
  assert.equal(progressCaption({ steps: [] }), "No plan yet");
  assert.equal(
    progressCaption({
      steps: [
        { step_id: "S1", status: "completed" },
        { step_id: "S2", status: "pending" },
      ],
    }),
    "Completed 1/2 steps, next: S2",
  );
  assert.equal(
    progressCaption({
      steps: [
        { step_id: "S1", status: "completed" },
        { step_id: "S2", status: "completed" },
      ],
      closeout_status: "running",
    }),
    "Completed 2/2 steps, closeout running",
  );
  assert.equal(
    progressCaption({
      steps: [{ step_id: "S1", status: "completed" }],
      closeout_status: "failed",
    }),
    "Completed 1/1 steps, closeout failed",
  );
});

test("toolbarProgressCaptionDisplay shows planning progress while plan generation is active", () => {
  assert.equal(
    toolbarProgressCaptionDisplay(
      { steps: [] },
      "en",
      {
        planningProgress: {
          stage_count: 4,
          current_stage_index: 2,
          current_stage_status: "running",
        },
      },
    ),
    "Planning stage 2/4, Running",
  );
  assert.equal(
    toolbarProgressCaptionDisplay(
      { steps: [] },
      "en",
      {
        activeJob: {
          status: "running",
          command: "generate-plan",
        },
      },
    ),
    "Generating execution plan",
  );
});

test("canEditStep only allows pending steps when the controller is idle", () => {
  assert.equal(canEditStep({ status: "pending" }, false), true);
  assert.equal(canEditStep({ status: "completed" }, false), false);
  assert.equal(canEditStep({ status: "pending" }, true), false);
  assert.equal(canEditStep(null, false), false);
});

test("commandLabel maps known commands and humanizes unknown ones", () => {
  assert.equal(commandLabel("generate-plan"), "Generate Plan");
  assert.equal(commandLabel("run-plan"), "Run Remaining Steps");
  assert.equal(commandLabel("run-closeout"), "Closeout");
  assert.equal(commandLabel("sync-workspace-now"), "sync workspace now");
  assert.equal(commandLabel(""), "Background Job");
  assert.equal(commandLabel("run-plan", "ko"), "남은 단계 실행");
});

test("statusTone maps operational states to UI tones", () => {
  assert.equal(statusTone("failed"), "danger");
  assert.equal(statusTone("running"), "info");
  assert.equal(statusTone("running:debugging"), "warning");
  assert.equal(statusTone("running:parallel-debugging"), "warning");
  assert.equal(statusTone("integrating"), "info");
  assert.equal(statusTone("awaiting_review"), "warning");
  assert.equal(statusTone("awaiting_checkpoint_approval"), "warning");
  assert.equal(statusTone("cancelled"), "neutral");
  assert.equal(statusTone("completed"), "success");
  assert.equal(statusTone("paused_for_review"), "warning");
  assert.equal(statusTone("pending"), "neutral");
});

test("effectiveStepStatus overlays debugging on the active running step", () => {
  assert.equal(effectiveStepStatus({ status: "running" }, "running:debugging"), "running:debugging");
  assert.equal(effectiveStepStatus({ status: "running" }, "running:parallel-debugging"), "running:debugging");
  assert.equal(effectiveStepStatus({ status: "pending" }, "running:debugging"), "pending");
  assert.equal(effectiveStepStatus({ status: "running" }, "running:block:2"), "running");
});

test("shouldShowEstimatedCost only enables paid cost displays when configured", () => {
  assert.equal(
    shouldShowEstimatedCost(
      { billing_mode: "included", model_provider: "openai" },
      { recent: { billing_mode: "included", configured: true }, remaining: { billing_mode: "included", configured: true } },
    ),
    false,
  );
  assert.equal(
    shouldShowEstimatedCost(
      { billing_mode: "token", model_provider: "openrouter" },
      { recent: { billing_mode: "token", configured: true }, remaining: { billing_mode: "token", configured: false } },
    ),
    true,
  );
  assert.equal(
    shouldShowEstimatedCost(
      { billing_mode: "per_pass", model_provider: "oss" },
      { recent: { billing_mode: "per_pass", configured: false }, remaining: { billing_mode: "per_pass", configured: false } },
    ),
    false,
  );
});

test("display progress captions include closeout in the visible total", () => {
  assert.equal(
    executionProgressCaptionDisplay({
      steps: [
        { step_id: "ST1", status: "completed" },
        { step_id: "ST2", status: "integrating", depends_on: ["ST1"], owned_paths: ["desktop/src"] },
        { step_id: "ST3", status: "running", depends_on: ["ST1"], owned_paths: ["src/jakal_flow"] },
      ],
      closeout_status: "not_started",
    }),
    "Completed 1/4 steps, running: ST3; integrating: ST2",
  );
  assert.equal(
    toolbarProgressCaptionDisplay({
      steps: [
        { step_id: "ST1", status: "completed" },
        { step_id: "ST2", status: "completed" },
      ],
      closeout_status: "running",
    }),
    "Completed 2/3 steps, closeout running",
  );
});
