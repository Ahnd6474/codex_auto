import assert from "node:assert/strict";
import test from "node:test";

import {
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
  reasoningEffortLabel,
  deriveGithubMode,
  firstSelectableStepId,
  mergeProjectDetailCodexStatus,
  progressCaption,
  programSettingsFromRuntime,
  projectFormFromDetail,
  runtimeSummary,
  selectedConfigReasoning,
  shouldKeepUnsavedPlan,
  shouldReplaceVisibleProject,
  statusTone,
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

test("deriveGithubMode distinguishes manual and existing projects", () => {
  assert.equal(deriveGithubMode("https://github.com/openai/codex-auto"), "manual");
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
    approval_mode: "untrusted",
    sandbox_mode: "workspace-write",
    checkpoint_interval_blocks: 1,
    codex_path: "codex.cmd",
    allow_push: false,
    require_checkpoint_approval: false,
    ui_theme: "dark",
  });

  assert.deepEqual(
    applyProgramSettings(
      {
        model: "gpt-5.4",
        test_cmd: "pytest -q",
      },
      settings,
    ),
    {
      model: "gpt-5.4",
      test_cmd: "pytest -q",
      approval_mode: "untrusted",
      sandbox_mode: "workspace-write",
      checkpoint_interval_blocks: 1,
      codex_path: "codex.cmd",
      allow_push: false,
      require_checkpoint_approval: false,
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
        test_cmd: "pytest -q",
        approval_mode: "untrusted",
        sandbox_mode: "workspace-write",
        checkpoint_interval_blocks: 1,
        codex_path: "codex.cmd",
        allow_push: false,
        require_checkpoint_approval: false,
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

test("runtimeSummary prefers preset summaries, then direct model settings, then a safe fallback", () => {
  assert.equal(
    runtimeSummary(
      { model_preset: "balanced" },
      [{ preset_id: "balanced", summary: "Balanced preset" }],
    ),
    "Balanced preset",
  );
  assert.equal(runtimeSummary({ model: "gpt-5.4", effort: "low" }, []), "gpt-5.4 | reasoning low");
  assert.equal(runtimeSummary({ model: "gpt-5.4", effort: "low", use_fast_mode: true }, []), "gpt-5.4 | reasoning low | /fast");
  assert.equal(runtimeSummary({ model: "gpt-5.4" }), "gpt-5.4 | reasoning high");
  assert.equal(runtimeSummary({}, undefined), "No model selected");
  assert.equal(runtimeSummary({ model: "gpt-5.4", effort: "high" }, [], "ko"), "gpt-5.4 | 추론 높음");
});

test("config reasoning helpers keep auto separate from explicit efforts", () => {
  const modelCatalog = [
    {
      model: "auto",
      default_reasoning_effort: "medium",
      supported_reasoning_efforts: ["low", "medium", "high", "xhigh"],
    },
  ];

  assert.deepEqual(configReasoningOptions(modelCatalog, "auto", "medium"), ["auto", "low", "medium", "high", "xhigh"]);
  assert.equal(selectedConfigReasoning(modelCatalog, { model: "auto", model_preset: "auto", effort: "medium" }), "auto");
  assert.equal(selectedConfigReasoning(modelCatalog, { model: "auto", model_preset: "medium", effort: "medium" }), "medium");
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
