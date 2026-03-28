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

LANGUAGE_OPTIONS.splice(
  0,
  LANGUAGE_OPTIONS.length,
  { value: "ko", label: "한국어" },
  { value: "en", label: "English" },
);

AVAILABLE_LANGUAGE_OPTIONS.splice(
  0,
  AVAILABLE_LANGUAGE_OPTIONS.length,
  { value: "ko", label: "한국어" },
  { value: "en", label: "English" },
  { value: "ja", label: "Japanese" },
  { value: "zh-cn", label: "Chinese (Simplified)" },
  { value: "zh-tw", label: "Chinese (Traditional)" },
  { value: "es", label: "Spanish" },
  { value: "fr", label: "French" },
  { value: "de", label: "German" },
  { value: "it", label: "Italian" },
  { value: "pt-br", label: "Portuguese (Brazil)" },
  { value: "pt-pt", label: "Portuguese (Portugal)" },
  { value: "ru", label: "Russian" },
  { value: "uk", label: "Ukrainian" },
  { value: "pl", label: "Polish" },
  { value: "nl", label: "Dutch" },
  { value: "tr", label: "Turkish" },
  { value: "ar", label: "Arabic" },
  { value: "he", label: "Hebrew" },
  { value: "hi", label: "Hindi" },
  { value: "bn", label: "Bengali" },
  { value: "th", label: "Thai" },
  { value: "vi", label: "Vietnamese" },
  { value: "id", label: "Indonesian" },
  { value: "ms", label: "Malay" },
  { value: "tl", label: "Filipino" },
  { value: "cs", label: "Czech" },
  { value: "hu", label: "Hungarian" },
  { value: "ro", label: "Romanian" },
  { value: "sv", label: "Swedish" },
  { value: "da", label: "Danish" },
  { value: "fi", label: "Finnish" },
  { value: "no", label: "Norwegian" },
  { value: "el", label: "Greek" },
  { value: "sk", label: "Slovak" },
  { value: "bg", label: "Bulgarian" },
  { value: "hr", label: "Croatian" },
  { value: "sr", label: "Serbian" },
  { value: "sl", label: "Slovenian" },
  { value: "lt", label: "Lithuanian" },
  { value: "lv", label: "Latvian" },
);

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
    "action.archiveAllProjects": "Archive All",
    "action.archiveProject": "Archive Project",
    "action.approveCheckpoint": "Approve Checkpoint",
    "action.browse": "Browse",
    "action.cancelReservation": "Cancel Reservation",
    "action.closeout": "Closeout",
    "action.copyLink": "Copy Link",
    "action.delete": "Delete",
    "action.deleteAllProjects": "Delete All",
    "action.deleteArchivedRun": "Delete Archived Run",
    "action.deleteAll": "Delete All",
    "action.deleteProject": "Delete Project",
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
    "dashboard.rateLimits": "Rate Limits",
    "dashboard.runtime": "Runtime",
    "dashboard.targetBlock": "Target block {block}",
    "field.approvalMode": "Approval Mode",
    "field.checkpointInterval": "Checkpoint Interval",
    "field.codexInstruction": "Codex Instruction",
    "field.codexPath": "Codex Path",
    "field.customModelSlug": "Custom Model Slug",
    "field.dependsOn": "Depends On",
    "field.description": "Description",
    "field.executionMode": "Execution Mode",
    "field.extraPrompt": "Extra Prompt",
    "field.gptReasoning": "GPT Reasoning",
    "field.localProvider": "Local Provider",
    "field.mlMaxCycles": "ML Max Cycles",
    "field.model": "Model",
    "field.modelProvider": "Model Provider",
    "field.optimizationMode": "Pre-Closeout Optimization",
    "field.providerBaseUrl": "Provider Base URL",
    "field.providerApiKeyEnv": "Provider API Key Env",
    "field.billingMode": "Billing Mode",
    "field.allowBackgroundQueue": "Allow Reservations",
    "field.backgroundQueuePriority": "Reservation Priority",
    "field.inputTokenRate": "Input $ / 1M",
    "field.outputTokenRate": "Output $ / 1M",
    "field.reasoningTokenRate": "Reasoning $ / 1M",
    "field.perPassRate": "Per Pass USD",
    "field.ownedPaths": "Owned Paths",
    "field.parallelGroup": "Parallel Group",
    "field.parallelWorkers": "Parallel Workers",
    "field.parallelMemoryPerWorkerGiB": "Memory / Worker (GiB)",
    "field.prompt": "Prompt",
    "field.sandboxMode": "Sandbox Mode",
    "field.successCriteria": "Success Criteria",
    "field.title": "Title",
    "field.verificationCommand": "Verification Command",
    "field.workflowMode": "Workflow Mode",
    "history.history": "History",
    "history.noEntries": "No entries.",
    "history.noFlowChart": "No flow chart captured for this run.",
    "history.noPrompt": "No prompt recorded.",
    "history.noSavedRuns": "No archived runs yet.",
    "history.noTaskTitle": "No task title",
    "history.noTestSummary": "No test summary",
    "history.recentActivity": "Recent Activity",
    "history.recentBlocks": "Recent Blocks",
    "history.archivedAt": "Archived: {timestamp}",
    "message.checkpointApproved": "Checkpoint approved.",
    "message.closeoutAfterAllSteps": "Closeout can run only after all steps are completed.",
    "message.commandCancelled": "{command} cancelled.",
    "message.commandCompleted": "{command} completed.",
    "message.commandFailed": "{command} failed.",
    "message.commandQueued": "{command} queued. Position {position}.",
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
    "message.projectArchived": "Project moved to history.",
    "message.projectDeleted": "Project removed from jakal-flow.",
    "message.allProjectsDeleted": "All projects removed from jakal-flow.",
    "message.allProjectsArchived": "All active projects moved to history.",
    "message.historyEntryDeleted": "Archived run deleted.",
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
    "message.stopRequested": "Immediate stop requested. The current step will be ignored.",
    "message.noShareLinkAvailable": "No active share link is available for this project.",
    "option.allowPushAfterSafeRuns": "Allow push after safe runs",
    "option.executionParallel": "Parallel",
    "option.executionSerial": "Serial",
    "option.generateWordReport": "Word Report Creation",
    "option.localProviderLmStudio": "LM Studio",
    "option.localProviderOllama": "Ollama",
    "option.providerOpenAI": "OpenAI / Codex Cloud",
    "option.providerOpenRouter": "OpenRouter",
    "option.providerOpenCDK": "OpenCDK",
    "option.providerLocalCompatible": "Local OpenAI-Compatible",
    "option.providerOSS": "Local OSS",
    "option.optimizationLight": "Light",
    "option.optimizationOff": "Off",
    "option.optimizationRefactor": "Refactor",
    "option.billingIncluded": "Included / zero",
    "option.billingToken": "Token pricing",
    "option.billingPerPass": "Per pass",
    "option.requireCheckpointApproval": "Require checkpoint approval",
    "option.useFastMode": "Use /fast",
    "option.workflowML": "ML Mode",
    "option.workflowStandard": "Standard Mode",
    "project.none": "No Project",
    "prompt.confirmCloseout": "Run final closeout now? This will do final cleanup, verification, smoke checks when possible, and handoff work.",
    "prompt.confirmArchiveProject": "Move this project to history? The managed docs, logs, and state will be preserved under history, and you can start a fresh run for the same directory.",
    "prompt.confirmArchiveAllProjects": "Move all active projects to history? The managed docs, logs, and state will be preserved under history.",
    "prompt.confirmCancelReservation": "Cancel this queued reservation? The project will stay unchanged and you can queue it again later.",
    "prompt.confirmDeleteHistoryEntry": "Delete this archived run permanently? Its managed docs, logs, reports, and state will be removed from history.",
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
    "run.autoRunAfterPlan": "Auto-run After Plan",
    "run.done": "Done",
    "run.dagLayer": "Layer {index}",
    "run.executionMode": "Execution Mode",
    "run.executionFlow": "Execution Flow",
    "run.executionTree": "Execution Tree",
    "run.flow": "Flow",
    "run.flowChart": "Flow Chart",
    "run.newPendingStep": "New pending step",
    "run.noShareSession": "No active share session.",
    "run.noReservations": "No queued runs.",
    "run.noSteps": "No steps yet. Generate a plan or add one.",
    "run.noSummary": "No summary",
    "run.parallelReady": "Ready Nodes",
    "run.queuePriority": "Priority {priority}",
    "run.queuePosition": "Queue #{position}",
    "run.remoteMonitor": "Remote Monitor",
    "run.reasoning": "Reasoning {effort}",
    "run.reservations": "Reservations",
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
    "run.stopAfterStep": "Ignore Current Step And Stop",
    "run.stepCheckpointDescription": "Describe the checkpoint for the user.",
    "run.stepCodexDescription": "Describe the implementation work Codex should perform for this checkpoint.",
    "run.stepSuccessCriteria": "Run the configured verification command successfully.",
    "runtime.modelSummary": "{model} | reasoning {effort}",
    "runtime.noModelSelected": "No model selected",
    "dashboard.estimatedRemaining": "Estimated Remaining",
    "dashboard.estimatedCost": "Estimated Cost",
    "dashboard.actualCost": "Actual Cost",
    "run.estimatedRemaining": "Est. Remaining",
    "run.estimatedTotal": "Est. Total",
    "run.stepEstimate": "Step Estimate",
    "run.estimatedCost": "Est. Cost",
    "run.currentElapsed": "Elapsed",
    "run.currentRemaining": "Remaining",
    "tool.estimatedCost": "Estimated Cost",
    "config.providerPresetModelHint": "This provider keeps the native model catalog and supports the selected preset flow.",
    "config.customProviderModelHint": "Enter the exact model slug exposed by this provider or local server.",
    "settings.application": "Application",
    "settings.applicationDescription": "These preferences affect the desktop shell itself.",
    "settings.executionDefaults": "Execution Defaults",
    "settings.executionDefaultsDescription": "These defaults are reused across projects unless a project-specific field replaces them.",
    "settings.dashboardPreferences": "Dashboard",
    "settings.dashboardPreferencesDescription": "Show only the dashboard cards you want to keep visible.",
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
    "status.cancelled": "Cancelled",
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
    "status.queued": "Queued",
    "status.queuedWithDetail": "Queued: {detail}",
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
    "action.cancelReservation": "예약 취소",
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
    "dashboard.rateLimits": "사용량 한도",
    "dashboard.runtime": "런타임",
    "dashboard.targetBlock": "대상 블록 {block}",
    "field.approvalMode": "승인 모드",
    "field.checkpointInterval": "체크포인트 간격",
    "field.codexInstruction": "Codex 지시문",
    "field.codexPath": "Codex 경로",
    "field.customModelSlug": "사용자 지정 모델 슬러그",
    "field.dependsOn": "선행 단계",
    "field.description": "설명",
    "field.executionMode": "실행 모드",
    "field.extraPrompt": "추가 프롬프트",
    "field.gptReasoning": "GPT 추론",
    "field.localProvider": "로컬 제공자",
    "field.model": "모델",
    "field.modelProvider": "모델 제공자",
    "field.providerBaseUrl": "Provider Base URL",
    "field.providerApiKeyEnv": "API 키 환경 변수",
    "field.billingMode": "과금 방식",
    "field.inputTokenRate": "입력 $ / 100만",
    "field.outputTokenRate": "출력 $ / 100만",
    "field.reasoningTokenRate": "추론 $ / 100만",
    "field.perPassRate": "패스당 USD",
    "field.ownedPaths": "소유 경로",
    "field.parallelGroup": "병렬 그룹",
    "field.parallelWorkers": "병렬 워커 수",
    "field.parallelMemoryPerWorkerGiB": "워커당 메모리 (GiB)",
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
    "message.commandCancelled": "{command} 작업을 취소했습니다.",
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
    "message.stopRequested": "현 단계를 무시하고 중지하도록 요청했습니다.",
    "option.allowPushAfterSafeRuns": "안전 실행 후 push 허용",
    "option.executionParallel": "병렬",
    "option.executionSerial": "직렬",
    "option.localProviderLmStudio": "LM Studio",
    "option.localProviderOllama": "Ollama",
    "option.providerOpenAI": "OpenAI / Codex 클라우드",
    "option.providerOpenRouter": "OpenRouter",
    "option.providerOpenCDK": "OpenCDK",
    "option.providerLocalCompatible": "로컬 OpenAI 호환",
    "option.providerOSS": "로컬 OSS",
    "option.billingIncluded": "포함됨 / 0원",
    "option.billingToken": "토큰 단가",
    "option.billingPerPass": "패스 단가",
    "option.requireCheckpointApproval": "체크포인트 승인 필요",
    "option.useFastMode": "/fast 사용",
    "project.none": "프로젝트 없음",
    "prompt.confirmCloseout": "지금 최종 마감을 실행할까요? 가능한 경우 최종 정리, 검증, 스모크 체크, 인수인계를 수행합니다.",
    "prompt.confirmCancelReservation": "대기열에 있는 이 예약을 취소할까요? 프로젝트 상태는 그대로 유지되고 나중에 다시 예약할 수 있습니다.",
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
    "run.dagLayer": "레이어 {index}",
    "run.executionMode": "실행 모드",
    "run.executionFlow": "실행 흐름",
    "run.executionTree": "실행 트리",
    "run.flow": "흐름",
    "run.flowChart": "흐름도",
    "run.newPendingStep": "새 대기 단계",
    "run.noReservations": "예약된 실행이 없습니다.",
    "run.noSteps": "아직 단계가 없습니다. 계획을 생성하거나 직접 추가하세요.",
    "run.noSummary": "요약 없음",
    "run.parallelReady": "실행 가능 노드",
    "run.queuePosition": "대기 순번 #{position}",
    "run.reasoning": "추론 {effort}",
    "run.reservations": "예약",
    "run.selectStep": "단계를 선택하세요.",
    "run.selectedStep": "선택된 단계",
    "run.stopAfterStep": "현 단계를 무시하고 중지",
    "run.stepCheckpointDescription": "사용자에게 보여줄 체크포인트를 설명하세요.",
    "run.stepCodexDescription": "이 체크포인트에서 Codex가 수행할 구현 작업을 설명하세요.",
    "run.stepSuccessCriteria": "설정된 검증 명령어가 성공적으로 실행되어야 합니다.",
    "runtime.modelSummary": "{model} | 추론 {effort}",
    "runtime.noModelSelected": "선택된 모델이 없습니다",
    "dashboard.estimatedRemaining": "예상 남은 시간",
    "dashboard.estimatedCost": "예상 비용",
    "dashboard.actualCost": "실비용",
    "run.estimatedRemaining": "예상 남은 시간",
    "run.estimatedTotal": "예상 전체 시간",
    "run.stepEstimate": "단계 예상치",
    "run.estimatedCost": "예상 비용",
    "run.currentElapsed": "경과",
    "run.currentRemaining": "남은 시간",
    "tool.estimatedCost": "예상 비용",
    "config.providerPresetModelHint": "이 제공자는 기본 모델 카탈로그를 유지하며 현재 프리셋 흐름을 그대로 사용할 수 있습니다.",
    "config.customProviderModelHint": "이 제공자나 로컬 서버가 노출하는 정확한 모델 슬러그를 입력하세요.",
    "settings.application": "프로그램",
    "settings.applicationDescription": "데스크톱 셸 자체에 적용되는 설정입니다.",
    "settings.executionDefaults": "실행 기본값",
    "settings.executionDefaultsDescription": "프로젝트 전반에 공통으로 쓸 실행 기본값입니다.",
    "settings.dashboardPreferences": "대시보드",
    "settings.dashboardPreferencesDescription": "대시보드에서 계속 보여둘 카드만 선택하세요.",
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
    "status.cancelled": "취소됨",
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
STRINGS.en["progress.runningIds"] = "Completed {completed}/{total} steps, running: {ids}";
STRINGS.en["progress.readyIds"] = "Completed {completed}/{total} steps, ready: {ids}";
STRINGS.en["action.backgroundJob"] = "Background Job";
STRINGS.en["run.closeoutRunning"] = "Running closeout";
STRINGS.en["run.completedStepsSummary"] = "{completed}/{total} steps completed";
STRINGS.en["run.liveRun"] = "Live Run";
STRINGS.en["run.planGeneration"] = "Generating execution plan";
STRINGS.en["run.preparingStep"] = "Preparing {step}";
STRINGS.en["run.progressPercent"] = "{percent}% complete";
STRINGS.en["run.readyNodeSummary"] = "{count} ready node(s)";
STRINGS.en["run.runningNodeSummary"] = "{count} node(s) running";
STRINGS.en["run.stepProgress"] = "Step Progress";
STRINGS.en["run.debugging"] = "Debugging";
STRINGS.en["run.workingOnStep"] = "Working on {step}";
STRINGS.en["run.workingOnSteps"] = "Working on {steps}";
STRINGS.en["run.parallelLimit"] = "Parallel Limit";
STRINGS.en["run.parallelLimitMemoryCap"] = "Memory cap {memoryCap}, CPU cap {cpuCap}, free {freeMemory}";
STRINGS.en["run.parallelLimitCpuCap"] = "CPU cap {cpuCap}, logical CPUs {logicalCpuCount}";
STRINGS.en["run.parallelLimitRequestedCap"] = "Requested {requested}, capped to {recommended} by CPU {cpuCap} and memory {memoryCap}";
STRINGS.en["run.parallelLimitAutoCap"] = "CPU cap {cpuCap}, memory cap {memoryCap}";
STRINGS.en["field.backgroundConcurrencyLimit"] = "Concurrent Background Jobs";
STRINGS.en["reports.wordReportReady"] = "Word report saved at {path}";
STRINGS.en["reports.wordReportDisabled"] = "Word report generation is disabled for this project.";
STRINGS.en["message.commandCompletedWithWordReport"] = "{command} completed. Word report: {path}";
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
STRINGS.ko["field.backgroundConcurrencyLimit"] = "동시 백그라운드 작업 수";
STRINGS.ko["field.allowBackgroundQueue"] = "이 프로젝트에서 예약 허용";
STRINGS.ko["field.backgroundQueuePriority"] = "예약 우선순위";
STRINGS.ko["action.backgroundJob"] = "백그라운드 작업";
STRINGS.ko["prompt.confirmDeleteAllProjects"] =
  "모든 프로젝트를 삭제할까요? 관리 중인 문서, 로그, 상태만 삭제되고 원본 저장소 폴더는 그대로 유지됩니다.";
STRINGS.ko["sidebar.projectContextDelete"] = "우클릭으로 프로젝트 메뉴 열기";

STRINGS.ko["reports.wordReportReady"] = "Word 보고서가 {path}에 저장되었습니다.";
STRINGS.ko["reports.wordReportDisabled"] = "이 프로젝트에서는 Word 보고서 생성을 사용하지 않습니다.";
STRINGS.ko["message.commandCompletedWithWordReport"] = "{command} 작업이 완료되었습니다. Word 보고서: {path}";

const KO_HIGH_QUALITY_OVERRIDES = {
  "action.add": "추가",
  "action.approveCheckpoint": "체크포인트 승인",
  "action.browse": "찾아보기",
  "action.closeout": "마감",
  "action.copyLink": "링크 복사",
  "action.delete": "삭제",
  "action.deleteAll": "전체 삭제",
  "action.dismiss": "닫기",
  "action.generate": "생성",
  "action.generatePlan": "계획 생성",
  "action.generateShareLink": "공유 링크 생성",
  "action.new": "새로 만들기",
  "action.refresh": "새로고침",
  "action.reset": "초기화",
  "action.run": "실행",
  "action.runRemaining": "남은 단계 실행",
  "action.revokeLink": "링크 해제",
  "action.save": "저장",
  "action.saveConfiguration": "설정 저장",
  "action.saveProgramSettings": "프로그램 설정 저장",
  "action.saveLocal": "로컬 저장",
  "action.stop": "중지",
  "common.account": "계정",
  "common.auth": "인증",
  "common.branch": "브랜치",
  "common.language": "언어",
  "common.project": "프로젝트",
  "common.repoUrl": "저장소 URL",
  "common.status": "상태",
  "config.additionalModels": "추가 모델",
  "config.advancedModelSettings": "고급 설정",
  "config.advancedModelSettingsDescription": "모델 선택, 추가 프롬프트, 실행 옵션을 세밀하게 조정합니다.",
  "config.executionModel": "실행 모델",
  "config.githubConnection": "GitHub 연결",
  "config.manualGithubUrl": "GitHub 저장소 URL 직접 입력",
  "config.maxPlannedSteps": "최대 계획 단계 수",
  "config.projectConfiguration": "프로젝트 설정",
  "config.projectConfigurationDescription": "저장소와 실행 설정을 명시적으로 유지해 추적성과 작업 분리를 보장합니다.",
  "config.projectName": "프로젝트 이름",
  "config.useExistingOrigin": "이 폴더의 기존 origin 사용",
  "config.workingDirectory": "작업 디렉터리",
  "dashboard.checkpoint": "체크포인트",
  "dashboard.checkpointPending": "체크포인트 대기 중",
  "dashboard.codexPlan": "Codex 요금제",
  "dashboard.codexUsage": "Codex 사용량",
  "dashboard.dashboard": "대시보드",
  "dashboard.inputTokens": "입력 토큰",
  "dashboard.lastSafeRevision": "마지막 안전 리비전",
  "dashboard.outputTokens": "출력 토큰",
  "dashboard.remainingSteps": "남은 단계",
  "dashboard.runtime": "런타임",
  "field.approvalMode": "승인 모드",
  "field.checkpointInterval": "체크포인트 간격",
  "field.codexInstruction": "Codex 지시문",
  "field.codexPath": "Codex 경로",
  "field.customModelSlug": "사용자 지정 모델 슬러그",
  "field.description": "설명",
  "field.executionMode": "실행 모드",
  "field.extraPrompt": "추가 프롬프트",
  "field.gptReasoning": "GPT 추론",
  "field.model": "모델",
  "field.parallelGroup": "병렬 그룹",
  "field.parallelWorkers": "병렬 작업 수",
  "field.parallelMemoryPerWorkerGiB": "워커당 메모리 (GiB)",
  "field.prompt": "프롬프트",
  "field.sandboxMode": "샌드박스 모드",
  "field.successCriteria": "성공 기준",
  "field.title": "제목",
  "field.verificationCommand": "검증 명령",
  "history.history": "기록",
  "history.noEntries": "기록이 없습니다.",
  "history.recentActivity": "최근 활동",
  "history.recentBlocks": "최근 블록",
  "message.allProjectsDeleted": "모든 프로젝트를 제거했습니다.",
  "message.checkpointApproved": "체크포인트를 승인했습니다.",
  "message.commandCompleted": "{command} 작업이 완료되었습니다.",
  "message.commandFailed": "{command} 작업이 실패했습니다.",
  "message.commandStarted": "{command} 작업을 시작했습니다.",
  "message.planSaved": "계획을 저장했습니다.",
  "message.programSettingsSaved": "프로그램 설정을 저장했습니다.",
  "message.projectConfigurationSaved": "프로젝트 설정을 저장했습니다.",
  "message.projectReloaded": "프로젝트를 다시 불러왔습니다.",
  "message.projectStateRefreshed": "프로젝트 상태를 새로고침했습니다.",
  "message.runStateRefreshed": "실행 상태를 새로고침했습니다.",
  "option.allowPushAfterSafeRuns": "안전 검증 후 push 허용",
  "option.developerMode": "개발자 모드",
  "option.executionParallel": "병렬",
  "option.executionSerial": "직렬",
  "option.generateWordReport": "Word 보고서 생성",
  "option.lightMode": "라이트 모드",
  "option.requireCheckpointApproval": "체크포인트 승인 필요",
  "option.useFastMode": "/fast 사용",
  "progress.closeoutCompleted": "{completed}/{total}단계 완료, 마감 완료",
  "progress.closeoutFailed": "{completed}/{total}단계 완료, 마감 실패",
  "progress.closeoutPending": "{completed}/{total}단계 완료, 마감 대기",
  "progress.closeoutRunning": "{completed}/{total}단계 완료, 마감 진행 중",
  "progress.doneNext": "{completed}/{total}단계 완료, 다음: {next}",
  "progress.noPlanYet": "아직 계획이 없습니다",
  "prompt.confirmDeleteAllProjects": "모든 프로젝트를 제거할까요? 관리 중인 문서, 로그, 상태는 삭제되지만 원본 저장소 폴더는 그대로 유지됩니다.",
  "prompt.confirmDeleteProject": "이 프로젝트를 jakal-flow에서 제거할까요? 관리 중인 문서, 로그, 상태는 삭제되지만 원본 저장소 폴더는 그대로 유지됩니다.",
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
  "run.selectedStep": "선택한 단계",
  "run.parallelLimit": "병렬 제한",
  "run.parallelLimitMemoryCap": "메모리 한도 {memoryCap}, CPU 한도 {cpuCap}, 가용 메모리 {freeMemory}",
  "run.parallelLimitCpuCap": "CPU 한도 {cpuCap}, 논리 프로세서 {logicalCpuCount}",
  "run.parallelLimitRequestedCap": "요청 {requested}, CPU {cpuCap} 및 메모리 {memoryCap} 한도로 {recommended}까지 제한",
  "run.parallelLimitAutoCap": "CPU 한도 {cpuCap}, 메모리 한도 {memoryCap}",
  "run.stopAfterStep": "현 단계를 무시하고 중지",
  "runtime.modelSummary": "{model} | 추론 {effort}",
  "runtime.modelSummaryGeneric": "{model} | 추론 {effort}",
  "settings.application": "프로그램",
  "settings.applicationDescription": "데스크톱 셸 자체에 적용되는 설정입니다.",
  "settings.executionDefaults": "실행 기본값",
  "settings.executionDefaultsDescription": "프로젝트별 값이 없으면 이 기본값을 재사용합니다.",
  "settings.programSettings": "프로그램 설정",
  "settings.programSettingsDescription": "데스크톱 전역 설정과 실행 기본값을 한 곳에서 관리합니다.",
  "sidebar.checkpoints": "체크포인트",
  "sidebar.emptyProjects": "관리 중인 프로젝트가 없습니다.",
  "sidebar.emptyWorkspace": "아직 워크스페이스 트리가 없습니다.",
  "sidebar.explorer": "탐색기",
  "sidebar.noGithubOrigin": "이 프로젝트에는 GitHub origin이 설정되어 있지 않습니다.",
  "sidebar.noRecordedCheckpoints": "기록된 체크포인트가 없습니다.",
  "sidebar.projectContextDelete": "오른쪽 클릭으로 프로젝트 작업 메뉴를 열 수 있습니다.",
  "sidebar.repositoryLink": "저장소 링크",
  "sidebar.searchFiles": "파일 검색",
  "sidebar.searchProjects": "프로젝트 검색",
  "sidebar.selectedSummary": "선택한 요약",
  "sidebar.targetBlock": "타깃 블록 {block}",
  "status.awaiting_review": "검토 대기 중",
  "status.closeout_failed": "마감 실패",
  "status.closed_out": "마감 완료",
  "status.completed": "완료",
  "status.failed": "실패",
  "status.idle": "대기 중",
  "status.not_started": "시작 전",
  "status.paused_for_review": "검토를 위해 일시 중지됨",
  "status.pending": "대기 중",
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
  "tool.eventJson": "이벤트 JSON",
  "tool.gitStatus": "Git 상태",
  "tool.tokenUsage": "토큰 사용량",
  "toolbar.bottom": "하단",
  "toolbar.plan": "계획",
  "toolbar.programSettings": "프로그램 설정",
  "toolbar.toggleBottom": "도구 창 토글",
  "usage.window5h": "5시간 사용량",
  "usage.window7d": "7일 사용량",
};

KO_HIGH_QUALITY_OVERRIDES["run.closeoutRunning"] = "마감 실행 중";
KO_HIGH_QUALITY_OVERRIDES["run.autoRunAfterPlan"] = "계획 생성 후 바로 실행";
KO_HIGH_QUALITY_OVERRIDES["run.completedStepsSummary"] = "{completed}/{total}단계 완료";
KO_HIGH_QUALITY_OVERRIDES["run.liveRun"] = "실행 중인 작업";
KO_HIGH_QUALITY_OVERRIDES["run.planGeneration"] = "계획 생성 중";
KO_HIGH_QUALITY_OVERRIDES["run.preparingStep"] = "{step} 준비 중";
KO_HIGH_QUALITY_OVERRIDES["run.progressPercent"] = "{percent}% 완료";
KO_HIGH_QUALITY_OVERRIDES["run.readyNodeSummary"] = "실행 가능 노드 {count}개";
KO_HIGH_QUALITY_OVERRIDES["run.runningNodeSummary"] = "실행 중인 노드 {count}개";
KO_HIGH_QUALITY_OVERRIDES["run.stepProgress"] = "단계 진행도";
KO_HIGH_QUALITY_OVERRIDES["run.debugging"] = "디버깅";
KO_HIGH_QUALITY_OVERRIDES["run.workingOnStep"] = "{step} 작업 중";
KO_HIGH_QUALITY_OVERRIDES["run.workingOnSteps"] = "{steps} 작업 중";
KO_HIGH_QUALITY_OVERRIDES["field.backgroundConcurrencyLimit"] = "동시 백그라운드 작업 수";
KO_HIGH_QUALITY_OVERRIDES["field.allowBackgroundQueue"] = "이 프로젝트에서 예약 허용";
KO_HIGH_QUALITY_OVERRIDES["field.backgroundQueuePriority"] = "예약 우선순위";
KO_HIGH_QUALITY_OVERRIDES["run.queuePriority"] = "우선순위 {priority}";

KO_HIGH_QUALITY_OVERRIDES["progress.runningIds"] = "{completed}/{total}\ub2e8\uacc4 \uc644\ub8cc, \uc2e4\ud589 \uc911: {ids}";
KO_HIGH_QUALITY_OVERRIDES["progress.readyIds"] = "{completed}/{total}\ub2e8\uacc4 \uc644\ub8cc, \uc2e4\ud589 \uac00\ub2a5: {ids}";
KO_HIGH_QUALITY_OVERRIDES["action.archiveAllProjects"] = "모두 보관";
KO_HIGH_QUALITY_OVERRIDES["action.archiveProject"] = "프로젝트 보관";
KO_HIGH_QUALITY_OVERRIDES["history.noFlowChart"] = "저장된 플로우 차트가 없습니다.";
KO_HIGH_QUALITY_OVERRIDES["history.noPrompt"] = "저장된 프롬프트가 없습니다.";
KO_HIGH_QUALITY_OVERRIDES["history.noSavedRuns"] = "아직 보관된 실행 기록이 없습니다.";
KO_HIGH_QUALITY_OVERRIDES["history.archivedAt"] = "보관 시각: {timestamp}";
KO_HIGH_QUALITY_OVERRIDES["message.projectArchived"] = "프로젝트를 history로 옮겼습니다.";
KO_HIGH_QUALITY_OVERRIDES["message.allProjectsArchived"] = "모든 프로젝트를 history로 옮겼습니다.";
KO_HIGH_QUALITY_OVERRIDES["prompt.confirmArchiveProject"] =
  "이 프로젝트를 history로 옮길까요? 관리 중인 문서, 로그, 상태는 history 아래에 보관되고 같은 디렉토리로 새 작업을 다시 시작할 수 있습니다.";
KO_HIGH_QUALITY_OVERRIDES["prompt.confirmArchiveAllProjects"] =
  "모든 프로젝트를 history로 옮길까요? 각 프로젝트의 문서, 로그, 상태는 보관되고 원본 작업 디렉토리는 그대로 유지됩니다.";

KO_HIGH_QUALITY_OVERRIDES["action.deleteAllProjects"] = "모두 삭제";
KO_HIGH_QUALITY_OVERRIDES["action.deleteArchivedRun"] = "보관본 삭제";
KO_HIGH_QUALITY_OVERRIDES["action.deleteProject"] = "프로젝트 삭제";
KO_HIGH_QUALITY_OVERRIDES["message.historyEntryDeleted"] = "보관된 실행 기록을 삭제했습니다.";
KO_HIGH_QUALITY_OVERRIDES["prompt.confirmDeleteHistoryEntry"] =
  "이 보관된 실행 기록을 완전히 삭제할까요? history 아래의 관리 문서, 로그, 리포트, 상태가 모두 제거됩니다.";

KO_HIGH_QUALITY_OVERRIDES["message.commandQueued"] = "{command} 작업을 대기열에 추가했습니다. {position}번째로 실행됩니다.";
KO_HIGH_QUALITY_OVERRIDES["message.commandCancelled"] = "{command} 예약을 취소했습니다.";
KO_HIGH_QUALITY_OVERRIDES["status.queued"] = "대기열에 있음";
KO_HIGH_QUALITY_OVERRIDES["status.queuedWithDetail"] = "대기열에 있음: {detail}";

const STATIC_LANGUAGE_PACKS = new Map(
  ["en", "ko"].map((language) => [
    language,
    {
      ...(STRINGS[language] || {}),
      ...(language === "ko" ? KO_HIGH_QUALITY_OVERRIDES : {}),
    },
  ]),
);

let externalLocaleModulesPromise = null;
const loadedDynamicLanguagePacks = new Map();
const pendingDynamicLanguagePacks = new Map();

function staticLanguagePack(language) {
  const normalized = normalizeLanguage(language);
  return STATIC_LANGUAGE_PACKS.get(normalized) || {};
}

function currentLanguagePack(language) {
  const normalized = normalizeLanguage(language);
  return loadedDynamicLanguagePacks.get(normalized) || staticLanguagePack(normalized);
}

async function loadExternalLocaleModules() {
  if (!externalLocaleModulesPromise) {
    externalLocaleModulesPromise = Promise.all([
      import("./generated_locale_data.js"),
      import("./manual_locale_overrides.js"),
    ]).then(([generatedModule, overridesModule]) => ({
      generated: generatedModule.GENERATED_STRINGS || {},
      overrides: overridesModule.MANUAL_LOCALE_OVERRIDES || {},
    }));
  }
  return externalLocaleModulesPromise;
}

function mergeDynamicLanguagePack(language, externalModules) {
  const normalized = normalizeLanguage(language);
  return {
    ...(STRINGS[normalized] || {}),
    ...(externalModules.generated?.[normalized] || {}),
    ...(externalModules.overrides?.[normalized] || {}),
    ...(normalized === "ko" ? KO_HIGH_QUALITY_OVERRIDES : {}),
  };
}

export function hasLanguageCatalog(language) {
  const normalized = normalizeLanguage(language);
  return STATIC_LANGUAGE_PACKS.has(normalized) || loadedDynamicLanguagePacks.has(normalized);
}

export async function ensureLanguageCatalog(language) {
  const normalized = normalizeLanguage(language);
  if (hasLanguageCatalog(normalized)) {
    return currentLanguagePack(normalized);
  }
  if (pendingDynamicLanguagePacks.has(normalized)) {
    return pendingDynamicLanguagePacks.get(normalized);
  }
  const pending = loadExternalLocaleModules()
    .then((externalModules) => {
      const merged = mergeDynamicLanguagePack(normalized, externalModules);
      loadedDynamicLanguagePacks.set(normalized, merged);
      pendingDynamicLanguagePacks.delete(normalized);
      return merged;
    })
    .catch((error) => {
      pendingDynamicLanguagePacks.delete(normalized);
      throw error;
    });
  pendingDynamicLanguagePacks.set(normalized, pending);
  return pending;
}

export function readStoredLanguagePreference(storageKey = "jakal-flow:language") {
  const storage = globalThis.localStorage;
  if (!storage || typeof storage.getItem !== "function") {
    return null;
  }
  try {
    const raw = storage.getItem(storageKey);
    if (raw === null) {
      return null;
    }
    return normalizeLanguage(JSON.parse(raw));
  } catch (_error) {
    return null;
  }
}

export function resolveInitialLanguage(sourceLanguage = null, storageKey = "jakal-flow:language") {
  return (
    readStoredLanguagePreference(storageKey)
    || detectInitialLanguage(sourceLanguage)
  );
}

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
  const value = currentLanguagePack(normalized)?.[key] ?? STRINGS.en[key];
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
  if (normalized === "debugging" || normalized === "running:debugging" || normalized === "running:parallel-debugging") {
    return translate(normalizedLanguage, "run.debugging");
  }
  if (normalized === "queued") {
    return translate(normalizedLanguage, "status.queued");
  }
  if (normalized.startsWith("queued:")) {
    const detail = humanizeToken(raw.slice(raw.indexOf(":") + 1));
    return translate(normalizedLanguage, "status.queuedWithDetail", {
      detail: normalizedLanguage === "ko" ? detail : titleCase(detail),
    });
  }
  if (normalized.startsWith("running:")) {
    const detail = humanizeToken(raw.slice(raw.indexOf(":") + 1));
    return translate(normalizedLanguage, "status.runningWithDetail", {
      detail: normalizedLanguage === "ko" ? detail : titleCase(detail),
    });
  }
  const key = `status.${normalized}`;
  const translated = currentLanguagePack(normalizedLanguage)?.[key] ?? STRINGS.en[key];
  if (translated) {
    return translated;
  }
  const humanized = humanizeToken(raw);
  if (!humanized) {
    return translate(normalizedLanguage, "status.unknown");
  }
  return normalizedLanguage === "ko" ? humanized : titleCase(humanized);
}
