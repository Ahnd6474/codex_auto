import test from "node:test";
import assert from "node:assert/strict";

import { planGenerationValidation } from "./controllerHelpers.js";

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
