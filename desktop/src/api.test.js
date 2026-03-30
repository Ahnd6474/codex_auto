import test from "node:test";
import assert from "node:assert/strict";

import { BRIDGE_ERROR_PREFIX } from "./bridgeProtocol.js";
import { BridgeApiError, createBridgeClient } from "./api.js";

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
  const error = await assert.rejects(
    () => client.startBridgeJob("run-plan"),
    BridgeApiError,
  );

  assert.equal(error.reasonCode, "unsupported_method");
  assert.equal(error.errorType, "ValueError");
  assert.equal(error.command, "run-plan");
  assert.equal(error.method, "start_bridge_job");
  assert.equal(error.requestId, "req-1");
  assert.equal(error.recoverable, true);
  assert.equal(error.message, "Bridge request could not be routed.");
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
  const error = await assert.rejects(
    () => client.startBridgeJob("send-chat-message"),
    BridgeApiError,
  );

  assert.equal(error.reasonCode, "duplicate_job");
  assert.equal(error.errorType, "RuntimeError");
  assert.equal(error.command, "send-chat-message");
  assert.equal(error.method, "start_bridge_job");
  assert.equal(error.requestId, "req-2");
  assert.equal(error.recoverable, false);
});
