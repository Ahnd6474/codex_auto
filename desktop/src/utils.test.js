import test from "node:test";
import assert from "node:assert/strict";

import { jobHasNewerActiveReplacement } from "./utils.js";

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
