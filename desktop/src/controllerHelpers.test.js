import test from "node:test";
import assert from "node:assert/strict";

import { nextRightSidebarState, planGenerationValidation } from "./controllerHelpers.js";
import { toggleStepSelection } from "./utils.js";

test("planGenerationValidation requires a prepared project", () => {
  assert.equal(
    planGenerationValidation({
      projectDir: "",
      prompt: "Ship the fix",
      plan: { steps: [] },
    }),
    "prepareProjectFirst",
  );
});

test("planGenerationValidation requires a prompt", () => {
  assert.equal(
    planGenerationValidation({
      projectDir: "C:/repo",
      prompt: "   ",
      plan: { steps: [] },
    }),
    "promptRequired",
  );
});

test("planGenerationValidation still allows regenerating after completed steps exist", () => {
  assert.deepEqual(
    planGenerationValidation({
      projectDir: "C:/repo",
      prompt: "Replan from the new prompt",
      plan: {
        steps: [
          { step_id: "ST1", status: "completed" },
          { step_id: "ST2", status: "pending" },
        ],
      },
    }),
    {
      canGenerate: true,
      requiresReplacementConfirmation: true,
    },
  );
});

test("toggleStepSelection clears the current step when the same step is selected again", () => {
  assert.equal(toggleStepSelection("ST2", "ST2"), "");
});

test("toggleStepSelection keeps the new selection for a different step", () => {
  assert.equal(toggleStepSelection("ST2", "ST3"), "ST3");
  assert.equal(toggleStepSelection("ST2", null), "");
});

test("nextRightSidebarState closes the panel when the active right tab is clicked again", () => {
  assert.deepEqual(
    nextRightSidebarState("chat", "chat", false),
    {
      tab: "chat",
      collapsed: true,
    },
  );
});

test("nextRightSidebarState opens the requested tab when the panel is collapsed", () => {
  assert.deepEqual(
    nextRightSidebarState("chat", "chat", true),
    {
      tab: "chat",
      collapsed: false,
    },
  );
});

test("nextRightSidebarState switches tabs without collapsing the panel", () => {
  assert.deepEqual(
    nextRightSidebarState("chat", "files", false),
    {
      tab: "files",
      collapsed: false,
    },
  );
});
