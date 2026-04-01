const CONSENT_KEY = "jakal_flow_analytics_consent";
const LANGUAGE_KEY = "jakal_flow_language";

const translations = {
  ko: {
    title: "jakal-flow | Traceable Multi-Repo Automation",
    description:
      "jakal-flow는 여러 저장소를 한 번에 다루되 각 저장소의 state, logs, reports, memory를 분리해서 남기는 추적 가능한 자동화 워크플로입니다.",
    nav_product: "제품",
    nav_advantages: "강점",
    nav_workflow: "워크플로",
    nav_release: "릴리즈",
    nav_contact: "문의",
    hero_badge: "CLI + Desktop on the same backend",
    hero_eyebrow: "Traceable Multi-Repo Automation",
    hero_title: "한 저장소 자동화가 아니라,<br>여러 저장소 운영을<br>추적 가능하게.",
    hero_text:
      "jakal-flow는 여러 저장소에서 AI 보조 작업을 반복 실행할 때, 각 프로젝트의 계획, 로그, 리포트, 메모리, 체크포인트, 롤백 상태를 섞지 않고 남기는 운영용 워크플로입니다.",
    hero_docs: "문서 보기",
    hero_contact: "문의하기",
    hero_meta_1: "저장소별 분리",
    hero_meta_2: "롤백 안전 실행",
    hero_meta_3: "리포트와 이력 내장",
    stat_1_label: "보존",
    stat_1_value: "docs, logs, memory, reports, state",
    stat_2_label: "표면",
    stat_2_value: "CLI + React + Tauri desktop",
    stat_3_label: "운영",
    stat_3_value: "status, history, report, logx",
    sidebar_title: "프로젝트",
    panel_label: "현재 실행",
    panel_title: "한 화면에서 실행 상태를 보고,<br>프로젝트별 산출물은 분리합니다.",
    panel_status: "실행 중",
    timeline_input: "입력",
    timeline_breakdown: "계획",
    timeline_execute: "실행",
    timeline_validate: "검증",
    timeline_sync: "클로즈아웃",
    block_1_title: "Regression and rollback guard",
    block_1_text: "실패를 재현하고 테스트를 추가한 뒤 safe revision을 지킵니다.",
    block_2_title: "Checkpoint-aware desktop flow",
    block_2_text: "체크포인트 승인, 백그라운드 작업 큐, 공유 링크 흐름을 함께 다룹니다.",
    block_3_title: "Traceable closeout",
    block_3_text: "마지막 리포트와 시도 이력을 남겨 다음 운영자가 다시 읽을 수 있게 합니다.",
    ops_model: "백엔드",
    ops_model_value: "Python orchestration",
    ops_reasoning: "데스크톱",
    ops_reasoning_value: "React + Tauri",
    ops_validation: "제어",
    ops_validation_value: "체크포인트와 롤백 인지",
    ops_sync: "산출물",
    ops_sync_value: "history, report, logx, share",
    callout_eyebrow: "Why It Stands Out",
    callout_title: "멀티 리포 운영에서 중요한 것들을<br>기본값으로 둡니다.",
    callout_1_title: "Per-repo isolation first",
    callout_1_text: "각 저장소마다 repo, docs, memory, logs, reports, state를 따로 유지합니다.",
    callout_2_title: "Traceability by default",
    callout_2_text: "계획 캐시, 실행 로그, closeout report, contract-wave audit trail이 프로젝트에 붙습니다.",
    callout_3_title: "Rollback-safe orchestration",
    callout_3_text: "safe revision과 복구 흐름이 구현 안에 들어 있어 실패를 운영 이슈로 남기지 않습니다.",
    callout_4_title: "CLI and desktop together",
    callout_4_text: "React + Tauri 셸이 같은 Python backend를 사용해 제품 경로가 둘로 갈라지지 않습니다.",
    workflow_eyebrow: "Workflow",
    workflow_title: "작업을 던지고 끝내는 도구가 아니라,<br>반복 가능한 운영 루프입니다.",
    workflow_1_title: "Register",
    workflow_1_text: "`init-repo`로 저장소를 작업공간에 등록하고 실행 기준을 정합니다.",
    workflow_2_title: "Plan and run",
    workflow_2_text: "`run`과 `resume`으로 블록 단위 실행을 이어가고 체크포인트를 관리합니다.",
    workflow_3_title: "Inspect",
    workflow_3_text: "`status`, `history`, `report`, `logx`로 현재 상태와 남은 설명 책임을 확인합니다.",
    workflow_4_title: "Operate visually",
    workflow_4_text: "데스크톱 셸에서 프로젝트 설정, 런 제어, 체크포인트, 공유 링크를 다룹니다.",
    showcase_eyebrow: "Current Surface",
    showcase_title: "문서만 좋은 프로젝트가 아니라,<br>지금 바로 돌릴 수 있는 표면이 있습니다.",
    showcase_1_title: "Operator commands already exist",
    showcase_1_text: "등록, 재개, 상태 조회, 이력, 리포트, 로그 인덱싱까지 현재 CLI에 연결되어 있습니다.",
    showcase_2_title: "Desktop is not a separate rewrite",
    showcase_2_text: "Tauri shell이 `python -m jakal_flow.ui_bridge`를 호출해 같은 백엔드를 그대로 사용합니다.",
    showcase_3_title: "Checkpoint and sharing flows are real",
    showcase_3_text: "체크포인트 승인, background queue, read-only share link 흐름이 UI와 브리지에 반영돼 있습니다.",
    showcase_4_title: "Shared-contract reporting is built in",
    showcase_4_text: "SPINE, common requirements, lineage manifest, planning metrics 같은 운영 산출물이 프로젝트 아래에 남습니다.",
    release_eyebrow: "Release",
    release_title: "현재 가치는 명확하고,<br>앞으로의 제품화 경로도 자연스럽습니다.",
    release_card_1_label: "지금",
    release_card_1_title: "A real operations tool",
    release_card_1_text: "여러 저장소를 반복적으로 관리해야 하는 팀이 이미 쓸 수 있는 CLI와 데스크톱 셸이 있습니다.",
    release_card_1_cta: "문서 열기",
    release_card_1_docs: "데모 문의",
    release_card_2_label: "Desktop",
    release_card_2_title: "React + Tauri shell",
    release_card_2_text: "프로젝트 설정, 실행 제어, 체크포인트, 공유 링크, 리포트를 같은 운영 표면에서 다룹니다.",
    release_card_3_label: "적합한 팀",
    release_card_3_title: "Teams with recurring repo work",
    release_card_3_text: "단발성 AI 세션보다, 저장소별 책임 추적과 운영 이력이 중요한 팀에 맞춰져 있습니다.",
    contact_eyebrow: "문의",
    contact_title: "도입, 협업, 데모 문의",
    contact_text: "jakal-flow를 내부 운영 도구로 확장하거나 실제 데스크톱 제품 흐름으로 정리하고 싶다면 메일로 연락해 주세요.",
    contact_cta: "메일 보내기",
    footer_cookie: "쿠키 설정",
    consent_title: "분석 안내",
    consent_text: "이 페이지는 방문 통계를 보기 위해 Google Analytics 4를 사용할 수 있습니다.",
    consent_decline: "거절",
    consent_accept: "허용",
  },
  en: {
    title: "jakal-flow | Traceable Multi-Repo Automation",
    description:
      "jakal-flow is a traceable automation workflow that operates across multiple repositories while keeping each project's state, logs, reports, and memory isolated.",
    nav_product: "Product",
    nav_advantages: "Advantages",
    nav_workflow: "Workflow",
    nav_release: "Release",
    nav_contact: "Contact",
    hero_badge: "CLI + Desktop on the same backend",
    hero_eyebrow: "Traceable Multi-Repo Automation",
    hero_title: "Not single-repo automation,<br>but traceable operations<br>across many repositories.",
    hero_text:
      "jakal-flow is built for teams repeating AI-assisted work across multiple repositories without mixing plans, logs, reports, memory, checkpoints, or rollback state between projects.",
    hero_docs: "Read docs",
    hero_contact: "Contact",
    hero_meta_1: "Per-repo isolation",
    hero_meta_2: "Rollback-safe runs",
    hero_meta_3: "Reports and history built in",
    stat_1_label: "Keeps",
    stat_1_value: "docs, logs, memory, reports, state",
    stat_2_label: "Surface",
    stat_2_value: "CLI plus React + Tauri desktop",
    stat_3_label: "Operators",
    stat_3_value: "status, history, report, logx",
    sidebar_title: "Projects",
    panel_label: "Current run",
    panel_title: "See active execution in one place,<br>while artifacts stay isolated per project.",
    panel_status: "Running",
    timeline_input: "Input",
    timeline_breakdown: "Plan",
    timeline_execute: "Execute",
    timeline_validate: "Validate",
    timeline_sync: "Closeout",
    block_1_title: "Regression and rollback guard",
    block_1_text: "Reproduce failures, add tests, and keep the safe revision intact.",
    block_2_title: "Checkpoint-aware desktop flow",
    block_2_text: "Handle checkpoint approval, background queues, and share links in one flow.",
    block_3_title: "Traceable closeout",
    block_3_text: "Keep final reports and attempt history readable for the next operator.",
    ops_model: "Backend",
    ops_model_value: "Python orchestration",
    ops_reasoning: "Desktop",
    ops_reasoning_value: "React + Tauri",
    ops_validation: "Control",
    ops_validation_value: "checkpoint and rollback aware",
    ops_sync: "Artifacts",
    ops_sync_value: "history, report, logx, share",
    callout_eyebrow: "Why It Stands Out",
    callout_title: "The things that matter in multi-repo operations<br>are treated as defaults.",
    callout_1_title: "Per-repo isolation first",
    callout_1_text: "Every managed repository keeps its own repo, docs, memory, logs, reports, and state.",
    callout_2_title: "Traceability by default",
    callout_2_text: "Planning caches, execution logs, closeout reports, and contract-wave audit data stay attached to the project that produced them.",
    callout_3_title: "Rollback-safe orchestration",
    callout_3_text: "Safe revisions and recovery flow are part of the implementation, not an afterthought.",
    callout_4_title: "CLI and desktop together",
    callout_4_text: "The React + Tauri shell uses the same Python backend instead of creating a separate product path.",
    workflow_eyebrow: "Workflow",
    workflow_title: "This is not a fire-and-forget tool,<br>but a repeatable operating loop.",
    workflow_1_title: "Register",
    workflow_1_text: "Use `init-repo` to add repositories to the workspace with explicit runtime defaults.",
    workflow_2_title: "Plan and run",
    workflow_2_text: "Use `run` and `resume` to continue block-based execution and manage checkpoints.",
    workflow_3_title: "Inspect",
    workflow_3_text: "Use `status`, `history`, `report`, and `logx` to inspect state and keep the run explainable.",
    workflow_4_title: "Operate visually",
    workflow_4_text: "Use the desktop shell for project setup, run control, checkpoints, and share links.",
    showcase_eyebrow: "Current Surface",
    showcase_title: "The project is not just well-described.<br>It already exposes a real operating surface.",
    showcase_1_title: "Operator commands already exist",
    showcase_1_text: "Register, resume, status, history, reporting, and log indexing are already wired into the CLI.",
    showcase_2_title: "Desktop is not a separate rewrite",
    showcase_2_text: "The Tauri shell calls `python -m jakal_flow.ui_bridge` and keeps the same backend model intact.",
    showcase_3_title: "Checkpoint and sharing flows are real",
    showcase_3_text: "Checkpoint approval, background queueing, and read-only sharing are reflected in the UI and bridge layer.",
    showcase_4_title: "Shared-contract reporting is built in",
    showcase_4_text: "SPINE, common requirements, lineage manifests, and planning metrics are preserved under each project.",
    release_eyebrow: "Release",
    release_title: "The value is already clear now,<br>and the productization path is natural.",
    release_card_1_label: "Now",
    release_card_1_title: "A real operations tool",
    release_card_1_text: "Teams that repeatedly manage multiple repositories already have a usable CLI and desktop shell here.",
    release_card_1_cta: "Open docs",
    release_card_1_docs: "Request demo",
    release_card_2_label: "Desktop",
    release_card_2_title: "React + Tauri shell",
    release_card_2_text: "Project setup, run control, checkpoints, share links, and reports are handled from the same operations surface.",
    release_card_3_label: "Fit",
    release_card_3_title: "Teams with recurring repo work",
    release_card_3_text: "Best suited for teams that care about per-repo accountability and durable operating history, not just one-off AI sessions.",
    contact_eyebrow: "Contact",
    contact_title: "Adoption, collaboration, demos",
    contact_text: "Reach out if you want to use jakal-flow as an internal operations tool or shape it into a shipped desktop product.",
    contact_cta: "Send email",
    footer_cookie: "Cookie settings",
    consent_title: "Analytics notice",
    consent_text: "This page can use Google Analytics 4 to understand visits and traffic.",
    consent_decline: "Decline",
    consent_accept: "Allow",
  },
};

const allTranslations = translations;

const supportedLanguages = [
  { value: "ko", label: "한국어", translation: "ko" },
  { value: "en", label: "English", translation: "en" },
];

const languageAliases = {
  "en-us": "en",
  "en-gb": "en",
  "ko-kr": "ko",
};

function normalizeLanguage(value) {
  const normalized = String(value || "").trim();
  if (!normalized) {
    return "ko";
  }
  const lower = normalized.toLowerCase();
  const aliased = languageAliases[lower] || normalized;
  const exact = supportedLanguages.find((item) => item.value.toLowerCase() === String(aliased).toLowerCase());
  if (exact) {
    return exact.value;
  }
  const base = lower.split("-")[0];
  const baseAliased = languageAliases[base] || base;
  const matchedBase = supportedLanguages.find((item) => item.value.toLowerCase() === String(baseAliased).toLowerCase());
  return matchedBase ? matchedBase.value : "en";
}

function translationLanguageFor(language) {
  const resolved = normalizeLanguage(language);
  return supportedLanguages.find((item) => item.value === resolved)?.translation || "en";
}

function populateLanguageSelect() {
  const select = document.querySelector("[data-language-select]");
  if (!select) {
    return null;
  }
  select.innerHTML = "";
  supportedLanguages.forEach((language) => {
    const option = document.createElement("option");
    option.value = language.value;
    option.textContent = language.label;
    select.appendChild(option);
  });
  return select;
}

function loadGoogleAnalytics(measurementId) {
  if (!measurementId || window.__codexAutoGaLoaded) {
    return;
  }
  window.__codexAutoGaLoaded = true;

  const script = document.createElement("script");
  script.async = true;
  script.src = `https://www.googletagmanager.com/gtag/js?id=${measurementId}`;
  document.head.appendChild(script);

  window.dataLayer = window.dataLayer || [];
  window.gtag = function gtag() {
    window.dataLayer.push(arguments);
  };
  window.gtag("js", new Date());
  window.gtag("config", measurementId, { anonymize_ip: true });
}

function applyAnalyticsConsent() {
  const config = window.CodexAutoAnalytics || {};
  loadGoogleAnalytics(config.gaMeasurementId);
}

function updateBannerVisibility(banner, visible) {
  banner.hidden = !visible;
}

function applyTranslations(language) {
  const resolved = normalizeLanguage(language);
  const translationLanguage = translationLanguageFor(resolved);
  const messages = allTranslations[translationLanguage] || allTranslations.en;
  document.documentElement.lang = resolved;
  document.title = messages.title;

  const metaDescription = document.getElementById("meta-description");
  if (metaDescription) {
    metaDescription.setAttribute("content", messages.description);
  }

  document.querySelectorAll("[data-i18n]").forEach((node) => {
    const key = node.getAttribute("data-i18n");
    if (key && messages[key]) {
      node.textContent = messages[key];
    }
  });

  document.querySelectorAll("[data-i18n-html]").forEach((node) => {
    const key = node.getAttribute("data-i18n-html");
    if (key && messages[key]) {
      node.innerHTML = messages[key];
    }
  });

  const select = document.querySelector("[data-language-select]");
  if (select) {
    select.value = resolved;
  }
}

function bootstrapLanguage() {
  const select = populateLanguageSelect();
  const stored = localStorage.getItem(LANGUAGE_KEY);
  const detected = normalizeLanguage(stored || window.navigator?.language || "ko");
  applyTranslations(detected);

  if (select) {
    select.value = detected;
    select.addEventListener("change", () => {
      const nextLanguage = normalizeLanguage(select.value);
      localStorage.setItem(LANGUAGE_KEY, nextLanguage);
      applyTranslations(nextLanguage);
    });
  }
}

function bootstrapConsent() {
  const banner = document.querySelector("[data-consent-banner]");
  const acceptButton = document.querySelector("[data-consent-accept]");
  const declineButton = document.querySelector("[data-consent-decline]");
  const openButton = document.querySelector("[data-open-consent]");
  if (!banner || !acceptButton || !declineButton || !openButton) {
    return;
  }

  const stored = localStorage.getItem(CONSENT_KEY);
  if (stored === "accepted") {
    applyAnalyticsConsent();
    updateBannerVisibility(banner, false);
  } else if (stored === "declined") {
    updateBannerVisibility(banner, false);
  } else {
    updateBannerVisibility(banner, true);
  }

  acceptButton.addEventListener("click", () => {
    localStorage.setItem(CONSENT_KEY, "accepted");
    applyAnalyticsConsent();
    updateBannerVisibility(banner, false);
  });

  declineButton.addEventListener("click", () => {
    localStorage.setItem(CONSENT_KEY, "declined");
    updateBannerVisibility(banner, false);
  });

  openButton.addEventListener("click", () => {
    localStorage.removeItem(CONSENT_KEY);
    updateBannerVisibility(banner, true);
  });
}

function bootstrapScrollEffects() {
  const bar = document.createElement("div");
  bar.className = "scroll-progress";
  document.body.prepend(bar);

  function updateProgress() {
    const total = document.documentElement.scrollHeight - window.innerHeight;
    bar.style.width = total > 0 ? `${(window.scrollY / total) * 100}%` : "0%";
  }
  window.addEventListener("scroll", updateProgress, { passive: true });
  updateProgress();

  const reveals = document.querySelectorAll(".reveal");
  if (reveals.length > 0 && "IntersectionObserver" in window) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("visible");
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.08, rootMargin: "0px 0px -40px 0px" });
    reveals.forEach((el) => observer.observe(el));
  } else {
    reveals.forEach((el) => el.classList.add("visible"));
  }

  const navLinks = document.querySelectorAll(".nav a[href^='#']");
  const sectionIds = ["product", "advantages", "workflow", "release", "contact"];
  const sections = sectionIds
    .map((id) => document.getElementById(id))
    .filter(Boolean);

  function updateActiveNav() {
    const scrollY = window.scrollY + 160;
    let current = "";
    sections.forEach((section) => {
      if (section.offsetTop <= scrollY) {
        current = section.id;
      }
    });
    navLinks.forEach((link) => {
      const target = link.getAttribute("href").replace("#", "");
      link.classList.toggle("active", target === current);
    });
  }

  window.addEventListener("scroll", updateActiveNav, { passive: true });
  updateActiveNav();
}

function bootstrapMobileMenu() {
  const toggle = document.querySelector("[data-menu-toggle]");
  const side = document.querySelector(".topbar-side");
  if (!toggle || !side) {
    return;
  }

  toggle.addEventListener("click", () => {
    const isOpen = toggle.getAttribute("aria-expanded") === "true";
    toggle.setAttribute("aria-expanded", String(!isOpen));
    side.classList.toggle("open", !isOpen);
  });

  side.querySelectorAll(".nav a").forEach((link) => {
    link.addEventListener("click", () => {
      toggle.setAttribute("aria-expanded", "false");
      side.classList.remove("open");
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  bootstrapLanguage();
  bootstrapConsent();
  bootstrapScrollEffects();
  bootstrapMobileMenu();
});
