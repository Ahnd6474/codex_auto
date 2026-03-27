import assert from "node:assert/strict";
import test from "node:test";

import { carryProjectPromptDraft, nextSidebarTab, resolveConfirmation, shouldPreserveProjectPrompt } from "../src/controllerHelpers.js";

test("resolveConfirmation accepts an explicit native confirmation", async () => {
  const confirmed = await resolveConfirmation(async () => true, () => false, "Delete project?");

  assert.equal(confirmed, true);
});

test("resolveConfirmation respects an explicit cancellation", async () => {
  const confirmed = await resolveConfirmation(async () => false, () => true, "Delete project?");

  assert.equal(confirmed, false);
});

test("resolveConfirmation falls back when the native dialog does not return a boolean", async () => {
  const confirmed = await resolveConfirmation(async () => undefined, () => false, "Delete project?");

  assert.equal(confirmed, false);
});

test("resolveConfirmation falls back when the native dialog throws", async () => {
  const confirmed = await resolveConfirmation(
    async () => {
      throw new Error("dialog unavailable");
    },
    () => true,
    "Delete project?",
  );

  assert.equal(confirmed, true);
});

test("shouldPreserveProjectPrompt keeps prompts until closeout completes", () => {
  assert.equal(
    shouldPreserveProjectPrompt({
      project_prompt: "Ship the desktop app.",
      closeout_status: "not_started",
    }),
    true,
  );
  assert.equal(
    shouldPreserveProjectPrompt({
      project_prompt: "Ship the desktop app.",
      closeout_status: "completed",
    }),
    false,
  );
  assert.equal(
    shouldPreserveProjectPrompt({
      project_prompt: "",
      closeout_status: "running",
    }),
    false,
  );
});

test("carryProjectPromptDraft preserves only the prompt for unfinished work", () => {
  assert.deepEqual(
    carryProjectPromptDraft({
      project_prompt: "Ship the desktop app.",
      workflow_mode: "ml",
      closeout_status: "failed",
      steps: [{ step_id: "ST1", status: "completed" }],
    }),
    {
      steps: [],
      project_prompt: "Ship the desktop app.",
      workflow_mode: "ml",
      execution_mode: "parallel",
      closeout_status: "not_started",
    },
  );
  assert.deepEqual(
    carryProjectPromptDraft({
      project_prompt: "Already done.",
      workflow_mode: "standard",
      closeout_status: "completed",
      steps: [{ step_id: "ST1", status: "completed" }],
    }),
    {
      steps: [],
      project_prompt: "",
      workflow_mode: "standard",
      execution_mode: "parallel",
      closeout_status: "not_started",
    },
  );
});

test("nextSidebarTab toggles the active sidebar section off on repeat click", () => {
  assert.equal(nextSidebarTab("projects", "projects"), "");
  assert.equal(nextSidebarTab("", "workspace"), "workspace");
  assert.equal(nextSidebarTab("history", "plans"), "plans");
  assert.equal(nextSidebarTab("plans", ""), "");
});
