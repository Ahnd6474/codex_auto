import test from "node:test";
import assert from "node:assert/strict";

import {
  applyProjectEventDetailState,
  applyProjectEventListingState,
  applyProjectDetailState,
  clearSelectedProjectState,
  mergeProjectDetailSupplement,
  preserveProjectDetailSupplement,
} from "./projectStore.js";

test("preserveProjectDetailSupplement keeps the previous workspace tree reference on core refresh", () => {
  const previousWorkspaceTree = [
    {
      label: "Repository",
      path: "C:/repo",
      kind: "dir",
      children: [{ label: "src", path: "C:/repo/src", kind: "dir" }],
    },
  ];
  const previousDetail = {
    detail_level: "full",
    project: { repo_id: "repo-1" },
    workspace_tree: previousWorkspaceTree,
    loaded_sections: { workspace: true },
  };
  const nextDetail = {
    detail_level: "core",
    project: { repo_id: "repo-1" },
    workspace_tree: [],
    loaded_sections: {},
  };

  const merged = preserveProjectDetailSupplement(nextDetail, previousDetail);

  assert.equal(merged.workspace_tree, previousWorkspaceTree);
});

test("preserveProjectDetailSupplement reuses the previous workspace tree when the refreshed tree is equivalent", () => {
  const previousWorkspaceTree = [
    {
      label: "repo",
      path: "C:/repo",
      kind: "dir",
      children: [{ label: "src", path: "C:/repo/src", kind: "dir" }],
    },
  ];
  const refreshedWorkspaceTree = [
    {
      label: "repo",
      path: "C:/repo",
      kind: "dir",
      children: [{ label: "src", path: "C:/repo/src", kind: "dir" }],
    },
  ];
  const merged = preserveProjectDetailSupplement(
    {
      detail_level: "full",
      project: { repo_id: "repo-1" },
      workspace_tree: refreshedWorkspaceTree,
      loaded_sections: { workspace: true },
    },
    {
      detail_level: "full",
      project: { repo_id: "repo-1" },
      workspace_tree: previousWorkspaceTree,
      loaded_sections: { workspace: true },
    },
  );

  assert.equal(merged.workspace_tree, previousWorkspaceTree);
});

test("mergeProjectDetailSupplement reuses the current workspace tree reference when the supplement is equivalent", () => {
  const currentWorkspaceTree = [
    {
      label: "repo",
      path: "C:/repo",
      kind: "dir",
      children: [{ label: "README.md", path: "C:/repo/README.md", kind: "file" }],
    },
  ];
  const merged = mergeProjectDetailSupplement(
    {
      detail_level: "core",
      project: { repo_id: "repo-1" },
      workspace_tree: currentWorkspaceTree,
      loaded_sections: { workspace: true },
    },
    {
      workspace_tree: [
        {
          label: "repo",
          path: "C:/repo",
          kind: "dir",
          children: [{ label: "README.md", path: "C:/repo/README.md", kind: "file" }],
        },
      ],
      loaded_sections: { workspace: true },
    },
  );

  assert.equal(merged.workspace_tree, currentWorkspaceTree);
});

test("preserveProjectDetailSupplement keeps full report text while accepting fresh core failure data", () => {
  const previousFailure = { summary: "old failure" };
  const nextFailure = { summary: "new failure" };
  const previousDetail = {
    detail_level: "full",
    project: { repo_id: "repo-1" },
    reports: {
      latest_failure: previousFailure,
      closeout_report_text: "full report body",
    },
    loaded_sections: { reports: true },
  };
  const nextDetail = {
    detail_level: "core",
    project: { repo_id: "repo-1" },
    reports: {
      latest_failure: nextFailure,
    },
    loaded_sections: {},
  };

  const merged = preserveProjectDetailSupplement(nextDetail, previousDetail);

  assert.equal(merged.reports.latest_failure.summary, "new failure");
  assert.equal(merged.reports.closeout_report_text, "full report body");
});

test("preserveProjectDetailSupplement clears stale latest failure when core refresh reports none", () => {
  const previousDetail = {
    detail_level: "full",
    project: { repo_id: "repo-1" },
    reports: {
      latest_failure: { summary: "old failure" },
      closeout_report_text: "full report body",
    },
    loaded_sections: { reports: true },
  };
  const nextDetail = {
    detail_level: "core",
    project: { repo_id: "repo-1" },
    reports: {
      latest_failure: {},
    },
    loaded_sections: {},
  };

  const merged = preserveProjectDetailSupplement(nextDetail, previousDetail);

  assert.deepEqual(merged.reports.latest_failure, {});
  assert.equal(merged.reports.closeout_report_text, "full report body");
});

test("preserveProjectDetailSupplement keeps contract-wave report sections on core refresh", () => {
  const previousDetail = {
    detail_level: "full",
    project: { repo_id: "repo-1" },
    reports: {
      latest_failure: {},
      spine: { current_version: "spine-v4", history_count: 2 },
      common_requirements: { open_count: 1, resolved_count: 3 },
      lineage_manifests: [{ manifest_id: "MAN-1", promotion_class: "yellow" }],
      shared_contracts_text: "# Shared Contracts\n\n- api/payments",
    },
    loaded_sections: { reports: true },
  };
  const nextDetail = {
    detail_level: "core",
    project: { repo_id: "repo-1" },
    reports: {
      latest_failure: {},
    },
    loaded_sections: {},
  };

  const merged = preserveProjectDetailSupplement(nextDetail, previousDetail);

  assert.equal(merged.reports.spine.current_version, "spine-v4");
  assert.equal(merged.reports.common_requirements.open_count, 1);
  assert.equal(merged.reports.lineage_manifests[0].manifest_id, "MAN-1");
  assert.equal(merged.reports.shared_contracts_text, "# Shared Contracts\n\n- api/payments");
});

test("applyProjectDetailState preserves the current project_dir when a sparse detail payload omits repo_path", () => {
  let capturedProjectForm = {
    project_dir: "C:/repo",
    display_name: "Existing Repo",
    branch: "main",
    origin_url: "https://example.com/repo.git",
    github_mode: "manual",
    runtime: { model_provider: "openai" },
  };

  applyProjectDetailState({
    detail: {
      project: {
        repo_id: "repo-1",
        repo_path: "",
        display_name: "Existing Repo",
        branch: "main",
        origin_url: "",
      },
      runtime: {
        model_provider: "gemini",
      },
      plan: {
        steps: [],
      },
      codex_status: {
        model_catalog: [],
      },
    },
    refs: {
      lastAppliedDetailSignatureRef: { current: "" },
    },
    state: {
      projectDetail: {
        project: {
          repo_id: "repo-1",
        },
      },
      modelCatalog: [],
      activeJob: null,
      defaultRuntime: {
        model_provider: "openai",
        model: "gpt-5.4",
        model_slug_input: "gpt-5.4",
      },
      planDirty: false,
    },
    setters: {
      transition: (callback) => callback(),
      setProjectDetail: () => {},
      setModelCatalog: () => {},
      setShareSettings: () => {},
      setLoadingProjectId: () => {},
      setProjectForm: (updater) => {
        capturedProjectForm = typeof updater === "function" ? updater(capturedProjectForm) : updater;
      },
      setPlanDraft: () => {},
      setSelectedStepId: () => {},
      setPlanDirty: () => {},
    },
  });

  assert.equal(capturedProjectForm.project_dir, "C:/repo");
  assert.equal(capturedProjectForm.display_name, "Existing Repo");
  assert.equal(capturedProjectForm.runtime.model_provider, "openai");
  assert.equal(capturedProjectForm.runtime.execution_model, "gpt-5.4");
});

test("applyProjectEventListingState clears repo_path and preserves hint when an event marks the repo unavailable", () => {
  let capturedProjects = null;
  let capturedWorkspaceStats = null;

  const nextProjects = applyProjectEventListingState({
    projects: [
      {
        repo_id: "repo-1",
        repo_path: "C:/repo",
        repo_path_hint: "C:/repo",
        repo_available: true,
        repo_binding: "bound",
        status: "plan_ready",
        detail: "",
      },
    ],
    project: {
      repo_id: "repo-1",
      project_dir: "",
      project_dir_hint: "C:/repo",
      repo_available: false,
      repo_binding: "missing",
      status: "failed",
    },
    setProjects: (value) => {
      capturedProjects = value;
    },
    setWorkspaceStats: (value) => {
      capturedWorkspaceStats = value;
    },
  });

  assert.ok(Array.isArray(nextProjects));
  assert.equal(capturedProjects[0].repo_path, "");
  assert.equal(capturedProjects[0].repo_path_hint, "C:/repo");
  assert.equal(capturedProjects[0].repo_available, false);
  assert.equal(capturedProjects[0].repo_binding, "missing");
  assert.equal(capturedProjects[0].status, "failed");
  assert.equal(capturedWorkspaceStats.failed, 1);
});

test("applyProjectEventDetailState matches disconnected projects by repo_path_hint", () => {
  const updated = applyProjectEventDetailState(
    {
      project: {
        repo_id: "",
        repo_path: "",
        repo_path_hint: "C:/stale-repo",
        repo_available: false,
        repo_binding: "missing",
        current_status: "plan_ready",
      },
      snapshot: {
        project: {
          repo_path: "",
          repo_path_hint: "C:/stale-repo",
          repo_available: false,
          repo_binding: "missing",
          current_status: "plan_ready",
        },
      },
    },
    {
      project_dir: "",
      project_dir_hint: "C:/stale-repo",
      repo_available: false,
      repo_binding: "missing",
      status: "running:run-plan",
    },
  );

  assert.equal(updated?.project?.current_status, "running:run-plan");
  assert.equal(updated?.project?.repo_path, "");
  assert.equal(updated?.project?.repo_path_hint, "C:/stale-repo");
  assert.equal(updated?.project?.repo_available, false);
  assert.equal(updated?.snapshot?.project?.repo_path_hint, "C:/stale-repo");
});

test("applyProjectDetailState keeps the selected project's saved AI settings instead of defaultRuntime values", () => {
  let capturedProjectForm = {
    project_dir: "C:/repo",
    display_name: "Existing Repo",
    branch: "main",
    origin_url: "https://example.com/repo.git",
    github_mode: "manual",
    runtime: {
      model_provider: "claude",
      model: "claude-sonnet-4-6",
      execution_model: "claude-sonnet-4-6",
      model_slug_input: "claude-sonnet-4-6",
      effort: "xhigh",
      planning_effort: "high",
    },
  };

  applyProjectDetailState({
    detail: {
      project: {
        repo_id: "repo-1",
        repo_path: "C:/repo",
        display_name: "Existing Repo",
        branch: "main",
        origin_url: "https://example.com/repo.git",
      },
      runtime: {
        model_provider: "claude",
        model: "claude-sonnet-4-6",
        execution_model: "claude-sonnet-4-6",
        model_slug_input: "claude-sonnet-4-6",
        effort: "xhigh",
        planning_effort: "high",
      },
      plan: {
        steps: [],
      },
      codex_status: {
        model_catalog: [],
      },
    },
    refs: {
      lastAppliedDetailSignatureRef: { current: "" },
    },
    state: {
      projectDetail: {
        project: {
          repo_id: "repo-1",
        },
      },
      modelCatalog: [],
      activeJob: null,
      defaultRuntime: {
        model_provider: "openai",
        model: "gpt-5.4",
        model_slug_input: "gpt-5.4",
        effort: "medium",
      },
      planDirty: false,
    },
    setters: {
      transition: (callback) => callback(),
      setProjectDetail: () => {},
      setModelCatalog: () => {},
      setShareSettings: () => {},
      setLoadingProjectId: () => {},
      setProjectForm: (updater) => {
        capturedProjectForm = typeof updater === "function" ? updater(capturedProjectForm) : updater;
      },
      setPlanDraft: () => {},
      setSelectedStepId: () => {},
      setPlanDirty: () => {},
    },
  });

  assert.equal(capturedProjectForm.runtime.model_provider, "claude");
  assert.equal(capturedProjectForm.runtime.model, "claude-sonnet-4-6");
  assert.equal(capturedProjectForm.runtime.execution_model, "claude-sonnet-4-6");
  assert.equal(capturedProjectForm.runtime.effort, "xhigh");
  assert.equal(capturedProjectForm.runtime.planning_effort, "high");
});

test("applyProjectDetailState preserves the full OpenAI model catalog when a refreshed project returns a sparse catalog", () => {
  let capturedProjectForm = {
    project_dir: "C:/repo-1",
    display_name: "Existing Repo",
    branch: "main",
    origin_url: "https://example.com/repo.git",
    github_mode: "manual",
    runtime: {
      model_provider: "openai",
      model: "gpt-5.4",
      execution_model: "gpt-5.4",
      model_slug_input: "gpt-5.4",
      effort: "medium",
      planning_effort: "medium",
    },
  };
  let capturedModelCatalog = null;

  applyProjectDetailState({
    detail: {
      project: {
        repo_id: "repo-2",
        repo_path: "C:/repo-2",
        display_name: "Another Repo",
        branch: "main",
        origin_url: "https://example.com/another.git",
      },
      runtime: {
        model_provider: "openai",
        model: "gpt-5.4",
        execution_model: "gpt-5.4",
        model_slug_input: "gpt-5.4",
        effort: "medium",
        planning_effort: "medium",
      },
      plan: {
        steps: [],
      },
      codex_status: {
        model_catalog: [
          {
            model: "gpt-5.4",
            display_name: "GPT-5.4",
            provider: "openai",
            hidden: false,
          },
        ],
      },
    },
    refs: {
      lastAppliedDetailSignatureRef: { current: "" },
    },
    state: {
      projectDetail: {
        project: {
          repo_id: "repo-1",
        },
        runtime: {
          model_provider: "claude",
          model: "claude-sonnet-4-6",
          execution_model: "claude-sonnet-4-6",
          model_slug_input: "claude-sonnet-4-6",
          effort: "high",
          planning_effort: "high",
        },
      },
      modelCatalog: [
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
      ],
      activeJob: null,
      defaultRuntime: {
        model_provider: "openai",
        model: "gpt-5.4",
      },
      planDirty: false,
    },
    setters: {
      transition: (callback) => callback(),
      setProjectDetail: () => {},
      setModelCatalog: (value) => {
        capturedModelCatalog = value;
      },
      setShareSettings: () => {},
      setLoadingProjectId: () => {},
      setProjectForm: (updater) => {
        capturedProjectForm = typeof updater === "function" ? updater(capturedProjectForm) : updater;
      },
      setPlanDraft: () => {},
      setSelectedStepId: () => {},
      setPlanDirty: () => {},
    },
  });

  assert.ok(Array.isArray(capturedModelCatalog));
  assert.deepEqual(
    capturedModelCatalog.map((item) => item.model),
    ["gpt-5.4", "gpt-5.4-mini"],
  );
  assert.equal(capturedProjectForm.project_dir, "C:/repo-2");
  assert.equal(capturedProjectForm.runtime.model_provider, "openai");
  assert.equal(capturedProjectForm.runtime.model, "gpt-5.4");
  assert.equal(capturedProjectForm.runtime.execution_model, "gpt-5.4");
});

test("applyProjectDetailState preserves local model and reasoning overrides on same-project refresh", () => {
  let capturedProjectForm = {
    project_dir: "C:/repo",
    display_name: "Existing Repo",
    branch: "main",
    origin_url: "https://example.com/repo.git",
    github_mode: "manual",
    runtime: {
      model_provider: "claude",
      model: "claude-sonnet-4-6",
      execution_model: "claude-sonnet-4-6",
      model_slug_input: "claude-sonnet-4-6",
      effort: "xhigh",
      planning_effort: "high",
    },
  };

  applyProjectDetailState({
    detail: {
      project: {
        repo_id: "repo-1",
        repo_path: "C:/repo",
        display_name: "Existing Repo",
        branch: "main",
        origin_url: "https://example.com/repo.git",
      },
      runtime: {
        model_provider: "openai",
        model: "gpt-5.4",
        execution_model: "gpt-5.4",
        model_slug_input: "gpt-5.4",
        effort: "medium",
        planning_effort: "medium",
      },
      plan: {
        steps: [],
      },
      codex_status: {
        model_catalog: [],
      },
    },
    refs: {
      lastAppliedDetailSignatureRef: { current: "" },
    },
    state: {
      projectDetail: {
        project: {
          repo_id: "repo-1",
        },
        runtime: {
          model_provider: "openai",
          model: "gpt-5.4",
          execution_model: "gpt-5.4",
          model_slug_input: "gpt-5.4",
          effort: "medium",
          planning_effort: "medium",
        },
      },
      modelCatalog: [],
      activeJob: null,
      defaultRuntime: {
        model_provider: "openai",
      },
      planDirty: false,
    },
    setters: {
      transition: (callback) => callback(),
      setProjectDetail: () => {},
      setModelCatalog: () => {},
      setShareSettings: () => {},
      setLoadingProjectId: () => {},
      setProjectForm: (updater) => {
        capturedProjectForm = typeof updater === "function" ? updater(capturedProjectForm) : updater;
      },
      setPlanDraft: () => {},
      setSelectedStepId: () => {},
      setPlanDirty: () => {},
    },
  });

  assert.equal(capturedProjectForm.runtime.model_provider, "claude");
  assert.equal(capturedProjectForm.runtime.model, "claude-sonnet-4-6");
  assert.equal(capturedProjectForm.runtime.execution_model, "claude-sonnet-4-6");
  assert.equal(capturedProjectForm.runtime.model_slug_input, "claude-sonnet-4-6");
  assert.equal(capturedProjectForm.runtime.effort, "xhigh");
  assert.equal(capturedProjectForm.runtime.planning_effort, "high");
});

test("applyProjectDetailState preserves chat model overrides on same-project refresh", () => {
  let capturedProjectForm = {
    project_dir: "C:/repo",
    display_name: "Existing Repo",
    branch: "main",
    origin_url: "https://example.com/repo.git",
    github_mode: "manual",
    runtime: {
      model_provider: "openai",
      model: "gpt-5.4",
      execution_model: "gpt-5.4",
      model_slug_input: "gpt-5.4",
      effort: "medium",
      planning_effort: "medium",
      chat_model_provider: "openai",
      chat_local_model_provider: "",
      chat_model: "gpt-5.4-mini",
      chat_effort: "high",
    },
  };

  applyProjectDetailState({
    detail: {
      project: {
        repo_id: "repo-1",
        repo_path: "C:/repo",
        display_name: "Existing Repo",
        branch: "main",
        origin_url: "https://example.com/repo.git",
      },
      runtime: {
        model_provider: "openai",
        model: "gpt-5.4",
        execution_model: "gpt-5.4",
        model_slug_input: "gpt-5.4",
        effort: "medium",
        planning_effort: "medium",
      },
      plan: {
        steps: [],
      },
      codex_status: {
        model_catalog: [],
      },
    },
    refs: {
      lastAppliedDetailSignatureRef: { current: "" },
    },
    state: {
      projectDetail: {
        project: {
          repo_id: "repo-1",
        },
        runtime: {
          model_provider: "openai",
          model: "gpt-5.4",
          execution_model: "gpt-5.4",
          model_slug_input: "gpt-5.4",
          effort: "medium",
          planning_effort: "medium",
        },
      },
      modelCatalog: [],
      activeJob: null,
      defaultRuntime: {
        model_provider: "openai",
      },
      planDirty: false,
    },
    setters: {
      transition: (callback) => callback(),
      setProjectDetail: () => {},
      setModelCatalog: () => {},
      setShareSettings: () => {},
      setLoadingProjectId: () => {},
      setProjectForm: (updater) => {
        capturedProjectForm = typeof updater === "function" ? updater(capturedProjectForm) : updater;
      },
      setPlanDraft: () => {},
      setSelectedStepId: () => {},
      setPlanDirty: () => {},
    },
  });

  assert.equal(capturedProjectForm.runtime.chat_model_provider, "openai");
  assert.equal(capturedProjectForm.runtime.chat_model, "gpt-5.4-mini");
  assert.equal(capturedProjectForm.runtime.chat_effort, "high");
});

test("applyProjectDetailState preserves chat model overrides when opening a project from a blank form", () => {
  let capturedProjectForm = {
    project_dir: "",
    display_name: "",
    branch: "main",
    origin_url: "",
    github_mode: "existing",
    runtime: {
      model_provider: "openai",
      model: "gpt-5.4",
      execution_model: "gpt-5.4",
      model_slug_input: "gpt-5.4",
      effort: "medium",
      planning_effort: "medium",
      chat_model_provider: "openai",
      chat_local_model_provider: "",
      chat_model: "gpt-5.4-mini",
      chat_effort: "high",
    },
  };

  applyProjectDetailState({
    detail: {
      project: {
        repo_id: "repo-2",
        repo_path: "C:/repo-2",
        display_name: "Another Repo",
        branch: "main",
        origin_url: "https://example.com/another.git",
      },
      runtime: {
        model_provider: "openai",
        model: "gpt-5.4",
        execution_model: "gpt-5.4",
        model_slug_input: "gpt-5.4",
        effort: "medium",
        planning_effort: "medium",
      },
      plan: {
        steps: [],
      },
      codex_status: {
        model_catalog: [],
      },
    },
    refs: {
      lastAppliedDetailSignatureRef: { current: "" },
    },
    state: {
      projectDetail: null,
      modelCatalog: [],
      activeJob: null,
      defaultRuntime: {
        model_provider: "openai",
        model: "gpt-5.4",
      },
      planDirty: false,
    },
    setters: {
      transition: (callback) => callback(),
      setProjectDetail: () => {},
      setModelCatalog: () => {},
      setShareSettings: () => {},
      setLoadingProjectId: () => {},
      setProjectForm: (updater) => {
        capturedProjectForm = typeof updater === "function" ? updater(capturedProjectForm) : updater;
      },
      setPlanDraft: () => {},
      setSelectedStepId: () => {},
      setPlanDirty: () => {},
    },
  });

  assert.equal(capturedProjectForm.project_dir, "C:/repo-2");
  assert.equal(capturedProjectForm.runtime.model_provider, "openai");
  assert.equal(capturedProjectForm.runtime.model, "gpt-5.4");
  assert.equal(capturedProjectForm.runtime.execution_model, "gpt-5.4");
  assert.equal(capturedProjectForm.runtime.chat_model_provider, "openai");
  assert.equal(capturedProjectForm.runtime.chat_model, "gpt-5.4-mini");
  assert.equal(capturedProjectForm.runtime.chat_effort, "high");
});

test("applyProjectDetailState clears chat model overrides when opening a project from a blank form with a different provider", () => {
  let capturedProjectForm = {
    project_dir: "",
    display_name: "",
    branch: "main",
    origin_url: "",
    github_mode: "existing",
    runtime: {
      model_provider: "openai",
      model: "gpt-5.4",
      execution_model: "gpt-5.4",
      model_slug_input: "gpt-5.4",
      effort: "medium",
      planning_effort: "medium",
      chat_model_provider: "openai",
      chat_local_model_provider: "",
      chat_model: "gpt-5.4-mini",
      chat_effort: "high",
    },
  };

  applyProjectDetailState({
    detail: {
      project: {
        repo_id: "repo-2",
        repo_path: "C:/repo-2",
        display_name: "Claude Repo",
        branch: "main",
        origin_url: "https://example.com/claude.git",
      },
      runtime: {
        model_provider: "claude",
        model: "claude-sonnet-4-6",
        execution_model: "claude-sonnet-4-6",
        model_slug_input: "claude-sonnet-4-6",
        effort: "high",
        planning_effort: "high",
      },
      plan: {
        steps: [],
      },
      codex_status: {
        model_catalog: [],
      },
    },
    refs: {
      lastAppliedDetailSignatureRef: { current: "" },
    },
    state: {
      projectDetail: null,
      modelCatalog: [],
      activeJob: null,
      defaultRuntime: {
        model_provider: "openai",
        model: "gpt-5.4",
      },
      planDirty: false,
    },
    setters: {
      transition: (callback) => callback(),
      setProjectDetail: () => {},
      setModelCatalog: () => {},
      setShareSettings: () => {},
      setLoadingProjectId: () => {},
      setProjectForm: (updater) => {
        capturedProjectForm = typeof updater === "function" ? updater(capturedProjectForm) : updater;
      },
      setPlanDraft: () => {},
      setSelectedStepId: () => {},
      setPlanDirty: () => {},
    },
  });

  assert.equal(capturedProjectForm.runtime.model_provider, "claude");
  assert.equal(capturedProjectForm.runtime.model, "claude-sonnet-4-6");
  assert.equal(capturedProjectForm.runtime.execution_model, "claude-sonnet-4-6");
  assert.equal(String(capturedProjectForm.runtime.chat_model_provider || ""), "");
  assert.equal(String(capturedProjectForm.runtime.chat_model || ""), "");
  assert.equal(String(capturedProjectForm.runtime.chat_effort || ""), "");
});

test("applyProjectDetailState preserves manual runtime overrides when switching projects within the same provider", () => {
  let capturedProjectForm = {
    project_dir: "C:/repo-1",
    display_name: "Existing Repo",
    branch: "main",
    origin_url: "https://example.com/repo.git",
    github_mode: "manual",
    runtime: {
      model_provider: "openai",
      model: "gpt-5.4-mini",
      execution_model: "gpt-5.4-mini",
      model_slug_input: "gpt-5.4-mini",
      effort: "high",
      planning_effort: "high",
      chat_model_provider: "openai",
      chat_local_model_provider: "",
      chat_model: "gpt-5.4-mini",
      chat_effort: "high",
    },
  };

  applyProjectDetailState({
    detail: {
      project: {
        repo_id: "repo-2",
        repo_path: "C:/repo-2",
        display_name: "Another Repo",
        branch: "main",
        origin_url: "https://example.com/another.git",
      },
      runtime: {
        model_provider: "openai",
        model: "gpt-5.4",
        execution_model: "gpt-5.4",
        model_slug_input: "gpt-5.4",
        effort: "medium",
        planning_effort: "medium",
      },
      plan: {
        steps: [],
      },
      codex_status: {
        model_catalog: [],
      },
    },
    refs: {
      lastAppliedDetailSignatureRef: { current: "" },
    },
    state: {
      projectDetail: {
        project: {
          repo_id: "repo-1",
        },
      },
      modelCatalog: [],
      activeJob: null,
      defaultRuntime: {
        model_provider: "openai",
        model: "gpt-5.4",
      },
      planDirty: false,
    },
    setters: {
      transition: (callback) => callback(),
      setProjectDetail: () => {},
      setModelCatalog: () => {},
      setShareSettings: () => {},
      setLoadingProjectId: () => {},
      setProjectForm: (updater) => {
        capturedProjectForm = typeof updater === "function" ? updater(capturedProjectForm) : updater;
      },
      setPlanDraft: () => {},
      setSelectedStepId: () => {},
      setPlanDirty: () => {},
    },
  });

  assert.equal(capturedProjectForm.runtime.model_provider, "openai");
  assert.equal(capturedProjectForm.runtime.model, "gpt-5.4-mini");
  assert.equal(capturedProjectForm.runtime.execution_model, "gpt-5.4-mini");
  assert.equal(capturedProjectForm.runtime.model_slug_input, "gpt-5.4-mini");
  assert.equal(capturedProjectForm.runtime.effort, "high");
  assert.equal(capturedProjectForm.runtime.planning_effort, "high");
  assert.equal(capturedProjectForm.runtime.chat_model_provider, "openai");
  assert.equal(capturedProjectForm.runtime.chat_model, "gpt-5.4-mini");
  assert.equal(capturedProjectForm.runtime.chat_effort, "high");
});

test("applyProjectDetailState resets manual runtime overrides when switching to a different provider", () => {
  let capturedProjectForm = {
    project_dir: "C:/repo-1",
    display_name: "Existing Repo",
    branch: "main",
    origin_url: "https://example.com/repo.git",
    github_mode: "manual",
    runtime: {
      model_provider: "openai",
      model: "gpt-5.4-mini",
      execution_model: "gpt-5.4-mini",
      model_slug_input: "gpt-5.4-mini",
      effort: "high",
      planning_effort: "high",
      chat_model_provider: "openai",
      chat_local_model_provider: "",
      chat_model: "gpt-5.4-mini",
      chat_effort: "high",
    },
  };

  applyProjectDetailState({
    detail: {
      project: {
        repo_id: "repo-2",
        repo_path: "C:/repo-2",
        display_name: "Claude Repo",
        branch: "main",
        origin_url: "https://example.com/claude.git",
      },
      runtime: {
        model_provider: "claude",
        model: "claude-sonnet-4-6",
        execution_model: "claude-sonnet-4-6",
        model_slug_input: "claude-sonnet-4-6",
        effort: "high",
        planning_effort: "high",
      },
      plan: {
        steps: [],
      },
      codex_status: {
        model_catalog: [],
      },
    },
    refs: {
      lastAppliedDetailSignatureRef: { current: "" },
    },
    state: {
      projectDetail: {
        project: {
          repo_id: "repo-1",
        },
        runtime: {
          model_provider: "openai",
          model: "gpt-5.4",
          execution_model: "gpt-5.4",
          model_slug_input: "gpt-5.4",
          effort: "medium",
          planning_effort: "medium",
          chat_model_provider: "openai",
          chat_model: "gpt-5.4",
          chat_effort: "medium",
        },
      },
      modelCatalog: [],
      activeJob: null,
      defaultRuntime: {
        model_provider: "openai",
        model: "gpt-5.4",
      },
      planDirty: false,
    },
    setters: {
      transition: (callback) => callback(),
      setProjectDetail: () => {},
      setModelCatalog: () => {},
      setShareSettings: () => {},
      setLoadingProjectId: () => {},
      setProjectForm: (updater) => {
        capturedProjectForm = typeof updater === "function" ? updater(capturedProjectForm) : updater;
      },
      setPlanDraft: () => {},
      setSelectedStepId: () => {},
      setPlanDirty: () => {},
    },
  });

  assert.equal(capturedProjectForm.runtime.model_provider, "claude");
  assert.equal(capturedProjectForm.runtime.model, "claude-sonnet-4-6");
  assert.equal(capturedProjectForm.runtime.execution_model, "claude-sonnet-4-6");
  assert.equal(capturedProjectForm.runtime.model_slug_input, "claude-sonnet-4-6");
  assert.equal(String(capturedProjectForm.runtime.chat_model_provider || ""), "");
  assert.equal(String(capturedProjectForm.runtime.chat_model || ""), "");
});

test("applyProjectDetailState preserves a manually cleared step selection on same-project refresh", () => {
  let capturedSelectedStepId = "__unset__";

  applyProjectDetailState({
    detail: {
      project: {
        repo_id: "repo-1",
        repo_path: "C:/repo",
      },
      runtime: {
        model_provider: "openai",
      },
      plan: {
        steps: [
          { step_id: "ST1", status: "pending" },
          { step_id: "ST2", status: "pending" },
        ],
      },
      codex_status: {
        model_catalog: [],
      },
    },
    refs: {
      lastAppliedDetailSignatureRef: { current: "" },
    },
    state: {
      projectDetail: {
        project: {
          repo_id: "repo-1",
        },
      },
      modelCatalog: [],
      activeJob: null,
      defaultRuntime: {
        model_provider: "openai",
      },
      planDirty: false,
    },
    setters: {
      transition: (callback) => callback(),
      setProjectDetail: () => {},
      setModelCatalog: () => {},
      setShareSettings: () => {},
      setLoadingProjectId: () => {},
      setProjectForm: () => {},
      setPlanDraft: () => {},
      setSelectedStepId: (updater) => {
        capturedSelectedStepId = typeof updater === "function" ? updater("") : updater;
      },
      setPlanDirty: () => {},
    },
  });

  assert.equal(capturedSelectedStepId, "");
});

test("applyProjectDetailState preserves step model selection on same-project refresh when the backend detail is stale", () => {
  let capturedPlanDraft = null;
  let capturedSelectedStepId = "__unset__";

  applyProjectDetailState({
    detail: {
      project: {
        repo_id: "repo-1",
        repo_path: "C:/repo",
      },
      runtime: {
        model_provider: "openai",
        model: "gpt-5.4",
        execution_model: "gpt-5.4",
        model_slug_input: "gpt-5.4",
        effort: "medium",
        planning_effort: "medium",
      },
      plan: {
        steps: [
          { step_id: "ST1", title: "Plan", status: "completed" },
          {
            step_id: "ST2",
            title: "Build",
            status: "pending",
            model_provider: "",
            model: "",
            reasoning_effort: "",
          },
        ],
      },
      codex_status: {
        model_catalog: [],
      },
    },
    refs: {
      lastAppliedDetailSignatureRef: { current: "" },
    },
    state: {
      projectDetail: {
        project: {
          repo_id: "repo-1",
        },
      },
      planDraft: {
        steps: [
          { step_id: "ST1", title: "Plan", status: "completed" },
          {
            step_id: "ST2",
            title: "Build",
            status: "pending",
            model_provider: "claude",
            model: "claude-sonnet-4-6",
            reasoning_effort: "high",
          },
        ],
      },
      modelCatalog: [],
      activeJob: null,
      defaultRuntime: {
        model_provider: "openai",
      },
      planDirty: false,
    },
    setters: {
      transition: (callback) => callback(),
      setProjectDetail: () => {},
      setModelCatalog: () => {},
      setShareSettings: () => {},
      setLoadingProjectId: () => {},
      setProjectForm: () => {},
      setPlanDraft: (updater) => {
        capturedPlanDraft = typeof updater === "function" ? updater(capturedPlanDraft) : updater;
      },
      setSelectedStepId: (updater) => {
        capturedSelectedStepId = typeof updater === "function" ? updater("ST2") : updater;
      },
      setPlanDirty: () => {},
    },
  });

  assert.equal(capturedSelectedStepId, "ST2");
  assert.equal(capturedPlanDraft.steps[1].model_provider, "claude");
  assert.equal(capturedPlanDraft.steps[1].model, "claude-sonnet-4-6");
  assert.equal(capturedPlanDraft.steps[1].reasoning_effort, "high");
});

test("applyProjectDetailState keeps the step editor closed when switching to a different project", () => {
  let capturedSelectedStepId = "__unset__";

  applyProjectDetailState({
    detail: {
      project: {
        repo_id: "repo-2",
        repo_path: "C:/repo-2",
      },
      runtime: {
        model_provider: "openai",
      },
      plan: {
        steps: [
          { step_id: "ST9", status: "completed" },
          { step_id: "ST10", status: "pending" },
        ],
      },
      codex_status: {
        model_catalog: [],
      },
    },
    refs: {
      lastAppliedDetailSignatureRef: { current: "" },
    },
    state: {
      projectDetail: {
        project: {
          repo_id: "repo-1",
        },
      },
      modelCatalog: [],
      activeJob: null,
      defaultRuntime: {
        model_provider: "openai",
      },
      planDirty: false,
    },
    setters: {
      transition: (callback) => callback(),
      setProjectDetail: () => {},
      setModelCatalog: () => {},
      setShareSettings: () => {},
      setLoadingProjectId: () => {},
      setProjectForm: () => {},
      setPlanDraft: () => {},
      setSelectedStepId: (updater) => {
        capturedSelectedStepId = typeof updater === "function" ? updater("") : updater;
      },
      setPlanDirty: () => {},
    },
  });

  assert.equal(capturedSelectedStepId, "");
});

test("clearSelectedProjectState can preserve the current project identity form", () => {
  let capturedProjectForm = null;

  clearSelectedProjectState({
    defaultRuntime: {
      model_provider: "openai",
    },
    nextProjectForm: {
      project_dir: "C:/repo",
      display_name: "Repo",
      branch: "main",
      origin_url: "https://example.com/repo.git",
      github_mode: "existing",
      runtime: {
        model_provider: "openai",
      },
    },
    refs: {
      lastAppliedDetailSignatureRef: { current: "sig" },
    },
    setters: {
      setProjectDetail: () => {},
      setSelectedProjectId: () => {},
      setSelectedStepId: () => {},
      setPlanDirty: () => {},
      setLoadingProjectId: () => {},
      setProjectForm: (value) => {
        capturedProjectForm = value;
      },
      setPlanDraft: () => {},
      setShareSettings: () => {},
    },
  });

  assert.deepEqual(capturedProjectForm, {
    project_dir: "C:/repo",
    display_name: "Repo",
    branch: "main",
    origin_url: "https://example.com/repo.git",
    github_mode: "existing",
    runtime: {
      model_provider: "openai",
    },
  });
});
