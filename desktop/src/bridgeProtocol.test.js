import test from "node:test";
import assert from "node:assert/strict";

import {
  BRIDGE_COMMANDS,
  BRIDGE_ERROR_PREFIX,
  bridgeErrorMessage,
  isBridgeMutationCommand,
  parseBridgeError,
} from "./bridgeProtocol.js";

test("contract-wave bridge commands are marked as mutations", () => {
  assert.equal(isBridgeMutationCommand(BRIDGE_COMMANDS.RESOLVE_COMMON_REQUIREMENT), true);
  assert.equal(isBridgeMutationCommand(BRIDGE_COMMANDS.REOPEN_COMMON_REQUIREMENT), true);
  assert.equal(isBridgeMutationCommand(BRIDGE_COMMANDS.RECORD_SPINE_CHECKPOINT), true);
  assert.equal(isBridgeMutationCommand(BRIDGE_COMMANDS.UPDATE_COMMON_REQUIREMENT), true);
  assert.equal(isBridgeMutationCommand(BRIDGE_COMMANDS.DELETE_COMMON_REQUIREMENT), true);
  assert.equal(isBridgeMutationCommand(BRIDGE_COMMANDS.UPDATE_SPINE_CHECKPOINT), true);
  assert.equal(isBridgeMutationCommand(BRIDGE_COMMANDS.DELETE_SPINE_CHECKPOINT), true);
});

test("parseBridgeError reads structured error objects from rust bridge payload", () => {
  const payload = parseBridgeError({
    reason_code: "duplicate_job",
    reasonCode: "ignored",
    message: "Another background task is already active for this project.",
    type: "RuntimeError",
    command: "run-plan",
    method: "start_job",
    request_id: "req-1",
    recoverable: false,
    details: { project_id: "demo" },
  });
  assert.equal(payload.message, "Another background task is already active for this project.");
  assert.equal(payload.reason_code, "duplicate_job");
  assert.equal(payload.type, "RuntimeError");
  assert.equal(payload.command, "run-plan");
  assert.equal(payload.method, "start_job");
  assert.equal(payload.request_id, "req-1");
  assert.equal(payload.recoverable, false);
  assert.deepEqual(payload.details, { project_id: "demo" });
});

test("parseBridgeError reads prefixed JSON string from tauri-bridge transport", () => {
  const payload = parseBridgeError(
    `${BRIDGE_ERROR_PREFIX}${JSON.stringify({
      message: "Unknown command.",
      reason_code: "unsupported_command",
      type: "RuntimeError",
    })}`,
  );
  assert.equal(payload.message, "Unknown command.");
  assert.equal(payload.reason_code, "unsupported_command");
  assert.equal(payload.type, "RuntimeError");
});

test("parseBridgeError reads fallback message from nested error field", () => {
  const payload = parseBridgeError({ error: "nested transport failure" });
  assert.equal(payload.message, "nested transport failure");
});

test("bridgeErrorMessage returns safe fallback for unparseable payloads", () => {
  assert.equal(bridgeErrorMessage(null, "fallback"), "fallback");
  assert.equal(bridgeErrorMessage(42, "fallback"), "42");
});

test("parseBridgeError reads plain numeric payloads as message text", () => {
  const payload = parseBridgeError(500);
  assert.equal(payload.message, "500");
  assert.equal(payload.reason_code, "");
  assert.equal(payload.type, "");
  assert.equal(payload.recoverable, null);
});

test("parseBridgeError ignores malformed BRIDGE_ERROR_JSON payloads and falls back", () => {
  const payload = parseBridgeError(`${BRIDGE_ERROR_PREFIX}not-a-json-object`);
  assert.equal(payload.message, "not-a-json-object");
  assert.equal(payload.reason_code, "");
});
