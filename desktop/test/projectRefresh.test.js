import assert from "node:assert/strict";
import test from "node:test";

import {
  mergeRefreshRepoId,
  projectRefreshDebounceMs,
  shouldForceCodexRefreshForManualRefresh,
  shouldRefreshListingForProjectEvent,
  shouldRefreshSelectedProject,
} from "../src/controller/projectRefresh.js";

test("mergeRefreshRepoId keeps the latest non-empty repo id", () => {
  assert.equal(mergeRefreshRepoId("", "repo-1"), "repo-1");
  assert.equal(mergeRefreshRepoId("repo-1", ""), "repo-1");
  assert.equal(mergeRefreshRepoId("repo-1", "repo-2"), "repo-2");
});

test("projectRefreshDebounceMs uses a slower cadence while a job is running", () => {
  assert.equal(projectRefreshDebounceMs(null), 150);
  assert.equal(projectRefreshDebounceMs({ status: "queued" }), 150);
  assert.equal(projectRefreshDebounceMs({ status: "running" }), 900);
});

test("shouldRefreshSelectedProject only targets the visible project", () => {
  assert.equal(shouldRefreshSelectedProject("repo-1", "repo-1"), true);
  assert.equal(shouldRefreshSelectedProject("repo-1", ""), true);
  assert.equal(shouldRefreshSelectedProject("repo-1", "repo-2"), false);
  assert.equal(shouldRefreshSelectedProject("", "repo-1"), false);
});

test("shouldRefreshListingForProjectEvent skips full listing reloads for the selected project", () => {
  assert.equal(shouldRefreshListingForProjectEvent("repo-1", "repo-1"), false);
  assert.equal(shouldRefreshListingForProjectEvent("repo-1", "repo-2"), true);
  assert.equal(shouldRefreshListingForProjectEvent("repo-1", ""), true);
  assert.equal(shouldRefreshListingForProjectEvent("", "repo-1"), true);
});

test("shouldForceCodexRefreshForManualRefresh only refreshes live model state on config surfaces", () => {
  assert.equal(shouldForceCodexRefreshForManualRefresh("config"), true);
  assert.equal(shouldForceCodexRefreshForManualRefresh("app-settings"), true);
  assert.equal(shouldForceCodexRefreshForManualRefresh("run"), false);
  assert.equal(shouldForceCodexRefreshForManualRefresh("dashboard"), false);
});
