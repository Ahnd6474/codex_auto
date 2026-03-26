import { GENERATED_STRINGS } from "./generated_locale_data.js";
import { MANUAL_LOCALE_OVERRIDES } from "./manual_locale_overrides.js";

export const DEFAULT_LANGUAGE = "en";
export const SUPPORTED_LANGUAGES = [
  "ko",
  "en",
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
export const LANGUAGE_OPTIONS = [
  { value: "ko", label: "한국어" },
  { value: "en", label: "English" },
];

export const AVAILABLE_LANGUAGE_OPTIONS = [
  { value: "ko", label: "한국어" },
  { value: "en", label: "English" },
  { value: "ja", label: "日本語" },
  { value: "zh-cn", label: "简体中文" },
  { value: "zh-tw", label: "繁體中文" },
  { value: "es", label: "Español" },
  { value: "fr", label: "Français" },
  { value: "de", label: "Deutsch" },
  { value: "it", label: "Italiano" },
  { value: "pt-br", label: "Português (Brasil)" },
  { value: "pt-pt", label: "Português (Portugal)" },
  { value: "ru", label: "Русский" },
  { value: "uk", label: "Українська" },
  { value: "pl", label: "Polski" },
  { value: "nl", label: "Nederlands" },
  { value: "tr", label: "Türkçe" },
  { value: "ar", label: "العربية" },
  { value: "he", label: "עברית" },
  { value: "hi", label: "हिन्दी" },
  { value: "bn", label: "বাংলা" },
  { value: "th", label: "ไทย" },
  { value: "vi", label: "Tiếng Việt" },
  { value: "id", label: "Bahasa Indonesia" },
  { value: "ms", label: "Bahasa Melayu" },
  { value: "tl", label: "Filipino" },
  { value: "cs", label: "Čeština" },
  { value: "hu", label: "Magyar" },
  { value: "ro", label: "Română" },
  { value: "sv", label: "Svenska" },
  { value: "da", label: "Dansk" },
  { value: "fi", label: "Suomi" },
  { value: "no", label: "Norsk" },
  { value: "el", label: "Ελληνικά" },
  { value: "sk", label: "Slovenčina" },
  { value: "bg", label: "Български" },
  { value: "hr", label: "Hrvatski" },
  { value: "sr", label: "Srpski" },
  { value: "sl", label: "Slovenščina" },
  { value: "lt", label: "Lietuvių" },
  { value: "lv", label: "Latviešu" },
];

const LANGUAGE_ALIASES = {
  "en-us": "en",
  "en-gb": "en",
  "ko-kr": "ko",
  "ja-jp": "ja",
  zh: "zh-cn",
  "zh-hans": "zh-cn",
  "zh-sg": "zh-cn",
  "zh-my": "zh-cn",
  "zh-hk": "zh-tw",
  "zh-mo": "zh-tw",
  "zh-hant": "zh-tw",
  "zh-cn": "zh-cn",
  "zh-tw": "zh-tw",
  pt: "pt-pt",
  "pt-br": "pt-br",
  "pt-pt": "pt-pt",
  nb: "no",
  nn: "no",
  no: "no",
  fil: "tl",
  iw: "he",
};

const STRINGS = {
  en: {
    "action.add": "Add",
    "action.approveCheckpoint": "Approve Checkpoint",
    "action.browse": "Browse",
    "action.closeout": "Closeout",
    "action.copyLink": "Copy Link",
    "action.delete": "Delete",
    "action.deleteAll": "Delete All",
    "action.dismiss": "Dismiss",
    "action.down": "Down",
    "action.generate": "Generate",
    "action.generatePlan": "Generate Plan",
    "action.generateShareLink": "Generate Share Link",
    "action.new": "New",
    "action.refresh": "Refresh",
    "action.reset": "Reset",
    "action.run": "Run",
    "action.runRemaining": "Run Remaining Steps",
    "action.revokeLink": "Revoke Link",
    "action.save": "Save",
    "action.saveConfiguration": "Save Configuration",
    "action.saveProgramSettings": "Save Program Settings",
    "action.saveLocal": "Save Local",
    "action.stop": "Stop",
    "action.up": "Up",
    "common.branch": "Branch",
    "common.connected": "connected",
    "common.filter": "Filter",
    "common.input": "Input",
    "common.language": "Language",
    "common.localOnly": "local-only",
    "common.no": "No",
    "common.none": "None",
    "common.off": "Off",
    "common.on": "On",
    "common.output": "Output",
    "common.project": "Project",
    "common.repoUrl": "Repo URL",
    "common.status": "Status",
    "common.total": "Total",
    "common.unknown": "Unknown",
    "common.unavailable": "Unavailable",
    "common.verification": "Verification",
    "common.yes": "Yes",
    "config.developerMode": "Developer Mode",
    "config.developerModeDescription": "Advanced runtime controls for debugging and custom execution.",
    "config.executionModel": "Execution Model",
    "config.fastModeDescription": "When enabled, jakal-flow prefixes each Codex prompt with /fast.",
    "config.githubConnection": "GitHub Connection",
    "config.githubConnectionDescription": "Keep local and GitHub-backed repositories explicit.",
    "config.githubUrl": "GitHub URL",
    "config.maxPlannedSteps": "Max Planned Steps",
    "config.projectConfiguration": "Project Configuration",
    "config.projectConfigurationDescription": "Repository setup stays editable here so the operations console can manage isolated workspaces without hiding the underlying runtime.",
    "config.projectName": "Project Name",
    "config.programSettingsMoved": "Program-wide runtime controls now live in Program Settings on the top bar.",
    "config.useExistingOrigin": "Use existing origin in this folder",
    "config.manualGithubUrl": "Paste a GitHub repository URL",
    "config.noGithubYet": "Do not connect GitHub yet",
    "config.workingDirectory": "Working Directory",
    "dashboard.checkpoint": "Checkpoint",
    "dashboard.checkpointPending": "Checkpoint Pending",
    "dashboard.dashboard": "Dashboard",
    "dashboard.inputTokens": "Input Tokens",
    "dashboard.lastSafeRevision": "Last Safe Revision",
    "dashboard.noCheckpointWaiting": "No checkpoint is waiting for review.",
    "dashboard.noProjectSelected": "No project selected",
    "dashboard.origin": "Origin",
    "dashboard.outputTokens": "Output Tokens",
    "dashboard.remainingSteps": "Remaining Steps",
    "dashboard.runtime": "Runtime",
    "dashboard.targetBlock": "Target block {block}",
    "field.approvalMode": "Approval Mode",
    "field.checkpointInterval": "Checkpoint Interval",
    "field.codexInstruction": "Codex Instruction",
    "field.codexPath": "Codex Path",
    "field.customModelSlug": "Custom Model Slug",
    "field.description": "Description",
    "field.extraPrompt": "Extra Prompt",
    "field.gptReasoning": "GPT Reasoning",
    "field.model": "Model",
    "field.prompt": "Prompt",
    "field.sandboxMode": "Sandbox Mode",
    "field.successCriteria": "Success Criteria",
    "field.title": "Title",
    "field.verificationCommand": "Verification Command",
    "history.history": "History",
    "history.noEntries": "No entries.",
    "history.noTaskTitle": "No task title",
    "history.noTestSummary": "No test summary",
    "history.recentActivity": "Recent Activity",
    "history.recentBlocks": "Recent Blocks",
    "message.checkpointApproved": "Checkpoint approved.",
    "message.closeoutAfterAllSteps": "Closeout can run only after all steps are completed.",
    "message.commandCompleted": "{command} completed.",
    "message.commandFailed": "{command} failed.",
    "message.commandStarted": "{command} started.",
    "message.createPlanBeforeCloseout": "Create and complete the execution plan before running closeout.",
    "message.createStepBeforeRun": "Create or add at least one planned step first.",
    "message.editRemainingSteps": "The plan already has completed steps. Edit the remaining steps instead of regenerating.",
    "message.insertAfterPending": "Insert new steps after a pending step, or clear the selection to append at the end.",
    "message.noProjectOpen": "No project is open.",
    "message.onlyPendingDelete": "Only pending steps can be deleted.",
    "message.onlyPendingEdit": "Only pending steps can be edited.",
    "message.onlyPendingMove": "Only pending steps can be reordered.",
    "message.openProjectFirst": "Open a project first.",
    "message.openOrCreateProjectFirst": "Open or create a project first.",
    "message.pendingMoveRange": "Pending steps can only move within the unstarted portion of the flow.",
    "message.planReset": "Plan reset.",
    "message.planSaved": "Plan saved.",
    "message.prepareProjectFirst": "Prepare or open a project first.",
    "message.projectConfigurationSaved": "Project configuration saved.",
    "message.projectDeleted": "Project removed from jakal-flow.",
    "message.allProjectsDeleted": "All projects removed from jakal-flow.",
    "message.programSettingsSaved": "Program settings saved.",
    "message.projectReloaded": "Project reloaded.",
    "message.projectStateRefreshed": "Project state refreshed.",
    "message.promptRequired": "Prompt is required to generate the plan.",
    "message.runStateRefreshed": "Run state refreshed.",
    "message.selectPendingStepFirst": "Select a pending step first.",
    "message.selectStepFirst": "Select a step first.",
    "message.shareLinkCopied": "Share link copied.",
    "message.shareLinkCopyFailed": "Could not copy the share link.",
    "message.shareLinkReady": "Read-only share link generated.",
    "message.shareLinkRevoked": "Share link revoked.",
    "message.stepUpdatedLocally": "Step updated locally. Save Plan to persist the change.",
    "message.stopRequested": "Stop requested after the current step.",
    "message.noShareLinkAvailable": "No active share link is available for this project.",
    "option.allowPushAfterSafeRuns": "Allow push after safe runs",
    "option.generateWordReport": "Word Report Creation",
    "option.requireCheckpointApproval": "Require checkpoint approval",
    "option.useFastMode": "Use /fast",
    "project.none": "No Project",
    "prompt.confirmCloseout": "Run final closeout now? This will do final cleanup, verification, smoke checks when possible, and handoff work.",
    "prompt.confirmRegeneratePlan": "Replace the current unstarted plan with a new Codex-generated plan?",
    "prompt.confirmResetPlan": "Reset the saved prompt and remove all execution steps for this project?",
    "prompt.confirmDeleteProject": "Remove this project from jakal-flow? The managed docs, logs, and state will be deleted, but the original repository folder will stay in place.",
    "prompt.confirmDeleteAllProjects": "Remove all projects from jakal-flow? The managed docs, logs, and state will be deleted, but the original repository folders will stay in place.",
    "preset.auto": "Auto",
    "preset.highOnly": "High Only",
    "preset.lowOnly": "Low Only",
    "preset.mediumOnly": "Medium Only",
    "preset.xhighOnly": "XHigh Only",
    "reasoning.auto": "Auto",
    "reasoning.high": "High",
    "reasoning.low": "Low",
    "reasoning.medium": "Medium",
    "reasoning.xhigh": "XHigh",
    "reports.attemptHistory": "Attempt History",
    "reports.blockReview": "Block Review",
    "reports.closeoutReport": "Closeout Report",
    "reports.historyEmpty": "No attempt history yet.",
    "reports.json": "Latest Report JSON",
    "reports.noBlockReview": "No block review yet.",
    "reports.noCloseoutReport": "No closeout report yet.",
    "reports.reports": "Reports",
    "run.closeout": "Closeout",
    "run.done": "Done",
    "run.executionFlow": "Execution Flow",
    "run.flow": "Flow",
    "run.flowChart": "Flow Chart",
    "run.newPendingStep": "New pending step",
    "run.noShareSession": "No active share session.",
    "run.noSteps": "No steps yet. Generate a plan or add one.",
    "run.noSummary": "No summary",
    "run.remoteMonitor": "Remote Monitor",
    "run.reasoning": "Reasoning {effort}",
    "run.selectStep": "Select a step.",
    "run.selectedStep": "Selected Step",
    "run.shareBindHost": "Server Bind Host",
    "run.shareBindLocal": "Local only (127.0.0.1)",
    "run.shareBindNetwork": "Network/tunnel ready (0.0.0.0)",
    "run.shareDescription": "Create a temporary read-only link so another device can watch the current run without any control actions.",
    "run.shareExpires": "Expires: {expiresAt}",
    "run.shareExternalHint": "Set a public base URL from your reverse proxy or tunnel to generate an internet-accessible share link.",
    "run.shareLink": "Share Link",
    "run.shareLocalLink": "Local Link",
    "run.sharePoll": "The remote viewer streams live updates and falls back to 5-second polling if needed.",
    "run.sharePublicBaseUrl": "Public Share Base URL",
    "run.shareServerAddress": "Local server: {address}",
    "run.stopAfterStep": "Stop After Step",
    "run.stepCheckpointDescription": "Describe the checkpoint for the user.",
    "run.stepCodexDescription": "Describe the implementation work Codex should perform for this checkpoint.",
    "run.stepSuccessCriteria": "Run the configured verification command successfully.",
    "runtime.modelSummary": "{model} | reasoning {effort}",
    "runtime.noModelSelected": "No model selected",
    "settings.application": "Application",
    "settings.applicationDescription": "These preferences affect the desktop shell itself.",
    "settings.executionDefaults": "Execution Defaults",
    "settings.executionDefaultsDescription": "These defaults are reused across projects unless a project-specific field replaces them.",
    "settings.programSettings": "Program Settings",
    "settings.programSettingsDescription": "Keep desktop-wide preferences and execution defaults in one place instead of scattering them across project forms.",
    "sidebar.checkpoints": "Checkpoints",
    "sidebar.emptyProjects": "No managed projects.",
    "sidebar.emptyWorkspace": "No workspace tree yet.",
    "sidebar.explorer": "Explorer",
    "sidebar.noGithubOrigin": "No GitHub origin configured for this project.",
    "sidebar.noProjectSummary": "Pick a project to inspect its managed state.",
    "sidebar.noRecordedCheckpoints": "No checkpoints recorded.",
    "sidebar.repositoryLink": "Repository Link",
    "sidebar.projectContextDelete": "Right-click to open project actions",
    "sidebar.searchFiles": "Search files",
    "sidebar.searchProjects": "Search projects",
    "sidebar.selectedSummary": "Selected summary",
    "sidebar.targetBlock": "Target block {block}",
    "status.awaiting_review": "Awaiting review",
    "status.closeout_failed": "Closeout failed",
    "status.closed_out": "Closed out",
    "status.completed": "Completed",
    "status.failed": "Failed",
    "status.idle": "Idle",
    "status.not_started": "Not started",
    "status.paused_for_review": "Paused for review",
    "status.pending": "Pending",
    "status.plan_completed": "Plan completed",
    "status.plan_ready": "Plan ready",
    "status.ready": "Ready",
    "status.running": "Running",
    "status.runningWithDetail": "Running: {detail}",
    "status.setup_ready": "Setup ready",
    "status.unknown": "Unknown",
    "tab.config": "Project Settings",
    "tab.dashboard": "Dashboard",
    "tab.flow": "Flow",
    "tab.history": "History",
    "tab.programSettings": "Program",
    "tab.reports": "Reports",
    "test.failed": "failed",
    "test.noRuns": "No test runs recorded yet.",
    "test.passed": "passed",
    "test.result": "Test Result",
    "test.run": "test run",
    "toolbar.bottom": "Bottom",
    "toolbar.plan": "Plan",
    "toolbar.programSettings": "Program Settings",
    "toolbar.toggleBottom": "Toggle tool window",
    "tool.eventJson": "Event JSON",
    "tool.gitStatus": "Git",
    "usage.codexSpark": "Codex Spark",
    "usage.window5h": "5h Usage",
    "usage.window7d": "7d Usage",
    "usage.windowSummary": "{used}% used, {remaining}% remaining, resets {resetsAt}",
    "tool.tokenUsage": "Token Usage",
  },
  ko: {
    "action.add": "추가",
    "action.approveCheckpoint": "체크포인트 승인",
    "action.browse": "찾아보기",
    "action.closeout": "마감",
    "action.delete": "삭제",
    "action.dismiss": "닫기",
    "action.down": "아래로",
    "action.generate": "생성",
    "action.generatePlan": "계획 생성",
    "action.new": "새로 만들기",
    "action.refresh": "새로고침",
    "action.reset": "초기화",
    "action.run": "실행",
    "action.runRemaining": "남은 단계 실행",
    "action.save": "저장",
    "action.saveConfiguration": "설정 저장",
    "action.saveProgramSettings": "프로그램 설정 저장",
    "action.saveLocal": "로컬 저장",
    "action.stop": "중지",
    "action.up": "위로",
    "common.branch": "브랜치",
    "common.connected": "연결됨",
    "common.filter": "필터",
    "common.input": "입력",
    "common.language": "언어",
    "common.localOnly": "로컬 전용",
    "common.no": "아니오",
    "common.none": "없음",
    "common.off": "끔",
    "common.on": "켬",
    "common.output": "출력",
    "common.project": "프로젝트",
    "common.repoUrl": "저장소 URL",
    "common.status": "상태",
    "common.total": "합계",
    "common.unknown": "알 수 없음",
    "common.unavailable": "사용할 수 없음",
    "common.verification": "검증",
    "common.yes": "예",
    "config.developerMode": "개발자 모드",
    "config.developerModeDescription": "디버깅과 사용자 지정 실행을 위한 고급 런타임 제어입니다.",
    "config.executionModel": "실행 모델",
    "config.fastModeDescription": "활성화하면 jakal-flow가 각 Codex 프롬프트 앞에 /fast를 붙입니다.",
    "config.githubConnection": "GitHub 연결",
    "config.githubConnectionDescription": "로컬 저장소와 GitHub 연결 저장소를 명시적으로 유지합니다.",
    "config.githubUrl": "GitHub URL",
    "config.maxPlannedSteps": "최대 계획 단계 수",
    "config.projectConfiguration": "프로젝트 설정",
    "config.projectConfigurationDescription": "저장소 설정은 여기서 계속 수정할 수 있어, 작업 콘솔이 런타임을 숨기지 않으면서도 격리된 워크스페이스를 관리할 수 있습니다.",
    "config.projectName": "프로젝트 이름",
    "config.programSettingsMoved": "프로그램 전체에 적용되는 실행 설정은 상단 바의 프로그램 설정으로 옮겼습니다.",
    "config.useExistingOrigin": "이 폴더의 기존 origin 사용",
    "config.manualGithubUrl": "GitHub 저장소 URL 직접 입력",
    "config.noGithubYet": "아직 GitHub에 연결하지 않음",
    "config.workingDirectory": "작업 디렉터리",
    "dashboard.checkpoint": "체크포인트",
    "dashboard.checkpointPending": "체크포인트 대기",
    "dashboard.dashboard": "대시보드",
    "dashboard.inputTokens": "입력 토큰",
    "dashboard.lastSafeRevision": "마지막 안전 리비전",
    "dashboard.noCheckpointWaiting": "검토를 기다리는 체크포인트가 없습니다.",
    "dashboard.noProjectSelected": "선택된 프로젝트가 없습니다",
    "dashboard.origin": "원격 저장소",
    "dashboard.outputTokens": "출력 토큰",
    "dashboard.remainingSteps": "남은 단계",
    "dashboard.runtime": "런타임",
    "dashboard.targetBlock": "대상 블록 {block}",
    "field.approvalMode": "승인 모드",
    "field.checkpointInterval": "체크포인트 간격",
    "field.codexInstruction": "Codex 지시문",
    "field.codexPath": "Codex 경로",
    "field.customModelSlug": "사용자 지정 모델 슬러그",
    "field.description": "설명",
    "field.extraPrompt": "추가 프롬프트",
    "field.gptReasoning": "GPT 추론",
    "field.model": "모델",
    "field.prompt": "프롬프트",
    "field.sandboxMode": "샌드박스 모드",
    "field.successCriteria": "성공 기준",
    "field.title": "제목",
    "field.verificationCommand": "검증 명령어",
    "history.history": "기록",
    "history.noEntries": "항목이 없습니다.",
    "history.noTaskTitle": "작업 제목이 없습니다",
    "history.noTestSummary": "테스트 요약이 없습니다",
    "history.recentActivity": "최근 활동",
    "history.recentBlocks": "최근 블록",
    "message.checkpointApproved": "체크포인트를 승인했습니다.",
    "message.closeoutAfterAllSteps": "모든 단계가 완료된 뒤에만 마감을 실행할 수 있습니다.",
    "message.commandCompleted": "{command} 작업이 완료되었습니다.",
    "message.commandFailed": "{command} 작업이 실패했습니다.",
    "message.commandStarted": "{command} 작업을 시작했습니다.",
    "message.createPlanBeforeCloseout": "마감을 실행하기 전에 실행 계획을 만들고 완료하세요.",
    "message.createStepBeforeRun": "먼저 계획된 단계를 하나 이상 만들거나 추가하세요.",
    "message.editRemainingSteps": "이미 완료된 단계가 있으므로 다시 생성하지 말고 남은 단계를 수정하세요.",
    "message.insertAfterPending": "새 단계는 대기 중인 단계 뒤에만 넣을 수 있습니다. 끝에 추가하려면 선택을 해제하세요.",
    "message.noProjectOpen": "열린 프로젝트가 없습니다.",
    "message.onlyPendingDelete": "대기 중인 단계만 삭제할 수 있습니다.",
    "message.onlyPendingEdit": "대기 중인 단계만 수정할 수 있습니다.",
    "message.onlyPendingMove": "대기 중인 단계만 순서를 바꿀 수 있습니다.",
    "message.openProjectFirst": "먼저 프로젝트를 여세요.",
    "message.openOrCreateProjectFirst": "먼저 프로젝트를 열거나 만드세요.",
    "message.pendingMoveRange": "대기 단계는 아직 시작하지 않은 구간 안에서만 이동할 수 있습니다.",
    "message.planReset": "계획을 초기화했습니다.",
    "message.planSaved": "계획을 저장했습니다.",
    "message.prepareProjectFirst": "먼저 프로젝트를 준비하거나 여세요.",
    "message.projectConfigurationSaved": "프로젝트 설정을 저장했습니다.",
    "message.projectDeleted": "jakal-flow에서 프로젝트를 제거했습니다.",
    "message.programSettingsSaved": "프로그램 설정을 저장했습니다.",
    "message.projectReloaded": "프로젝트를 다시 불러왔습니다.",
    "message.projectStateRefreshed": "프로젝트 상태를 새로고침했습니다.",
    "message.promptRequired": "계획을 생성하려면 프롬프트가 필요합니다.",
    "message.runStateRefreshed": "실행 상태를 새로고침했습니다.",
    "message.selectPendingStepFirst": "먼저 대기 중인 단계를 선택하세요.",
    "message.selectStepFirst": "먼저 단계를 선택하세요.",
    "message.stepUpdatedLocally": "단계를 로컬에서 업데이트했습니다. 변경 사항을 유지하려면 계획을 저장하세요.",
    "message.stopRequested": "현재 단계가 끝나면 중지하도록 요청했습니다.",
    "option.allowPushAfterSafeRuns": "안전 실행 후 push 허용",
    "option.requireCheckpointApproval": "체크포인트 승인 필요",
    "option.useFastMode": "/fast 사용",
    "project.none": "프로젝트 없음",
    "prompt.confirmCloseout": "지금 최종 마감을 실행할까요? 가능한 경우 최종 정리, 검증, 스모크 체크, 인수인계를 수행합니다.",
    "prompt.confirmRegeneratePlan": "현재 시작 전 계획을 Codex가 새로 생성한 계획으로 바꿀까요?",
    "prompt.confirmResetPlan": "저장된 프롬프트를 초기화하고 이 프로젝트의 모든 실행 단계를 제거할까요?",
    "prompt.confirmDeleteProject": "이 프로젝트를 jakal-flow에서 제거할까요? 관리 중인 문서, 로그, 상태만 삭제되고 원본 저장소 폴더는 그대로 둡니다.",
    "preset.auto": "자동",
    "preset.highOnly": "높음만",
    "preset.lowOnly": "낮음만",
    "preset.mediumOnly": "중간만",
    "preset.xhighOnly": "매우 높음만",
    "reasoning.high": "높음",
    "reasoning.low": "낮음",
    "reasoning.medium": "중간",
    "reasoning.xhigh": "매우 높음",
    "reports.attemptHistory": "시도 기록",
    "reports.blockReview": "블록 리뷰",
    "reports.closeoutReport": "마감 보고서",
    "reports.historyEmpty": "아직 시도 기록이 없습니다.",
    "reports.json": "최신 보고서 JSON",
    "reports.noBlockReview": "아직 블록 리뷰가 없습니다.",
    "reports.noCloseoutReport": "아직 마감 보고서가 없습니다.",
    "reports.reports": "보고서",
    "run.closeout": "마감",
    "run.done": "완료",
    "run.executionFlow": "실행 흐름",
    "run.flow": "흐름",
    "run.flowChart": "흐름도",
    "run.newPendingStep": "새 대기 단계",
    "run.noSteps": "아직 단계가 없습니다. 계획을 생성하거나 직접 추가하세요.",
    "run.noSummary": "요약 없음",
    "run.reasoning": "추론 {effort}",
    "run.selectStep": "단계를 선택하세요.",
    "run.selectedStep": "선택된 단계",
    "run.stopAfterStep": "단계 후 중지",
    "run.stepCheckpointDescription": "사용자에게 보여줄 체크포인트를 설명하세요.",
    "run.stepCodexDescription": "이 체크포인트에서 Codex가 수행할 구현 작업을 설명하세요.",
    "run.stepSuccessCriteria": "설정된 검증 명령어가 성공적으로 실행되어야 합니다.",
    "runtime.modelSummary": "{model} | 추론 {effort}",
    "runtime.noModelSelected": "선택된 모델이 없습니다",
    "settings.application": "프로그램",
    "settings.applicationDescription": "데스크톱 셸 자체에 적용되는 설정입니다.",
    "settings.executionDefaults": "실행 기본값",
    "settings.executionDefaultsDescription": "프로젝트 전반에 공통으로 쓸 실행 기본값입니다.",
    "settings.programSettings": "프로그램 설정",
    "settings.programSettingsDescription": "프로젝트와 무관한 데스크톱 설정과 실행 기본값을 한 곳에서 관리합니다.",
    "sidebar.checkpoints": "체크포인트",
    "sidebar.emptyProjects": "관리 중인 프로젝트가 없습니다.",
    "sidebar.emptyWorkspace": "아직 워크스페이스 트리가 없습니다.",
    "sidebar.explorer": "탐색기",
    "sidebar.noGithubOrigin": "이 프로젝트에는 GitHub origin이 설정되어 있지 않습니다.",
    "sidebar.noProjectSummary": "관리 상태를 확인하려면 프로젝트를 선택하세요.",
    "sidebar.noRecordedCheckpoints": "기록된 체크포인트가 없습니다.",
    "sidebar.repositoryLink": "저장소 연결",
    "sidebar.searchFiles": "파일 검색",
    "sidebar.searchProjects": "프로젝트 검색",
    "sidebar.selectedSummary": "선택된 요약",
    "sidebar.targetBlock": "대상 블록 {block}",
    "status.awaiting_review": "검토 대기",
    "status.closeout_failed": "마감 실패",
    "status.closed_out": "마감 완료",
    "status.completed": "완료",
    "status.failed": "실패",
    "status.idle": "대기",
    "status.not_started": "시작 전",
    "status.paused_for_review": "검토 대기 중지",
    "status.pending": "대기",
    "status.plan_completed": "계획 완료",
    "status.plan_ready": "계획 준비됨",
    "status.ready": "준비됨",
    "status.running": "실행 중",
    "status.runningWithDetail": "실행 중: {detail}",
    "status.setup_ready": "설정 완료",
    "status.unknown": "알 수 없음",
    "tab.config": "프로젝트 설정",
    "tab.dashboard": "대시보드",
    "tab.flow": "흐름",
    "tab.history": "기록",
    "tab.programSettings": "프로그램",
    "tab.reports": "보고서",
    "test.failed": "실패",
    "test.noRuns": "아직 기록된 테스트 실행이 없습니다.",
    "test.passed": "성공",
    "test.result": "테스트 결과",
    "test.run": "테스트 실행",
    "toolbar.bottom": "하단",
    "toolbar.plan": "계획",
    "toolbar.programSettings": "프로그램 설정",
    "toolbar.toggleBottom": "도구 창 토글",
    "tool.eventJson": "이벤트 JSON",
    "tool.gitStatus": "Git",
    "usage.codexSpark": "Codex Spark",
    "usage.window5h": "5시간 사용량",
    "usage.window7d": "7일 사용량",
    "usage.windowSummary": "{used}% 사용, {remaining}% 남음, {resetsAt} 재설정",
    "tool.tokenUsage": "토큰 사용량",
  },
};

STRINGS.en["action.deleteAll"] = "Delete All";
STRINGS.en["config.advancedModelSettings"] = "Advanced Settings";
STRINGS.en["config.advancedModelSettingsDescription"] = "Advanced Settings";
STRINGS.en["message.allProjectsDeleted"] = "All projects removed from jakal-flow.";
STRINGS.en["option.generateWordReport"] = "Word Report Creation";
STRINGS.en["option.lightMode"] = "Light Mode";
STRINGS.en["option.developerMode"] = "Developer Mode";
STRINGS.en["dashboard.codexPlan"] = "Codex Plan";
STRINGS.en["dashboard.codexUsage"] = "Codex Usage";
STRINGS.en["common.auth"] = "Auth";
STRINGS.en["common.account"] = "Account";
STRINGS.en["config.additionalModels"] = "Additional Models";
STRINGS.en["runtime.modelSummaryGeneric"] = "{model} | reasoning {effort}";
STRINGS.en["progress.noPlanYet"] = "No plan yet";
STRINGS.en["progress.doneNext"] = "Completed {completed}/{total} steps, next: {next}";
STRINGS.en["progress.closeoutCompleted"] = "Completed {completed}/{total} steps, closeout completed";
STRINGS.en["progress.closeoutRunning"] = "Completed {completed}/{total} steps, closeout running";
STRINGS.en["progress.closeoutFailed"] = "Completed {completed}/{total} steps, closeout failed";
STRINGS.en["progress.closeoutPending"] = "Completed {completed}/{total} steps, closeout pending";
STRINGS.en["action.backgroundJob"] = "Background Job";
STRINGS.en["prompt.confirmDeleteAllProjects"] =
  "Remove all projects from jakal-flow? The managed docs, logs, and state will be deleted, but the original repository folders will stay in place.";
STRINGS.en["sidebar.projectContextDelete"] = "Right-click to open project actions";

STRINGS.ko["action.deleteAll"] = "전부 삭제";
STRINGS.ko["config.advancedModelSettings"] = "고급 설정";
STRINGS.ko["config.advancedModelSettingsDescription"] = "고급 설정";
STRINGS.ko["message.allProjectsDeleted"] = "모든 프로젝트를 제거했습니다.";
STRINGS.ko["option.generateWordReport"] = "Word 보고서 제작";
STRINGS.ko["option.lightMode"] = "밝은 모드";
STRINGS.ko["option.developerMode"] = "개발자 모드";
STRINGS.ko["dashboard.codexPlan"] = "Codex 요금제";
STRINGS.ko["dashboard.codexUsage"] = "Codex 사용량";
STRINGS.ko["common.auth"] = "인증 방식";
STRINGS.ko["common.account"] = "계정";
STRINGS.ko["config.additionalModels"] = "추가 지원 모델";
STRINGS.ko["runtime.modelSummaryGeneric"] = "{model} | 추론 {effort}";
STRINGS.ko["progress.noPlanYet"] = "아직 계획이 없습니다";
STRINGS.ko["progress.doneNext"] = "{completed}/{total}단계 완료, 다음: {next}";
STRINGS.ko["progress.closeoutCompleted"] = "{completed}/{total}단계 완료, 마감 완료";
STRINGS.ko["progress.closeoutRunning"] = "{completed}/{total}단계 완료, 마감 진행 중";
STRINGS.ko["progress.closeoutFailed"] = "{completed}/{total}단계 완료, 마감 실패";
STRINGS.ko["progress.closeoutPending"] = "{completed}/{total}단계 완료, 마감 대기";
STRINGS.ko["action.backgroundJob"] = "백그라운드 작업";
STRINGS.ko["prompt.confirmDeleteAllProjects"] =
  "모든 프로젝트를 삭제할까요? 관리 중인 문서, 로그, 상태만 삭제되고 원본 저장소 폴더는 그대로 유지됩니다.";
STRINGS.ko["sidebar.projectContextDelete"] = "우클릭으로 프로젝트 메뉴 열기";

const ALL_STRINGS = Object.fromEntries(
  Array.from(new Set([...Object.keys(STRINGS), ...Object.keys(GENERATED_STRINGS), ...Object.keys(MANUAL_LOCALE_OVERRIDES)])).map((language) => [
    language,
    {
      ...(STRINGS[language] || {}),
      ...(GENERATED_STRINGS[language] || {}),
      ...(MANUAL_LOCALE_OVERRIDES[language] || {}),
    },
  ]),
);

function titleCase(text) {
  if (!text) {
    return "";
  }
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function interpolate(template, params) {
  return String(template).replace(/\{(\w+)\}/g, (_match, key) => String(params[key] ?? ""));
}

function humanizeToken(value) {
  return String(value || "")
    .trim()
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ");
}

export function normalizeLanguage(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (!normalized) {
    return DEFAULT_LANGUAGE;
  }
  const aliased = LANGUAGE_ALIASES[normalized] || normalized;
  if (SUPPORTED_LANGUAGES.includes(aliased)) {
    return aliased;
  }
  const base = aliased.split("-")[0];
  if (SUPPORTED_LANGUAGES.includes(base)) {
    return base;
  }
  return LANGUAGE_ALIASES[base] || DEFAULT_LANGUAGE;
}

export function detectInitialLanguage(sourceLanguage = null) {
  const source =
    sourceLanguage ||
    globalThis.navigator?.language ||
    globalThis.navigator?.languages?.[0] ||
    DEFAULT_LANGUAGE;
  return normalizeLanguage(source);
}

export function translate(language, key, params = {}) {
  const normalized = normalizeLanguage(language);
  const value = ALL_STRINGS[normalized]?.[key] ?? STRINGS.en[key];
  if (value === undefined) {
    return key;
  }
  return interpolate(value, params);
}

export function displayStatus(status, language) {
  const normalizedLanguage = normalizeLanguage(language);
  const raw = String(status || "").trim();
  const normalized = raw.toLowerCase();
  if (!normalized) {
    return translate(normalizedLanguage, "status.unknown");
  }
  if (normalized.startsWith("running:")) {
    const detail = humanizeToken(raw.slice(raw.indexOf(":") + 1));
    return translate(normalizedLanguage, "status.runningWithDetail", {
      detail: normalizedLanguage === "ko" ? detail : titleCase(detail),
    });
  }
  const key = `status.${normalized}`;
  const translated = ALL_STRINGS[normalizedLanguage]?.[key] ?? STRINGS.en[key];
  if (translated) {
    return translated;
  }
  const humanized = humanizeToken(raw);
  if (!humanized) {
    return translate(normalizedLanguage, "status.unknown");
  }
  return normalizedLanguage === "ko" ? humanized : titleCase(humanized);
}
