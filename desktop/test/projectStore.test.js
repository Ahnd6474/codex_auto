import assert from "node:assert/strict";
import test from "node:test";

import { applyProjectDetailListingState, applyProjectDetailState } from "../src/controller/projectStore.js";

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

test("applyProjectDetailState keeps persisted project runtime instead of reapplying app defaults", () => {
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

  assert.equal(applied, true);
  assert.equal(nextProjectDetail.project.repo_id, "demo");
  assert.deepEqual(nextModelCatalog, []);
  assert.deepEqual(nextShareSettings, {
    bind_host: "0.0.0.0",
  });
  assert.equal(nextLoadingProjectId, "");
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

  assert.equal(applied, true);
  assert.equal(nextSelectedStepId, "");
  assert.deepEqual(nextPlanDraft, {
    closeout_status: "completed",
    steps: [
      { step_id: "ST1", status: "completed", title: "Plan" },
      { step_id: "ST2", status: "completed", title: "Ship" },
    ],
  });
});
