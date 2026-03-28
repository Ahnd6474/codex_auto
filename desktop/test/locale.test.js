import assert from "node:assert/strict";
import test from "node:test";

import { AVAILABLE_LANGUAGE_OPTIONS, detectInitialLanguage, displayStatus, ensureLanguageCatalog, normalizeLanguage, translate } from "../src/locale.js";

test("normalizeLanguage keeps supported values, resolves aliases, and falls back to english", () => {
  assert.equal(normalizeLanguage("ko"), "ko");
  assert.equal(normalizeLanguage("en"), "en");
  assert.equal(normalizeLanguage("fr"), "fr");
  assert.equal(normalizeLanguage("pt-BR"), "pt-br");
  assert.equal(normalizeLanguage("zh-Hant"), "zh-tw");
  assert.equal(normalizeLanguage("fil"), "tl");
  assert.equal(normalizeLanguage(""), "en");
});

test("detectInitialLanguage returns the nearest supported locale", () => {
  assert.equal(detectInitialLanguage("ko-KR"), "ko");
  assert.equal(detectInitialLanguage("ja-JP"), "ja");
  assert.equal(detectInitialLanguage("zh-CN"), "zh-cn");
  assert.equal(detectInitialLanguage("nb-NO"), "no");
  assert.equal(detectInitialLanguage("en-US"), "en");
});

test("translate interpolates parameters and loads non-default locale catalogs on demand", async () => {
  assert.equal(translate("ko", "sidebar.targetBlock", { block: 3 }), "타깃 블록 3");
  assert.equal(translate("fr", "action.run"), "Run");

  await ensureLanguageCatalog("fr");

  assert.equal(translate("fr", "action.run"), "Courir");
});

test("available language options include the extended locale list", () => {
  const values = new Set(AVAILABLE_LANGUAGE_OPTIONS.map((option) => option.value));
  ["ja", "zh-cn", "zh-tw", "pt-br", "pt-pt", "ar", "he", "tl", "lv"].forEach((value) => {
    assert.equal(values.has(value), true);
  });
});

test("displayStatus still localizes existing translations", async () => {
  await ensureLanguageCatalog("fr");

  assert.equal(displayStatus("completed", "ko"), "완료");
  assert.equal(displayStatus("paused_for_review", "en"), "Paused for review");
  assert.equal(displayStatus("integrating", "ko"), "병합 중");
  assert.equal(displayStatus("running:merging", "en"), "Merging");
  assert.equal(displayStatus("awaiting_checkpoint_approval", "en"), "Awaiting checkpoint approval");
  assert.equal(displayStatus("running:generate plan", "ko"), "실행 중: generate plan");
  assert.equal(displayStatus("setup_ready", "fr"), "Configuration prête");
});

test("korean overrides prefer higher-quality copy", () => {
  assert.equal(translate("ko", "reports.closeoutReport"), "마감 보고서");
  assert.equal(translate("ko", "option.generateWordReport"), "Word 보고서 생성");
});
