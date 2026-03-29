import test from "node:test";
import assert from "node:assert/strict";

import { preserveProjectDetailSupplement } from "./projectStore.js";

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
