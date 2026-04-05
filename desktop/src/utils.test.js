import test from "node:test";
import assert from "node:assert/strict";

import {
  applyChatRuntimeSelectionToProject,
  applyConfigRuntimeModelSelection,
  applyProjectModelSelection,
  canEditStep,
  canEditProjectConfig,
  canEditStepModel,
  defaultModelForRuntime,
  failureReasonCode,
  failureReasonLabel,
  buildProjectPayload,
  isDuplicateProjectJobError,
  filterModelCatalogByProvider,
  groupedModelCatalogOptions,
  jobHasNewerActiveReplacement,
  mergeModelCatalogs,
  modelCatalogOptionValue,
  providerHasRemainingUsage,
  projectDetailStatus,
  projectScopedJobFromJobs,
  projectFormFromDetail,
  resolveChatRuntimeSelection,
  resolveRuntimeModelSelectionState,
  sanitizeProjectListForJobState,
  sanitizeProjectDetailForJobState,
  sameQueuedJobs,
  selectedConfigReasoning,
  shouldAutoSelectProject,
  shouldReplaceVisibleProject,
  statusTone,
  stepModelSelectionPatch,
} from "./utils.js";

test("jobHasNewerActiveReplacement detects a newer active job for the same project", () => {
  const jobs = [
    {
      id: "job-new",
      repo_id: "repo-1",
      project_dir: "C:/repo",
      status: "running",
      updated_at_ms: 200,
    },
    {
      id: "job-old",
      repo_id: "repo-1",
      project_dir: "C:/repo",
      status: "failed",
      updated_at_ms: 100,
    },
  ];

  assert.equal(jobHasNewerActiveReplacement(jobs[1], jobs), true);
});

test("jobHasNewerActiveReplacement ignores terminal jobs when no newer active replacement exists", () => {
  const jobs = [
    {
      id: "job-old",
      repo_id: "repo-1",
      project_dir: "C:/repo",
      status: "failed",
      updated_at_ms: 100,
    },
    {
      id: "job-other",
      repo_id: "repo-2",
      project_dir: "C:/other",
      status: "running",
      updated_at_ms: 300,
    },
  ];

  assert.equal(jobHasNewerActiveReplacement(jobs[0], jobs), false);
});

test("sanitizeProjectListForJobState overlays queue snapshots onto project cards", () => {
  const projects = [
    {
      repo_id: "repo-1",
      repo_path: "C:/repo",
      status: "setup_ready",
      current_step_label: "ST2 Implement API",
      progress: {
        caption: "Completed 1/3 steps, running: ST2",
        percent: 33,
        currentStep: "ST2 Implement API",
      },
      stats: {
        total_steps: 3,
        completed_steps: 1,
        running_steps: 1,
      },
      queue_priority: 2,
    },
  ];
  const jobs = [
    {
      id: "job-run",
      repo_id: "repo-1",
      project_dir: "C:/repo",
      status: "queued",
      command: "run-plan",
      queue_position: 2,
      queue_priority: 4,
      updated_at_ms: 100,
    },
  ];

  const sanitized = sanitizeProjectListForJobState(projects, jobs);

  assert.equal(sanitized[0].status, "queued:run-plan");
  assert.equal(sanitized[0].display_status, "queued:run-plan");
  assert.equal(sanitized[0].queue_position, 2);
  assert.equal(sanitized[0].queue_priority, 2);
  assert.equal(sanitized[0].queue_command, "run-plan");
  assert.equal(sanitized[0].current_step_label, "ST2 Implement API");
  assert.equal(sanitized[0].progress.currentStep, "ST2 Implement API");
  assert.equal(sanitized[0].progress.percent, 33);
});

test("sanitizeProjectListForJobState rebuilds structured progress when legacy captions are still present", () => {
  const sanitized = sanitizeProjectListForJobState([
    {
      repo_id: "repo-1",
      repo_path: "C:/repo",
      status: "running:run-plan",
      progress: "Completed 2/4 steps, running: ST3",
      current_step_label: "ST3 Build UI",
      stats: {
        total_steps: 4,
        completed_steps: 2,
        running_steps: 1,
      },
    },
  ]);

  assert.equal(sanitized[0].progress.caption, "Completed 2/4 steps, running: ST3");
  assert.equal(sanitized[0].progress.percent, 50);
  assert.equal(sanitized[0].progress.total, 4);
  assert.equal(sanitized[0].progress.completed, 2);
  assert.equal(sanitized[0].progress.currentStep, "ST3 Build UI");
});

test("canEditStep allows editing failed steps when the run is idle", () => {
  assert.equal(
    canEditStep(
      {
        step_id: "ST2",
        status: "failed",
        metadata: {},
      },
      false,
    ),
    true,
  );
});

test("canEditStep still blocks failed steps while a run is active", () => {
  assert.equal(
    canEditStep(
      {
        step_id: "ST2",
        status: "failed",
        metadata: {},
      },
      true,
    ),
    false,
  );
});

test("canEditProjectConfig allows edits while paused but blocks active runs", () => {
  assert.equal(canEditProjectConfig("paused", ""), true);
  assert.equal(canEditProjectConfig("paused", "running"), true);
  assert.equal(canEditProjectConfig("ready", "running"), false);
  assert.equal(canEditProjectConfig("running", ""), false);
});

test("statusTone keeps flowchart colors aligned with queued and review statuses", () => {
  assert.equal(statusTone("queued"), "info");
  assert.equal(statusTone("queued:run-plan"), "info");
  assert.equal(statusTone("awaiting_review"), "warning");
  assert.equal(statusTone("awaiting_checkpoint_approval"), "warning");
  assert.equal(statusTone("running:debugging"), "warning");
  assert.equal(statusTone("completed"), "success");
  assert.equal(statusTone("failed"), "danger");
});

test("project selection helpers keep new-project drafts from being overwritten", () => {
  assert.equal(shouldReplaceVisibleProject("", "repo-1"), true);
  assert.equal(shouldReplaceVisibleProject("", "repo-1", { allowEmptySelection: false }), false);
  assert.equal(shouldAutoSelectProject("", false), true);
  assert.equal(shouldAutoSelectProject("", true), false);
  assert.equal(shouldAutoSelectProject("repo-1", true), false);
});

test("canEditStepModel allows model edits on paused steps while preserving normal locks", () => {
  assert.equal(
    canEditStepModel(
      {
        step_id: "ST1",
        status: "running",
      },
      true,
      "paused",
    ),
    true,
  );
  assert.equal(
    canEditStepModel(
      {
        step_id: "ST2",
        status: "completed",
      },
      false,
      "paused",
    ),
    false,
  );
  assert.equal(
    canEditStepModel(
      {
        step_id: "ST3",
        status: "running",
      },
      true,
      "running",
    ),
    false,
  );
  assert.equal(
    canEditStepModel(
      {
        step_id: "CO1",
        status: "completed",
        metadata: {
          system_step: true,
          system_step_kind: "closeout",
        },
      },
      false,
      "ready",
    ),
    true,
  );
  assert.equal(
    canEditStepModel(
      {
        step_id: "CO1",
        status: "completed",
        metadata: {
          system_step: true,
          system_step_kind: "closeout",
        },
      },
      false,
      "running",
    ),
    false,
  );
});

test("failureReasonLabel maps step metadata reason codes to readable labels", () => {
  assert.equal(
    failureReasonLabel(
      {
        metadata: {
          failure_reason_code: "verification_test_failed",
        },
      },
      "en",
    ),
    "Verification tests failed",
  );
  assert.equal(
    failureReasonLabel(
      {
        metadata: {
          failure_reason_code: "verification_test_failed",
        },
      },
      "ko",
    ),
    "검증 테스트 실패",
  );
});

test("failureReasonCode reads both top-level and step metadata reason codes", () => {
  assert.equal(failureReasonCode({ failure_reason_code: "agent_pass_failed" }), "agent_pass_failed");
  assert.equal(failureReasonCode({ metadata: { failure_reason_code: "parallel_merge_conflict" } }), "parallel_merge_conflict");
});

test("isDuplicateProjectJobError reads structured reason code fields", () => {
  assert.equal(
    isDuplicateProjectJobError({
      reasonCode: "duplicate_job",
      message: "This project is busy.",
    }),
    true,
  );
  assert.equal(
    isDuplicateProjectJobError({
      reason_code: "already_active_for_project",
      message: "This project is busy.",
    }),
    true,
  );
});

test("isDuplicateProjectJobError ignores message-only legacy payloads", () => {
  assert.equal(
    isDuplicateProjectJobError({
      message: "Another background task is already active for this project.",
    }),
    false,
  );
  assert.equal(isDuplicateProjectJobError({ message: "No match here." }), false);
});

test("defaultModelForRuntime skips auto catalog entries for openai providers", () => {
  const modelCatalog = [
    { model: "auto", display_name: "Auto", provider: "openai", hidden: false },
    { model: "gpt-5.4", display_name: "GPT-5.4", provider: "openai", hidden: false },
  ];

  assert.equal(defaultModelForRuntime(modelCatalog, { model_provider: "openai" }), "gpt-5.4");
});

test("filterModelCatalogByProvider limits chat model choices to the selected provider", () => {
  const modelCatalog = [
    { model: "gpt-5.4", display_name: "GPT-5.4", provider: "openai", hidden: false },
    { model: "gpt-5.4-mini", display_name: "GPT-5.4 Mini", provider: "openai", hidden: false },
    { model: "claude-sonnet-4-6", display_name: "Claude Sonnet 4.6", provider: "claude", hidden: false },
  ];

  assert.deepEqual(
    filterModelCatalogByProvider(modelCatalog, { model_provider: "openai" }).map((item) => item.model),
    ["gpt-5.4", "gpt-5.4-mini"],
  );
  assert.deepEqual(
    filterModelCatalogByProvider(modelCatalog, { model_provider: "claude" }).map((item) => item.model),
    ["claude-sonnet-4-6"],
  );
});

test("filterModelCatalogByProvider aliases OpenAI catalog entries for OpenAI-compatible providers", () => {
  const modelCatalog = [
    { id: "openai:gpt-5.4", model: "gpt-5.4", display_name: "GPT-5.4", provider: "openai", hidden: false },
    { id: "openai:gpt-5.4-mini", model: "gpt-5.4-mini", display_name: "GPT-5.4 Mini", provider: "openai", hidden: false },
  ];

  const openRouterEntries = filterModelCatalogByProvider(modelCatalog, { model_provider: "openrouter" });
  assert.deepEqual(
    openRouterEntries.map((item) => [item.provider, item.model]),
    [
      ["openrouter", "gpt-5.4"],
      ["openrouter", "gpt-5.4-mini"],
    ],
  );

  assert.equal(defaultModelForRuntime(modelCatalog, { model_provider: "openrouter" }), "gpt-5.4");
});

test("groupedModelCatalogOptions filters unusable providers and keeps local models in a separate group", () => {
  const modelCatalog = [
    { model: "gpt-5.4", display_name: "GPT-5.4", provider: "openai", hidden: false },
    { model: "claude-sonnet-4-6", display_name: "Claude Sonnet 4.6", provider: "claude", hidden: false },
    { model: "llama3.2", display_name: "Llama 3.2", provider: "oss", local_provider: "ollama", hidden: false },
    { model: "mistral-nemo", display_name: "Mistral Nemo", provider: "oss", local_provider: "lmstudio", hidden: false },
  ];
  const codexStatus = {
    provider_statuses: {
      openai: { usable: true },
      claude: { usable: false },
      oss: { usable: true },
      ollama: { usable: true },
    },
  };

  const tree = groupedModelCatalogOptions(
    modelCatalog,
    { local_model_provider: "ollama" },
    codexStatus,
    { scope: "all" },
  );

  assert.deepEqual(tree.entries.map((item) => item.model), ["gpt-5.4", "llama3.2"]);
  assert.deepEqual(tree.groups.map((group) => group.label), ["OpenAI/Codex", "Local Runtime / Ollama"]);
});

test("groupedModelCatalogOptions hides exhausted Codex providers when quota data is present", () => {
  const codexStatus = {
    rate_limits: {
      default_limit_id: "codex",
      items: [
        {
          limit_id: "codex",
          limit_name: "Codex",
          primary: { remaining_percent: 0 },
          secondary: { remaining_percent: 0 },
        },
      ],
    },
  };

  assert.equal(providerHasRemainingUsage("openai", codexStatus), false);

  const tree = groupedModelCatalogOptions(
    [
      { model: "gpt-5.4", display_name: "GPT-5.4", provider: "openai", hidden: false },
      { model: "claude-sonnet-4-6", display_name: "Claude Sonnet 4.6", provider: "claude", hidden: false },
    ],
    { model_provider: "openai" },
    codexStatus,
    { scope: "all" },
  );

  assert.deepEqual(tree.entries.map((item) => item.model), ["claude-sonnet-4-6"]);
});

test("mergeModelCatalogs preserves both global and detail model catalogs without duplicating entries", () => {
  const merged = mergeModelCatalogs(
    [
      { id: "openai:gpt-5.4", model: "gpt-5.4", provider: "openai", display_name: "GPT-5.4" },
      { id: "claude:claude-sonnet-4-6", model: "claude-sonnet-4-6", provider: "claude", display_name: "Claude Sonnet 4.6" },
    ],
    [
      { id: "claude:claude-sonnet-4-6", model: "claude-sonnet-4-6", provider: "claude", display_name: "Claude Sonnet 4.6" },
      { id: "gemini:gemini-3-flash-preview", model: "gemini-3-flash-preview", provider: "gemini", display_name: "Gemini 3 Flash Preview" },
    ],
  );

  assert.equal(merged.length, 3);
  assert.equal(merged[0].model, "gpt-5.4");
  assert.equal(merged[1].model, "claude-sonnet-4-6");
  assert.equal(merged[2].model, "gemini-3-flash-preview");
});

test("stepModelSelectionPatch clears overrides when returning to the execution model", () => {
  const modelCatalog = [
    { id: "openai:gpt-5.4", model: "gpt-5.4", provider: "openai", display_name: "GPT-5.4" },
    { id: "claude:claude-sonnet-4-6", model: "claude-sonnet-4-6", provider: "claude", display_name: "Claude Sonnet 4.6" },
  ];

  assert.deepEqual(
    stepModelSelectionPatch(modelCatalog, { execution_model: "gpt-5.4" }, ""),
    { model_provider: "", model: "" },
  );
  assert.deepEqual(
    stepModelSelectionPatch(modelCatalog, { execution_model: "gpt-5.4" }, "gpt-5.4"),
    { model_provider: "", model: "" },
  );
  assert.deepEqual(
    stepModelSelectionPatch(modelCatalog, { execution_model: "gpt-5.4" }, "claude-sonnet-4-6"),
    { model_provider: "claude", model: "claude-sonnet-4-6" },
  );
  assert.deepEqual(
    stepModelSelectionPatch(
      modelCatalog,
      { execution_model: "gpt-5.4" },
      modelCatalogOptionValue({ model: "claude-sonnet-4-6", provider: "claude" }),
    ),
    { model_provider: "claude", model: "claude-sonnet-4-6" },
  );
});

test("applyConfigRuntimeModelSelection keeps a concrete model while supporting auto reasoning", () => {
  const modelCatalog = [
    {
      model: "gpt-5.4",
      display_name: "GPT-5.4",
      provider: "openai",
      hidden: false,
      default_reasoning_effort: "medium",
      supported_reasoning_efforts: ["low", "medium", "high", "xhigh"],
    },
  ];

  const nextRuntime = applyConfigRuntimeModelSelection(
    { model_provider: "openai", model: "gpt-5.4", model_slug_input: "gpt-5.4", effort: "medium" },
    modelCatalog,
    "gpt-5.4",
    "auto",
  );

  assert.equal(nextRuntime.model, "gpt-5.4");
  assert.equal(nextRuntime.execution_model, "gpt-5.4");
  assert.equal(nextRuntime.model_slug_input, "gpt-5.4");
  assert.equal(nextRuntime.effort_selection_mode, "auto");
  assert.equal(selectedConfigReasoning(modelCatalog, nextRuntime), "auto");
});

test("applyProjectModelSelection keeps the runtime model fields synchronized", () => {
  const modelCatalog = [
    {
      model: "gpt-5.4",
      display_name: "GPT-5.4",
      provider: "openai",
      hidden: false,
      default_reasoning_effort: "medium",
      supported_reasoning_efforts: ["low", "medium", "high", "xhigh"],
    },
  ];

  const nextRuntime = applyProjectModelSelection(
    {
      model_provider: "openai",
      model: "gpt-4.1",
      execution_model: "gpt-4.1",
      model_slug_input: "gpt-4.1",
      effort: "medium",
      planning_effort: "medium",
    },
    modelCatalog,
    "gpt-5.4",
    "high",
  );

  assert.equal(nextRuntime.model, "gpt-5.4");
  assert.equal(nextRuntime.model_slug_input, "gpt-5.4");
  assert.equal(nextRuntime.execution_model, "gpt-5.4");
  assert.equal(nextRuntime.effort, "high");
  assert.equal(nextRuntime.planning_effort, "medium");
});

test("resolveRuntimeModelSelectionState centralizes execution model and reasoning selection", () => {
  const modelCatalog = [
    {
      model: "gpt-5.4",
      display_name: "GPT-5.4",
      provider: "openai",
      hidden: false,
      default_reasoning_effort: "medium",
      supported_reasoning_efforts: ["low", "medium", "high", "xhigh"],
    },
  ];

  const state = resolveRuntimeModelSelectionState(
    {
      model_provider: "openai",
      model: "gpt-4.1",
      execution_model: "gpt-4.1",
      model_slug_input: "gpt-4.1",
      effort: "low",
      planning_effort: "low",
      model_selection_mode: "codex",
    },
    modelCatalog,
    "gpt-5.4",
    "high",
  );

  assert.equal(state.model, "gpt-5.4");
  assert.equal(state.selectedModel, "gpt-5.4");
  assert.equal(state.selectedReasoning, "high");
  assert.equal(state.visibleModels[0].model, "gpt-5.4");
  assert.equal(state.selectedExecutionModel, "gpt-5.4");
  assert.equal(state.selectedExecutionModelVisible, true);
  assert.equal(state.runtime.model_selection_mode, "codex");
});

test("resolveRuntimeModelSelectionState hides unusable provider catalog entries", () => {
  const modelCatalog = [
    {
      model: "gpt-5.4",
      display_name: "GPT-5.4",
      provider: "openai",
      hidden: false,
      default_reasoning_effort: "medium",
      supported_reasoning_efforts: ["low", "medium", "high", "xhigh"],
    },
  ];
  const codexStatus = {
    provider_statuses: {
      openai: { usable: false },
    },
  };

  const state = resolveRuntimeModelSelectionState(
    {
      model_provider: "openai",
      model: "gpt-5.4",
      execution_model: "gpt-5.4",
      model_slug_input: "gpt-5.4",
      effort: "medium",
    },
    modelCatalog,
    "",
    null,
    codexStatus,
  );

  assert.deepEqual(state.visibleModels, []);
  assert.deepEqual(state.visibleModelGroups, []);
});

test("applyChatRuntimeSelectionToProject maps a chat selection into project model settings", () => {
  const modelCatalog = [
    {
      model: "claude-sonnet-4-6",
      display_name: "Claude Sonnet 4.6",
      provider: "claude",
      hidden: false,
      default_reasoning_effort: "high",
      supported_reasoning_efforts: ["low", "medium", "high", "xhigh"],
    },
  ];

  const nextRuntime = applyChatRuntimeSelectionToProject(
    {
      model_provider: "openai",
      model: "gpt-5.4",
      execution_model: "gpt-5.4",
      model_slug_input: "gpt-5.4",
      effort: "medium",
      planning_effort: "medium",
    },
    modelCatalog,
    {
      provider: "claude",
      model: "claude-sonnet-4-6",
    },
    "auto",
  );

  assert.equal(nextRuntime.model_provider, "claude");
  assert.equal(nextRuntime.model, "claude-sonnet-4-6");
  assert.equal(nextRuntime.execution_model, "claude-sonnet-4-6");
  assert.equal(nextRuntime.model_slug_input, "claude-sonnet-4-6");
  assert.equal(nextRuntime.effort, "high");
  assert.equal(nextRuntime.effort_selection_mode, "auto");
});

test("resolveChatRuntimeSelection keeps a manual OpenAI chat model when the project is reselected", () => {
  const modelCatalog = [
    {
      model: "gpt-5.4",
      display_name: "GPT-5.4",
      provider: "openai",
      hidden: false,
    },
    {
      model: "gpt-5.4-mini",
      display_name: "GPT-5.4 Mini",
      provider: "openai",
      hidden: false,
    },
  ];

  const nextRuntime = resolveChatRuntimeSelection(
    {
      chat_model_provider: "openai",
      chat_local_model_provider: "",
      chat_model: "gpt-5.4-mini",
      chat_effort: "high",
    },
    {
      model_provider: "openai",
      model: "gpt-5.4",
      execution_model: "gpt-5.4",
      model_slug_input: "gpt-5.4",
      effort: "medium",
    },
    modelCatalog,
  );

  assert.equal(nextRuntime.chat_model_provider, "openai");
  assert.equal(nextRuntime.chat_local_model_provider, "");
  assert.equal(nextRuntime.chat_model, "gpt-5.4-mini");
  assert.equal(nextRuntime.chat_effort, "high");
});

test("resolveChatRuntimeSelection uses the project's saved chat model when no manual override exists", () => {
  const modelCatalog = [
    {
      model: "gpt-5.4",
      display_name: "GPT-5.4",
      provider: "openai",
      hidden: false,
    },
    {
      model: "gpt-5.4-mini",
      display_name: "GPT-5.4 Mini",
      provider: "openai",
      hidden: false,
    },
  ];

  const nextRuntime = resolveChatRuntimeSelection(
    {
      chat_model_provider: "",
      chat_local_model_provider: "",
      chat_model: "",
      chat_effort: "",
    },
    {
      model_provider: "openai",
      chat_model_provider: "openai",
      chat_local_model_provider: "",
      chat_model: "gpt-5.4-mini",
      chat_effort: "high",
      model: "gpt-5.4",
      execution_model: "gpt-5.4",
      model_slug_input: "gpt-5.4",
      effort: "medium",
    },
    modelCatalog,
  );

  assert.equal(nextRuntime.chat_model_provider, "openai");
  assert.equal(nextRuntime.chat_local_model_provider, "");
  assert.equal(nextRuntime.chat_model, "gpt-5.4-mini");
  assert.equal(nextRuntime.chat_effort, "high");
});

test("resolveChatRuntimeSelection clears a stale chat model when the provider changes", () => {
  const modelCatalog = [
    {
      model: "claude-sonnet-4-6",
      display_name: "Claude Sonnet 4.6",
      provider: "claude",
      hidden: false,
    },
  ];

  const nextRuntime = resolveChatRuntimeSelection(
    {
      chat_model_provider: "openai",
      chat_local_model_provider: "",
      chat_model: "gpt-5.4-mini",
      chat_effort: "high",
    },
    {
      model_provider: "claude",
      model: "claude-sonnet-4-6",
      execution_model: "claude-sonnet-4-6",
      model_slug_input: "claude-sonnet-4-6",
      effort: "high",
    },
    modelCatalog,
  );

  assert.equal(nextRuntime.chat_model_provider, "");
  assert.equal(nextRuntime.chat_local_model_provider, "");
  assert.equal(nextRuntime.chat_model, "");
  assert.equal(nextRuntime.chat_effort, "high");
});

test("projectFormFromDetail preserves the project's saved model when selecting a project", () => {
  const form = projectFormFromDetail(
    {
      project: {
        repo_path: "C:/repo",
        display_name: "Repo",
        branch: "main",
        origin_url: "https://example.com/repo.git",
      },
      runtime: {
        model_provider: "openai",
        model: "gpt-5.4",
        model_slug_input: "gpt-5.4",
        effort: "medium",
        planning_effort: "medium",
      },
    },
    {
      model_provider: "openai",
      model: "gpt-5.5",
      model_slug_input: "gpt-5.5",
      effort: "xhigh",
      planning_effort: "high",
      effort_selection_mode: "explicit",
    },
  );

  assert.equal(form.runtime.model_provider, "openai");
  assert.equal(form.runtime.model, "gpt-5.4");
  assert.equal(form.runtime.execution_model, "gpt-5.4");
  assert.equal(form.runtime.model_slug_input, "gpt-5.4");
  assert.equal(form.runtime.effort, "medium");
  assert.equal(form.runtime.planning_effort, "medium");
});

test("projectFormFromDetail does not replace a different saved project provider and model with program defaults", () => {
  const form = projectFormFromDetail(
    {
      project: {
        repo_path: "C:/repo",
      },
      runtime: {
        model_provider: "claude",
        model: "claude-sonnet-4-6",
        model_slug_input: "claude-sonnet-4-6",
        effort: "high",
        planning_effort: "high",
      },
    },
    {
      model_provider: "openai",
      model: "gpt-5.5",
      model_slug_input: "gpt-5.5",
      effort: "xhigh",
      planning_effort: "xhigh",
    },
  );

  assert.equal(form.runtime.model_provider, "claude");
  assert.equal(form.runtime.model, "claude-sonnet-4-6");
  assert.equal(form.runtime.execution_model, "claude-sonnet-4-6");
  assert.equal(form.runtime.model_slug_input, "claude-sonnet-4-6");
  assert.equal(form.runtime.effort, "high");
  assert.equal(form.runtime.planning_effort, "high");
});

test("projectFormFromDetail still falls back to program defaults for missing runtime fields", () => {
  const form = projectFormFromDetail(
    {
      project: {
        repo_path: "C:/repo",
      },
      runtime: {
        model_provider: "openai",
      },
    },
    {
      model_provider: "openai",
      model: "gpt-5.5",
      model_slug_input: "gpt-5.5",
      effort: "xhigh",
      planning_effort: "high",
      effort_selection_mode: "explicit",
    },
  );

  assert.equal(form.runtime.model_provider, "openai");
  assert.equal(form.runtime.model, "gpt-5.5");
  assert.equal(form.runtime.model_slug_input, "gpt-5.5");
  assert.equal(form.runtime.effort, "xhigh");
  assert.equal(form.runtime.planning_effort, "high");
});

test("projectFormFromDetail keeps repo identity and repo_path_hint for disconnected projects", () => {
  const form = projectFormFromDetail(
    {
      project: {
        repo_id: "repo-1",
        repo_path: "",
        repo_path_hint: "C:/stale-repo",
        display_name: "Repo",
        branch: "main",
      },
      runtime: {
        model_provider: "openai",
        model: "gpt-5.4",
      },
    },
    {
      model_provider: "openai",
      model: "gpt-5.5",
      model_slug_input: "gpt-5.5",
      effort: "high",
      planning_effort: "high",
    },
  );

  const payload = buildProjectPayload(form);

  assert.equal(form.repo_id, "repo-1");
  assert.equal(form.project_dir, "C:/stale-repo");
  assert.equal(payload.repo_id, "repo-1");
  assert.equal(payload.project_dir, "C:/stale-repo");
});

test("projectDetailStatus prefers backend execution_state and sanitizeProjectDetailForJobState preserves mirrored surfaces", () => {
  const detail = {
    project: {
      repo_id: "repo-1",
      repo_path: "C:/repo",
      current_status: "queued:generate-plan",
    },
    plan: {
      steps: [{ step_id: "ST1", title: "Plan", status: "pending" }],
      closeout_status: "not_started",
    },
    loop_state: {
      current_task: "",
      current_checkpoint_id: "",
      current_checkpoint_lineage_id: "",
      pending_checkpoint_approval: false,
    },
    checkpoints: {
      items: [],
      pending: null,
      timeline_markdown: "",
    },
    snapshot: {
      project: {
        current_status: "queued:generate-plan",
      },
      loop_state: {
        current_task: "",
        current_checkpoint_id: "",
        current_checkpoint_lineage_id: "",
        pending_checkpoint_approval: false,
      },
      plan: {
        steps: [{ step_id: "ST1", title: "Plan", status: "pending" }],
        closeout_status: "not_started",
      },
    },
    bottom_panels: {
      git_status: {
        current_status: "queued:generate-plan",
        pending_checkpoint_approval: false,
      },
    },
    execution_state: {
      display_family: "queued",
      display_status: "queued:generate-plan",
      project_status: "queued:generate-plan",
      consistent: true,
      active_families: ["queued"],
      checkpoint_family: "idle",
      flow_family: "queued",
      process_family: "queued",
      toolbar_family: "queued",
      mismatch_summary: "",
      report_lines: [],
    },
  };
  const queuedJob = {
    repo_id: "repo-1",
    project_dir: "C:/repo",
    status: "queued",
    command: "generate-plan",
  };

  const normalized = sanitizeProjectDetailForJobState(detail, queuedJob);

  assert.equal(projectDetailStatus(detail, queuedJob), "queued:generate-plan");
  assert.equal(normalized.project.current_status, "queued:generate-plan");
  assert.equal(normalized.snapshot.project.current_status, "queued:generate-plan");
  assert.equal(normalized.bottom_panels.git_status.current_status, "queued:generate-plan");
  assert.equal(normalized.execution_state.project_status, "queued:generate-plan");
});

test("sanitizeProjectDetailForJobState no longer rewrites backend detail mirrors when execution_state is missing", () => {
  const detail = {
    project: {
      repo_id: "repo-1",
      repo_path: "C:/repo",
      current_status: "running:st1",
    },
    plan: {
      steps: [{ step_id: "ST1", title: "Build", status: "running" }],
      closeout_status: "not_started",
    },
    loop_state: {
      current_task: "Build",
      current_checkpoint_id: "CP-1",
      current_checkpoint_lineage_id: "LN-1",
      pending_checkpoint_approval: false,
    },
    checkpoints: {
      items: [{ checkpoint_id: "CP-1", lineage_id: "LN-1", status: "running", title: "Checkpoint" }],
      pending: null,
      timeline_markdown: "stale",
    },
    activity: ["2026-03-01T00:00:00Z | step-started | stale run"],
    snapshot: {
      project: {
        current_status: "running:st1",
      },
      loop_state: {
        current_task: "Build",
        current_checkpoint_id: "CP-1",
        current_checkpoint_lineage_id: "LN-1",
        pending_checkpoint_approval: false,
      },
      plan: {
        steps: [{ step_id: "ST1", title: "Build", status: "running" }],
        closeout_status: "not_started",
      },
    },
    bottom_panels: {
      git_status: {
        current_status: "running:st1",
        pending_checkpoint_approval: false,
      },
    },
  };

  const normalized = sanitizeProjectDetailForJobState(detail, null, {
    nowMs: Date.parse("2026-04-01T00:00:00Z"),
  });

  assert.equal(normalized.project.current_status, "running:st1");
  assert.equal(normalized.plan.steps[0].status, "running");
  assert.equal(normalized.loop_state.current_task, "Build");
  assert.equal(normalized.loop_state.current_checkpoint_id, "CP-1");
  assert.equal(normalized.loop_state.current_checkpoint_lineage_id, "LN-1");
  assert.equal(normalized.checkpoints.items[0].status, "running");
  assert.equal(normalized.snapshot.project.current_status, "running:st1");
  assert.equal(normalized.bottom_panels.git_status.current_status, "running:st1");
  assert.equal(normalized.execution_state.project_status, "running:st1");
});
