import test from "node:test";
import assert from "node:assert/strict";

import { shouldImmediatelyRefreshProjectUiEvent } from "./projectRefresh.js";

function projectUiEvent(repoId, eventType) {
  return {
    payload: {
      repo_id: repoId,
      event: {
        event_type: eventType,
        details: {},
      },
    },
  };
}

test("shouldImmediatelyRefreshProjectUiEvent waits for step-started updates", () => {
  assert.equal(
    shouldImmediatelyRefreshProjectUiEvent("repo-1", projectUiEvent("repo-1", "step-started")),
    false,
  );
});

test("shouldImmediatelyRefreshProjectUiEvent waits for batch-started updates", () => {
  assert.equal(
    shouldImmediatelyRefreshProjectUiEvent("repo-1", projectUiEvent("repo-1", "batch-started")),
    false,
  );
});

test("shouldImmediatelyRefreshProjectUiEvent still refreshes immediately for step-finished", () => {
  assert.equal(
    shouldImmediatelyRefreshProjectUiEvent("repo-1", projectUiEvent("repo-1", "step-finished")),
    true,
  );
});
