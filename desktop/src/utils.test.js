import test from "node:test";
import assert from "node:assert/strict";

import {
  applyChatRuntimeSelectionToProject,
  applyConfigRuntimeModelSelection,
  applyProjectModelSelection,
  canEditStep,
  defaultModelForRuntime,
  failureReasonCode,
  failureReasonLabel,
  isDuplicateProjectJobError,
  filterModelCatalogByProvider,
  jobHasNewerActiveReplacement,
  mergeModelCatalogs,
  projectFormFromDetail,
  resolveChatRuntimeSelection,
  selectedConfigReasoning,
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

test("isDuplicateProjectJobError falls back to legacy message match", () => {
  assert.equal(
    isDuplicateProjectJobError({
      message: "Another background task is already active for this project.",
    }),
    true,
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

test("applyProjectModelSelection updates model reasoning without touching execution_model", () => {
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
  assert.equal(nextRuntime.execution_model, "gpt-4.1");
  assert.equal(nextRuntime.effort, "high");
  assert.equal(nextRuntime.planning_effort, "medium");
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
  assert.equal(nextRuntime.execution_model, "gpt-5.4");
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
