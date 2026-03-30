import test from "node:test";
import assert from "node:assert/strict";

import { BRIDGE_ERROR_PREFIX } from "./bridgeProtocol.js";
import { createBridgeClient } from "./api.js";

test("createBridgeClient converts structured transport errors into BridgeApiError", async () => {
  const invoke = async () => {
    const payload = {
      message: "Bridge request could not be routed.",
      reason_code: "unsupported_method",
      command: "run-plan",
      method: "start_bridge_job",
      request_id: "req-1",
      type: "ValueError",
      recoverable: true,
    };
    throw new Error(`${BRIDGE_ERROR_PREFIX}${JSON.stringify(payload)}`);
  };
  const client = createBridgeClient(invoke, async () => null);
  await assert.rejects(
    () => client.startBridgeJob("run-plan"),
    (error) => {
      assert.equal(error.reasonCode, "unsupported_method");
      assert.equal(error.errorType, "ValueError");
      assert.equal(error.command, "run-plan");
      assert.equal(error.method, "start_bridge_job");
      assert.equal(error.requestId, "req-1");
      assert.equal(error.recoverable, true);
      assert.equal(error.message, "Bridge request could not be routed.");
      return true;
    },
  );
});

test("createBridgeClient keeps existing reason codes from plain structured objects", async () => {
  const invoke = async () => {
    throw {
      reason_code: "duplicate_job",
      message: "Duplicate run is already active.",
      command: "send-chat-message",
      method: "start_bridge_job",
      request_id: "req-2",
      type: "RuntimeError",
      recoverable: false,
    };
  };
  const client = createBridgeClient(invoke, async () => null);
  await assert.rejects(
    () => client.startBridgeJob("send-chat-message"),
    (error) => {
      assert.equal(error.reasonCode, "duplicate_job");
      assert.equal(error.errorType, "RuntimeError");
      assert.equal(error.command, "send-chat-message");
      assert.equal(error.method, "start_bridge_job");
      assert.equal(error.requestId, "req-2");
      assert.equal(error.recoverable, false);
      return true;
    },
  );
});

test("listBridgeJobs sends no invoke payload when parameters are unnecessary", async () => {
  const calls = [];
  const invoke = async (...args) => {
    calls.push(args);
    return [];
  };
  const client = createBridgeClient(invoke, async () => null);

  await client.listBridgeJobs();

  assert.equal(calls.length, 1);
  assert.equal(calls[0].length, 1);
  assert.equal(calls[0][0], "list_bridge_jobs");
});

test("createBridgeClient reports structured bridge errors with logger context", async () => {
  const logs = [];
  const logger = {
    error: (...args) => logs.push(args),
  };
  const invoke = async () => {
    throw {
      reason_code: "bridge_unavailable",
      message: "Backend unavailable.",
      command: "run-plan",
      method: "start_bridge_job",
      request_id: "req-3",
      type: "RuntimeError",
      recoverable: false,
    };
  };
  const client = createBridgeClient(invoke, async () => null, { logger });

  await assert.rejects(
    () => client.startBridgeJob("run-plan"),
    (error) => {
      assert.equal(error.reasonCode, "bridge_unavailable");
      assert.equal(error.command, "run-plan");
      assert.equal(error.method, "start_bridge_job");
      return true;
    },
  );

  assert.equal(logs.length, 1);
  assert.equal(logs[0][0], "[jakal-flow bridge]");
  assert.equal(logs[0][1], "invoke_failed");
  assert.equal(logs[0][2].method, "start_bridge_job");
});
