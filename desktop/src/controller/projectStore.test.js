import test from "node:test";
import assert from "node:assert/strict";

import { applyProjectDetailState, preserveProjectDetailSupplement } from "./projectStore.js";

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
  assert.equal(capturedProjectForm.runtime.model_provider, "gemini");
});
