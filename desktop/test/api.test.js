import assert from "node:assert/strict";
import test from "node:test";

import { createBridgeClient } from "../src/api.js";

test("bridgeRequest forwards the bridge command and payload", async () => {
  const calls = [];
  const client = createBridgeClient(async (...args) => {
    calls.push(args);
    return { ok: true };
  });

  const result = await client.bridgeRequest("bootstrap", { repo_id: "demo" }, "C:/workspace");

  assert.deepEqual(result, { ok: true });
  assert.deepEqual(calls, [
    [
      "bridge_request",
      {
        command: "bootstrap",
        payload: { repo_id: "demo" },
        workspaceRoot: "C:/workspace",
      },
    ],
  ]);
});

test("startBridgeJob forwards the job request", async () => {
  const calls = [];
  const client = createBridgeClient(async (...args) => {
    calls.push(args);
    return { id: "job-1" };
  });

  const result = await client.startBridgeJob("run-plan", { repo_id: "demo" }, null);

  assert.deepEqual(result, { id: "job-1" });
  assert.deepEqual(calls, [
    [
      "start_bridge_job",
      {
        command: "run-plan",
        payload: { repo_id: "demo" },
        workspaceRoot: null,
      },
    ],
  ]);
});

test("getBridgeJob forwards the job lookup", async () => {
  const calls = [];
  const client = createBridgeClient(async (...args) => {
    calls.push(args);
    return { status: "running" };
  });

  const result = await client.getBridgeJob("job-42");

  assert.deepEqual(result, { status: "running" });
  assert.deepEqual(calls, [["get_bridge_job", { jobId: "job-42" }]]);
});

test("listBridgeJobs forwards the listing request without payload", async () => {
  const calls = [];
  const client = createBridgeClient(async (...args) => {
    calls.push(args);
    return [];
  });

  const result = await client.listBridgeJobs();

  assert.deepEqual(result, []);
  assert.deepEqual(calls, [["list_bridge_jobs"]]);
});

test("configureBridgeScheduler forwards the scheduler update request", async () => {
  const calls = [];
  const client = createBridgeClient(async (...args) => {
    calls.push(args);
    return { max_concurrent_jobs: 3 };
  });

  const result = await client.configureBridgeScheduler(3, "C:/workspace");

  assert.deepEqual(result, { max_concurrent_jobs: 3 });
  assert.deepEqual(calls, [["configure_bridge_scheduler", { maxConcurrentJobs: 3, workspaceRoot: "C:/workspace" }]]);
});

test("cancelBridgeJob forwards the queued job cancellation request", async () => {
  const calls = [];
  const client = createBridgeClient(async (...args) => {
    calls.push(args);
    return { id: "job-1", status: "cancelled" };
  });

  const result = await client.cancelBridgeJob("job-1");

  assert.deepEqual(result, { id: "job-1", status: "cancelled" });
  assert.deepEqual(calls, [["cancel_bridge_job", { jobId: "job-1" }]]);
});

test("subscribeBridgeEvents forwards bridge events to the provided handler", async () => {
  const handled = [];
  const client = createBridgeClient(
    async () => null,
    async (_eventName, callback) => {
      callback({ payload: { event: "job.updated", payload: { job: { id: "job-1", status: "running" } } } });
      return () => {};
    },
  );

  const unlisten = await client.subscribeBridgeEvents((payload) => {
    handled.push(payload);
  });

  assert.equal(typeof unlisten, "function");
  assert.deepEqual(handled, [
    {
      event: "job.updated",
      payload: {
        job: {
          id: "job-1",
          status: "running",
        },
      },
    },
  ]);
});
