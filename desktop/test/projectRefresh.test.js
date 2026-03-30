import assert from "node:assert/strict";
import test from "node:test";

import {
  mergeRefreshRepoId,
  projectRefreshDebounceMs,
  shouldImmediatelyRefreshProjectEvent,
  shouldImmediatelyRefreshProjectUiEvent,
  shouldForceCodexRefreshForManualRefresh,
  shouldRefreshListingForManualRefresh,
  shouldRefreshListingForProjectEvent,
  shouldRefreshSelectedProject,
} from "../src/controller/projectRefresh.js";

test("mergeRefreshRepoId keeps the latest non-empty repo id", () => {
  assert.equal(mergeRefreshRepoId("", "repo-1"), "repo-1");
  assert.equal(mergeRefreshRepoId("repo-1", ""), "repo-1");
  assert.equal(mergeRefreshRepoId("repo-1", "repo-2"), "repo-2");
});

test("projectRefreshDebounceMs uses shorter defaults and bypasses debounce for immediate refreshes", () => {
  assert.equal(projectRefreshDebounceMs(null), 120);
  assert.equal(projectRefreshDebounceMs({ status: "queued" }), 120);
  assert.equal(projectRefreshDebounceMs({ status: "running" }), 250);
  assert.equal(projectRefreshDebounceMs({ status: "running" }, { immediate: true }), 0);
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

test("shouldRefreshListingForManualRefresh only reloads the full listing when no project is selected", () => {
  assert.equal(shouldRefreshListingForManualRefresh("repo-1"), false);
  assert.equal(shouldRefreshListingForManualRefresh(""), true);
  assert.equal(shouldRefreshListingForManualRefresh("   "), true);
});

test("shouldForceCodexRefreshForManualRefresh only refreshes live model state on config surfaces", () => {
  assert.equal(shouldForceCodexRefreshForManualRefresh("config"), true);
  assert.equal(shouldForceCodexRefreshForManualRefresh("app-settings"), true);
  assert.equal(shouldForceCodexRefreshForManualRefresh("run"), false);
  assert.equal(shouldForceCodexRefreshForManualRefresh("dashboard"), false);
});

test("shouldImmediatelyRefreshProjectEvent prioritizes visible status transitions", () => {
  assert.equal(
    shouldImmediatelyRefreshProjectEvent("repo-1", { repo_id: "repo-1", current_status: "running:block:2" }),
    true,
  );
  assert.equal(
    shouldImmediatelyRefreshProjectEvent("repo-1", { repo_id: "repo-1", current_status: "failed" }),
    true,
  );
  assert.equal(
    shouldImmediatelyRefreshProjectEvent("repo-1", { repo_id: "repo-2", current_status: "running:block:2" }),
    false,
  );
  assert.equal(
    shouldImmediatelyRefreshProjectEvent("repo-1", { repo_id: "repo-1", current_status: "plan_ready" }),
    false,
  );
});

test("shouldImmediatelyRefreshProjectUiEvent only fast-tracks visible structural run events", () => {
  assert.equal(
    shouldImmediatelyRefreshProjectUiEvent("repo-1", {
      payload: {
        repo_id: "repo-1",
        event: {
          event_type: "step-finished",
          details: {},
        },
      },
    }),
    true,
  );
  assert.equal(
    shouldImmediatelyRefreshProjectUiEvent("repo-1", {
      payload: {
        repo_id: "repo-1",
        event: {
          event_type: "step-finished",
          details: { flow: "planning" },
        },
      },
    }),
    false,
  );
  assert.equal(
    shouldImmediatelyRefreshProjectUiEvent("repo-1", {
      payload: {
        repo_id: "repo-2",
        event: {
          event_type: "step-finished",
          details: {},
        },
      },
    }),
    false,
  );
});
