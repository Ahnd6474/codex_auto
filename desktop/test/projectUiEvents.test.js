import assert from "node:assert/strict";
import test from "node:test";

import {
  applyProjectUiEvent,
  projectUiEventActivityLine,
  projectUiEventRecord,
  shouldRefreshProjectDetailForUiEvent,
} from "../src/controller/projectUiEvents.js";

function sampleEvent(eventType, overrides = {}) {
  return {
    event: "project.ui_event",
    payload: {
      repo_id: "repo-1",
      project_dir: "C:/work/repo-1",
      project_status: "running:parallel",
      event: {
        timestamp: "2026-03-30T00:00:00+00:00",
        event_type: eventType,
        message: "Updated project state.",
        details: {},
        ...(overrides.event || {}),
      },
      ...(overrides.payload || {}),
    },
  };
}

test("projectUiEventRecord extracts normalized event data", () => {
  const record = projectUiEventRecord(
    sampleEvent("project-state-synced", {
      event: {
        details: {
          current_task: "Run ST2",
          current_checkpoint_id: "CP2",
          pending_checkpoint_approval: true,
        },
      },
    }),
  );

  assert.equal(record.repoId, "repo-1");
  assert.equal(record.projectStatus, "running:parallel");
  assert.equal(record.details.current_task, "Run ST2");
});

test("projectUiEventActivityLine includes the step id suffix when available", () => {
  const line = projectUiEventActivityLine(
    projectUiEventRecord(
      sampleEvent("step-finished", {
        event: {
          details: {
            step_id: "ST2",
          },
        },
      }),
    ),
  );

  assert.equal(line, "2026-03-30T00:00:00+00:00 | step-finished [ST2] | Updated project state.");
});

test("applyProjectUiEvent patches local detail without clearing existing history", () => {
  const detail = {
    project: {
      repo_id: "repo-1",
      current_status: "running:step",
      last_run_at: "",
    },
    loop_state: {
      current_task: "",
      current_checkpoint_id: "",
      pending_checkpoint_approval: false,
    },
    checkpoints: {
      items: [
        { checkpoint_id: "CP1", status: "approved" },
        { checkpoint_id: "CP2", status: "approved", title: "Review integration" },
      ],
      pending: null,
      timeline_markdown: "",
    },
    activity: ["older line"],
    history: {
      ui_events: [{ event_type: "older" }],
    },
    bottom_panels: {
      execution_log_lines: ["older line"],
      git_status: {
        current_status: "running:step",
        pending_checkpoint_approval: false,
      },
    },
    snapshot: {
      project: {
        current_status: "running:step",
        last_run_at: "",
      },
      loop_state: {
        current_task: "",
        current_checkpoint_id: "",
        pending_checkpoint_approval: false,
      },
    },
  };

  const updated = applyProjectUiEvent(
    detail,
    sampleEvent("project-state-synced", {
      event: {
        details: {
          current_task: "Run ST2",
          current_checkpoint_id: "CP2",
          pending_checkpoint_approval: true,
          last_run_at: "2026-03-30T00:00:01+00:00",
        },
      },
    }),
    {
      activeJob: {
        id: "job-1",
        status: "running",
        command: "run-plan",
      },
    },
  );

  assert.equal(updated.project.current_status, "running:parallel");
  assert.equal(updated.project.last_run_at, "2026-03-30T00:00:01+00:00");
  assert.equal(updated.loop_state.current_task, "Run ST2");
  assert.equal(updated.loop_state.current_checkpoint_id, "CP2");
  assert.equal(updated.loop_state.pending_checkpoint_approval, true);
  assert.equal(updated.checkpoints.pending.checkpoint_id, "CP2");
  assert.equal(updated.checkpoints.items[1].status, "awaiting_review");
  assert.equal(updated.activity[0], "2026-03-30T00:00:00+00:00 | project-state-synced | Updated project state.");
  assert.equal(updated.history.ui_events[0].event_type, "project-state-synced");
  assert.equal(updated.bottom_panels.git_status.pending_checkpoint_approval, true);
});

test("applyProjectUiEvent keeps checkpoint state idle when no visible execution job is active", () => {
  const updated = applyProjectUiEvent(
    {
      project: { repo_id: "repo-1", current_status: "running:step" },
      loop_state: {
        current_task: "Waiting for approval",
        current_checkpoint_id: "CP2",
        pending_checkpoint_approval: true,
      },
      checkpoints: {
        items: [
          { checkpoint_id: "CP1", status: "approved" },
          { checkpoint_id: "CP2", status: "running", title: "Review integration" },
        ],
        pending: { checkpoint_id: "CP2", status: "running", title: "Review integration" },
        timeline_markdown: "",
      },
    },
    sampleEvent("project-state-synced", {
      event: {
        details: {
          current_task: "Waiting for approval",
          current_checkpoint_id: "CP2",
          pending_checkpoint_approval: true,
        },
      },
    }),
  );

  assert.equal(updated.loop_state.current_task, "");
  assert.equal(updated.loop_state.current_checkpoint_id, "");
  assert.equal(updated.loop_state.pending_checkpoint_approval, false);
  assert.equal(updated.checkpoints.current_checkpoint_id, null);
  assert.equal(updated.checkpoints.pending, null);
  assert.equal(updated.checkpoints.items[1].status, "pending");
});

test("applyProjectUiEvent keeps the active checkpoint running while the process is active", () => {
  const updated = applyProjectUiEvent(
    {
      project: { repo_id: "repo-1", current_status: "running:parallel" },
      loop_state: {
        current_task: "Running ST2",
        current_checkpoint_id: "",
        pending_checkpoint_approval: false,
      },
      checkpoints: {
        items: [
          { checkpoint_id: "CP1", status: "approved" },
          { checkpoint_id: "CP2", status: "running", title: "Review integration" },
        ],
        pending: { checkpoint_id: "CP2", status: "running", title: "Review integration" },
        timeline_markdown: "",
      },
    },
    sampleEvent("project-state-synced", {
      event: {
        details: {
          current_task: "Running ST2",
          current_checkpoint_id: "CP2",
          pending_checkpoint_approval: false,
        },
      },
    }),
    {
      activeJob: {
        id: "job-1",
        status: "running",
        command: "run-plan",
      },
    },
  );

  assert.equal(updated.loop_state.pending_checkpoint_approval, false);
  assert.equal(updated.checkpoints.current_checkpoint_id, "CP2");
  assert.equal(updated.checkpoints.pending, null);
  assert.equal(updated.checkpoints.items[1].status, "running");
});

test("applyProjectUiEvent clears the live pending checkpoint when approval finishes", () => {
  const updated = applyProjectUiEvent(
    {
      project: { repo_id: "repo-1", current_status: "running:parallel" },
      loop_state: {
        current_task: "Waiting for approval",
        current_checkpoint_id: "CP2",
        pending_checkpoint_approval: true,
      },
      checkpoints: {
        items: [
          { checkpoint_id: "CP1", status: "approved" },
          { checkpoint_id: "CP2", status: "awaiting_review", title: "Review integration" },
        ],
        pending: { checkpoint_id: "CP2", status: "awaiting_review", title: "Review integration" },
        timeline_markdown: "",
      },
    },
    sampleEvent("checkpoint-approved"),
  );

  assert.equal(updated.checkpoints.pending, null);
  assert.equal(updated.checkpoints.items[1].status, "approved");
});

test("applyProjectUiEvent updates planning progress from planning events", () => {
  const updated = applyProjectUiEvent(
    {
      project: { repo_id: "repo-1" },
      planning_progress: null,
    },
    sampleEvent("planner-agent-started", {
      event: {
        details: {
          flow: "planning",
          stage_key: "planner_a",
          stage_index: 2,
          stage_count: 4,
          status: "running",
          agent_label: "Planner Agent A",
        },
      },
    }),
  );

  assert.equal(updated.planning_progress.current_stage_index, 2);
  assert.equal(updated.planning_progress.current_stage_status, "running");
  assert.equal(updated.planning_progress.stages[1].label, "Planner Agent A");
});

test("applyProjectUiEvent clears planning progress when plan generation stops", () => {
  const updated = applyProjectUiEvent(
    {
      project: { repo_id: "repo-1", current_status: "running:generate-plan" },
      planning_progress: {
        stage_count: 4,
        current_stage_index: 2,
        current_stage_status: "running",
        stages: [
          { key: "context_scan", index: 1, label: "Scan repository context", status: "completed" },
          { key: "planner_a", index: 2, label: "Planner Agent A", status: "running" },
          { key: "planner_b", index: 3, label: "Planner Agent B", status: "pending" },
          { key: "finalize", index: 4, label: "Validate and save plan", status: "pending" },
        ],
      },
    },
    sampleEvent("plan-stopped", {
      payload: {
        project_status: "setup_ready",
      },
      event: {
        details: {
          flow: "planning",
          status: "stopped",
        },
      },
    }),
  );

  assert.equal(updated.project.current_status, "setup_ready");
  assert.equal(updated.planning_progress, null);
});

test("applyProjectUiEvent patches running step state from run events", () => {
  const updated = applyProjectUiEvent(
    {
      project: { repo_id: "repo-1", current_status: "running:parallel" },
      plan: {
        execution_mode: "parallel",
        closeout_status: "not_started",
        steps: [
          { step_id: "ST1", title: "Plan", status: "completed" },
          { step_id: "ST2", title: "Build", status: "pending" },
          { step_id: "ST3", title: "API", status: "pending" },
        ],
      },
      snapshot: {
        plan: {
          execution_mode: "parallel",
          closeout_status: "not_started",
          steps: [
            { step_id: "ST1", title: "Plan", status: "completed" },
            { step_id: "ST2", title: "Build", status: "pending" },
            { step_id: "ST3", title: "API", status: "pending" },
          ],
        },
      },
    },
    sampleEvent("step-started", {
      event: {
        details: {
          step_id: "ST2",
          execution_mode: "parallel",
        },
      },
    }),
    {
      activeJob: {
        id: "job-1",
        status: "running",
        command: "run-plan",
      },
    },
  );

  assert.equal(updated.plan.steps[1].status, "running");
  assert.equal(updated.snapshot.plan.steps[1].status, "running");
});

test("applyProjectUiEvent marks a finished step completed and keeps the live snapshot aligned", () => {
  const updated = applyProjectUiEvent(
    {
      project: { repo_id: "repo-1", current_status: "running:parallel" },
      plan: {
        execution_mode: "parallel",
        closeout_status: "not_started",
        steps: [
          { step_id: "ST1", title: "Plan", status: "completed" },
          { step_id: "ST2", title: "Build", status: "running" },
          { step_id: "ST3", title: "API", status: "pending" },
        ],
      },
      snapshot: {
        plan: {
          execution_mode: "parallel",
          closeout_status: "not_started",
          steps: [
            { step_id: "ST1", title: "Plan", status: "completed" },
            { step_id: "ST2", title: "Build", status: "running" },
            { step_id: "ST3", title: "API", status: "pending" },
          ],
        },
      },
    },
    sampleEvent("step-finished", {
      event: {
        timestamp: "2026-03-30T00:05:00+00:00",
        details: {
          step_id: "ST2",
          status: "completed",
          commit_hash: "abc123",
        },
      },
    }),
    {
      activeJob: {
        id: "job-1",
        status: "running",
        command: "run-plan",
      },
    },
  );

  assert.equal(updated.project.current_status, "running:parallel");
  assert.equal(updated.plan.steps[1].status, "completed");
  assert.equal(updated.plan.steps[1].completed_at, "2026-03-30T00:05:00+00:00");
  assert.equal(updated.plan.steps[1].commit_hash, "abc123");
  assert.equal(updated.snapshot.plan.steps[1].status, "completed");
});

test("shouldRefreshProjectDetailForUiEvent only reloads for structural run updates", () => {
  assert.equal(shouldRefreshProjectDetailForUiEvent(sampleEvent("step-started")), true);
  assert.equal(shouldRefreshProjectDetailForUiEvent(sampleEvent("step-finished")), true);
  assert.equal(
    shouldRefreshProjectDetailForUiEvent(
      sampleEvent("planner-agent-started", {
        event: {
          details: {
            flow: "planning",
            stage_key: "planner_a",
            stage_index: 2,
            stage_count: 4,
          },
        },
      }),
    ),
    false,
  );
});
