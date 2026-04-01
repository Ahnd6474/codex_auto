import test from "node:test";
import assert from "node:assert/strict";

import { reduceProjectDetailState, reduceProjectListingState, reduceSelectedProjectState } from "./projectStateReducer.js";
import { selectProjectLaneJob, selectProjectStateTree } from "./projectStateSelectors.js";

function buildQueuedProjectFixture() {
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
      updated_at_ms: 20,
    },
    {
      id: "job-run",
      status: "queued",
      command: "run-plan",
      repo_id: "repo-1",
      queue_position: 1,
      updated_at_ms: 10,
    },
  ];
  return { detail, projects, jobs };
}

test("project state reducer centralizes selected project execution flags", () => {
  const { detail, jobs } = buildQueuedProjectFixture();

  const selectedState = reduceSelectedProjectState({
    selectedProjectId: "repo-1",
    projectDetail: detail,
    projectForm: { project_dir: "C:/repo" },
    planDraft: detail.plan,
    jobs,
  });

  assert.equal(selectedState.projectJob?.id, "job-run");
  assert.equal(selectedState.activeJob?.id, "job-run");
  assert.equal(selectedState.chatJob?.id, "job-chat");
  assert.equal(selectedState.queuedJobs[0]?.id, "job-run");
  assert.equal(selectedState.busy, true);
  assert.equal(selectedState.canRequestStop, false);
  assert.equal(selectedState.canRequestChatStop, true);
  assert.equal(selectedState.canCancelReservation, true);
  assert.equal(selectedState.hasRunnablePlan, true);
  assert.equal(selectedState.runActionDisabled, true);
  assert.equal(selectedState.canRunPlan, false);
});

test("project state reducer keeps emergency stop available from project status when job snapshots lag behind", () => {
  const detail = {
    project: {
      repo_id: "repo-1",
      repo_path: "C:/repo",
      current_status: "running:run-plan",
    },
    plan: {
      steps: [{ step_id: "ST1", title: "Run", status: "running" }],
      closeout_status: "not_started",
    },
    planning_progress: null,
  };

  const selectedState = reduceSelectedProjectState({
    selectedProjectId: "repo-1",
    projectDetail: detail,
    projectForm: { project_dir: "C:/repo" },
    planDraft: detail.plan,
    jobs: [],
  });

  assert.equal(selectedState.canRequestStop, true);
  assert.equal(selectedState.canRequestChatStop, false);
  assert.equal(selectedState.runActionRunning, true);
  assert.equal(selectedState.runActionDisabled, true);
  assert.equal(selectedState.canRunPlan, false);
});

test("project state reducer does not bind draft project forms to background jobs without a selected project", () => {
  const selectedState = reduceSelectedProjectState({
    selectedProjectId: "",
    projectDetail: null,
    projectForm: {
      project_dir: "C:/draft-repo",
    },
    planDraft: {
      steps: [{ step_id: "ST1", title: "Draft", status: "pending" }],
    },
    jobs: [
      {
        id: "job-run",
        status: "running",
        command: "run-plan",
        project_dir: "C:/draft-repo",
        updated_at_ms: 10,
      },
    ],
  });

  assert.equal(selectedState.projectJob, null);
  assert.equal(selectedState.activeJob, null);
  assert.equal(selectedState.canRequestStop, false);
  assert.equal(selectedState.canRequestChatStop, false);
  assert.equal(selectedState.canRunPlan, true);
});

test("project reducers and selectors preserve the queued status invariant", () => {
  const { detail, projects, jobs } = buildQueuedProjectFixture();
  const detailState = reduceProjectDetailState({ detail, jobs });
  const listingState = reduceProjectListingState({ projects, jobs });
  const stateTree = selectProjectStateTree({
    project: detail.project,
    jobs,
  });

  assert.equal(detailState.detail.project.current_status, "queued:run-plan");
  assert.equal(detailState.detail.snapshot.project.current_status, "queued:run-plan");
  assert.equal(listingState.projects[0].status, "queued:run-plan");
  assert.equal(selectProjectLaneJob(stateTree, "execution")?.id, "job-run");
  assert.equal(selectProjectLaneJob(stateTree, "chat")?.id, "job-chat");
});
