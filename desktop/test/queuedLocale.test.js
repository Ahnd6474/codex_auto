import assert from "node:assert/strict";
import test from "node:test";

import { displayStatus } from "../src/locale.js";

test("displayStatus localizes queued job labels", () => {
  assert.equal(displayStatus("queued:run-plan", "en"), "Queued: Run plan");
  assert.equal(displayStatus("queued", "en"), "Queued");
});
