import assert from "node:assert/strict";
import test from "node:test";

import {
  activityLineSummary,
  applyProviderDefaults,
  applyProgramSettings,
  applyProgramSettingsToForm,
  autoRoutingPresetLabel,
  configReasoningOptions,
  basename,
  blankProjectForm,
  buildProjectPayload,
  canEditStep,
  codexUsageBuckets,
  cloneValue,
  commandLabel,
  detailApplySignature,
  computePlanStats,
  deriveExecutionProgress,
  reasoningEffortLabel,
  deriveIdleProjectStatus,
  deriveGithubMode,
  firstSelectableStepId,
  mergeProjectDetailCodexStatus,
  normalizeInterruptedPlan,
  progressCaption,
  programSettingsFromRuntime,
  projectFormFromDetail,
  runtimeSummary,
  sanitizeProjectDetailForJobState,
  sanitizeProjectListForJobState,
  selectedConfigReasoning,
  shouldKeepUnsavedPlan,
  shouldReplaceVisibleProject,
  statusTone,
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

test("deriveGithubMode distinguishes manual and existing projects", () => {
  assert.equal(deriveGithubMode("https://github.com/openai/jakal-flow"), "manual");
  assert.equal(deriveGithubMode(""), "existing");
  assert.equal(deriveGithubMode(null), "existing");
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
    model: "auto",
    model_preset: "auto",
    model_selection_mode: "slug",
    model_slug_input: "auto",
    approval_mode: "untrusted",
    sandbox_mode: "workspace-write",
    checkpoint_interval_blocks: 1,
    codex_path: "codex.cmd",
    allow_push: false,
    require_checkpoint_approval: false,
    execution_mode: "serial",
    parallel_workers: 2,
    developer_mode: false,
    ui_theme: "dark",
    dashboard_visibility: {
      status: true,
      remaining_steps: true,
      checkpoint_pending: true,
      input_tokens: true,
      output_tokens: true,
      estimated_remaining: true,
      estimated_cost: true,
      actual_cost: true,
      codex_plan: true,
      rate_limits: true,
      runtime_card: true,
      codex_usage_card: true,
      word_report_card: true,
    },
  });

  assert.deepEqual(
    applyProgramSettings(
      {
        test_cmd: "pytest -q",
      },
      settings,
    ),
    {
      model: "gpt-5.4",
      test_cmd: "pytest -q",
      model_provider: "openai",
      local_model_provider: "ollama",
      provider_base_url: "",
      provider_api_key_env: "OPENAI_API_KEY",
      model: "auto",
      model_preset: "auto",
      model_selection_mode: "slug",
      model_slug_input: "auto",
      approval_mode: "untrusted",
      sandbox_mode: "workspace-write",
      checkpoint_interval_blocks: 1,
      codex_path: "codex.cmd",
      allow_push: false,
      require_checkpoint_approval: false,
      execution_mode: "serial",
      parallel_workers: 2,
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
        model: "auto",
        model_preset: "auto",
        model_selection_mode: "slug",
        model_slug_input: "auto",
        test_cmd: "pytest -q",
        model_provider: "openai",
        local_model_provider: "ollama",
        provider_base_url: "",
        provider_api_key_env: "OPENAI_API_KEY",
        approval_mode: "untrusted",
        sandbox_mode: "workspace-write",
        checkpoint_interval_blocks: 1,
        codex_path: "codex.cmd",
        allow_push: false,
        require_checkpoint_approval: false,
        execution_mode: "serial",
        parallel_workers: 2,
      },
    },
  );
});

test("blankProjectForm seeds runtime defaults without mutating the source runtime", () => {
  const defaultRuntime = {
    model_preset: "default",
    max_blocks: 9,
    test_cmd: "pytest -q",
  };

  const form = blankProjectForm(defaultRuntime);
  form.runtime.test_cmd = "npm test";

  assert.deepEqual(defaultRuntime, {
    model_preset: "default",
    max_blocks: 9,
    test_cmd: "pytest -q",
  });
  assert.equal(form.branch, "main");
  assert.equal(form.github_mode, "existing");
  assert.equal(form.runtime.max_blocks, 9);
});

test("blankProjectForm falls back to repository defaults when runtime is missing", () => {
  const form = blankProjectForm(null);

  assert.equal(form.runtime.max_blocks, 5);
  assert.equal(form.runtime.test_cmd, "python -m pytest");
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
      test_cmd: "npm run check",
      model: "gpt-5.4",
    },
  });
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
      { step_id: "ST2", status: "running" },
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
  assert.equal(progress.percent, 33);
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
      execution_mode: "serial",
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
  assert.equal(firstSelectableStepId({ steps: [{ step_id: "S1", status: "completed" }] }), "S1");
  assert.equal(firstSelectableStepId({ steps: [] }), "");
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
    "OpenAI/Codex | Balanced preset | serial",
  );
  assert.equal(runtimeSummary({ model: "gpt-5.4", effort: "low" }, []), "OpenAI/Codex | gpt-5.4 | reasoning Low | serial");
  assert.equal(
    runtimeSummary({ model: "gpt-5.4", effort: "medium", effort_selection_mode: "auto" }, []),
    "OpenAI/Codex | gpt-5.4 | reasoning Auto | serial",
  );
  assert.equal(
    runtimeSummary({ model: "gpt-5.4", effort: "low", use_fast_mode: true }, []),
    "OpenAI/Codex | gpt-5.4 | reasoning Low | serial | /fast",
  );
  assert.equal(runtimeSummary({ model: "gpt-5.4" }), "OpenAI/Codex | gpt-5.4 | reasoning High | serial");
  assert.equal(
    runtimeSummary({ model: "gpt-5.4", effort: "high", execution_mode: "parallel", parallel_workers: 4 }, []),
    "OpenAI/Codex | gpt-5.4 | reasoning High | parallel x4",
  );
  assert.equal(runtimeSummary({}, undefined), "No model selected");
  assert.match(runtimeSummary({ model: "gpt-5.4", effort: "high" }, [], "ko"), /^OpenAI\/Codex \| gpt-5\.4 .* serial$/);
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
    "Local/Ollama | qwen2.5-coder:0.5b | reasoning Medium | serial",
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
  assert.equal(statusTone("completed"), "success");
  assert.equal(statusTone("paused_for_review"), "warning");
  assert.equal(statusTone("pending"), "neutral");
});
