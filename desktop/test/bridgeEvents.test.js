import assert from "node:assert/strict";
import test from "node:test";

import { bridgeEventProject, isProjectUiEvent } from "../src/controller/bridgeEvents.js";

test("bridgeEventProject reads nested project payloads", () => {
  const project = bridgeEventProject({
    event: "project.changed",
    payload: {
      project: {
        repo_id: "repo-1",
        project_dir: "C:/work/repo-1",
        status: "running:generate-plan",
      },
    },
  });

  assert.deepEqual(project, {
    repo_id: "repo-1",
    project_dir: "C:/work/repo-1",
    status: "running:generate-plan",
  });
});

test("bridgeEventProject falls back to top-level project fields for UI events", () => {
  const eventPayload = {
    event: "project.ui_event",
    payload: {
      repo_id: "repo-2",
      project_dir: "C:/work/repo-2",
      project_status: "running:generate-plan",
      event: {
        event_type: "planner-agent-started",
      },
    },
  };

  assert.equal(isProjectUiEvent(eventPayload), true);
  assert.deepEqual(bridgeEventProject(eventPayload), {
    repo_id: "repo-2",
    project_dir: "C:/work/repo-2",
    status: "running:generate-plan",
  });
});
