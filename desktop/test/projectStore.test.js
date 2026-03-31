import assert from "node:assert/strict";
import test from "node:test";

import {
  applyProjectDetailListingState,
  applyProjectDetailState,
  mergeProjectDetailSupplement,
  preserveProjectDetailSupplement,
} from "../src/controller/projectStore.js";
import { detailApplySignature } from "../src/utils.js";

test("applyProjectDetailListingState merges refreshed detail into the existing project row", () => {
  let nextProjects = null;
  let nextWorkspaceStats = null;

  const nextListing = applyProjectDetailListingState({
    projects: [
      {
        repo_id: "demo",
        slug: "demo",
        display_name: "Demo",
        repo_path: "/repo",
        origin_url: "",
        branch: "main",
        status: "plan_ready",
        detail: "Branch main",
        created_at: "2026-03-27T00:00:00+00:00",
        last_run_at: "2026-03-27T00:00:00+00:00",
        summary: "Old summary",
        progress: "Old progress",
        stats: {
          total_steps: 2,
          completed_steps: 0,
          failed_steps: 0,
          running_steps: 0,
          remaining_steps: 2,
        },
        closeout_status: "not_started",
      },
    ],
    detail: {
      project: {
        repo_id: "demo",
        slug: "demo",
        display_name: "Demo",
        repo_path: "/repo",
        origin_url: "https://github.com/example/demo",
        branch: "main",
        current_status: "running:block:2",
        created_at: "2026-03-27T00:00:00+00:00",
        last_run_at: "2026-03-27T01:00:00+00:00",
      },
      summary: "New summary",
      progress: "Completed 1/2 steps, next: ST2",
      stats: {
        total_steps: 2,
        completed_steps: 1,
        failed_steps: 0,
        running_steps: 1,
        remaining_steps: 1,
      },
      plan: {
        closeout_status: "not_started",
      },
    },
    runningJob: {
      id: "job-1",
      status: "running",
    },
    setProjects: (projects) => {
      nextProjects = projects;
    },
    setWorkspaceStats: (stats) => {
      nextWorkspaceStats = stats;
    },
  });

  assert.deepEqual(nextListing, nextProjects);
  assert.equal(nextProjects.length, 1);
  assert.deepEqual(nextProjects[0], {
    repo_id: "demo",
    slug: "demo",
    display_name: "Demo",
    repo_path: "/repo",
    origin_url: "https://github.com/example/demo",
    branch: "main",
    status: "running:block:2",
    detail: "https://github.com/example/demo",
    created_at: "2026-03-27T00:00:00+00:00",
    last_run_at: "2026-03-27T01:00:00+00:00",
    summary: "New summary",
    progress: "Completed 1/2 steps, next: ST2",
    stats: {
      total_steps: 2,
      completed_steps: 1,
      failed_steps: 0,
      running_steps: 1,
      remaining_steps: 1,
    },
    closeout_status: "not_started",
  });
  assert.deepEqual(nextWorkspaceStats, {
    project_count: 1,
    ready_like: 0,
    running: 1,
    failed: 0,
  });
});

test("applyProjectDetailState reapplies program model defaults while keeping other persisted runtime settings", () => {
  let nextProjectDetail = null;
  let nextModelCatalog = null;
  let nextShareSettings = null;
  let nextLoadingProjectId = "demo";
  let nextProjectForm = {
    project_dir: "/repo",
    display_name: "Demo",
    branch: "main",
    origin_url: "",
    github_mode: "existing",
    runtime: {
      model: "auto",
      effort: "medium",
      parallel_memory_per_worker_gib: 3,
      test_cmd: "python -m pytest",
    },
  };
  let nextPlanDraft = null;
  let nextSelectedStepId = "";
  let nextPlanDirty = true;

  const applied = applyProjectDetailState({
    detail: {
      project: {
        repo_id: "demo",
        repo_path: "/repo",
        display_name: "Demo",
        slug: "demo",
        branch: "main",
        origin_url: "",
      },
      runtime: {
        model: "gpt-5.4-mini",
        effort: "high",
        parallel_memory_per_worker_gib: 7,
        test_cmd: "npm test",
      },
      plan: {
        steps: [],
        closeout_status: "not_started",
      },
      codex_status: {
        model_catalog: [],
      },
    },
    refs: {
      lastAppliedDetailSignatureRef: {
        current: "",
      },
    },
    state: {
      projectDetail: null,
      modelCatalog: [],
      activeJob: null,
      defaultRuntime: {
        model: "auto",
        effort: "medium",
        parallel_memory_per_worker_gib: 3,
        test_cmd: "python -m pytest",
      },
      planDirty: false,
    },
    setters: {
      transition: (callback) => callback(),
      setProjectDetail: (value) => {
        nextProjectDetail = value;
      },
      setModelCatalog: (value) => {
        nextModelCatalog = value;
      },
      setShareSettings: (value) => {
        nextShareSettings = value;
      },
      setLoadingProjectId: (value) => {
        nextLoadingProjectId = value;
      },
      setProjectForm: (value) => {
        nextProjectForm = typeof value === "function" ? value(nextProjectForm) : value;
      },
      setPlanDraft: (value) => {
        nextPlanDraft = value;
      },
      setSelectedStepId: (value) => {
        nextSelectedStepId = typeof value === "function" ? value(nextSelectedStepId) : value;
      },
      setPlanDirty: (value) => {
        nextPlanDirty = value;
      },
    },
  });

  assert.equal(applied.project.repo_id, "demo");
  assert.equal(nextProjectDetail.project.repo_id, "demo");
  assert.deepEqual(nextModelCatalog, []);
  assert.deepEqual(nextShareSettings, {
    bind_host: "0.0.0.0",
  });
  assert.equal(nextLoadingProjectId, "");
  assert.equal(nextProjectForm.project_dir, "/repo");
  assert.equal(nextProjectForm.display_name, "Demo");
  assert.equal(nextProjectForm.branch, "main");
  assert.equal(nextProjectForm.origin_url, "");
  assert.equal(nextProjectForm.github_mode, "existing");
  assert.equal(nextProjectForm.runtime.model, "gpt-5.4-mini");
  assert.equal(nextProjectForm.runtime.effort, "high");
  assert.equal(nextProjectForm.runtime.parallel_memory_per_worker_gib, 7);
  assert.equal(nextProjectForm.runtime.test_cmd, "npm test");
  assert.deepEqual(nextPlanDraft, {
    steps: [],
    closeout_status: "not_started",
  });
  assert.equal(nextSelectedStepId, "");
  assert.equal(nextPlanDirty, false);
});

test("applyProjectDetailState preserves an unsaved plan draft and selected step on same-project refresh", () => {
  let nextProjectDetail = null;
  let nextProjectForm = {
    project_dir: "/repo",
    display_name: "Demo",
    branch: "main",
    origin_url: "",
    github_mode: "existing",
    runtime: {
      model: "auto",
      effort: "medium",
      test_cmd: "python -m pytest",
    },
  };
  let nextPlanDraft = {
    project_prompt: "Unsaved prompt",
    execution_mode: "parallel",
    closeout_status: "not_started",
    steps: [
      { step_id: "ST1", title: "Plan", status: "completed" },
      { step_id: "ST2", title: "Build", status: "running" },
    ],
  };
  let nextSelectedStepId = "ST2";
  let nextPlanDirty = true;

  const applied = applyProjectDetailState({
    detail: {
      project: {
        repo_id: "demo",
        repo_path: "/repo",
        display_name: "Demo",
        slug: "demo",
        branch: "main",
        origin_url: "",
      },
      runtime: {
        model: "gpt-5.4-mini",
        effort: "high",
        test_cmd: "npm test",
      },
      plan: {
        execution_mode: "parallel",
        closeout_status: "not_started",
        steps: [
          { step_id: "ST1", title: "Plan", status: "completed" },
          { step_id: "ST2", title: "Build", status: "running" },
        ],
      },
      codex_status: {
        model_catalog: [],
      },
    },
    options: {
      preserveDirtyPlan: true,
    },
    refs: {
      lastAppliedDetailSignatureRef: {
        current: "",
      },
    },
    state: {
      projectDetail: {
        project: {
          repo_id: "demo",
        },
        codex_status: {},
      },
      modelCatalog: [],
      activeJob: null,
      defaultRuntime: {
        model: "auto",
        effort: "medium",
        test_cmd: "python -m pytest",
      },
      planDirty: true,
    },
    setters: {
      transition: (callback) => callback(),
      setProjectDetail: (value) => {
        nextProjectDetail = value;
      },
      setModelCatalog: () => {},
      setShareSettings: () => {},
      setLoadingProjectId: () => {},
      setProjectForm: (value) => {
        nextProjectForm = typeof value === "function" ? value(nextProjectForm) : value;
      },
      setPlanDraft: (value) => {
        nextPlanDraft = value;
      },
      setSelectedStepId: (value) => {
        nextSelectedStepId = typeof value === "function" ? value(nextSelectedStepId) : value;
      },
      setPlanDirty: (value) => {
        nextPlanDirty = value;
      },
    },
  });

  assert.equal(applied.project.repo_id, "demo");
  assert.equal(nextProjectDetail.project.repo_id, "demo");
  assert.equal(nextProjectForm.project_dir, "/repo");
  assert.equal(nextProjectForm.runtime.model, "auto");
  assert.equal(nextPlanDraft.project_prompt, "Unsaved prompt");
  assert.equal(nextSelectedStepId, "ST2");
  assert.equal(nextPlanDirty, true);
});

test("applyProjectDetailState preserves closeout draft fields on same-project refresh", () => {
  let nextPlanDraft = {
    project_prompt: "Unsaved prompt",
    execution_mode: "parallel",
    closeout_status: "not_started",
    closeout_title: "Custom Closeout",
    closeout_display_description: "Wrap up the project",
    closeout_codex_description: "Wrap up the project",
    closeout_success_criteria: "Close the project cleanly",
    closeout_reasoning_effort: "high",
    closeout_model_provider: "claude",
    closeout_model: "claude-sonnet-4-6",
    closeout_depends_on: ["ST2"],
    closeout_owned_paths: ["README.md"],
    steps: [
      { step_id: "ST1", title: "Plan", status: "completed" },
      { step_id: "ST2", title: "Build", status: "running" },
    ],
  };

  applyProjectDetailState({
    detail: {
      project: {
        repo_id: "demo",
        repo_path: "/repo",
        display_name: "Demo",
        slug: "demo",
        branch: "main",
        origin_url: "",
      },
      runtime: {
        model: "gpt-5.4-mini",
        effort: "high",
        test_cmd: "npm test",
      },
      plan: {
        execution_mode: "parallel",
        closeout_status: "not_started",
        steps: [
          { step_id: "ST1", title: "Plan", status: "completed" },
          { step_id: "ST2", title: "Build", status: "running" },
        ],
      },
      codex_status: {
        model_catalog: [],
      },
    },
    options: {
      preserveDirtyPlan: false,
    },
    refs: {
      lastAppliedDetailSignatureRef: {
        current: "",
      },
    },
    state: {
      projectDetail: {
        project: {
          repo_id: "demo",
        },
        codex_status: {},
      },
      modelCatalog: [],
      activeJob: null,
      defaultRuntime: {
        model: "auto",
        effort: "medium",
        test_cmd: "python -m pytest",
      },
      planDirty: false,
      planDraft: nextPlanDraft,
    },
    setters: {
      transition: (callback) => callback(),
      setProjectDetail: () => {},
      setModelCatalog: () => {},
      setShareSettings: () => {},
      setLoadingProjectId: () => {},
      setProjectForm: () => {},
      setPlanDraft: (value) => {
        nextPlanDraft = typeof value === "function" ? value(nextPlanDraft) : value;
      },
      setSelectedStepId: () => {},
      setPlanDirty: () => {},
    },
  });

  assert.equal(nextPlanDraft.closeout_title, "Custom Closeout");
  assert.equal(nextPlanDraft.closeout_display_description, "Wrap up the project");
  assert.equal(nextPlanDraft.closeout_codex_description, "Wrap up the project");
  assert.equal(nextPlanDraft.closeout_success_criteria, "Close the project cleanly");
  assert.equal(nextPlanDraft.closeout_model_provider, "claude");
  assert.equal(nextPlanDraft.closeout_model, "claude-sonnet-4-6");
  assert.deepEqual(nextPlanDraft.closeout_depends_on, ["ST2"]);
  assert.deepEqual(nextPlanDraft.closeout_owned_paths, ["README.md"]);
});

test("applyProjectDetailState keeps the synthetic closeout step selected on refresh", () => {
  let nextSelectedStepId = "CO1";

  applyProjectDetailState({
    detail: {
      project: {
        repo_id: "demo",
        repo_path: "/repo",
        display_name: "Demo",
        slug: "demo",
        branch: "main",
        origin_url: "",
      },
      runtime: {
        model: "gpt-5.4-mini",
        effort: "high",
        test_cmd: "npm test",
      },
      plan: {
        execution_mode: "parallel",
        closeout_status: "not_started",
        steps: [
          { step_id: "ST1", title: "Plan", status: "completed" },
          { step_id: "ST2", title: "Build", status: "running" },
        ],
      },
      codex_status: {
        model_catalog: [],
      },
    },
    options: {
      preserveDirtyPlan: false,
      force: true,
    },
    refs: {
      lastAppliedDetailSignatureRef: {
        current: "",
      },
    },
    state: {
      projectDetail: {
        project: {
          repo_id: "demo",
        },
        codex_status: {},
      },
      modelCatalog: [],
      activeJob: null,
      defaultRuntime: {
        model: "auto",
        effort: "medium",
        test_cmd: "python -m pytest",
      },
      planDirty: false,
      planDraft: {
        closeout_status: "not_started",
        closeout_title: "Closeout",
        closeout_display_description: "Closeout",
        closeout_codex_description: "Closeout",
        closeout_success_criteria: "Closeout",
        steps: [
          { step_id: "ST1", title: "Plan", status: "completed" },
          { step_id: "ST2", title: "Build", status: "running" },
        ],
      },
    },
    setters: {
      transition: (callback) => callback(),
      setProjectDetail: () => {},
      setModelCatalog: () => {},
      setShareSettings: () => {},
      setLoadingProjectId: () => {},
      setProjectForm: () => {},
      setPlanDraft: () => {},
      setSelectedStepId: (value) => {
        nextSelectedStepId = typeof value === "function" ? value(nextSelectedStepId) : value;
      },
      setPlanDirty: () => {},
    },
  });

  assert.equal(nextSelectedStepId, "CO1");
});

test("applyProjectDetailState force reapplies the same detail signature on a manual refresh", () => {
  let nextProjectDetail = null;
  let nextProjectForm = {
    project_dir: "/repo",
    display_name: "Demo",
    branch: "main",
    origin_url: "",
    github_mode: "existing",
    runtime: {
      model: "gpt-5.4-mini",
      effort: "high",
      test_cmd: "npm test",
    },
  };
  const detail = {
    project: {
      repo_id: "demo",
      repo_path: "/repo",
      display_name: "Demo",
      slug: "demo",
      branch: "main",
      origin_url: "",
    },
    runtime: {
      model: "gpt-5.4-mini",
      effort: "high",
      test_cmd: "npm test",
    },
    plan: {
      execution_mode: "parallel",
      closeout_status: "not_started",
      steps: [
        { step_id: "ST1", title: "Plan", status: "completed" },
        { step_id: "ST2", title: "Build", status: "running" },
      ],
    },
    codex_status: {
      model_catalog: [],
    },
  };

  const applied = applyProjectDetailState({
    detail,
    options: {
      force: true,
    },
    refs: {
      lastAppliedDetailSignatureRef: {
        current: detailApplySignature(detail, null),
      },
    },
    state: {
      projectDetail: {
        project: {
          repo_id: "demo",
        },
        codex_status: {},
      },
      modelCatalog: [],
      activeJob: null,
      defaultRuntime: {
        model: "gpt-5.4-mini",
        effort: "high",
        test_cmd: "npm test",
      },
      planDirty: false,
    },
    setters: {
      transition: (callback) => callback(),
      setProjectDetail: (value) => {
        nextProjectDetail = value;
      },
      setModelCatalog: () => {},
      setShareSettings: () => {},
      setLoadingProjectId: () => {},
      setProjectForm: (value) => {
        nextProjectForm = typeof value === "function" ? value(nextProjectForm) : value;
      },
      setPlanDraft: () => {},
      setSelectedStepId: () => {},
      setPlanDirty: () => {},
    },
  });

  assert.equal(applied.project.repo_id, "demo");
  assert.equal(nextProjectDetail.project.repo_id, "demo");
  assert.equal(nextProjectForm.project_dir, "/repo");
});

test("applyProjectDetailState clears stale checkpoint approval state when the refreshed project is idle", () => {
  let nextProjectDetail = null;

  const applied = applyProjectDetailState({
    detail: {
      project: {
        repo_id: "demo",
        repo_path: "/repo",
        display_name: "Demo",
        slug: "demo",
        branch: "main",
        origin_url: "",
        current_status: "setup_ready",
      },
      runtime: {
        model: "gpt-5.4-mini",
        effort: "high",
      },
      loop_state: {
        current_checkpoint_id: null,
        current_checkpoint_lineage_id: null,
        pending_checkpoint_approval: false,
      },
      plan: {
        closeout_status: "not_started",
        steps: [],
      },
      codex_status: {
        model_catalog: [],
      },
      detail_level: "core",
      checkpoints: {
        current_checkpoint_id: "CP1",
        current_checkpoint_lineage_id: "LN1",
        items: [
          {
            checkpoint_id: "CP1",
            lineage_id: "LN1",
            title: "Review work",
            target_block: 2,
            status: "awaiting_review",
          },
        ],
        pending: {
          checkpoint_id: "CP1",
          lineage_id: "LN1",
          title: "Review work",
          target_block: 2,
          status: "awaiting_review",
        },
        timeline_markdown: "- CP1 | awaiting_review | Review work",
      },
    },
    refs: {
      lastAppliedDetailSignatureRef: {
        current: "",
      },
    },
    state: {
      projectDetail: {
        project: {
          repo_id: "demo",
        },
        checkpoints: {
          current_checkpoint_id: "CP1",
          current_checkpoint_lineage_id: "LN1",
          items: [
            {
              checkpoint_id: "CP1",
              lineage_id: "LN1",
              title: "Review work",
              target_block: 2,
              status: "awaiting_review",
            },
          ],
          pending: {
            checkpoint_id: "CP1",
            lineage_id: "LN1",
            title: "Review work",
            target_block: 2,
            status: "awaiting_review",
          },
          timeline_markdown: "- CP1 | awaiting_review | Review work",
        },
        codex_status: {},
      },
      modelCatalog: [],
      activeJob: null,
      defaultRuntime: {
        model: "gpt-5.4-mini",
        effort: "high",
      },
      planDirty: false,
    },
    setters: {
      transition: (callback) => callback(),
      setProjectDetail: (value) => {
        nextProjectDetail = value;
      },
      setModelCatalog: () => {},
      setShareSettings: () => {},
      setLoadingProjectId: () => {},
      setProjectForm: () => {},
      setPlanDraft: () => {},
      setSelectedStepId: () => {},
      setPlanDirty: () => {},
    },
  });

  assert.equal(applied.project.current_status, "setup_ready");
  assert.equal(nextProjectDetail.checkpoints.current_checkpoint_id, null);
  assert.equal(nextProjectDetail.checkpoints.pending, null);
  assert.equal(nextProjectDetail.checkpoints.items[0].status, "pending");
  assert.match(nextProjectDetail.checkpoints.timeline_markdown, /pending/);
});

test("applyProjectDetailState preserves checkpoint approval state when the refreshed project is actually waiting", () => {
  let nextProjectDetail = null;

  const applied = applyProjectDetailState({
    detail: {
      project: {
        repo_id: "demo",
        repo_path: "/repo",
        display_name: "Demo",
        slug: "demo",
        branch: "main",
        origin_url: "",
        current_status: "awaiting_checkpoint_approval",
      },
      runtime: {
        model: "gpt-5.4-mini",
        effort: "high",
      },
      loop_state: {
        current_checkpoint_id: "CP1",
        current_checkpoint_lineage_id: "LN1",
        pending_checkpoint_approval: true,
      },
      plan: {
        closeout_status: "not_started",
        steps: [],
      },
      codex_status: {
        model_catalog: [],
      },
      detail_level: "core",
      checkpoints: {
        current_checkpoint_id: "CP1",
        current_checkpoint_lineage_id: "LN1",
        items: [
          {
            checkpoint_id: "CP1",
            lineage_id: "LN1",
            title: "Review work",
            target_block: 2,
            status: "running",
          },
        ],
        pending: null,
        timeline_markdown: "",
      },
    },
    refs: {
      lastAppliedDetailSignatureRef: {
        current: "",
      },
    },
    state: {
      projectDetail: {
        project: {
          repo_id: "demo",
        },
        codex_status: {},
      },
      modelCatalog: [],
      activeJob: {
        id: "job-1",
        status: "running",
        command: "run-plan",
      },
      defaultRuntime: {
        model: "gpt-5.4-mini",
        effort: "high",
      },
      planDirty: false,
    },
    setters: {
      transition: (callback) => callback(),
      setProjectDetail: (value) => {
        nextProjectDetail = value;
      },
      setModelCatalog: () => {},
      setShareSettings: () => {},
      setLoadingProjectId: () => {},
      setProjectForm: () => {},
      setPlanDraft: () => {},
      setSelectedStepId: () => {},
      setPlanDirty: () => {},
    },
  });

  assert.equal(applied.project.current_status, "awaiting_checkpoint_approval");
  assert.equal(nextProjectDetail.checkpoints.current_checkpoint_id, "CP1");
  assert.equal(nextProjectDetail.checkpoints.pending.checkpoint_id, "CP1");
  assert.equal(nextProjectDetail.checkpoints.pending.status, "awaiting_review");
  assert.equal(nextProjectDetail.checkpoints.items[0].status, "awaiting_review");
  assert.match(nextProjectDetail.checkpoints.timeline_markdown, /awaiting_review/);
});

test("applyProjectDetailState normalizes stale running checkpoints back to pending when approval is not active", () => {
  let nextProjectDetail = null;

  const applied = applyProjectDetailState({
    detail: {
      project: {
        repo_id: "demo",
        repo_path: "/repo",
        display_name: "Demo",
        slug: "demo",
        branch: "main",
        origin_url: "",
        current_status: "running:parallel",
      },
      loop_state: {
        current_checkpoint_id: "",
        current_checkpoint_lineage_id: "",
        pending_checkpoint_approval: false,
      },
      plan: {
        closeout_status: "not_started",
        steps: [],
      },
      codex_status: {
        model_catalog: [],
      },
      detail_level: "core",
      checkpoints: {
        current_checkpoint_id: "CP1",
        current_checkpoint_lineage_id: "LN1",
        items: [
          {
            checkpoint_id: "CP1",
            lineage_id: "LN1",
            title: "Review work",
            target_block: 2,
            status: "running",
          },
        ],
        pending: {
          checkpoint_id: "CP1",
          lineage_id: "LN1",
          title: "Review work",
          target_block: 2,
          status: "running",
        },
        timeline_markdown: "- CP1 | running | Review work",
      },
    },
    refs: {
      lastAppliedDetailSignatureRef: {
        current: "",
      },
    },
    state: {
      projectDetail: {
        project: {
          repo_id: "demo",
        },
        checkpoints: {
          current_checkpoint_id: "CP1",
          current_checkpoint_lineage_id: "LN1",
          items: [
            {
              checkpoint_id: "CP1",
              lineage_id: "LN1",
              title: "Review work",
              target_block: 2,
              status: "running",
            },
          ],
          pending: {
            checkpoint_id: "CP1",
            lineage_id: "LN1",
            title: "Review work",
            target_block: 2,
            status: "running",
          },
          timeline_markdown: "- CP1 | running | Review work",
        },
        codex_status: {},
      },
      modelCatalog: [],
      activeJob: {
        id: "job-1",
        status: "running",
        command: "run-plan",
      },
      defaultRuntime: {
        model: "gpt-5.4-mini",
        effort: "high",
      },
      planDirty: false,
    },
    setters: {
      transition: (callback) => callback(),
      setProjectDetail: (value) => {
        nextProjectDetail = value;
      },
      setModelCatalog: () => {},
      setShareSettings: () => {},
      setLoadingProjectId: () => {},
      setProjectForm: () => {},
      setPlanDraft: () => {},
      setSelectedStepId: () => {},
      setPlanDirty: () => {},
    },
  });

  assert.equal(applied.project.current_status, "setup_ready");
  assert.equal(nextProjectDetail.checkpoints.current_checkpoint_id, null);
  assert.equal(nextProjectDetail.checkpoints.pending, null);
  assert.equal(nextProjectDetail.checkpoints.items[0].status, "pending");
  assert.match(nextProjectDetail.checkpoints.timeline_markdown, /pending/);
});

test("applyProjectDetailState clears a stale selected step when the refreshed plan is already complete", () => {
  let nextSelectedStepId = "ST1";
  let nextPlanDraft = null;

  const applied = applyProjectDetailState({
    detail: {
      project: {
        repo_id: "demo",
        repo_path: "/repo",
        display_name: "Demo",
        slug: "demo",
        branch: "main",
        origin_url: "",
        current_status: "closed_out",
        last_run_at: "2026-03-27T03:25:31Z",
      },
      runtime: {
        model: "gpt-5.4",
      },
      plan: {
        closeout_status: "completed",
        steps: [
          { step_id: "ST1", status: "completed", title: "Plan" },
          { step_id: "ST2", status: "completed", title: "Ship" },
        ],
      },
      codex_status: {
        model_catalog: [],
      },
    },
    options: {
      preserveSelectedStep: true,
    },
    refs: {
      lastAppliedDetailSignatureRef: {
        current: "",
      },
    },
    state: {
      projectDetail: {
        project: {
          repo_id: "demo",
        },
        codex_status: {},
      },
      modelCatalog: [],
      activeJob: null,
      defaultRuntime: {
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
      setProjectForm: () => {},
      setPlanDraft: (value) => {
        nextPlanDraft = value;
      },
      setSelectedStepId: (value) => {
        nextSelectedStepId = typeof value === "function" ? value(nextSelectedStepId) : value;
      },
      setPlanDirty: () => {},
    },
  });

  assert.equal(applied.project.repo_id, "demo");
  assert.equal(nextSelectedStepId, "");
  assert.deepEqual(nextPlanDraft, {
    closeout_status: "completed",
    steps: [
      { step_id: "ST1", status: "completed", title: "Plan" },
      { step_id: "ST2", status: "completed", title: "Ship" },
    ],
  });
});

test("preserveProjectDetailSupplement keeps loaded sidebar and report sections on core refresh", () => {
  const preserved = preserveProjectDetailSupplement(
    {
      detail_level: "core",
      project: { repo_id: "demo" },
      reports: { latest_failure: { summary: "fresh" } },
      workspace_tree: [],
      checkpoints: { items: [], pending: null, timeline_markdown: "" },
      history: { ui_events: [], blocks: [], passes: [], test_runs: [] },
      config: {},
    },
    {
      detail_level: "core",
      project: { repo_id: "demo" },
      workspace_tree: [{ label: "Repository" }],
      reports: {
        closeout_report_text: "closeout",
        latest_failure: { summary: "older" },
      },
      checkpoints: {
        items: [{ checkpoint_id: "CP1" }],
        pending: { checkpoint_id: "CP1" },
        timeline_markdown: "timeline",
      },
      history: {
        ui_events: [{ event_type: "run-started" }],
        blocks: [{ block_index: 1 }],
        passes: [],
        test_runs: [],
      },
      config: { active_task: "Ship it" },
      loaded_sections: {
        reports: true,
        workspace: true,
        checkpoints: true,
        history: true,
        config: true,
      },
    },
  );

  assert.deepEqual(preserved.workspace_tree, [{ label: "Repository" }]);
  assert.equal(preserved.reports.closeout_report_text, "closeout");
  assert.equal(preserved.reports.latest_failure.summary, "fresh");
  assert.equal(preserved.checkpoints.timeline_markdown, "timeline");
  assert.equal(preserved.history.ui_events.length, 1);
  assert.equal(preserved.config.active_task, "Ship it");
  assert.equal(preserved.loaded_sections.workspace, true);
});

test("preserveProjectDetailSupplement reuses the existing workspace tree when a full refresh returns equivalent nodes", () => {
  const previousWorkspaceTree = [
    {
      label: "repo",
      path: "/repo",
      kind: "dir",
      children: [{ label: "src", path: "/repo/src", kind: "dir" }],
    },
  ];

  const preserved = preserveProjectDetailSupplement(
    {
      detail_level: "full",
      project: { repo_id: "demo" },
      workspace_tree: [
        {
          label: "repo",
          path: "/repo",
          kind: "dir",
          children: [{ label: "src", path: "/repo/src", kind: "dir" }],
        },
      ],
      loaded_sections: { workspace: true },
    },
    {
      detail_level: "full",
      project: { repo_id: "demo" },
      workspace_tree: previousWorkspaceTree,
      loaded_sections: { workspace: true },
    },
  );

  assert.equal(preserved.workspace_tree, previousWorkspaceTree);
});

test("mergeProjectDetailSupplement applies loaded partial sections onto the selected project", () => {
  const merged = mergeProjectDetailSupplement(
    {
      detail_level: "core",
      project: { repo_id: "demo" },
      reports: { latest_failure: { summary: "old" } },
      workspace_tree: [],
      checkpoints: { items: [], pending: null, timeline_markdown: "" },
      history: { ui_events: [], blocks: [], passes: [], test_runs: [] },
      loaded_sections: {},
    },
    {
      reports: {
        closeout_report_text: "closeout",
        latest_failure: {},
      },
      workspace_tree: [{ label: "Repository" }],
      checkpoints: { items: [], pending: null, timeline_markdown: "" },
      loaded_sections: {
        reports: true,
        workspace: true,
        checkpoints: true,
      },
    },
  );

  assert.equal(merged.reports.closeout_report_text, "closeout");
  assert.deepEqual(merged.reports.latest_failure, {});
  assert.deepEqual(merged.workspace_tree, [{ label: "Repository" }]);
  assert.equal(merged.loaded_sections.reports, true);
  assert.equal(merged.loaded_sections.workspace, true);
  assert.equal(merged.loaded_sections.checkpoints, true);
});

test("mergeProjectDetailSupplement keeps the current workspace tree reference when the supplement tree matches", () => {
  const currentWorkspaceTree = [
    {
      label: "repo",
      path: "/repo",
      kind: "dir",
      children: [{ label: "README.md", path: "/repo/README.md", kind: "file" }],
    },
  ];

  const merged = mergeProjectDetailSupplement(
    {
      detail_level: "core",
      project: { repo_id: "demo" },
      workspace_tree: currentWorkspaceTree,
      loaded_sections: { workspace: true },
    },
    {
      workspace_tree: [
        {
          label: "repo",
          path: "/repo",
          kind: "dir",
          children: [{ label: "README.md", path: "/repo/README.md", kind: "file" }],
        },
      ],
      loaded_sections: { workspace: true },
    },
  );

  assert.equal(merged.workspace_tree, currentWorkspaceTree);
});

test("mergeProjectDetailSupplement preserves unchanged workspace tree branches when one branch changes", () => {
  const previousWorkspaceTree = [
    {
      label: "repo",
      path: "/repo",
      kind: "dir",
      children: [
        {
          label: "src",
          path: "/repo/src",
          kind: "dir",
          children: [{ label: "app.js", path: "/repo/src/app.js", kind: "file" }],
        },
        {
          label: "docs",
          path: "/repo/docs",
          kind: "dir",
          children: [{ label: "guide.md", path: "/repo/docs/guide.md", kind: "file" }],
        },
      ],
    },
  ];

  const merged = mergeProjectDetailSupplement(
    {
      detail_level: "core",
      project: { repo_id: "demo" },
      workspace_tree: previousWorkspaceTree,
      loaded_sections: { workspace: true },
    },
    {
      workspace_tree: [
        {
          label: "repo",
          path: "/repo",
          kind: "dir",
          children: [
            {
              label: "src",
              path: "/repo/src",
              kind: "dir",
              children: [{ label: "app.js", path: "/repo/src/app.js", kind: "file" }],
            },
            {
              label: "docs",
              path: "/repo/docs",
              kind: "dir",
              children: [
                { label: "guide.md", path: "/repo/docs/guide.md", kind: "file" },
                { label: "readme.md", path: "/repo/docs/readme.md", kind: "file" },
              ],
            },
          ],
        },
      ],
      loaded_sections: { workspace: true },
    },
  );

  assert.notEqual(merged.workspace_tree, previousWorkspaceTree);
  assert.equal(merged.workspace_tree[0].children[0], previousWorkspaceTree[0].children[0]);
  assert.notEqual(merged.workspace_tree[0].children[1], previousWorkspaceTree[0].children[1]);
  assert.equal(merged.workspace_tree[0].children[1].children[0], previousWorkspaceTree[0].children[1].children[0]);
});
