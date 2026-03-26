const CONSENT_KEY = "jakal_flow_analytics_consent";
const LANGUAGE_KEY = "jakal_flow_language";

const translations = {
  ko: {
    title: "jakal-flow | AI Repo Operations",
    description: "jakal-flow는 여러 저장소를 안전하게 관리하고, Codex가 작업을 쪼개고 실행하고 검증하도록 돕는 데스크톱 자동화 앱입니다.",
    nav_product: "제품",
    nav_workflow: "워크플로우",
    nav_release: "릴리즈",
    nav_contact: "문의",
    hero_badge: "데스크톱 앱 준비 중",
    hero_eyebrow: "AI Repo Operations",
    hero_title: "계획부터 검증까지,<br>저장소 개선을<br>실행 가능한 흐름으로.",
    hero_text: "jakal-flow는 여러 저장소를 하나의 운영 화면에서 다루며, Codex가 일을 쪼개고, 블록 단위로 실행하고, 테스트와 롤백까지 관리하도록 설계된 자동화 앱입니다.",
    hero_docs: "문서 보기",
    hero_contact: "연락하기",
    hero_meta_1: "멀티 저장소",
    hero_meta_2: "엄격한 검증",
    hero_meta_3: "Codex 작업 배분",
    sidebar_title: "저장소",
    panel_label: "타임라인",
    panel_title: "지금 어디까지 진행됐는지,<br>한 번에 보입니다.",
    panel_status: "실행 중",
    timeline_input: "입력",
    timeline_breakdown: "배분",
    timeline_execute: "실행",
    timeline_validate: "검증",
    timeline_sync: "동기화",
    block_1_title: "테스트 안정화",
    block_1_text: "실패 재현, 회귀 테스트 추가, safe revision 유지",
    block_2_title: "GUI 단순화",
    block_2_text: "실행 흐름을 줄이고 진행 정보 가시성 강화",
    block_3_title: "문서 반영",
    block_3_text: "검증된 동작만 README와 릴리즈 페이지에 반영",
    ops_model: "모델",
    ops_reasoning: "추론 강도",
    ops_validation: "검증",
    ops_validation_value: "매 pass 뒤 테스트",
    ops_sync: "동기화",
    ops_sync_value: "블록 완료 후 push",
    callout_eyebrow: "포지셔닝",
    callout_title: "자동화 툴이 아니라,<br>릴리즈 가능한 운영 레이어.",
    callout_1_title: "계획",
    callout_1_text: "장기 프롬프트와 저장소 문맥을 바탕으로 작업을 세분화합니다.",
    callout_2_title: "실행",
    callout_2_text: "Codex가 블록 단위로 구현을 진행하고 진행 상황을 남깁니다.",
    callout_3_title: "검증",
    callout_3_text: "매 pass 뒤 테스트하고 실패 시 즉시 rollback 합니다.",
    callout_4_title: "기록",
    callout_4_text: "docs, logs, memory, state를 남겨 이후 릴리즈 설명이 가능합니다.",
    workflow_eyebrow: "워크플로우",
    workflow_title: "사람은 방향을 주고,<br>Codex는 블록으로 움직입니다.",
    workflow_1_title: "입력",
    workflow_1_text: "장기 프롬프트 또는 개선할 저장소를 입력으로 받습니다.",
    workflow_2_title: "Codex 작업 분해",
    workflow_2_text: "Codex가 실제 구현 가능한 블록 목록과 우선순위를 제안합니다.",
    workflow_3_title: "실행 루프",
    workflow_3_text: "블록이 끝날 때까지 구현, 테스트, 기록을 반복합니다.",
    workflow_4_title: "체크포인트",
    workflow_4_text: "승인 경계와 GitHub 동기화를 통해 릴리즈 흐름을 유지합니다.",
    showcase_eyebrow: "차별점",
    showcase_title: "제품처럼 보이고,<br>운영 도구처럼 작동합니다.",
    showcase_1_title: "멀티 저장소 구조",
    showcase_1_text: "repo, docs, memory, logs, reports, state를 저장소별로 분리해 섞이지 않게 관리합니다.",
    showcase_2_title: "엄격한 검증",
    showcase_2_text: "테스트 실패 시 safe revision으로 바로 되돌아갑니다.",
    showcase_3_title: "진행 타임라인",
    showcase_3_text: "현재 블록, 남은 흐름, Codex 상태를 직관적으로 보여줍니다.",
    showcase_4_title: "앱 확장 전제",
    showcase_4_text: "데스크톱 GUI에서 시작해 릴리즈 가능한 제품 경험으로 확장하기 쉽습니다.",
    release_eyebrow: "릴리즈",
    release_title: "앱 릴리즈 페이지에 필요한 정보도<br>지금부터 정리합니다.",
    release_card_1_label: "버전",
    release_card_1_title: "알파 프리뷰",
    release_card_1_text: "현재는 워크스페이스와 실행 흐름을 다듬는 단계이며, 이후 데스크톱 앱 패키징을 목표로 합니다.",
    release_card_1_cta: "알파 문의",
    release_card_1_docs: "문서 읽기",
    release_card_2_label: "플랫폼",
    release_card_2_title: "Windows 우선 데스크톱",
    release_card_2_text: "React + Tauri 데스크톱 앱으로 실제 운영 화면과 배포 경험을 함께 다듬고 있습니다.",
    release_card_3_label: "대상",
    release_card_3_title: "반복 개선이 필요한 개발 팀",
    release_card_3_text: "한두 개가 아니라 여러 저장소를 안정적으로 돌려야 하는 팀에 맞춘 구조입니다.",
    contact_eyebrow: "문의",
    contact_title: "도입 문의, 협업, 제품화 논의",
    contact_text: "jakal-flow를 내부 자동화 도구나 배포 가능한 앱으로 확장하려면 아래 메일로 연락할 수 있습니다.",
    contact_cta: "메일 보내기",
    footer_cookie: "쿠키 설정",
    consent_title: "분석 도구 사용 안내",
    consent_text: "이 페이지는 방문 통계 확인을 위해 Google Analytics 4를 사용할 수 있습니다.",
    consent_decline: "거부",
    consent_accept: "허용",
  },
  en: {
    title: "jakal-flow | AI Repo Operations",
    description: "jakal-flow is a desktop automation app that manages multiple repositories safely and lets Codex break down, execute, and validate work.",
    nav_product: "Product",
    nav_workflow: "Workflow",
    nav_release: "Release",
    nav_contact: "Contact",
    hero_badge: "Desktop app in progress",
    hero_eyebrow: "AI Repo Operations",
    hero_title: "From planning to validation,<br>turn repo improvement<br>into an executable flow.",
    hero_text: "jakal-flow operates multiple repositories from one surface and is designed so Codex can break work into blocks, execute them, and manage tests and rollbacks.",
    hero_docs: "Docs",
    hero_contact: "Contact",
    hero_meta_1: "Multi-repo",
    hero_meta_2: "Strict validation",
    hero_meta_3: "Codex-planned blocks",
    sidebar_title: "Repositories",
    panel_label: "Timeline",
    panel_title: "See progress instantly,<br>without digging around.",
    panel_status: "Running",
    timeline_input: "Input",
    timeline_breakdown: "Breakdown",
    timeline_execute: "Execute",
    timeline_validate: "Validate",
    timeline_sync: "Sync",
    block_1_title: "Test stabilization",
    block_1_text: "Reproduce failures, add regression coverage, keep the safe revision",
    block_2_title: "GUI simplification",
    block_2_text: "Reduce friction in the run flow and improve progress visibility",
    block_3_title: "Documentation update",
    block_3_text: "Reflect only verified behavior in README and release pages",
    ops_model: "Model",
    ops_reasoning: "Reasoning",
    ops_validation: "Validation",
    ops_validation_value: "test after every pass",
    ops_sync: "Sync",
    ops_sync_value: "push after block",
    callout_eyebrow: "Positioning",
    callout_title: "Not just an automation tool,<br>but an operational layer ready for release.",
    callout_1_title: "Plan",
    callout_1_text: "Break work down from the long-term prompt and repository context.",
    callout_2_title: "Execute",
    callout_2_text: "Let Codex move block by block while leaving a visible trace.",
    callout_3_title: "Validate",
    callout_3_text: "Run tests after every pass and roll back immediately on failure.",
    callout_4_title: "Record",
    callout_4_text: "Keep docs, logs, memory, and state so the release story stays explainable.",
    workflow_eyebrow: "Workflow",
    workflow_title: "Humans set direction.<br>Codex moves in blocks.",
    workflow_1_title: "Input",
    workflow_1_text: "Start from a long-term prompt or a repository that needs improvement.",
    workflow_2_title: "Codex Breakdown",
    workflow_2_text: "Codex proposes an actionable block list with priorities.",
    workflow_3_title: "Execution Loop",
    workflow_3_text: "Implementation, tests, and logging repeat until a block is complete.",
    workflow_4_title: "Checkpoint",
    workflow_4_text: "Approval boundaries and GitHub sync keep the release flow controlled.",
    showcase_eyebrow: "Why It Feels Different",
    showcase_title: "It looks like a product,<br>and works like an operations tool.",
    showcase_1_title: "Multi-repo architecture",
    showcase_1_text: "repo, docs, memory, logs, reports, and state stay isolated per repository.",
    showcase_2_title: "Strict validation",
    showcase_2_text: "Failures snap back to the safe revision immediately.",
    showcase_3_title: "Progress timeline",
    showcase_3_text: "Current block, remaining flow, and Codex status are easy to read.",
    showcase_4_title: "App-ready foundation",
    showcase_4_text: "It starts with a desktop GUI and is shaped to evolve into a shipped product.",
    release_eyebrow: "Release",
    release_title: "The information you need for an app release page<br>is being organized from day one.",
    release_card_1_label: "Version",
    release_card_1_title: "Alpha preview",
    release_card_1_text: "The current phase is focused on refining the workspace and execution flow, with desktop packaging as the next target.",
    release_card_1_cta: "Alpha access",
    release_card_1_docs: "Read docs",
    release_card_2_label: "Platform",
    release_card_2_title: "Windows-first desktop",
    release_card_2_text: "Built as a React + Tauri desktop app while refining the real operating workflow and packaging experience.",
    release_card_3_label: "Audience",
    release_card_3_title: "Teams with recurring improvement work",
    release_card_3_text: "Designed for teams that need to operate several repositories, not just one or two.",
    contact_eyebrow: "Contact",
    contact_title: "Adoption, collaboration, productization",
    contact_text: "If you want to expand jakal-flow into an internal automation tool or a shippable app, reach out by email.",
    contact_cta: "Send email",
    footer_cookie: "Cookie settings",
    consent_title: "Analytics notice",
    consent_text: "This page can use Google Analytics 4 to understand visits and traffic.",
    consent_decline: "Decline",
    consent_accept: "Allow",
  },
  zh: {
    title: "jakal-flow | AI 仓库运营",
    description: "jakal-flow 是一款桌面自动化应用，可安全管理多个仓库，并让 Codex 拆分、执行和验证工作。",
    nav_product: "产品",
    nav_workflow: "流程",
    nav_release: "发布",
    nav_contact: "联系",
    hero_badge: "桌面应用开发中",
    hero_eyebrow: "AI Repo Operations",
    hero_title: "从规划到验证，<br>把仓库改进<br>变成可执行流程。",
    hero_text: "jakal-flow 在一个界面中管理多个仓库，并让 Codex 拆分任务、按区块执行，同时管理测试与回滚。",
    hero_docs: "文档",
    hero_contact: "联系",
    hero_meta_1: "多仓库",
    hero_meta_2: "严格验证",
    hero_meta_3: "Codex 自动拆分区块",
    sidebar_title: "仓库",
    panel_label: "时间线",
    panel_title: "现在进行到哪里，<br>一眼就能看到。",
    panel_status: "运行中",
    timeline_input: "输入",
    timeline_breakdown: "拆分",
    timeline_execute: "执行",
    timeline_validate: "验证",
    timeline_sync: "同步",
    block_1_title: "测试稳定化",
    block_1_text: "复现失败、补回归测试、保持安全版本",
    block_2_title: "GUI 简化",
    block_2_text: "减少执行路径摩擦并增强进度可见性",
    block_3_title: "文档更新",
    block_3_text: "只把已验证行为反映到 README 和发布页面",
    ops_model: "模型",
    ops_reasoning: "推理强度",
    ops_validation: "验证",
    ops_validation_value: "每次 pass 后测试",
    ops_sync: "同步",
    ops_sync_value: "区块完成后 push",
    callout_eyebrow: "定位",
    callout_title: "不只是自动化工具，<br>而是可发布的运营层。",
    callout_1_title: "规划",
    callout_1_text: "从长期提示和仓库上下文中细分工作。",
    callout_2_title: "执行",
    callout_2_text: "让 Codex 以区块为单位推进实现，并留下可见轨迹。",
    callout_3_title: "验证",
    callout_3_text: "每次 pass 后运行测试，失败立即回滚。",
    callout_4_title: "记录",
    callout_4_text: "保留 docs、logs、memory 和 state，使发布说明始终可解释。",
    workflow_eyebrow: "流程",
    workflow_title: "人给方向，<br>Codex 以区块推进。",
    workflow_1_title: "输入",
    workflow_1_text: "从长期提示或待改进仓库开始。",
    workflow_2_title: "Codex 拆分",
    workflow_2_text: "Codex 生成可执行的区块列表和优先级。",
    workflow_3_title: "执行循环",
    workflow_3_text: "直到区块完成前，持续进行实现、测试和记录。",
    workflow_4_title: "检查点",
    workflow_4_text: "通过审批边界和 GitHub 同步维持发布节奏。",
    showcase_eyebrow: "差异化",
    showcase_title: "它看起来像产品，<br>但工作方式像运营工具。",
    showcase_1_title: "多仓库架构",
    showcase_1_text: "repo、docs、memory、logs、reports、state 按仓库隔离存放。",
    showcase_2_title: "严格验证",
    showcase_2_text: "失败时会立即回到安全版本。",
    showcase_3_title: "进度时间线",
    showcase_3_text: "当前区块、剩余流程和 Codex 状态都清晰可见。",
    showcase_4_title: "为应用扩展而准备",
    showcase_4_text: "从桌面 GUI 起步，后续易于扩展为可发布产品。",
    release_eyebrow: "发布",
    release_title: "应用发布页需要的信息，<br>从一开始就被整理。",
    release_card_1_label: "版本",
    release_card_1_title: "Alpha 预览",
    release_card_1_text: "当前阶段聚焦于工作区和执行流程打磨，下一步目标是桌面应用打包。",
    release_card_1_cta: "申请 Alpha",
    release_card_1_docs: "查看文档",
    release_card_2_label: "平台",
    release_card_2_title: "Windows 优先桌面端",
    release_card_2_text: "以 React + Tauri 桌面应用为基础，同时打磨实际操作流程和桌面分发体验。",
    release_card_3_label: "目标用户",
    release_card_3_title: "有持续改进需求的团队",
    release_card_3_text: "适合需要稳定运营多个仓库的团队，而不仅仅是一两个项目。",
    contact_eyebrow: "联系",
    contact_title: "导入、协作、产品化讨论",
    contact_text: "如果你希望把 jakal-flow 扩展为内部自动化工具或可发布应用，可以通过邮件联系。",
    contact_cta: "发送邮件",
    footer_cookie: "Cookie 设置",
    consent_title: "分析说明",
    consent_text: "本页面可使用 Google Analytics 4 来了解访问量和流量来源。",
    consent_decline: "拒绝",
    consent_accept: "允许",
  },
  ja: {
    title: "jakal-flow | AI Repo Operations",
    description: "jakal-flow は複数リポジトリを安全に管理し、Codex が作業を分解・実行・検証できるようにするデスクトップ自動化アプリです。",
    nav_product: "製品",
    nav_workflow: "ワークフロー",
    nav_release: "リリース",
    nav_contact: "問い合わせ",
    hero_badge: "デスクトップアプリ準備中",
    hero_eyebrow: "AI Repo Operations",
    hero_title: "計画から検証まで、<br>リポジトリ改善を<br>実行可能な流れに。",
    hero_text: "jakal-flow は複数のリポジトリを一つの運用画面で扱い、Codex が作業を分解し、ブロック単位で実行し、テストとロールバックまで管理できるよう設計された自動化アプリです。",
    hero_docs: "ドキュメント",
    hero_contact: "連絡する",
    hero_meta_1: "マルチリポジトリ",
    hero_meta_2: "厳格な検証",
    hero_meta_3: "Codex によるブロック計画",
    sidebar_title: "リポジトリ",
    panel_label: "タイムライン",
    panel_title: "いまどこまで進んだか、<br>一目でわかります。",
    panel_status: "実行中",
    timeline_input: "入力",
    timeline_breakdown: "分解",
    timeline_execute: "実行",
    timeline_validate: "検証",
    timeline_sync: "同期",
    block_1_title: "テスト安定化",
    block_1_text: "失敗の再現、回帰テスト追加、安全リビジョンの維持",
    block_2_title: "GUI の簡素化",
    block_2_text: "実行フローの摩擦を減らし、進捗の見やすさを強化",
    block_3_title: "ドキュメント反映",
    block_3_text: "検証済みの動作だけを README とリリースページに反映",
    ops_model: "モデル",
    ops_reasoning: "推論強度",
    ops_validation: "検証",
    ops_validation_value: "各 pass 後にテスト",
    ops_sync: "同期",
    ops_sync_value: "ブロック完了後に push",
    callout_eyebrow: "ポジショニング",
    callout_title: "ただの自動化ツールではなく、<br>リリース可能な運用レイヤー。",
    callout_1_title: "計画",
    callout_1_text: "長期プロンプトとリポジトリ文脈をもとに作業を細分化します。",
    callout_2_title: "実行",
    callout_2_text: "Codex がブロック単位で実装を進め、進捗を残します。",
    callout_3_title: "検証",
    callout_3_text: "各 pass 後にテストし、失敗時は即時 rollback します。",
    callout_4_title: "記録",
    callout_4_text: "docs、logs、memory、state を残し、後からも説明可能にします。",
    workflow_eyebrow: "ワークフロー",
    workflow_title: "人が方向を決め、<br>Codex がブロックで進みます。",
    workflow_1_title: "入力",
    workflow_1_text: "長期プロンプトまたは改善対象のリポジトリから始めます。",
    workflow_2_title: "Codex 分解",
    workflow_2_text: "Codex が実装可能なブロック一覧と優先順位を提案します。",
    workflow_3_title: "実行ループ",
    workflow_3_text: "ブロック完了まで実装、テスト、記録を繰り返します。",
    workflow_4_title: "チェックポイント",
    workflow_4_text: "承認境界と GitHub 同期でリリースフローを保ちます。",
    showcase_eyebrow: "特徴",
    showcase_title: "製品のように見えて、<br>運用ツールのように動きます。",
    showcase_1_title: "マルチリポジトリ構造",
    showcase_1_text: "repo、docs、memory、logs、reports、state をリポジトリごとに分離します。",
    showcase_2_title: "厳格な検証",
    showcase_2_text: "失敗すると安全リビジョンへ即座に戻します。",
    showcase_3_title: "進捗タイムライン",
    showcase_3_text: "現在のブロック、残りの流れ、Codex 状態を直感的に示します。",
    showcase_4_title: "アプリ拡張前提",
    showcase_4_text: "デスクトップ GUI から始めて、リリース可能な製品体験へ拡張しやすい構成です。",
    release_eyebrow: "リリース",
    release_title: "アプリのリリースページに必要な情報も<br>最初から整理します。",
    release_card_1_label: "バージョン",
    release_card_1_title: "アルファプレビュー",
    release_card_1_text: "現在はワークスペースと実行フローを磨く段階で、次の目標はデスクトップアプリのパッケージ化です。",
    release_card_1_cta: "アルファ問い合わせ",
    release_card_1_docs: "ドキュメントを見る",
    release_card_2_label: "プラットフォーム",
    release_card_2_title: "Windows 優先デスクトップ",
    release_card_2_text: "React + Tauri のデスクトップアプリとして、実運用フローと配布体験の両方を磨いています。",
    release_card_3_label: "対象",
    release_card_3_title: "継続的改善が必要な開発チーム",
    release_card_3_text: "一つ二つではなく、複数リポジトリを安定運用したいチーム向けです。",
    contact_eyebrow: "問い合わせ",
    contact_title: "導入、協業、製品化の相談",
    contact_text: "jakal-flow を社内自動化ツールや配布可能なアプリへ拡張したい場合は、以下のメールで連絡できます。",
    contact_cta: "メールを送る",
    footer_cookie: "Cookie 設定",
    consent_title: "分析ツールの案内",
    consent_text: "このページでは訪問統計の確認のため Google Analytics 4 を利用できます。",
    consent_decline: "拒否",
    consent_accept: "許可",
  },
};

const allTranslations = Object.fromEntries(
  Array.from(
    new Set([
      ...Object.keys(translations),
      ...Object.keys(window.JakalFlowGeneratedTranslations || {}),
      ...Object.keys(window.JakalFlowManualTranslations || {}),
    ]),
  ).map((language) => [
    language,
    {
      ...(translations[language] || {}),
      ...((window.JakalFlowGeneratedTranslations || {})[language] || {}),
      ...((window.JakalFlowManualTranslations || {})[language] || {}),
    },
  ]),
);

const supportedLanguages = [
  { value: "ko", label: "한국어", translation: "ko" },
  { value: "en", label: "English", translation: "en" },
  { value: "ja", label: "日本語", translation: "ja" },
  { value: "zh-CN", label: "简体中文", translation: "zh" },
  { value: "zh-TW", label: "繁體中文", translation: "zh" },
  { value: "es", label: "Español", translation: "en" },
  { value: "fr", label: "Français", translation: "en" },
  { value: "de", label: "Deutsch", translation: "en" },
  { value: "it", label: "Italiano", translation: "en" },
  { value: "pt-BR", label: "Português (Brasil)", translation: "en" },
  { value: "pt-PT", label: "Português (Portugal)", translation: "en" },
  { value: "ru", label: "Русский", translation: "en" },
  { value: "uk", label: "Українська", translation: "en" },
  { value: "pl", label: "Polski", translation: "en" },
  { value: "nl", label: "Nederlands", translation: "en" },
  { value: "tr", label: "Türkçe", translation: "en" },
  { value: "ar", label: "العربية", translation: "en" },
  { value: "he", label: "עברית", translation: "en" },
  { value: "hi", label: "हिन्दी", translation: "en" },
  { value: "bn", label: "বাংলা", translation: "en" },
  { value: "th", label: "ไทย", translation: "en" },
  { value: "vi", label: "Tiếng Việt", translation: "en" },
  { value: "id", label: "Bahasa Indonesia", translation: "en" },
  { value: "ms", label: "Bahasa Melayu", translation: "en" },
  { value: "tl", label: "Filipino", translation: "en" },
  { value: "cs", label: "Čeština", translation: "en" },
  { value: "hu", label: "Magyar", translation: "en" },
  { value: "ro", label: "Română", translation: "en" },
  { value: "sv", label: "Svenska", translation: "en" },
  { value: "da", label: "Dansk", translation: "en" },
  { value: "fi", label: "Suomi", translation: "en" },
  { value: "no", label: "Norsk", translation: "en" },
  { value: "el", label: "Ελληνικά", translation: "en" },
  { value: "sk", label: "Slovenčina", translation: "en" },
  { value: "bg", label: "Български", translation: "en" },
  { value: "hr", label: "Hrvatski", translation: "en" },
  { value: "sr", label: "Srpski", translation: "en" },
  { value: "sl", label: "Slovenščina", translation: "en" },
  { value: "lt", label: "Lietuvių", translation: "en" },
  { value: "lv", label: "Latviešu", translation: "en" },
];

const languageAliases = {
  zh: "zh-CN",
  "zh-cn": "zh-CN",
  "zh-hans": "zh-CN",
  "zh-sg": "zh-CN",
  "zh-tw": "zh-TW",
  "zh-hant": "zh-TW",
  "zh-hk": "zh-TW",
  "zh-mo": "zh-TW",
  pt: "pt-PT",
  "pt-br": "pt-BR",
  "pt-pt": "pt-PT",
  fil: "tl",
  iw: "he",
  nb: "no",
  nn: "no",
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
  return matchedBase ? matchedBase.value : "ko";
}

function translationLanguageFor(language) {
  const normalized = normalizeLanguage(language);
  if (allTranslations[normalized]) {
    return normalized;
  }
  return supportedLanguages.find((item) => item.value === normalized)?.translation || "en";
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
  const messages = allTranslations[translationLanguage] || allTranslations.ko;
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

document.addEventListener("DOMContentLoaded", () => {
  bootstrapLanguage();
  bootstrapConsent();
});
