import assert from "node:assert/strict";
import test from "node:test";

import { loadInitialDesktopState, refreshVisibleProjectState } from "../src/controller/projectQueries.js";

test("refreshVisibleProjectState loads listing and selected project detail in parallel", async () => {
  const calls = [];
  const bridgeRequest = async (command, payload, workspaceRoot) => {
    calls.push({ command, payload, workspaceRoot });
    if (command === "list-projects") {
      await new Promise((resolve) => setTimeout(resolve, 40));
      return { projects: [{ repo_id: "demo" }] };
    }
    if (command === "load-project") {
      await new Promise((resolve) => setTimeout(resolve, 40));
      return { project: { repo_id: "demo" }, detail_level: "core" };
    }
    throw new Error(`Unexpected command: ${command}`);
  };

  const startedAt = Date.now();
  const result = await refreshVisibleProjectState(bridgeRequest, "/workspace", "demo", { detailLevel: "core" });
  const elapsedMs = Date.now() - startedAt;

  assert.deepEqual(result, {
    listing: { projects: [{ repo_id: "demo" }] },
    detail: { project: { repo_id: "demo" }, detail_level: "core" },
  });
  assert.equal(calls[0].command, "list-projects");
  assert.equal(calls[1].command, "load-project");
  assert.ok(elapsedMs < 70, `expected parallel refresh to finish quickly, took ${elapsedMs}ms`);
});

test("refreshVisibleProjectState skips detail loading when no project is selected", async () => {
  const calls = [];
  const bridgeRequest = async (command) => {
    calls.push(command);
    return { projects: [] };
  };

  const result = await refreshVisibleProjectState(bridgeRequest, "/workspace", "", { detailLevel: "core" });

  assert.deepEqual(result, {
    listing: { projects: [] },
    detail: null,
  });
  assert.deepEqual(calls, ["list-projects"]);
});

test("refreshVisibleProjectState can skip listing when only selected detail needs a live refresh", async () => {
  const calls = [];
  const bridgeRequest = async (command, payload, workspaceRoot) => {
    calls.push({ command, payload, workspaceRoot });
    if (command === "load-project") {
      return { project: { repo_id: "demo" }, detail_level: "full" };
    }
    throw new Error(`Unexpected command: ${command}`);
  };

  const result = await refreshVisibleProjectState(bridgeRequest, "/workspace", "demo", {
    detailLevel: "full",
    refreshListing: false,
  });

  assert.deepEqual(result, {
    listing: null,
    detail: { project: { repo_id: "demo" }, detail_level: "full" },
  });
  assert.deepEqual(calls, [
    {
      command: "load-project",
      payload: {
        repo_id: "demo",
        refresh_codex_status: false,
        detail_level: "full",
      },
      workspaceRoot: "/workspace",
    },
  ]);
});

test("loadInitialDesktopState overlaps bootstrap and job snapshot loading", async () => {
  const bridgeRequest = async (command, _payload, workspaceRoot) => {
    if (command === "bootstrap") {
      await new Promise((resolve) => setTimeout(resolve, 40));
      return { workspace_root: "/workspace" };
    }
    if (command === "list-projects") {
      assert.equal(workspaceRoot, "/workspace");
      return { projects: [] };
    }
    throw new Error(`Unexpected command: ${command}`);
  };

  const originalListBridgeJobs = globalThis.__JAKAL_FLOW_TEST_LIST_BRIDGE_JOBS__;
  globalThis.__JAKAL_FLOW_TEST_LIST_BRIDGE_JOBS__ = async () => {
    await new Promise((resolve) => setTimeout(resolve, 40));
    return [];
  };

  const startedAt = Date.now();
  try {
    const result = await loadInitialDesktopState(bridgeRequest);
    const elapsedMs = Date.now() - startedAt;

    assert.deepEqual(result, {
      bootstrap: { workspace_root: "/workspace" },
      listing: { projects: [] },
      jobSnapshot: {
        jobs: [],
        runningJob: null,
        activeJob: null,
        activeJobId: "",
      },
    });
    assert.ok(elapsedMs < 70, `expected bootstrap and jobs to overlap, took ${elapsedMs}ms`);
  } finally {
    globalThis.__JAKAL_FLOW_TEST_LIST_BRIDGE_JOBS__ = originalListBridgeJobs;
  }
});

test("loadInitialDesktopState keeps queued jobs as the active snapshot when nothing is running", async () => {
  const bridgeRequest = async (command, _payload, workspaceRoot) => {
    if (command === "bootstrap") {
      return { workspace_root: "/workspace" };
    }
    if (command === "list-projects") {
      assert.equal(workspaceRoot, "/workspace");
      return { projects: [] };
    }
    throw new Error(`Unexpected command: ${command}`);
  };

  const originalListBridgeJobs = globalThis.__JAKAL_FLOW_TEST_LIST_BRIDGE_JOBS__;
  globalThis.__JAKAL_FLOW_TEST_LIST_BRIDGE_JOBS__ = async () => [
    { id: "job-queued", status: "queued", command: "run-plan" },
  ];

  try {
    const result = await loadInitialDesktopState(bridgeRequest, "job-queued");

    assert.equal(result.jobSnapshot.activeJob?.id, "job-queued");
    assert.equal(result.jobSnapshot.activeJobId, "job-queued");
    assert.equal(result.jobSnapshot.runningJob, null);
  } finally {
    globalThis.__JAKAL_FLOW_TEST_LIST_BRIDGE_JOBS__ = originalListBridgeJobs;
  }
});
