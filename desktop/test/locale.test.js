import assert from "node:assert/strict";
import test from "node:test";

import { detectInitialLanguage, displayStatus, normalizeLanguage, translate } from "../src/locale.js";

test("normalizeLanguage keeps supported values and falls back to english", () => {
  assert.equal(normalizeLanguage("ko"), "ko");
  assert.equal(normalizeLanguage("en"), "en");
  assert.equal(normalizeLanguage("fr"), "en");
  assert.equal(normalizeLanguage(""), "en");
});

test("detectInitialLanguage prefers korean locales and otherwise returns english", () => {
  assert.equal(detectInitialLanguage("ko-KR"), "ko");
  assert.equal(detectInitialLanguage("ko"), "ko");
  assert.equal(detectInitialLanguage("en-US"), "en");
  assert.equal(detectInitialLanguage("ja-JP"), "en");
});

test("translate interpolates parameters and falls back to english keys", () => {
  assert.equal(translate("ko", "sidebar.targetBlock", { block: 3 }), "대상 블록 3");
  assert.equal(translate("fr", "action.run"), "Run");
});

test("displayStatus localizes known states and humanizes running details", () => {
  assert.equal(displayStatus("completed", "ko"), "완료");
  assert.equal(displayStatus("paused_for_review", "en"), "Paused for review");
  assert.equal(displayStatus("running:generate plan", "ko"), "실행 중: generate plan");
  assert.equal(displayStatus("setup_ready", "en"), "Setup ready");
});
