import test from "node:test";
import assert from "node:assert/strict";

import { buildProjectStateTree, projectStateIdentity } from "./projectStateTree.js";

test("projectStateIdentity prefers explicit project detail over form fallbacks", () => {
  const identity = projectStateIdentity({
    selectedProjectId: "repo-1",
    projectDetail: {
      project: {
        repo_id: "repo-1",
        repo_path: "C:/repo",
        current_status: "plan_ready",
        last_run_at: "2026-04-01T09:00:00Z",
      },
    },
    projectForm: {
      project_dir: "C:/fallback",
    },
  });

  assert.deepEqual(identity, {
    repo_id: "repo-1",
    project_dir: "C:/repo",
    current_status: "plan_ready",
    last_run_at: "2026-04-01T09:00:00Z",
  });
});

test("buildProjectStateTree branches execution, detail, listing, and ui from one root", () => {
  const detail = {
    project: {
      repo_id: "repo-1",
      repo_path: "C:/repo",
      current_status: "plan_ready",
    },
    plan: {
      steps: [{ step_id: "ST1", title: "Plan", status: "pending" }],
      closeout_status: "not_started",
    },
    stats: {
      total_steps: 1,
      completed_steps: 0,
      failed_steps: 0,
      running_steps: 0,
      remaining_steps: 1,
    },
    progress: {},
    loop_state: {
      current_task: "",
      current_checkpoint_id: "",
      current_checkpoint_lineage_id: "",
      pending_checkpoint_approval: false,
    },
    checkpoints: {
      items: [],
      pending: null,
      timeline_markdown: "",
    },
    snapshot: {
      project: {
        current_status: "plan_ready",
      },
      loop_state: {
        current_task: "",
        current_checkpoint_id: "",
        current_checkpoint_lineage_id: "",
        pending_checkpoint_approval: false,
      },
      plan: {
        steps: [{ step_id: "ST1", title: "Plan", status: "pending" }],
        closeout_status: "not_started",
      },
    },
    bottom_panels: {
      git_status: {
        current_status: "plan_ready",
      },
    },
  };
  const projects = [
    {
      repo_id: "repo-1",
      repo_path: "C:/repo",
      status: "plan_ready",
      stats: {
        total_steps: 1,
        completed_steps: 0,
        failed_steps: 0,
        running_steps: 0,
        remaining_steps: 1,
      },
      closeout_status: "not_started",
    },
  ];
  const jobs = [
    {
      id: "job-chat",
      status: "running",
      command: "send-chat-message",
      chat_mode: "conversation",
      repo_id: "repo-1",
      updated_at_ms: 30,
    },
    {
      id: "job-run",
      status: "queued",
      command: "run-plan",
      repo_id: "repo-1",
      queue_position: 2,
      updated_at_ms: 20,
    },
    {
      id: "job-other",
      status: "queued",
      command: "run-plan",
      repo_id: "repo-2",
      queue_position: 1,
      updated_at_ms: 10,
    },
  ];

  const tree = buildProjectStateTree({
    selectedProjectId: "repo-1",
    projectDetail: detail,
    projectForm: {
      project_dir: "C:/fallback",
    },
    projects,
    jobs,
  });

  assert.equal(tree.execution.selectedJob?.id, "job-run");
  assert.equal(tree.execution.activeJob?.id, "job-run");
  assert.equal(tree.execution.chatJob?.id, "job-chat");
  assert.deepEqual(tree.execution.queuedJobs.map((job) => job.id), ["job-other", "job-run"]);
  assert.equal(tree.ui.busy, true);
  assert.equal(tree.ui.canRequestStop, false);
  assert.equal(tree.ui.canRequestChatStop, true);
  assert.equal(tree.ui.canCancelReservation, true);
  assert.equal(tree.detail.normalized.project.current_status, "queued:run-plan");
  assert.equal(tree.detail.normalized.snapshot.project.current_status, "queued:run-plan");
  assert.equal(tree.listing.normalized[0].status, "queued:run-plan");
  assert.equal(tree.listing.workspaceStats.project_count, 1);
});

test("projectStateIdentity ignores draft form paths when no project is selected", () => {
  const identity = projectStateIdentity({
    selectedProjectId: "",
    projectDetail: null,
    projectForm: {
      project_dir: "C:/draft-repo",
    },
  });

  assert.deepEqual(identity, {
    repo_id: "",
    project_dir: "",
    current_status: "",
    last_run_at: "",
  });
});
