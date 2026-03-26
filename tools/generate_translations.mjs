import fs from "node:fs";
import path from "node:path";

const ROOT = process.cwd();
const DESKTOP_LOCALE_PATH = path.join(ROOT, "desktop", "src", "locale.js");
const WEBSITE_SITE_PATH = path.join(ROOT, "website", "site.js");
const DESKTOP_OUTPUT_PATH = path.join(ROOT, "desktop", "src", "generated_locale_data.js");
const WEBSITE_OUTPUT_PATH = path.join(ROOT, "website", "generated_translations.js");
const WEBSITE_SHARE_OUTPUT_PATH = path.join(ROOT, "website", "generated_share_translations.js");
const CACHE_PATH = path.join(ROOT, ".tmp_translation_cache.json");
const SEPARATOR = "QZXSEPZXQ";

const DESKTOP_TARGETS = [
  "ko",
  "ja",
  "zh-cn",
  "zh-tw",
  "es",
  "fr",
  "de",
  "it",
  "pt-br",
  "pt-pt",
  "ru",
  "uk",
  "pl",
  "nl",
  "tr",
  "ar",
  "he",
  "hi",
  "bn",
  "th",
  "vi",
  "id",
  "ms",
  "tl",
  "cs",
  "hu",
  "ro",
  "sv",
  "da",
  "fi",
  "no",
  "el",
  "sk",
  "bg",
  "hr",
  "sr",
  "sl",
  "lt",
  "lv",
];

const WEBSITE_TARGETS = [
  "ko",
  "en",
  "ja",
  "zh-CN",
  "zh-TW",
  "es",
  "fr",
  "de",
  "it",
  "pt-BR",
  "pt-PT",
  "ru",
  "uk",
  "pl",
  "nl",
  "tr",
  "ar",
  "he",
  "hi",
  "bn",
  "th",
  "vi",
  "id",
  "ms",
  "tl",
  "cs",
  "hu",
  "ro",
  "sv",
  "da",
  "fi",
  "no",
  "el",
  "sk",
  "bg",
  "hr",
  "sr",
  "sl",
  "lt",
  "lv",
];

const GOOGLE_TARGETS = {
  ko: "ko",
  ja: "ja",
  "zh-cn": "zh-CN",
  "zh-tw": "zh-TW",
  "zh-CN": "zh-CN",
  "zh-TW": "zh-TW",
  es: "es",
  fr: "fr",
  de: "de",
  it: "it",
  "pt-br": "pt-BR",
  "pt-pt": "pt-PT",
  "pt-BR": "pt-BR",
  "pt-PT": "pt-PT",
  ru: "ru",
  uk: "uk",
  pl: "pl",
  nl: "nl",
  tr: "tr",
  ar: "ar",
  he: "he",
  hi: "hi",
  bn: "bn",
  th: "th",
  vi: "vi",
  id: "id",
  ms: "ms",
  tl: "tl",
  cs: "cs",
  hu: "hu",
  ro: "ro",
  sv: "sv",
  da: "da",
  fi: "fi",
  no: "no",
  el: "el",
  sk: "sk",
  bg: "bg",
  hr: "hr",
  sr: "sr",
  sl: "sl",
  lt: "lt",
  lv: "lv",
  en: "en",
};

const SHARE_ENGLISH = {
  page_title: "jakal-flow | Remote Monitor",
  hero_eyebrow: "jakal-flow remote monitor",
  hero_title: "Read-only progress view",
  hero_copy: "This page streams masked progress updates in near real time and never exposes remote controls.",
  poll_waiting: "Waiting",
  read_only: "Read only",
  project_label: "Project",
  project_loading: "Loading...",
  run_status_label: "Run status",
  current_task_label: "Current task",
  latest_test_label: "Latest test",
  recent_logs_label: "Recent logs",
  masked_activity_tail: "Masked activity tail",
  refresh_connecting: "Connecting live stream",
  log_waiting: "Waiting for status...",
  access_label: "Access",
  error_unable_load: "Unable to load share session",
  unnamed_project: "Unnamed project",
  slug_prefix: "Slug: {value}",
  last_updated_prefix: "Last updated: {value}",
  expires_prefix: "Expires: {value}",
  phase_prefix: "Phase: {value}",
  phase_unavailable: "Phase unavailable",
  no_task_reported: "No task reported",
  no_current_task_summary: "No current task summary",
  test_label_default: "test",
  no_test_result_yet: "No test result yet",
  no_test_result_summary: "No test result summary",
  no_recent_logs: "No recent logs available.",
  request_failed_with: "Request failed with {status}",
  live_stream: "Live stream",
  streaming_live_updates: "Streaming live updates",
  live_connection_lost: "Live connection lost.",
  missing_link: "Missing link",
  missing_share_link_data: "This URL does not include the required session and token.",
  missing_share_link_title: "Missing share link data",
  refreshing: "Refreshing",
  polling_every_5s: "Polling every 5s",
  polling: "Polling",
  access_denied: "Access denied",
  unable_keep_live_connection: "Unable to keep live connection",
  live_stream_unavailable: "Live stream unavailable",
  falling_back_to_polling: "{message} Falling back to polling.",
};

function readCache() {
  if (!fs.existsSync(CACHE_PATH)) {
    return {};
  }
  return JSON.parse(fs.readFileSync(CACHE_PATH, "utf8"));
}

function writeCache(cache) {
  fs.writeFileSync(CACHE_PATH, JSON.stringify(cache, null, 2) + "\n", "utf8");
}

function parseDesktopEnglishStrings() {
  const lines = fs.readFileSync(DESKTOP_LOCALE_PATH, "utf8").split(/\r?\n/);
  const start = lines.findIndex((line) => line.includes("  en: {"));
  const end = lines.findIndex((line, index) => index > start && line.includes("  ko: {"));
  return lines
    .slice(start + 1, end)
    .map((line) => line.match(/^\s+"([^"]+)":\s+"((?:[^"\\]|\\.)*)",?$/))
    .filter(Boolean)
    .reduce((result, match) => {
      result[match[1]] = JSON.parse(`"${match[2]}"`);
      return result;
    }, {});
}

function parseWebsiteEnglishStrings() {
  const lines = fs.readFileSync(WEBSITE_SITE_PATH, "utf8").split(/\r?\n/);
  const start = lines.findIndex((line) => line.includes("  en: {"));
  const end = lines.findIndex((line, index) => index > start && line.includes("  zh: {"));
  return lines
    .slice(start + 1, end)
    .map((line) => line.match(/^\s+([a-zA-Z0-9_]+):\s+"((?:[^"\\]|\\.)*)",?$/))
    .filter(Boolean)
    .reduce((result, match) => {
      result[match[1]] = JSON.parse(`"${match[2]}"`);
      return result;
    }, {});
}

function protectTokens(text) {
  const replacements = [];
  let index = 0;
  const protectedText = text
    .replace(/<br\s*\/?>/g, (match) => {
      const token = `PHTOKENBR${index}X`;
      replacements.push([token, match]);
      index += 1;
      return token;
    })
    .replace(/\{(\w+)\}/g, (match) => {
      const token = `PHTOKENVAR${index}X`;
      replacements.push([token, match]);
      index += 1;
      return token;
    });
  return { protectedText, replacements };
}

function restoreTokens(text, replacements) {
  return replacements.reduce((result, [token, original]) => result.replaceAll(token, original), text);
}

async function translateBatch(batch, targetLanguage) {
  const payload = batch.map((item) => item.protectedText).join(`\n${SEPARATOR}\n`);
  const params = new URLSearchParams({
    client: "gtx",
    sl: "en",
    tl: GOOGLE_TARGETS[targetLanguage] || targetLanguage,
    dt: "t",
    q: payload,
  });
  const response = await fetch(`https://translate.googleapis.com/translate_a/single?${params.toString()}`);
  if (!response.ok) {
    throw new Error(`translation request failed: ${response.status}`);
  }
  const data = await response.json();
  const segments = [];
  let current = "";
  for (const item of data[0] || []) {
    const translatedPart = item[0] || "";
    const originalPart = item[1] || "";
    if (originalPart.includes(SEPARATOR)) {
      segments.push(current.trim());
      current = "";
      continue;
    }
    current += translatedPart;
  }
  segments.push(current.trim());
  if (segments.length !== batch.length) {
    throw new Error(`expected ${batch.length} segments but received ${segments.length}`);
  }
  return segments.map((segment, index) => restoreTokens(segment, batch[index].replacements));
}

async function translateEntries(scope, entries, targetLanguage, cache) {
  const result = {};
  const pending = [];
  Object.entries(entries).forEach(([key, value]) => {
    const cacheKey = `${scope}:${targetLanguage}:${key}`;
    if (cache[cacheKey]) {
      result[key] = cache[cacheKey];
      return;
    }
    const protectedValue = protectTokens(value);
    pending.push({ key, value, cacheKey, ...protectedValue });
  });

  while (pending.length) {
    const batch = [];
    let size = 0;
    while (pending.length) {
      const next = pending[0];
      const nextSize = next.protectedText.length + SEPARATOR.length + 2;
      if (batch.length && size + nextSize > 2200) {
        break;
      }
      batch.push(next);
      pending.shift();
      size += nextSize;
    }
    let translated;
    try {
      translated = await translateBatch(batch, targetLanguage);
    } catch (error) {
      if (batch.length === 1) {
        throw error;
      }
      translated = [];
      for (const item of batch) {
        const [value] = await translateBatch([item], targetLanguage);
        translated.push(value);
      }
    }
    translated.forEach((value, index) => {
      const item = batch[index];
      result[item.key] = value;
      cache[item.cacheKey] = value;
    });
    writeCache(cache);
    console.log(`[${scope}] ${targetLanguage}: ${Object.keys(result).length}/${Object.keys(entries).length}`);
  }

  return result;
}

function writeDesktopFile(strings) {
  const content = `export const GENERATED_STRINGS = ${JSON.stringify(strings, null, 2)};\n`;
  fs.writeFileSync(DESKTOP_OUTPUT_PATH, content, "utf8");
}

function writeWebsiteFile(strings) {
  const content = `window.JakalFlowGeneratedTranslations = ${JSON.stringify(strings, null, 2)};\n`;
  fs.writeFileSync(WEBSITE_OUTPUT_PATH, content, "utf8");
}

function writeWebsiteShareFile(strings) {
  const content = `window.JakalFlowGeneratedShareTranslations = ${JSON.stringify(strings, null, 2)};\n`;
  fs.writeFileSync(WEBSITE_SHARE_OUTPUT_PATH, content, "utf8");
}

async function main() {
  const cache = readCache();
  const desktopEnglish = parseDesktopEnglishStrings();
  const websiteEnglish = parseWebsiteEnglishStrings();

  const desktopStrings = {};
  for (const locale of DESKTOP_TARGETS) {
    desktopStrings[locale] = await translateEntries("desktop", desktopEnglish, locale, cache);
  }
  writeDesktopFile(desktopStrings);

  const websiteStrings = {};
  for (const locale of WEBSITE_TARGETS) {
    if (locale === "en") {
      websiteStrings[locale] = websiteEnglish;
      continue;
    }
    websiteStrings[locale] = await translateEntries("website", websiteEnglish, locale, cache);
  }
  writeWebsiteFile(websiteStrings);

  const websiteShareStrings = {};
  for (const locale of WEBSITE_TARGETS) {
    if (locale === "en") {
      websiteShareStrings[locale] = SHARE_ENGLISH;
      continue;
    }
    websiteShareStrings[locale] = await translateEntries("website-share", SHARE_ENGLISH, locale, cache);
  }
  writeWebsiteShareFile(websiteShareStrings);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
