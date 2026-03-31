// src/components/common/ExecutionFlowChart.jsx
import { memo, useId, useMemo } from "react";

// src/locale.js
var DEFAULT_LANGUAGE = "en";
var SUPPORTED_LANGUAGES = [
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
  "lv"
];
var LANGUAGE_OPTIONS = [
  { value: "ko", label: "\uD55C\uAD6D\uC5B4" },
  { value: "en", label: "English" }
];
var AVAILABLE_LANGUAGE_OPTIONS = [
  { value: "ko", label: "\uD55C\uAD6D\uC5B4" },
  { value: "en", label: "English" },
  { value: "ja", label: "\u65E5\u672C\u8A9E" },
  { value: "zh-cn", label: "\u7B80\u4F53\u4E2D\u6587" },
  { value: "zh-tw", label: "\u7E41\u9AD4\u4E2D\u6587" },
  { value: "es", label: "Espa\xF1ol" },
  { value: "fr", label: "Fran\xE7ais" },
  { value: "de", label: "Deutsch" },
  { value: "it", label: "Italiano" },
  { value: "pt-br", label: "Portugu\xEAs (Brasil)" },
  { value: "pt-pt", label: "Portugu\xEAs (Portugal)" },
  { value: "ru", label: "\u0420\u0443\u0441\u0441\u043A\u0438\u0439" },
  { value: "uk", label: "\u0423\u043A\u0440\u0430\u0457\u043D\u0441\u044C\u043A\u0430" },
  { value: "pl", label: "Polski" },
  { value: "nl", label: "Nederlands" },
  { value: "tr", label: "T\xFCrk\xE7e" },
  { value: "ar", label: "\u0627\u0644\u0639\u0631\u0628\u064A\u0629" },
  { value: "he", label: "\u05E2\u05D1\u05E8\u05D9\u05EA" },
  { value: "hi", label: "\u0939\u093F\u0928\u094D\u0926\u0940" },
  { value: "bn", label: "\u09AC\u09BE\u0982\u09B2\u09BE" },
  { value: "th", label: "\u0E44\u0E17\u0E22" },
  { value: "vi", label: "Ti\u1EBFng Vi\u1EC7t" },
  { value: "id", label: "Bahasa Indonesia" },
  { value: "ms", label: "Bahasa Melayu" },
  { value: "tl", label: "Filipino" },
  { value: "cs", label: "\u010Ce\u0161tina" },
  { value: "hu", label: "Magyar" },
  { value: "ro", label: "Rom\xE2n\u0103" },
  { value: "sv", label: "Svenska" },
  { value: "da", label: "Dansk" },
  { value: "fi", label: "Suomi" },
  { value: "no", label: "Norsk" },
  { value: "el", label: "\u0395\u03BB\u03BB\u03B7\u03BD\u03B9\u03BA\u03AC" },
  { value: "sk", label: "Sloven\u010Dina" },
  { value: "bg", label: "\u0411\u044A\u043B\u0433\u0430\u0440\u0441\u043A\u0438" },
  { value: "hr", label: "Hrvatski" },
  { value: "sr", label: "Srpski" },
  { value: "sl", label: "Sloven\u0161\u010Dina" },
  { value: "lt", label: "Lietuvi\u0173" },
  { value: "lv", label: "Latvie\u0161u" }
];
LANGUAGE_OPTIONS.splice(
  0,
  LANGUAGE_OPTIONS.length,
  { value: "ko", label: "\uD55C\uAD6D\uC5B4" },
  { value: "en", label: "English" }
);
AVAILABLE_LANGUAGE_OPTIONS.splice(
  0,
  AVAILABLE_LANGUAGE_OPTIONS.length,
  { value: "ko", label: "\uD55C\uAD6D\uC5B4" },
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
  { value: "lv", label: "Latvian" }
);
LANGUAGE_OPTIONS[0] = { value: "ko", label: "\uD55C\uAD6D\uC5B4" };
AVAILABLE_LANGUAGE_OPTIONS[0] = { value: "ko", label: "\uD55C\uAD6D\uC5B4" };
var LANGUAGE_ALIASES = {
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
  iw: "he"
};
var STRINGS = {
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
    "config.fastModeDescription": "When enabled, plan generation skips Planner Agent A and uses the faster planning path.",
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
    "field.model": "Execution Model",
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
    "option.providerEnsemble": "GPT + Gemini + Claude Ensemble",
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
    "option.useFastMode": "Faster Planning",
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
    "runtime.compactPlanning": "faster planning",
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
    "status.awaiting_checkpoint_approval": "Awaiting checkpoint approval",
    "status.awaiting_review": "Awaiting review",
    "status.cancelled": "Cancelled",
    "status.closeout_failed": "Closeout failed",
    "status.closed_out": "Closed out",
    "status.completed": "Completed",
    "status.failed": "Failed",
    "status.idle": "Idle",
    "status.integrating": "Integrating",
    "status.merging": "Merging",
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
    "status.syncing": "Syncing",
    "status.unknown": "Unknown",
    "tab.config": "Project Settings",
    "tab.aiChat": "AI Chat",
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
    "tool.tokenUsage": "Token Usage"
  },
  ko: {
    "action.add": "\uCD94\uAC00",
    "action.approveCheckpoint": "\uCCB4\uD06C\uD3EC\uC778\uD2B8 \uC2B9\uC778",
    "action.browse": "\uCC3E\uC544\uBCF4\uAE30",
    "action.cancelReservation": "\uC608\uC57D \uCDE8\uC18C",
    "action.closeout": "\uB9C8\uAC10",
    "action.delete": "\uC0AD\uC81C",
    "action.dismiss": "\uB2EB\uAE30",
    "action.down": "\uC544\uB798\uB85C",
    "action.generate": "\uC0DD\uC131",
    "action.generatePlan": "\uACC4\uD68D \uC0DD\uC131",
    "action.new": "\uC0C8\uB85C \uB9CC\uB4E4\uAE30",
    "action.refresh": "\uC0C8\uB85C\uACE0\uCE68",
    "action.reset": "\uCD08\uAE30\uD654",
    "action.run": "\uC2E4\uD589",
    "action.runRemaining": "\uB0A8\uC740 \uB2E8\uACC4 \uC2E4\uD589",
    "action.save": "\uC800\uC7A5",
    "action.saveConfiguration": "\uC124\uC815 \uC800\uC7A5",
    "action.saveProgramSettings": "\uD504\uB85C\uADF8\uB7A8 \uC124\uC815 \uC800\uC7A5",
    "action.saveLocal": "\uB85C\uCEEC \uC800\uC7A5",
    "action.stop": "\uC911\uC9C0",
    "action.up": "\uC704\uB85C",
    "common.branch": "\uBE0C\uB79C\uCE58",
    "common.connected": "\uC5F0\uACB0\uB428",
    "common.filter": "\uD544\uD130",
    "common.input": "\uC785\uB825",
    "common.language": "\uC5B8\uC5B4",
    "common.localOnly": "\uB85C\uCEEC \uC804\uC6A9",
    "common.no": "\uC544\uB2C8\uC624",
    "common.none": "\uC5C6\uC74C",
    "common.off": "\uB054",
    "common.on": "\uCF2C",
    "common.output": "\uCD9C\uB825",
    "common.project": "\uD504\uB85C\uC81D\uD2B8",
    "common.repoUrl": "\uC800\uC7A5\uC18C URL",
    "common.status": "\uC0C1\uD0DC",
    "common.total": "\uD569\uACC4",
    "common.unknown": "\uC54C \uC218 \uC5C6\uC74C",
    "common.unavailable": "\uC0AC\uC6A9\uD560 \uC218 \uC5C6\uC74C",
    "common.verification": "\uAC80\uC99D",
    "common.yes": "\uC608",
    "config.developerMode": "\uAC1C\uBC1C\uC790 \uBAA8\uB4DC",
    "config.developerModeDescription": "\uB514\uBC84\uAE45\uACFC \uC0AC\uC6A9\uC790 \uC9C0\uC815 \uC2E4\uD589\uC744 \uC704\uD55C \uACE0\uAE09 \uB7F0\uD0C0\uC784 \uC81C\uC5B4\uC785\uB2C8\uB2E4.",
    "config.executionModel": "\uC2E4\uD589 \uBAA8\uB378",
    "config.fastModeDescription": "\uD65C\uC131\uD654\uD558\uBA74 \uACC4\uD68D \uC0DD\uC131 \uC2DC\uAC04\uC744 \uC904\uC774\uAE30 \uC704\uD574 Planner Agent A\uB97C \uAC74\uB108\uB6F0\uACE0 \uBE60\uB978 \uACC4\uD68D \uACBD\uB85C\uB97C \uC0AC\uC6A9\uD569\uB2C8\uB2E4.",
    "config.githubConnection": "GitHub \uC5F0\uACB0",
    "config.githubConnectionDescription": "\uB85C\uCEEC \uC800\uC7A5\uC18C\uC640 GitHub \uC5F0\uACB0 \uC800\uC7A5\uC18C\uB97C \uBA85\uC2DC\uC801\uC73C\uB85C \uC720\uC9C0\uD569\uB2C8\uB2E4.",
    "config.githubUrl": "GitHub URL",
    "config.maxPlannedSteps": "\uCD5C\uB300 \uACC4\uD68D \uB2E8\uACC4 \uC218",
    "config.projectConfiguration": "\uD504\uB85C\uC81D\uD2B8 \uC124\uC815",
    "config.projectConfigurationDescription": "\uC800\uC7A5\uC18C \uC124\uC815\uC740 \uC5EC\uAE30\uC11C \uACC4\uC18D \uC218\uC815\uD560 \uC218 \uC788\uC5B4, \uC791\uC5C5 \uCF58\uC194\uC774 \uB7F0\uD0C0\uC784\uC744 \uC228\uAE30\uC9C0 \uC54A\uC73C\uBA74\uC11C\uB3C4 \uACA9\uB9AC\uB41C \uC6CC\uD06C\uC2A4\uD398\uC774\uC2A4\uB97C \uAD00\uB9AC\uD560 \uC218 \uC788\uC2B5\uB2C8\uB2E4.",
    "config.projectName": "\uD504\uB85C\uC81D\uD2B8 \uC774\uB984",
    "config.programSettingsMoved": "\uD504\uB85C\uADF8\uB7A8 \uC804\uCCB4\uC5D0 \uC801\uC6A9\uB418\uB294 \uC2E4\uD589 \uC124\uC815\uC740 \uC0C1\uB2E8 \uBC14\uC758 \uD504\uB85C\uADF8\uB7A8 \uC124\uC815\uC73C\uB85C \uC62E\uACBC\uC2B5\uB2C8\uB2E4.",
    "config.useExistingOrigin": "\uC774 \uD3F4\uB354\uC758 \uAE30\uC874 origin \uC0AC\uC6A9",
    "config.manualGithubUrl": "GitHub \uC800\uC7A5\uC18C URL \uC9C1\uC811 \uC785\uB825",
    "config.noGithubYet": "\uC544\uC9C1 GitHub\uC5D0 \uC5F0\uACB0\uD558\uC9C0 \uC54A\uC74C",
    "config.workingDirectory": "\uC791\uC5C5 \uB514\uB809\uD130\uB9AC",
    "dashboard.checkpoint": "\uCCB4\uD06C\uD3EC\uC778\uD2B8",
    "dashboard.checkpointPending": "\uCCB4\uD06C\uD3EC\uC778\uD2B8 \uB300\uAE30",
    "dashboard.dashboard": "\uB300\uC2DC\uBCF4\uB4DC",
    "dashboard.inputTokens": "\uC785\uB825 \uD1A0\uD070",
    "dashboard.lastSafeRevision": "\uB9C8\uC9C0\uB9C9 \uC548\uC804 \uB9AC\uBE44\uC804",
    "dashboard.noCheckpointWaiting": "\uAC80\uD1A0\uB97C \uAE30\uB2E4\uB9AC\uB294 \uCCB4\uD06C\uD3EC\uC778\uD2B8\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4.",
    "dashboard.noProjectSelected": "\uC120\uD0DD\uB41C \uD504\uB85C\uC81D\uD2B8\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4",
    "dashboard.origin": "\uC6D0\uACA9 \uC800\uC7A5\uC18C",
    "dashboard.outputTokens": "\uCD9C\uB825 \uD1A0\uD070",
    "dashboard.remainingSteps": "\uB0A8\uC740 \uB2E8\uACC4",
    "dashboard.rateLimits": "\uC0AC\uC6A9\uB7C9 \uD55C\uB3C4",
    "dashboard.runtime": "\uB7F0\uD0C0\uC784",
    "dashboard.targetBlock": "\uB300\uC0C1 \uBE14\uB85D {block}",
    "field.approvalMode": "\uC2B9\uC778 \uBAA8\uB4DC",
    "field.checkpointInterval": "\uCCB4\uD06C\uD3EC\uC778\uD2B8 \uAC04\uACA9",
    "field.codexInstruction": "Codex \uC9C0\uC2DC\uBB38",
    "field.codexPath": "Codex \uACBD\uB85C",
    "field.customModelSlug": "\uC0AC\uC6A9\uC790 \uC9C0\uC815 \uBAA8\uB378 \uC2AC\uB7EC\uADF8",
    "field.dependsOn": "\uC120\uD589 \uB2E8\uACC4",
    "field.description": "\uC124\uBA85",
    "field.executionMode": "\uC2E4\uD589 \uBAA8\uB4DC",
    "field.extraPrompt": "\uCD94\uAC00 \uD504\uB86C\uD504\uD2B8",
    "field.gptReasoning": "GPT \uCD94\uB860",
    "field.localProvider": "\uB85C\uCEEC \uC81C\uACF5\uC790",
    "field.model": "\uC2E4\uD589 \uBAA8\uB378",
    "field.modelProvider": "\uBAA8\uB378 \uC81C\uACF5\uC790",
    "field.providerBaseUrl": "Provider Base URL",
    "field.providerApiKeyEnv": "API \uD0A4 \uD658\uACBD \uBCC0\uC218",
    "field.billingMode": "\uACFC\uAE08 \uBC29\uC2DD",
    "field.inputTokenRate": "\uC785\uB825 $ / 100\uB9CC",
    "field.outputTokenRate": "\uCD9C\uB825 $ / 100\uB9CC",
    "field.reasoningTokenRate": "\uCD94\uB860 $ / 100\uB9CC",
    "field.perPassRate": "\uD328\uC2A4\uB2F9 USD",
    "field.ownedPaths": "\uC18C\uC720 \uACBD\uB85C",
    "field.parallelGroup": "\uBCD1\uB82C \uADF8\uB8F9",
    "field.parallelWorkers": "\uBCD1\uB82C \uC6CC\uCEE4 \uC218",
    "field.parallelMemoryPerWorkerGiB": "\uC6CC\uCEE4\uB2F9 \uBA54\uBAA8\uB9AC (GiB)",
    "field.prompt": "\uD504\uB86C\uD504\uD2B8",
    "field.sandboxMode": "\uC0CC\uB4DC\uBC15\uC2A4 \uBAA8\uB4DC",
    "field.successCriteria": "\uC131\uACF5 \uAE30\uC900",
    "field.title": "\uC81C\uBAA9",
    "field.verificationCommand": "\uAC80\uC99D \uBA85\uB839\uC5B4",
    "history.history": "\uAE30\uB85D",
    "history.noEntries": "\uD56D\uBAA9\uC774 \uC5C6\uC2B5\uB2C8\uB2E4.",
    "history.noTaskTitle": "\uC791\uC5C5 \uC81C\uBAA9\uC774 \uC5C6\uC2B5\uB2C8\uB2E4",
    "history.noTestSummary": "\uD14C\uC2A4\uD2B8 \uC694\uC57D\uC774 \uC5C6\uC2B5\uB2C8\uB2E4",
    "history.recentActivity": "\uCD5C\uADFC \uD65C\uB3D9",
    "history.recentBlocks": "\uCD5C\uADFC \uBE14\uB85D",
    "message.checkpointApproved": "\uCCB4\uD06C\uD3EC\uC778\uD2B8\uB97C \uC2B9\uC778\uD588\uC2B5\uB2C8\uB2E4.",
    "message.closeoutAfterAllSteps": "\uBAA8\uB4E0 \uB2E8\uACC4\uAC00 \uC644\uB8CC\uB41C \uB4A4\uC5D0\uB9CC \uB9C8\uAC10\uC744 \uC2E4\uD589\uD560 \uC218 \uC788\uC2B5\uB2C8\uB2E4.",
    "message.commandCancelled": "{command} \uC791\uC5C5\uC744 \uCDE8\uC18C\uD588\uC2B5\uB2C8\uB2E4.",
    "message.commandCompleted": "{command} \uC791\uC5C5\uC774 \uC644\uB8CC\uB418\uC5C8\uC2B5\uB2C8\uB2E4.",
    "message.commandFailed": "{command} \uC791\uC5C5\uC774 \uC2E4\uD328\uD588\uC2B5\uB2C8\uB2E4.",
    "message.commandStarted": "{command} \uC791\uC5C5\uC744 \uC2DC\uC791\uD588\uC2B5\uB2C8\uB2E4.",
    "message.createPlanBeforeCloseout": "\uB9C8\uAC10\uC744 \uC2E4\uD589\uD558\uAE30 \uC804\uC5D0 \uC2E4\uD589 \uACC4\uD68D\uC744 \uB9CC\uB4E4\uACE0 \uC644\uB8CC\uD558\uC138\uC694.",
    "message.createStepBeforeRun": "\uBA3C\uC800 \uACC4\uD68D\uB41C \uB2E8\uACC4\uB97C \uD558\uB098 \uC774\uC0C1 \uB9CC\uB4E4\uAC70\uB098 \uCD94\uAC00\uD558\uC138\uC694.",
    "message.editRemainingSteps": "\uC774\uBBF8 \uC644\uB8CC\uB41C \uB2E8\uACC4\uAC00 \uC788\uC73C\uBBC0\uB85C \uB2E4\uC2DC \uC0DD\uC131\uD558\uC9C0 \uB9D0\uACE0 \uB0A8\uC740 \uB2E8\uACC4\uB97C \uC218\uC815\uD558\uC138\uC694.",
    "message.insertAfterPending": "\uC0C8 \uB2E8\uACC4\uB294 \uB300\uAE30 \uC911\uC778 \uB2E8\uACC4 \uB4A4\uC5D0\uB9CC \uB123\uC744 \uC218 \uC788\uC2B5\uB2C8\uB2E4. \uB05D\uC5D0 \uCD94\uAC00\uD558\uB824\uBA74 \uC120\uD0DD\uC744 \uD574\uC81C\uD558\uC138\uC694.",
    "message.noProjectOpen": "\uC5F4\uB9B0 \uD504\uB85C\uC81D\uD2B8\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4.",
    "message.onlyPendingDelete": "\uB300\uAE30 \uC911\uC778 \uB2E8\uACC4\uB9CC \uC0AD\uC81C\uD560 \uC218 \uC788\uC2B5\uB2C8\uB2E4.",
    "message.onlyPendingEdit": "\uB300\uAE30 \uC911\uC778 \uB2E8\uACC4\uB9CC \uC218\uC815\uD560 \uC218 \uC788\uC2B5\uB2C8\uB2E4.",
    "message.onlyPendingMove": "\uB300\uAE30 \uC911\uC778 \uB2E8\uACC4\uB9CC \uC21C\uC11C\uB97C \uBC14\uAFC0 \uC218 \uC788\uC2B5\uB2C8\uB2E4.",
    "message.openProjectFirst": "\uBA3C\uC800 \uD504\uB85C\uC81D\uD2B8\uB97C \uC5EC\uC138\uC694.",
    "message.openOrCreateProjectFirst": "\uBA3C\uC800 \uD504\uB85C\uC81D\uD2B8\uB97C \uC5F4\uAC70\uB098 \uB9CC\uB4DC\uC138\uC694.",
    "message.pendingMoveRange": "\uB300\uAE30 \uB2E8\uACC4\uB294 \uC544\uC9C1 \uC2DC\uC791\uD558\uC9C0 \uC54A\uC740 \uAD6C\uAC04 \uC548\uC5D0\uC11C\uB9CC \uC774\uB3D9\uD560 \uC218 \uC788\uC2B5\uB2C8\uB2E4.",
    "message.planReset": "\uACC4\uD68D\uC744 \uCD08\uAE30\uD654\uD588\uC2B5\uB2C8\uB2E4.",
    "message.planSaved": "\uACC4\uD68D\uC744 \uC800\uC7A5\uD588\uC2B5\uB2C8\uB2E4.",
    "message.prepareProjectFirst": "\uBA3C\uC800 \uD504\uB85C\uC81D\uD2B8\uB97C \uC900\uBE44\uD558\uAC70\uB098 \uC5EC\uC138\uC694.",
    "message.projectConfigurationSaved": "\uD504\uB85C\uC81D\uD2B8 \uC124\uC815\uC744 \uC800\uC7A5\uD588\uC2B5\uB2C8\uB2E4.",
    "message.projectDeleted": "jakal-flow\uC5D0\uC11C \uD504\uB85C\uC81D\uD2B8\uB97C \uC81C\uAC70\uD588\uC2B5\uB2C8\uB2E4.",
    "message.programSettingsSaved": "\uD504\uB85C\uADF8\uB7A8 \uC124\uC815\uC744 \uC800\uC7A5\uD588\uC2B5\uB2C8\uB2E4.",
    "message.projectReloaded": "\uD504\uB85C\uC81D\uD2B8\uB97C \uB2E4\uC2DC \uBD88\uB7EC\uC654\uC2B5\uB2C8\uB2E4.",
    "message.projectStateRefreshed": "\uD504\uB85C\uC81D\uD2B8 \uC0C1\uD0DC\uB97C \uC0C8\uB85C\uACE0\uCE68\uD588\uC2B5\uB2C8\uB2E4.",
    "message.promptRequired": "\uACC4\uD68D\uC744 \uC0DD\uC131\uD558\uB824\uBA74 \uD504\uB86C\uD504\uD2B8\uAC00 \uD544\uC694\uD569\uB2C8\uB2E4.",
    "message.runStateRefreshed": "\uC2E4\uD589 \uC0C1\uD0DC\uB97C \uC0C8\uB85C\uACE0\uCE68\uD588\uC2B5\uB2C8\uB2E4.",
    "message.selectPendingStepFirst": "\uBA3C\uC800 \uB300\uAE30 \uC911\uC778 \uB2E8\uACC4\uB97C \uC120\uD0DD\uD558\uC138\uC694.",
    "message.selectStepFirst": "\uBA3C\uC800 \uB2E8\uACC4\uB97C \uC120\uD0DD\uD558\uC138\uC694.",
    "message.stepUpdatedLocally": "\uB2E8\uACC4\uB97C \uB85C\uCEEC\uC5D0\uC11C \uC5C5\uB370\uC774\uD2B8\uD588\uC2B5\uB2C8\uB2E4. \uBCC0\uACBD \uC0AC\uD56D\uC744 \uC720\uC9C0\uD558\uB824\uBA74 \uACC4\uD68D\uC744 \uC800\uC7A5\uD558\uC138\uC694.",
    "message.stopRequested": "\uD604 \uB2E8\uACC4\uB97C \uBB34\uC2DC\uD558\uACE0 \uC911\uC9C0\uD558\uB3C4\uB85D \uC694\uCCAD\uD588\uC2B5\uB2C8\uB2E4.",
    "option.allowPushAfterSafeRuns": "\uC548\uC804 \uC2E4\uD589 \uD6C4 push \uD5C8\uC6A9",
    "option.executionParallel": "\uBCD1\uB82C",
    "option.executionSerial": "\uC9C1\uB82C",
    "option.localProviderLmStudio": "LM Studio",
    "option.localProviderOllama": "Ollama",
    "option.providerEnsemble": "GPT + Gemini + Claude \uC559\uC0C1\uBE14",
    "option.providerOpenAI": "OpenAI / Codex \uD074\uB77C\uC6B0\uB4DC",
    "option.providerOpenRouter": "OpenRouter",
    "option.providerOpenCDK": "OpenCDK",
    "option.providerLocalCompatible": "\uB85C\uCEEC OpenAI \uD638\uD658",
    "option.providerOSS": "\uB85C\uCEEC OSS",
    "option.billingIncluded": "\uD3EC\uD568\uB428 / 0\uC6D0",
    "option.billingToken": "\uD1A0\uD070 \uB2E8\uAC00",
    "option.billingPerPass": "\uD328\uC2A4 \uB2E8\uAC00",
    "option.requireCheckpointApproval": "\uCCB4\uD06C\uD3EC\uC778\uD2B8 \uC2B9\uC778 \uD544\uC694",
    "option.useFastMode": "\uBE60\uB978 \uACC4\uD68D \uC0DD\uC131",
    "project.none": "\uD504\uB85C\uC81D\uD2B8 \uC5C6\uC74C",
    "prompt.confirmCloseout": "\uC9C0\uAE08 \uCD5C\uC885 \uB9C8\uAC10\uC744 \uC2E4\uD589\uD560\uAE4C\uC694? \uAC00\uB2A5\uD55C \uACBD\uC6B0 \uCD5C\uC885 \uC815\uB9AC, \uAC80\uC99D, \uC2A4\uBAA8\uD06C \uCCB4\uD06C, \uC778\uC218\uC778\uACC4\uB97C \uC218\uD589\uD569\uB2C8\uB2E4.",
    "prompt.confirmCancelReservation": "\uB300\uAE30\uC5F4\uC5D0 \uC788\uB294 \uC774 \uC608\uC57D\uC744 \uCDE8\uC18C\uD560\uAE4C\uC694? \uD504\uB85C\uC81D\uD2B8 \uC0C1\uD0DC\uB294 \uADF8\uB300\uB85C \uC720\uC9C0\uB418\uACE0 \uB098\uC911\uC5D0 \uB2E4\uC2DC \uC608\uC57D\uD560 \uC218 \uC788\uC2B5\uB2C8\uB2E4.",
    "prompt.confirmRegeneratePlan": "\uD604\uC7AC \uC2DC\uC791 \uC804 \uACC4\uD68D\uC744 Codex\uAC00 \uC0C8\uB85C \uC0DD\uC131\uD55C \uACC4\uD68D\uC73C\uB85C \uBC14\uAFC0\uAE4C\uC694?",
    "prompt.confirmResetPlan": "\uC800\uC7A5\uB41C \uD504\uB86C\uD504\uD2B8\uB97C \uCD08\uAE30\uD654\uD558\uACE0 \uC774 \uD504\uB85C\uC81D\uD2B8\uC758 \uBAA8\uB4E0 \uC2E4\uD589 \uB2E8\uACC4\uB97C \uC81C\uAC70\uD560\uAE4C\uC694?",
    "prompt.confirmDeleteProject": "\uC774 \uD504\uB85C\uC81D\uD2B8\uB97C jakal-flow\uC5D0\uC11C \uC81C\uAC70\uD560\uAE4C\uC694? \uAD00\uB9AC \uC911\uC778 \uBB38\uC11C, \uB85C\uADF8, \uC0C1\uD0DC\uB9CC \uC0AD\uC81C\uB418\uACE0 \uC6D0\uBCF8 \uC800\uC7A5\uC18C \uD3F4\uB354\uB294 \uADF8\uB300\uB85C \uB461\uB2C8\uB2E4.",
    "preset.auto": "\uC790\uB3D9",
    "preset.highOnly": "\uB192\uC74C\uB9CC",
    "preset.lowOnly": "\uB0AE\uC74C\uB9CC",
    "preset.mediumOnly": "\uC911\uAC04\uB9CC",
    "preset.xhighOnly": "\uB9E4\uC6B0 \uB192\uC74C\uB9CC",
    "reasoning.high": "\uB192\uC74C",
    "reasoning.low": "\uB0AE\uC74C",
    "reasoning.medium": "\uC911\uAC04",
    "reasoning.xhigh": "\uB9E4\uC6B0 \uB192\uC74C",
    "reports.attemptHistory": "\uC2DC\uB3C4 \uAE30\uB85D",
    "reports.blockReview": "\uBE14\uB85D \uB9AC\uBDF0",
    "reports.closeoutReport": "\uB9C8\uAC10 \uBCF4\uACE0\uC11C",
    "reports.historyEmpty": "\uC544\uC9C1 \uC2DC\uB3C4 \uAE30\uB85D\uC774 \uC5C6\uC2B5\uB2C8\uB2E4.",
    "reports.json": "\uCD5C\uC2E0 \uBCF4\uACE0\uC11C JSON",
    "reports.noBlockReview": "\uC544\uC9C1 \uBE14\uB85D \uB9AC\uBDF0\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4.",
    "reports.noCloseoutReport": "\uC544\uC9C1 \uB9C8\uAC10 \uBCF4\uACE0\uC11C\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4.",
    "reports.reports": "\uBCF4\uACE0\uC11C",
    "run.closeout": "\uB9C8\uAC10",
    "run.done": "\uC644\uB8CC",
    "run.dagLayer": "\uB808\uC774\uC5B4 {index}",
    "run.executionMode": "\uC2E4\uD589 \uBAA8\uB4DC",
    "run.executionFlow": "\uC2E4\uD589 \uD750\uB984",
    "run.executionTree": "\uC2E4\uD589 \uD2B8\uB9AC",
    "run.flow": "\uD750\uB984",
    "run.flowChart": "\uD750\uB984\uB3C4",
    "run.newPendingStep": "\uC0C8 \uB300\uAE30 \uB2E8\uACC4",
    "run.noReservations": "\uC608\uC57D\uB41C \uC2E4\uD589\uC774 \uC5C6\uC2B5\uB2C8\uB2E4.",
    "run.noSteps": "\uC544\uC9C1 \uB2E8\uACC4\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4. \uACC4\uD68D\uC744 \uC0DD\uC131\uD558\uAC70\uB098 \uC9C1\uC811 \uCD94\uAC00\uD558\uC138\uC694.",
    "run.noSummary": "\uC694\uC57D \uC5C6\uC74C",
    "run.parallelReady": "\uC2E4\uD589 \uAC00\uB2A5 \uB178\uB4DC",
    "run.queuePosition": "\uB300\uAE30 \uC21C\uBC88 #{position}",
    "run.reasoning": "\uCD94\uB860 {effort}",
    "run.reservations": "\uC608\uC57D",
    "run.selectStep": "\uB2E8\uACC4\uB97C \uC120\uD0DD\uD558\uC138\uC694.",
    "run.selectedStep": "\uC120\uD0DD\uB41C \uB2E8\uACC4",
    "run.stopAfterStep": "\uD604 \uB2E8\uACC4\uB97C \uBB34\uC2DC\uD558\uACE0 \uC911\uC9C0",
    "run.stepCheckpointDescription": "\uC0AC\uC6A9\uC790\uC5D0\uAC8C \uBCF4\uC5EC\uC904 \uCCB4\uD06C\uD3EC\uC778\uD2B8\uB97C \uC124\uBA85\uD558\uC138\uC694.",
    "run.stepCodexDescription": "\uC774 \uCCB4\uD06C\uD3EC\uC778\uD2B8\uC5D0\uC11C Codex\uAC00 \uC218\uD589\uD560 \uAD6C\uD604 \uC791\uC5C5\uC744 \uC124\uBA85\uD558\uC138\uC694.",
    "run.stepSuccessCriteria": "\uC124\uC815\uB41C \uAC80\uC99D \uBA85\uB839\uC5B4\uAC00 \uC131\uACF5\uC801\uC73C\uB85C \uC2E4\uD589\uB418\uC5B4\uC57C \uD569\uB2C8\uB2E4.",
    "runtime.modelSummary": "{model} | \uCD94\uB860 {effort}",
    "runtime.noModelSelected": "\uC120\uD0DD\uB41C \uBAA8\uB378\uC774 \uC5C6\uC2B5\uB2C8\uB2E4",
    "runtime.compactPlanning": "\uBE60\uB978 \uACC4\uD68D",
    "dashboard.estimatedRemaining": "\uC608\uC0C1 \uB0A8\uC740 \uC2DC\uAC04",
    "dashboard.estimatedCost": "\uC608\uC0C1 \uBE44\uC6A9",
    "dashboard.actualCost": "\uC2E4\uBE44\uC6A9",
    "run.estimatedRemaining": "\uC608\uC0C1 \uB0A8\uC740 \uC2DC\uAC04",
    "run.estimatedTotal": "\uC608\uC0C1 \uC804\uCCB4 \uC2DC\uAC04",
    "run.stepEstimate": "\uB2E8\uACC4 \uC608\uC0C1\uCE58",
    "run.estimatedCost": "\uC608\uC0C1 \uBE44\uC6A9",
    "run.currentElapsed": "\uACBD\uACFC",
    "run.currentRemaining": "\uB0A8\uC740 \uC2DC\uAC04",
    "tool.estimatedCost": "\uC608\uC0C1 \uBE44\uC6A9",
    "config.providerPresetModelHint": "\uC774 \uC81C\uACF5\uC790\uB294 \uAE30\uBCF8 \uBAA8\uB378 \uCE74\uD0C8\uB85C\uADF8\uB97C \uC720\uC9C0\uD558\uBA70 \uD604\uC7AC \uD504\uB9AC\uC14B \uD750\uB984\uC744 \uADF8\uB300\uB85C \uC0AC\uC6A9\uD560 \uC218 \uC788\uC2B5\uB2C8\uB2E4.",
    "config.customProviderModelHint": "\uC774 \uC81C\uACF5\uC790\uB098 \uB85C\uCEEC \uC11C\uBC84\uAC00 \uB178\uCD9C\uD558\uB294 \uC815\uD655\uD55C \uBAA8\uB378 \uC2AC\uB7EC\uADF8\uB97C \uC785\uB825\uD558\uC138\uC694.",
    "settings.application": "\uD504\uB85C\uADF8\uB7A8",
    "settings.applicationDescription": "\uB370\uC2A4\uD06C\uD1B1 \uC178 \uC790\uCCB4\uC5D0 \uC801\uC6A9\uB418\uB294 \uC124\uC815\uC785\uB2C8\uB2E4.",
    "settings.executionDefaults": "\uC2E4\uD589 \uAE30\uBCF8\uAC12",
    "settings.executionDefaultsDescription": "\uD504\uB85C\uC81D\uD2B8 \uC804\uBC18\uC5D0 \uACF5\uD1B5\uC73C\uB85C \uC4F8 \uC2E4\uD589 \uAE30\uBCF8\uAC12\uC785\uB2C8\uB2E4.",
    "settings.dashboardPreferences": "\uB300\uC2DC\uBCF4\uB4DC",
    "settings.dashboardPreferencesDescription": "\uB300\uC2DC\uBCF4\uB4DC\uC5D0\uC11C \uACC4\uC18D \uBCF4\uC5EC\uB458 \uCE74\uB4DC\uB9CC \uC120\uD0DD\uD558\uC138\uC694.",
    "settings.programSettings": "\uD504\uB85C\uADF8\uB7A8 \uC124\uC815",
    "settings.programSettingsDescription": "\uD504\uB85C\uC81D\uD2B8\uC640 \uBB34\uAD00\uD55C \uB370\uC2A4\uD06C\uD1B1 \uC124\uC815\uACFC \uC2E4\uD589 \uAE30\uBCF8\uAC12\uC744 \uD55C \uACF3\uC5D0\uC11C \uAD00\uB9AC\uD569\uB2C8\uB2E4.",
    "sidebar.checkpoints": "\uCCB4\uD06C\uD3EC\uC778\uD2B8",
    "sidebar.emptyProjects": "\uAD00\uB9AC \uC911\uC778 \uD504\uB85C\uC81D\uD2B8\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4.",
    "sidebar.emptyWorkspace": "\uC544\uC9C1 \uC6CC\uD06C\uC2A4\uD398\uC774\uC2A4 \uD2B8\uB9AC\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4.",
    "sidebar.explorer": "\uD0D0\uC0C9\uAE30",
    "sidebar.noGithubOrigin": "\uC774 \uD504\uB85C\uC81D\uD2B8\uC5D0\uB294 GitHub origin\uC774 \uC124\uC815\uB418\uC5B4 \uC788\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4.",
    "sidebar.noProjectSummary": "\uAD00\uB9AC \uC0C1\uD0DC\uB97C \uD655\uC778\uD558\uB824\uBA74 \uD504\uB85C\uC81D\uD2B8\uB97C \uC120\uD0DD\uD558\uC138\uC694.",
    "sidebar.noRecordedCheckpoints": "\uAE30\uB85D\uB41C \uCCB4\uD06C\uD3EC\uC778\uD2B8\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4.",
    "sidebar.repositoryLink": "\uC800\uC7A5\uC18C \uC5F0\uACB0",
    "sidebar.searchFiles": "\uD30C\uC77C \uAC80\uC0C9",
    "sidebar.searchProjects": "\uD504\uB85C\uC81D\uD2B8 \uAC80\uC0C9",
    "sidebar.selectedSummary": "\uC120\uD0DD\uB41C \uC694\uC57D",
    "sidebar.targetBlock": "\uB300\uC0C1 \uBE14\uB85D {block}",
    "status.awaiting_review": "\uAC80\uD1A0 \uB300\uAE30",
    "status.cancelled": "\uCDE8\uC18C\uB428",
    "status.closeout_failed": "\uB9C8\uAC10 \uC2E4\uD328",
    "status.closed_out": "\uB9C8\uAC10 \uC644\uB8CC",
    "status.completed": "\uC644\uB8CC",
    "status.failed": "\uC2E4\uD328",
    "status.idle": "\uB300\uAE30",
    "status.not_started": "\uC2DC\uC791 \uC804",
    "status.paused_for_review": "\uAC80\uD1A0 \uB300\uAE30 \uC911\uC9C0",
    "status.pending": "\uB300\uAE30",
    "status.plan_completed": "\uACC4\uD68D \uC644\uB8CC",
    "status.plan_ready": "\uACC4\uD68D \uC900\uBE44\uB428",
    "status.ready": "\uC900\uBE44\uB428",
    "status.running": "\uC2E4\uD589 \uC911",
    "status.runningWithDetail": "\uC2E4\uD589 \uC911: {detail}",
    "status.setup_ready": "\uC124\uC815 \uC644\uB8CC",
    "status.syncing": "\uB3D9\uAE30\uD654 \uC911",
    "status.unknown": "\uC54C \uC218 \uC5C6\uC74C",
    "tab.config": "\uD504\uB85C\uC81D\uD2B8 \uC124\uC815",
    "tab.aiChat": "AI Chat",
    "tab.dashboard": "\uB300\uC2DC\uBCF4\uB4DC",
    "tab.flow": "\uD750\uB984",
    "tab.history": "\uAE30\uB85D",
    "tab.programSettings": "\uD504\uB85C\uADF8\uB7A8",
    "tab.reports": "\uBCF4\uACE0\uC11C",
    "test.failed": "\uC2E4\uD328",
    "test.noRuns": "\uC544\uC9C1 \uAE30\uB85D\uB41C \uD14C\uC2A4\uD2B8 \uC2E4\uD589\uC774 \uC5C6\uC2B5\uB2C8\uB2E4.",
    "test.passed": "\uC131\uACF5",
    "test.result": "\uD14C\uC2A4\uD2B8 \uACB0\uACFC",
    "test.run": "\uD14C\uC2A4\uD2B8 \uC2E4\uD589",
    "toolbar.bottom": "\uD558\uB2E8",
    "toolbar.plan": "\uACC4\uD68D",
    "toolbar.programSettings": "\uD504\uB85C\uADF8\uB7A8 \uC124\uC815",
    "toolbar.toggleBottom": "\uB3C4\uAD6C \uCC3D \uD1A0\uAE00",
    "tool.eventJson": "\uC774\uBCA4\uD2B8 JSON",
    "tool.gitStatus": "Git",
    "usage.codexSpark": "Codex Spark",
    "usage.window5h": "5\uC2DC\uAC04 \uC0AC\uC6A9\uB7C9",
    "usage.window7d": "7\uC77C \uC0AC\uC6A9\uB7C9",
    "usage.windowSummary": "{used}% \uC0AC\uC6A9, {remaining}% \uB0A8\uC74C, {resetsAt} \uC7AC\uC124\uC815",
    "tool.tokenUsage": "\uD1A0\uD070 \uC0AC\uC6A9\uB7C9"
  }
};
STRINGS.en["action.deleteAll"] = "Delete All";
STRINGS.en["config.advancedModelSettings"] = "Advanced Settings";
STRINGS.en["config.advancedModelSettingsDescription"] = "Advanced Settings";
STRINGS.en["message.allProjectsDeleted"] = "All projects removed from jakal-flow.";
STRINGS.en["option.generateWordReport"] = "Word Report Creation";
STRINGS.en["option.lightMode"] = "Light Mode";
STRINGS.en["option.developerMode"] = "Developer Mode";
STRINGS.en["option.saveProjectLogs"] = "Save Project Activity Logs";
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
STRINGS.en["progress.integratingIds"] = "Completed {completed}/{total} steps, integrating: {ids}";
STRINGS.en["progress.runningAndIntegratingIds"] = "Completed {completed}/{total} steps, running: {runningIds}; integrating: {integratingIds}";
STRINGS.en["progress.readyIds"] = "Completed {completed}/{total} steps, ready: {ids}";
STRINGS.en["action.backgroundJob"] = "Background Job";
STRINGS.en["run.closeoutRunning"] = "Running closeout";
STRINGS.en["run.completedStepsSummary"] = "{completed}/{total} steps completed";
STRINGS.en["run.liveRun"] = "Live Run";
STRINGS.en["run.planGeneration"] = "Generating execution plan";
STRINGS.en["run.planningStage"] = "Planning stage {current}/{total}";
STRINGS.en["run.planningStageWithStatus"] = "Planning stage {current}/{total}, {status}";
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
STRINGS.en["prompt.confirmDeleteAllProjects"] = "Remove all projects from jakal-flow? The managed docs, logs, and state will be deleted, but the original repository folders will stay in place.";
STRINGS.en["sidebar.projectContextDelete"] = "Right-click to open project actions";
STRINGS.ko["action.deleteAll"] = "\uC804\uBD80 \uC0AD\uC81C";
STRINGS.ko["config.advancedModelSettings"] = "\uACE0\uAE09 \uC124\uC815";
STRINGS.ko["config.advancedModelSettingsDescription"] = "\uACE0\uAE09 \uC124\uC815";
STRINGS.ko["message.allProjectsDeleted"] = "\uBAA8\uB4E0 \uD504\uB85C\uC81D\uD2B8\uB97C \uC81C\uAC70\uD588\uC2B5\uB2C8\uB2E4.";
STRINGS.ko["option.generateWordReport"] = "Word \uBCF4\uACE0\uC11C \uC81C\uC791";
STRINGS.ko["option.lightMode"] = "\uBC1D\uC740 \uBAA8\uB4DC";
STRINGS.ko["option.developerMode"] = "\uAC1C\uBC1C\uC790 \uBAA8\uB4DC";
STRINGS.ko["option.saveProjectLogs"] = "\uD504\uB85C\uC81D\uD2B8 \uC791\uC5C5 \uB85C\uADF8 \uC800\uC7A5";
STRINGS.ko["dashboard.codexPlan"] = "Codex \uC694\uAE08\uC81C";
STRINGS.ko["dashboard.codexUsage"] = "Codex \uC0AC\uC6A9\uB7C9";
STRINGS.ko["common.auth"] = "\uC778\uC99D \uBC29\uC2DD";
STRINGS.ko["common.account"] = "\uACC4\uC815";
STRINGS.ko["config.additionalModels"] = "\uCD94\uAC00 \uC9C0\uC6D0 \uBAA8\uB378";
STRINGS.ko["runtime.modelSummaryGeneric"] = "{model} | \uCD94\uB860 {effort}";
STRINGS.ko["progress.noPlanYet"] = "\uC544\uC9C1 \uACC4\uD68D\uC774 \uC5C6\uC2B5\uB2C8\uB2E4";
STRINGS.ko["progress.doneNext"] = "{completed}/{total}\uB2E8\uACC4 \uC644\uB8CC, \uB2E4\uC74C: {next}";
STRINGS.ko["progress.closeoutCompleted"] = "{completed}/{total}\uB2E8\uACC4 \uC644\uB8CC, \uB9C8\uAC10 \uC644\uB8CC";
STRINGS.ko["progress.closeoutRunning"] = "{completed}/{total}\uB2E8\uACC4 \uC644\uB8CC, \uB9C8\uAC10 \uC9C4\uD589 \uC911";
STRINGS.ko["progress.closeoutFailed"] = "{completed}/{total}\uB2E8\uACC4 \uC644\uB8CC, \uB9C8\uAC10 \uC2E4\uD328";
STRINGS.ko["progress.closeoutPending"] = "{completed}/{total}\uB2E8\uACC4 \uC644\uB8CC, \uB9C8\uAC10 \uB300\uAE30";
STRINGS.ko["field.backgroundConcurrencyLimit"] = "\uB3D9\uC2DC \uBC31\uADF8\uB77C\uC6B4\uB4DC \uC791\uC5C5 \uC218";
STRINGS.ko["field.allowBackgroundQueue"] = "\uC774 \uD504\uB85C\uC81D\uD2B8\uC5D0\uC11C \uC608\uC57D \uD5C8\uC6A9";
STRINGS.ko["field.backgroundQueuePriority"] = "\uC608\uC57D \uC6B0\uC120\uC21C\uC704";
STRINGS.ko["action.backgroundJob"] = "\uBC31\uADF8\uB77C\uC6B4\uB4DC \uC791\uC5C5";
STRINGS.ko["prompt.confirmDeleteAllProjects"] = "\uBAA8\uB4E0 \uD504\uB85C\uC81D\uD2B8\uB97C \uC0AD\uC81C\uD560\uAE4C\uC694? \uAD00\uB9AC \uC911\uC778 \uBB38\uC11C, \uB85C\uADF8, \uC0C1\uD0DC\uB9CC \uC0AD\uC81C\uB418\uACE0 \uC6D0\uBCF8 \uC800\uC7A5\uC18C \uD3F4\uB354\uB294 \uADF8\uB300\uB85C \uC720\uC9C0\uB429\uB2C8\uB2E4.";
STRINGS.ko["sidebar.projectContextDelete"] = "\uC6B0\uD074\uB9AD\uC73C\uB85C \uD504\uB85C\uC81D\uD2B8 \uBA54\uB274 \uC5F4\uAE30";
STRINGS.ko["reports.wordReportReady"] = "Word \uBCF4\uACE0\uC11C\uAC00 {path}\uC5D0 \uC800\uC7A5\uB418\uC5C8\uC2B5\uB2C8\uB2E4.";
STRINGS.ko["reports.wordReportDisabled"] = "\uC774 \uD504\uB85C\uC81D\uD2B8\uC5D0\uC11C\uB294 Word \uBCF4\uACE0\uC11C \uC0DD\uC131\uC744 \uC0AC\uC6A9\uD558\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4.";
STRINGS.ko["message.commandCompletedWithWordReport"] = "{command} \uC791\uC5C5\uC774 \uC644\uB8CC\uB418\uC5C8\uC2B5\uB2C8\uB2E4. Word \uBCF4\uACE0\uC11C: {path}";
var KO_HIGH_QUALITY_OVERRIDES = {
  "action.add": "\uCD94\uAC00",
  "action.approveCheckpoint": "\uCCB4\uD06C\uD3EC\uC778\uD2B8 \uC2B9\uC778",
  "action.browse": "\uCC3E\uC544\uBCF4\uAE30",
  "action.closeout": "\uB9C8\uAC10",
  "action.copyLink": "\uB9C1\uD06C \uBCF5\uC0AC",
  "action.delete": "\uC0AD\uC81C",
  "action.deleteAll": "\uC804\uCCB4 \uC0AD\uC81C",
  "action.dismiss": "\uB2EB\uAE30",
  "action.generate": "\uC0DD\uC131",
  "action.generatePlan": "\uACC4\uD68D \uC0DD\uC131",
  "action.generateShareLink": "\uACF5\uC720 \uB9C1\uD06C \uC0DD\uC131",
  "action.new": "\uC0C8\uB85C \uB9CC\uB4E4\uAE30",
  "action.refresh": "\uC0C8\uB85C\uACE0\uCE68",
  "action.reset": "\uCD08\uAE30\uD654",
  "action.run": "\uC2E4\uD589",
  "action.runRemaining": "\uB0A8\uC740 \uB2E8\uACC4 \uC2E4\uD589",
  "action.revokeLink": "\uB9C1\uD06C \uD574\uC81C",
  "action.save": "\uC800\uC7A5",
  "action.saveConfiguration": "\uC124\uC815 \uC800\uC7A5",
  "action.saveProgramSettings": "\uD504\uB85C\uADF8\uB7A8 \uC124\uC815 \uC800\uC7A5",
  "action.saveLocal": "\uB85C\uCEEC \uC800\uC7A5",
  "action.stop": "\uC911\uC9C0",
  "common.account": "\uACC4\uC815",
  "common.auth": "\uC778\uC99D",
  "common.branch": "\uBE0C\uB79C\uCE58",
  "common.language": "\uC5B8\uC5B4",
  "common.project": "\uD504\uB85C\uC81D\uD2B8",
  "common.repoUrl": "\uC800\uC7A5\uC18C URL",
  "common.status": "\uC0C1\uD0DC",
  "config.additionalModels": "\uCD94\uAC00 \uBAA8\uB378",
  "config.advancedModelSettings": "\uACE0\uAE09 \uC124\uC815",
  "config.advancedModelSettingsDescription": "\uBAA8\uB378 \uC120\uD0DD, \uCD94\uAC00 \uD504\uB86C\uD504\uD2B8, \uC2E4\uD589 \uC635\uC158\uC744 \uC138\uBC00\uD558\uAC8C \uC870\uC815\uD569\uB2C8\uB2E4.",
  "config.executionModel": "\uC2E4\uD589 \uBAA8\uB378",
  "config.githubConnection": "GitHub \uC5F0\uACB0",
  "config.manualGithubUrl": "GitHub \uC800\uC7A5\uC18C URL \uC9C1\uC811 \uC785\uB825",
  "config.maxPlannedSteps": "\uCD5C\uB300 \uACC4\uD68D \uB2E8\uACC4 \uC218",
  "config.projectConfiguration": "\uD504\uB85C\uC81D\uD2B8 \uC124\uC815",
  "config.projectConfigurationDescription": "\uC800\uC7A5\uC18C\uC640 \uC2E4\uD589 \uC124\uC815\uC744 \uBA85\uC2DC\uC801\uC73C\uB85C \uC720\uC9C0\uD574 \uCD94\uC801\uC131\uACFC \uC791\uC5C5 \uBD84\uB9AC\uB97C \uBCF4\uC7A5\uD569\uB2C8\uB2E4.",
  "config.projectName": "\uD504\uB85C\uC81D\uD2B8 \uC774\uB984",
  "config.useExistingOrigin": "\uC774 \uD3F4\uB354\uC758 \uAE30\uC874 origin \uC0AC\uC6A9",
  "config.workingDirectory": "\uC791\uC5C5 \uB514\uB809\uD130\uB9AC",
  "dashboard.checkpoint": "\uCCB4\uD06C\uD3EC\uC778\uD2B8",
  "dashboard.checkpointPending": "\uCCB4\uD06C\uD3EC\uC778\uD2B8 \uB300\uAE30 \uC911",
  "dashboard.codexPlan": "Codex \uC694\uAE08\uC81C",
  "dashboard.codexUsage": "Codex \uC0AC\uC6A9\uB7C9",
  "dashboard.dashboard": "\uB300\uC2DC\uBCF4\uB4DC",
  "dashboard.inputTokens": "\uC785\uB825 \uD1A0\uD070",
  "dashboard.lastSafeRevision": "\uB9C8\uC9C0\uB9C9 \uC548\uC804 \uB9AC\uBE44\uC804",
  "dashboard.outputTokens": "\uCD9C\uB825 \uD1A0\uD070",
  "dashboard.remainingSteps": "\uB0A8\uC740 \uB2E8\uACC4",
  "dashboard.runtime": "\uB7F0\uD0C0\uC784",
  "field.approvalMode": "\uC2B9\uC778 \uBAA8\uB4DC",
  "field.checkpointInterval": "\uCCB4\uD06C\uD3EC\uC778\uD2B8 \uAC04\uACA9",
  "field.codexInstruction": "Codex \uC9C0\uC2DC\uBB38",
  "field.codexPath": "Codex \uACBD\uB85C",
  "field.customModelSlug": "\uC0AC\uC6A9\uC790 \uC9C0\uC815 \uBAA8\uB378 \uC2AC\uB7EC\uADF8",
  "field.description": "\uC124\uBA85",
  "field.executionMode": "\uC2E4\uD589 \uBAA8\uB4DC",
  "field.extraPrompt": "\uCD94\uAC00 \uD504\uB86C\uD504\uD2B8",
  "field.gptReasoning": "GPT \uCD94\uB860",
  "field.model": "\uBAA8\uB378",
  "field.parallelGroup": "\uBCD1\uB82C \uADF8\uB8F9",
  "field.parallelWorkers": "\uBCD1\uB82C \uC791\uC5C5 \uC218",
  "field.parallelMemoryPerWorkerGiB": "\uC6CC\uCEE4\uB2F9 \uBA54\uBAA8\uB9AC (GiB)",
  "field.prompt": "\uD504\uB86C\uD504\uD2B8",
  "field.sandboxMode": "\uC0CC\uB4DC\uBC15\uC2A4 \uBAA8\uB4DC",
  "field.successCriteria": "\uC131\uACF5 \uAE30\uC900",
  "field.title": "\uC81C\uBAA9",
  "field.verificationCommand": "\uAC80\uC99D \uBA85\uB839",
  "history.history": "\uAE30\uB85D",
  "history.noEntries": "\uAE30\uB85D\uC774 \uC5C6\uC2B5\uB2C8\uB2E4.",
  "history.recentActivity": "\uCD5C\uADFC \uD65C\uB3D9",
  "history.recentBlocks": "\uCD5C\uADFC \uBE14\uB85D",
  "message.allProjectsDeleted": "\uBAA8\uB4E0 \uD504\uB85C\uC81D\uD2B8\uB97C \uC81C\uAC70\uD588\uC2B5\uB2C8\uB2E4.",
  "message.checkpointApproved": "\uCCB4\uD06C\uD3EC\uC778\uD2B8\uB97C \uC2B9\uC778\uD588\uC2B5\uB2C8\uB2E4.",
  "message.commandCompleted": "{command} \uC791\uC5C5\uC774 \uC644\uB8CC\uB418\uC5C8\uC2B5\uB2C8\uB2E4.",
  "message.commandFailed": "{command} \uC791\uC5C5\uC774 \uC2E4\uD328\uD588\uC2B5\uB2C8\uB2E4.",
  "message.commandStarted": "{command} \uC791\uC5C5\uC744 \uC2DC\uC791\uD588\uC2B5\uB2C8\uB2E4.",
  "message.planSaved": "\uACC4\uD68D\uC744 \uC800\uC7A5\uD588\uC2B5\uB2C8\uB2E4.",
  "message.programSettingsSaved": "\uD504\uB85C\uADF8\uB7A8 \uC124\uC815\uC744 \uC800\uC7A5\uD588\uC2B5\uB2C8\uB2E4.",
  "message.projectConfigurationSaved": "\uD504\uB85C\uC81D\uD2B8 \uC124\uC815\uC744 \uC800\uC7A5\uD588\uC2B5\uB2C8\uB2E4.",
  "message.projectReloaded": "\uD504\uB85C\uC81D\uD2B8\uB97C \uB2E4\uC2DC \uBD88\uB7EC\uC654\uC2B5\uB2C8\uB2E4.",
  "message.projectStateRefreshed": "\uD504\uB85C\uC81D\uD2B8 \uC0C1\uD0DC\uB97C \uC0C8\uB85C\uACE0\uCE68\uD588\uC2B5\uB2C8\uB2E4.",
  "message.runStateRefreshed": "\uC2E4\uD589 \uC0C1\uD0DC\uB97C \uC0C8\uB85C\uACE0\uCE68\uD588\uC2B5\uB2C8\uB2E4.",
  "option.allowPushAfterSafeRuns": "\uC548\uC804 \uAC80\uC99D \uD6C4 push \uD5C8\uC6A9",
  "option.developerMode": "\uAC1C\uBC1C\uC790 \uBAA8\uB4DC",
  "option.saveProjectLogs": "\uD504\uB85C\uC81D\uD2B8 \uC791\uC5C5 \uB85C\uADF8 \uC800\uC7A5",
  "option.executionParallel": "\uBCD1\uB82C",
  "option.executionSerial": "\uC9C1\uB82C",
  "option.generateWordReport": "Word \uBCF4\uACE0\uC11C \uC0DD\uC131",
  "option.lightMode": "\uB77C\uC774\uD2B8 \uBAA8\uB4DC",
  "option.requireCheckpointApproval": "\uCCB4\uD06C\uD3EC\uC778\uD2B8 \uC2B9\uC778 \uD544\uC694",
  "option.useFastMode": "\uBE60\uB978 \uACC4\uD68D \uC0DD\uC131",
  "progress.closeoutCompleted": "{completed}/{total}\uB2E8\uACC4 \uC644\uB8CC, \uB9C8\uAC10 \uC644\uB8CC",
  "progress.closeoutFailed": "{completed}/{total}\uB2E8\uACC4 \uC644\uB8CC, \uB9C8\uAC10 \uC2E4\uD328",
  "progress.closeoutPending": "{completed}/{total}\uB2E8\uACC4 \uC644\uB8CC, \uB9C8\uAC10 \uB300\uAE30",
  "progress.closeoutRunning": "{completed}/{total}\uB2E8\uACC4 \uC644\uB8CC, \uB9C8\uAC10 \uC9C4\uD589 \uC911",
  "progress.doneNext": "{completed}/{total}\uB2E8\uACC4 \uC644\uB8CC, \uB2E4\uC74C: {next}",
  "progress.noPlanYet": "\uC544\uC9C1 \uACC4\uD68D\uC774 \uC5C6\uC2B5\uB2C8\uB2E4",
  "prompt.confirmDeleteAllProjects": "\uBAA8\uB4E0 \uD504\uB85C\uC81D\uD2B8\uB97C \uC81C\uAC70\uD560\uAE4C\uC694? \uAD00\uB9AC \uC911\uC778 \uBB38\uC11C, \uB85C\uADF8, \uC0C1\uD0DC\uB294 \uC0AD\uC81C\uB418\uC9C0\uB9CC \uC6D0\uBCF8 \uC800\uC7A5\uC18C \uD3F4\uB354\uB294 \uADF8\uB300\uB85C \uC720\uC9C0\uB429\uB2C8\uB2E4.",
  "prompt.confirmDeleteProject": "\uC774 \uD504\uB85C\uC81D\uD2B8\uB97C jakal-flow\uC5D0\uC11C \uC81C\uAC70\uD560\uAE4C\uC694? \uAD00\uB9AC \uC911\uC778 \uBB38\uC11C, \uB85C\uADF8, \uC0C1\uD0DC\uB294 \uC0AD\uC81C\uB418\uC9C0\uB9CC \uC6D0\uBCF8 \uC800\uC7A5\uC18C \uD3F4\uB354\uB294 \uADF8\uB300\uB85C \uC720\uC9C0\uB429\uB2C8\uB2E4.",
  "reports.attemptHistory": "\uC2DC\uB3C4 \uAE30\uB85D",
  "reports.blockReview": "\uBE14\uB85D \uB9AC\uBDF0",
  "reports.closeoutReport": "\uB9C8\uAC10 \uBCF4\uACE0\uC11C",
  "reports.historyEmpty": "\uC544\uC9C1 \uC2DC\uB3C4 \uAE30\uB85D\uC774 \uC5C6\uC2B5\uB2C8\uB2E4.",
  "reports.json": "\uCD5C\uC2E0 \uBCF4\uACE0\uC11C JSON",
  "reports.noBlockReview": "\uC544\uC9C1 \uBE14\uB85D \uB9AC\uBDF0\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4.",
  "reports.noCloseoutReport": "\uC544\uC9C1 \uB9C8\uAC10 \uBCF4\uACE0\uC11C\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4.",
  "reports.reports": "\uBCF4\uACE0\uC11C",
  "run.closeout": "\uB9C8\uAC10",
  "run.done": "\uC644\uB8CC",
  "run.executionFlow": "\uC2E4\uD589 \uD750\uB984",
  "run.flow": "\uD750\uB984",
  "run.flowChart": "\uD750\uB984\uB3C4",
  "run.newPendingStep": "\uC0C8 \uB300\uAE30 \uB2E8\uACC4",
  "run.noSteps": "\uC544\uC9C1 \uB2E8\uACC4\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4. \uACC4\uD68D\uC744 \uC0DD\uC131\uD558\uAC70\uB098 \uC9C1\uC811 \uCD94\uAC00\uD558\uC138\uC694.",
  "run.noSummary": "\uC694\uC57D \uC5C6\uC74C",
  "run.reasoning": "\uCD94\uB860 {effort}",
  "run.selectStep": "\uB2E8\uACC4\uB97C \uC120\uD0DD\uD558\uC138\uC694.",
  "run.selectedStep": "\uC120\uD0DD\uD55C \uB2E8\uACC4",
  "run.parallelLimit": "\uBCD1\uB82C \uC81C\uD55C",
  "run.parallelLimitMemoryCap": "\uBA54\uBAA8\uB9AC \uD55C\uB3C4 {memoryCap}, CPU \uD55C\uB3C4 {cpuCap}, \uAC00\uC6A9 \uBA54\uBAA8\uB9AC {freeMemory}",
  "run.parallelLimitCpuCap": "CPU \uD55C\uB3C4 {cpuCap}, \uB17C\uB9AC \uD504\uB85C\uC138\uC11C {logicalCpuCount}",
  "run.parallelLimitRequestedCap": "\uC694\uCCAD {requested}, CPU {cpuCap} \uBC0F \uBA54\uBAA8\uB9AC {memoryCap} \uD55C\uB3C4\uB85C {recommended}\uAE4C\uC9C0 \uC81C\uD55C",
  "run.parallelLimitAutoCap": "CPU \uD55C\uB3C4 {cpuCap}, \uBA54\uBAA8\uB9AC \uD55C\uB3C4 {memoryCap}",
  "run.stopAfterStep": "\uD604 \uB2E8\uACC4\uB97C \uBB34\uC2DC\uD558\uACE0 \uC911\uC9C0",
  "runtime.modelSummary": "{model} | \uCD94\uB860 {effort}",
  "runtime.modelSummaryGeneric": "{model} | \uCD94\uB860 {effort}",
  "settings.application": "\uD504\uB85C\uADF8\uB7A8",
  "settings.applicationDescription": "\uB370\uC2A4\uD06C\uD1B1 \uC178 \uC790\uCCB4\uC5D0 \uC801\uC6A9\uB418\uB294 \uC124\uC815\uC785\uB2C8\uB2E4.",
  "settings.executionDefaults": "\uC2E4\uD589 \uAE30\uBCF8\uAC12",
  "settings.executionDefaultsDescription": "\uD504\uB85C\uC81D\uD2B8\uBCC4 \uAC12\uC774 \uC5C6\uC73C\uBA74 \uC774 \uAE30\uBCF8\uAC12\uC744 \uC7AC\uC0AC\uC6A9\uD569\uB2C8\uB2E4.",
  "settings.programSettings": "\uD504\uB85C\uADF8\uB7A8 \uC124\uC815",
  "settings.programSettingsDescription": "\uB370\uC2A4\uD06C\uD1B1 \uC804\uC5ED \uC124\uC815\uACFC \uC2E4\uD589 \uAE30\uBCF8\uAC12\uC744 \uD55C \uACF3\uC5D0\uC11C \uAD00\uB9AC\uD569\uB2C8\uB2E4.",
  "sidebar.checkpoints": "\uCCB4\uD06C\uD3EC\uC778\uD2B8",
  "sidebar.emptyProjects": "\uAD00\uB9AC \uC911\uC778 \uD504\uB85C\uC81D\uD2B8\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4.",
  "sidebar.emptyWorkspace": "\uC544\uC9C1 \uC6CC\uD06C\uC2A4\uD398\uC774\uC2A4 \uD2B8\uB9AC\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4.",
  "sidebar.explorer": "\uD0D0\uC0C9\uAE30",
  "sidebar.noGithubOrigin": "\uC774 \uD504\uB85C\uC81D\uD2B8\uC5D0\uB294 GitHub origin\uC774 \uC124\uC815\uB418\uC5B4 \uC788\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4.",
  "sidebar.noRecordedCheckpoints": "\uAE30\uB85D\uB41C \uCCB4\uD06C\uD3EC\uC778\uD2B8\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4.",
  "sidebar.projectContextDelete": "\uC624\uB978\uCABD \uD074\uB9AD\uC73C\uB85C \uD504\uB85C\uC81D\uD2B8 \uC791\uC5C5 \uBA54\uB274\uB97C \uC5F4 \uC218 \uC788\uC2B5\uB2C8\uB2E4.",
  "sidebar.repositoryLink": "\uC800\uC7A5\uC18C \uB9C1\uD06C",
  "sidebar.searchFiles": "\uD30C\uC77C \uAC80\uC0C9",
  "sidebar.searchProjects": "\uD504\uB85C\uC81D\uD2B8 \uAC80\uC0C9",
  "sidebar.selectedSummary": "\uC120\uD0DD\uD55C \uC694\uC57D",
  "sidebar.targetBlock": "\uD0C0\uAE43 \uBE14\uB85D {block}",
  "status.awaiting_review": "\uAC80\uD1A0 \uB300\uAE30 \uC911",
  "status.closeout_failed": "\uB9C8\uAC10 \uC2E4\uD328",
  "status.closed_out": "\uB9C8\uAC10 \uC644\uB8CC",
  "status.completed": "\uC644\uB8CC",
  "status.failed": "\uC2E4\uD328",
  "status.idle": "\uB300\uAE30 \uC911",
  "status.not_started": "\uC2DC\uC791 \uC804",
  "status.paused_for_review": "\uAC80\uD1A0\uB97C \uC704\uD574 \uC77C\uC2DC \uC911\uC9C0\uB428",
  "status.pending": "\uB300\uAE30 \uC911",
  "status.plan_completed": "\uACC4\uD68D \uC644\uB8CC",
  "status.plan_ready": "\uACC4\uD68D \uC900\uBE44\uB428",
  "status.ready": "\uC900\uBE44\uB428",
  "status.running": "\uC2E4\uD589 \uC911",
  "status.runningWithDetail": "\uC2E4\uD589 \uC911: {detail}",
  "status.setup_ready": "\uC124\uC815 \uC644\uB8CC",
  "status.unknown": "\uC54C \uC218 \uC5C6\uC74C",
  "tab.config": "\uD504\uB85C\uC81D\uD2B8 \uC124\uC815",
  "tab.dashboard": "\uB300\uC2DC\uBCF4\uB4DC",
  "tab.flow": "\uD750\uB984",
  "tab.history": "\uAE30\uB85D",
  "tab.programSettings": "\uD504\uB85C\uADF8\uB7A8",
  "tab.reports": "\uBCF4\uACE0\uC11C",
  "tool.eventJson": "\uC774\uBCA4\uD2B8 JSON",
  "tool.gitStatus": "Git \uC0C1\uD0DC",
  "tool.tokenUsage": "\uD1A0\uD070 \uC0AC\uC6A9\uB7C9",
  "toolbar.bottom": "\uD558\uB2E8",
  "toolbar.plan": "\uACC4\uD68D",
  "toolbar.programSettings": "\uD504\uB85C\uADF8\uB7A8 \uC124\uC815",
  "toolbar.toggleBottom": "\uB3C4\uAD6C \uCC3D \uD1A0\uAE00",
  "usage.window5h": "5\uC2DC\uAC04 \uC0AC\uC6A9\uB7C9",
  "usage.window7d": "7\uC77C \uC0AC\uC6A9\uB7C9"
};
KO_HIGH_QUALITY_OVERRIDES["run.closeoutRunning"] = "\uB9C8\uAC10 \uC2E4\uD589 \uC911";
KO_HIGH_QUALITY_OVERRIDES["run.autoRunAfterPlan"] = "\uACC4\uD68D \uC0DD\uC131 \uD6C4 \uBC14\uB85C \uC2E4\uD589";
KO_HIGH_QUALITY_OVERRIDES["run.completedStepsSummary"] = "{completed}/{total}\uB2E8\uACC4 \uC644\uB8CC";
KO_HIGH_QUALITY_OVERRIDES["run.liveRun"] = "\uC2E4\uD589 \uC911\uC778 \uC791\uC5C5";
KO_HIGH_QUALITY_OVERRIDES["run.planGeneration"] = "\uACC4\uD68D \uC0DD\uC131 \uC911";
KO_HIGH_QUALITY_OVERRIDES["run.planningStage"] = "\uACC4\uD68D \uB2E8\uACC4 {current}/{total}";
KO_HIGH_QUALITY_OVERRIDES["run.planningStageWithStatus"] = "\uACC4\uD68D \uB2E8\uACC4 {current}/{total}, {status}";
KO_HIGH_QUALITY_OVERRIDES["run.preparingStep"] = "{step} \uC900\uBE44 \uC911";
KO_HIGH_QUALITY_OVERRIDES["run.progressPercent"] = "{percent}% \uC644\uB8CC";
KO_HIGH_QUALITY_OVERRIDES["run.readyNodeSummary"] = "\uC2E4\uD589 \uAC00\uB2A5 \uB178\uB4DC {count}\uAC1C";
KO_HIGH_QUALITY_OVERRIDES["run.runningNodeSummary"] = "\uC2E4\uD589 \uC911\uC778 \uB178\uB4DC {count}\uAC1C";
KO_HIGH_QUALITY_OVERRIDES["run.stepProgress"] = "\uB2E8\uACC4 \uC9C4\uD589\uB3C4";
KO_HIGH_QUALITY_OVERRIDES["run.debugging"] = "\uB514\uBC84\uAE45";
KO_HIGH_QUALITY_OVERRIDES["run.workingOnStep"] = "{step} \uC791\uC5C5 \uC911";
KO_HIGH_QUALITY_OVERRIDES["run.workingOnSteps"] = "{steps} \uC791\uC5C5 \uC911";
KO_HIGH_QUALITY_OVERRIDES["field.backgroundConcurrencyLimit"] = "\uB3D9\uC2DC \uBC31\uADF8\uB77C\uC6B4\uB4DC \uC791\uC5C5 \uC218";
KO_HIGH_QUALITY_OVERRIDES["field.allowBackgroundQueue"] = "\uC774 \uD504\uB85C\uC81D\uD2B8\uC5D0\uC11C \uC608\uC57D \uD5C8\uC6A9";
KO_HIGH_QUALITY_OVERRIDES["field.backgroundQueuePriority"] = "\uC608\uC57D \uC6B0\uC120\uC21C\uC704";
KO_HIGH_QUALITY_OVERRIDES["run.queuePriority"] = "\uC6B0\uC120\uC21C\uC704 {priority}";
KO_HIGH_QUALITY_OVERRIDES["progress.runningIds"] = "{completed}/{total}\uB2E8\uACC4 \uC644\uB8CC, \uC2E4\uD589 \uC911: {ids}";
KO_HIGH_QUALITY_OVERRIDES["progress.integratingIds"] = "{completed}/{total}\uB2E8\uACC4 \uC644\uB8CC, \uBCD1\uD569 \uC911: {ids}";
KO_HIGH_QUALITY_OVERRIDES["progress.runningAndIntegratingIds"] = "{completed}/{total}\uB2E8\uACC4 \uC644\uB8CC, \uC2E4\uD589 \uC911: {runningIds}; \uBCD1\uD569 \uC911: {integratingIds}";
KO_HIGH_QUALITY_OVERRIDES["progress.readyIds"] = "{completed}/{total}\uB2E8\uACC4 \uC644\uB8CC, \uC2E4\uD589 \uAC00\uB2A5: {ids}";
KO_HIGH_QUALITY_OVERRIDES["status.awaiting_checkpoint_approval"] = "\uCCB4\uD06C\uD3EC\uC778\uD2B8 \uC2B9\uC778 \uB300\uAE30";
KO_HIGH_QUALITY_OVERRIDES["status.integrating"] = "\uBCD1\uD569 \uC911";
KO_HIGH_QUALITY_OVERRIDES["status.merging"] = "\uBCD1\uD569 \uC911";
KO_HIGH_QUALITY_OVERRIDES["action.archiveAllProjects"] = "\uBAA8\uB450 \uBCF4\uAD00";
KO_HIGH_QUALITY_OVERRIDES["action.archiveProject"] = "\uD504\uB85C\uC81D\uD2B8 \uBCF4\uAD00";
KO_HIGH_QUALITY_OVERRIDES["history.noFlowChart"] = "\uC800\uC7A5\uB41C \uD50C\uB85C\uC6B0 \uCC28\uD2B8\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4.";
KO_HIGH_QUALITY_OVERRIDES["history.noPrompt"] = "\uC800\uC7A5\uB41C \uD504\uB86C\uD504\uD2B8\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4.";
KO_HIGH_QUALITY_OVERRIDES["history.noSavedRuns"] = "\uC544\uC9C1 \uBCF4\uAD00\uB41C \uC2E4\uD589 \uAE30\uB85D\uC774 \uC5C6\uC2B5\uB2C8\uB2E4.";
KO_HIGH_QUALITY_OVERRIDES["history.archivedAt"] = "\uBCF4\uAD00 \uC2DC\uAC01: {timestamp}";
KO_HIGH_QUALITY_OVERRIDES["message.projectArchived"] = "\uD504\uB85C\uC81D\uD2B8\uB97C history\uB85C \uC62E\uACBC\uC2B5\uB2C8\uB2E4.";
KO_HIGH_QUALITY_OVERRIDES["message.allProjectsArchived"] = "\uBAA8\uB4E0 \uD504\uB85C\uC81D\uD2B8\uB97C history\uB85C \uC62E\uACBC\uC2B5\uB2C8\uB2E4.";
KO_HIGH_QUALITY_OVERRIDES["prompt.confirmArchiveProject"] = "\uC774 \uD504\uB85C\uC81D\uD2B8\uB97C history\uB85C \uC62E\uAE38\uAE4C\uC694? \uAD00\uB9AC \uC911\uC778 \uBB38\uC11C, \uB85C\uADF8, \uC0C1\uD0DC\uB294 history \uC544\uB798\uC5D0 \uBCF4\uAD00\uB418\uACE0 \uAC19\uC740 \uB514\uB809\uD1A0\uB9AC\uB85C \uC0C8 \uC791\uC5C5\uC744 \uB2E4\uC2DC \uC2DC\uC791\uD560 \uC218 \uC788\uC2B5\uB2C8\uB2E4.";
KO_HIGH_QUALITY_OVERRIDES["prompt.confirmArchiveAllProjects"] = "\uBAA8\uB4E0 \uD504\uB85C\uC81D\uD2B8\uB97C history\uB85C \uC62E\uAE38\uAE4C\uC694? \uAC01 \uD504\uB85C\uC81D\uD2B8\uC758 \uBB38\uC11C, \uB85C\uADF8, \uC0C1\uD0DC\uB294 \uBCF4\uAD00\uB418\uACE0 \uC6D0\uBCF8 \uC791\uC5C5 \uB514\uB809\uD1A0\uB9AC\uB294 \uADF8\uB300\uB85C \uC720\uC9C0\uB429\uB2C8\uB2E4.";
KO_HIGH_QUALITY_OVERRIDES["action.deleteAllProjects"] = "\uBAA8\uB450 \uC0AD\uC81C";
KO_HIGH_QUALITY_OVERRIDES["action.deleteArchivedRun"] = "\uBCF4\uAD00\uBCF8 \uC0AD\uC81C";
KO_HIGH_QUALITY_OVERRIDES["action.deleteProject"] = "\uD504\uB85C\uC81D\uD2B8 \uC0AD\uC81C";
KO_HIGH_QUALITY_OVERRIDES["message.historyEntryDeleted"] = "\uBCF4\uAD00\uB41C \uC2E4\uD589 \uAE30\uB85D\uC744 \uC0AD\uC81C\uD588\uC2B5\uB2C8\uB2E4.";
KO_HIGH_QUALITY_OVERRIDES["prompt.confirmDeleteHistoryEntry"] = "\uC774 \uBCF4\uAD00\uB41C \uC2E4\uD589 \uAE30\uB85D\uC744 \uC644\uC804\uD788 \uC0AD\uC81C\uD560\uAE4C\uC694? history \uC544\uB798\uC758 \uAD00\uB9AC \uBB38\uC11C, \uB85C\uADF8, \uB9AC\uD3EC\uD2B8, \uC0C1\uD0DC\uAC00 \uBAA8\uB450 \uC81C\uAC70\uB429\uB2C8\uB2E4.";
KO_HIGH_QUALITY_OVERRIDES["message.commandQueued"] = "{command} \uC791\uC5C5\uC744 \uB300\uAE30\uC5F4\uC5D0 \uCD94\uAC00\uD588\uC2B5\uB2C8\uB2E4. {position}\uBC88\uC9F8\uB85C \uC2E4\uD589\uB429\uB2C8\uB2E4.";
KO_HIGH_QUALITY_OVERRIDES["message.commandCancelled"] = "{command} \uC608\uC57D\uC744 \uCDE8\uC18C\uD588\uC2B5\uB2C8\uB2E4.";
KO_HIGH_QUALITY_OVERRIDES["status.queued"] = "\uB300\uAE30\uC5F4\uC5D0 \uC788\uC74C";
KO_HIGH_QUALITY_OVERRIDES["status.queuedWithDetail"] = "\uB300\uAE30\uC5F4\uC5D0 \uC788\uC74C: {detail}";
var STATIC_LANGUAGE_PACKS = new Map(
  ["en", "ko"].map((language) => [
    language,
    {
      ...STRINGS[language] || {},
      ...language === "ko" ? KO_HIGH_QUALITY_OVERRIDES : {}
    }
  ])
);
var loadedDynamicLanguagePacks = /* @__PURE__ */ new Map();
function staticLanguagePack(language) {
  const normalized = normalizeLanguage(language);
  return STATIC_LANGUAGE_PACKS.get(normalized) || {};
}
function currentLanguagePack(language) {
  const normalized = normalizeLanguage(language);
  return loadedDynamicLanguagePacks.get(normalized) || staticLanguagePack(normalized);
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
  return String(value || "").trim().replace(/[_-]+/g, " ").replace(/\s+/g, " ");
}
function normalizeLanguage(value) {
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
function translate(language, key, params = {}) {
  const normalized = normalizeLanguage(language);
  const value = currentLanguagePack(normalized)?.[key] ?? STRINGS.en[key];
  if (value === void 0) {
    return key;
  }
  return interpolate(value, params);
}
function displayStatus(status, language) {
  const normalizedLanguage = normalizeLanguage(language);
  const raw = String(status || "").trim();
  const normalized = raw.toLowerCase();
  if (!normalized) {
    return translate(normalizedLanguage, "status.unknown");
  }
  if (normalized === "debugging" || normalized === "running:debugging" || normalized === "running:parallel-debugging") {
    return translate(normalizedLanguage, "run.debugging");
  }
  if (normalized === "running:merging") {
    return translate(normalizedLanguage, "status.merging");
  }
  if (normalized === "running:closeout") {
    return translate(normalizedLanguage, "run.closeoutRunning");
  }
  if (normalized === "queued") {
    return translate(normalizedLanguage, "status.queued");
  }
  if (normalized.startsWith("queued:")) {
    const detail = humanizeToken(raw.slice(raw.indexOf(":") + 1));
    return translate(normalizedLanguage, "status.queuedWithDetail", {
      detail: normalizedLanguage === "ko" ? detail : titleCase(detail)
    });
  }
  if (normalized.startsWith("running:")) {
    const detail = humanizeToken(raw.slice(raw.indexOf(":") + 1));
    return translate(normalizedLanguage, "status.runningWithDetail", {
      detail: normalizedLanguage === "ko" ? detail : titleCase(detail)
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

// src/utils.js
function defaultCodexPath(provider = "openai") {
  const normalizedProvider = String(provider || "").trim().toLowerCase();
  if (normalizedProvider === "claude" || normalizedProvider === "deepseek" || normalizedProvider === "minimax" || normalizedProvider === "glm") {
    const platform2 = String(globalThis.process?.platform || "").trim().toLowerCase();
    if (platform2 === "win32") {
      return "claude.cmd";
    }
    const userAgent2 = String(globalThis.navigator?.userAgent || "").toLowerCase();
    if (userAgent2.includes("windows")) {
      return "claude.cmd";
    }
    return "claude";
  }
  if (normalizedProvider === "gemini") {
    const platform2 = String(globalThis.process?.platform || "").trim().toLowerCase();
    if (platform2 === "win32") {
      return "gemini.cmd";
    }
    const userAgent2 = String(globalThis.navigator?.userAgent || "").toLowerCase();
    if (userAgent2.includes("windows")) {
      return "gemini.cmd";
    }
    return "gemini";
  }
  if (normalizedProvider === "qwen_code") {
    const platform2 = String(globalThis.process?.platform || "").trim().toLowerCase();
    if (platform2 === "win32") {
      return "qwen.cmd";
    }
    const userAgent2 = String(globalThis.navigator?.userAgent || "").toLowerCase();
    if (userAgent2.includes("windows")) {
      return "qwen.cmd";
    }
    return "qwen";
  }
  const platform = String(globalThis.process?.platform || "").trim().toLowerCase();
  if (platform === "win32") {
    return "codex.cmd";
  }
  const userAgent = String(globalThis.navigator?.userAgent || "").toLowerCase();
  if (userAgent.includes("windows")) {
    return "codex.cmd";
  }
  return "codex";
}
function cloneValue(value) {
  if (value === null || value === void 0) {
    return value;
  }
  if (typeof globalThis.structuredClone === "function") {
    return globalThis.structuredClone(value);
  }
  return JSON.parse(JSON.stringify(value));
}
function normalizedChatMode(mode = "") {
  const normalized = String(mode || "").trim().toLowerCase();
  return ["conversation", "review", "debugger", "merger"].includes(normalized) ? normalized : "conversation";
}
function jobLaneForRequest(command = "", payload = null) {
  const normalizedCommand = String(command || "").trim().toLowerCase();
  if (normalizedCommand === "send-chat-message" && ["conversation", "review"].includes(normalizedChatMode(payload?.chat_mode))) {
    return "chat";
  }
  return "execution";
}
function jobLane(job = null) {
  const explicitLane = String(job?.job_lane || "").trim().toLowerCase();
  if (explicitLane === "chat" || explicitLane === "execution") {
    return explicitLane;
  }
  return jobLaneForRequest(job?.command, job);
}
function isChatJob(job = null) {
  return jobLane(job) === "chat";
}
function visibleExecutionJob(job = null) {
  if (!job || isChatJob(job)) {
    return null;
  }
  return job;
}
function isActiveExecutionStatus(status = "") {
  const normalized = String(status || "").trim().toLowerCase();
  return normalized === "running" || normalized.startsWith("running:") || normalized === "queued" || normalized.startsWith("queued:");
}
var AUTO_REASONING_OPTION = "auto";
var REASONING_OPTIONS = ["low", "medium", "high", "xhigh"];
var MODEL_REASONING_OPTIONS = [AUTO_REASONING_OPTION, ...REASONING_OPTIONS];
var DEFAULT_DASHBOARD_VISIBILITY = Object.freeze({
  status: true,
  remaining_steps: true,
  checkpoint_pending: false,
  input_tokens: false,
  output_tokens: false,
  estimated_remaining: true,
  estimated_cost: false,
  actual_cost: false,
  codex_plan: false,
  rate_limit_window_5h: false,
  rate_limit_window_7d: true,
  rate_limit_codex_spark: false,
  runtime_card: false,
  codex_usage_card: false,
  word_report_card: true
});
var CLAUDE_DEFAULT_MODEL = "claude-sonnet-4-6";
var GEMINI_DEFAULT_MODEL = "gemini-3-flash-preview";
var LEGACY_DASHBOARD_VISIBILITY_ALIASES = Object.freeze({
  rate_limit_window_5h: "rate_limits",
  rate_limit_window_7d: "rate_limits",
  rate_limit_codex_spark: "rate_limits"
});
var DEFAULT_PROGRAM_RUNTIME = {
  model_provider: "openai",
  local_model_provider: "ollama",
  chat_model_provider: "",
  chat_local_model_provider: "",
  provider_base_url: "",
  provider_api_key_env: "OPENAI_API_KEY",
  ensemble_openai_model: "gpt-5.4",
  ensemble_gemini_model: GEMINI_DEFAULT_MODEL,
  ensemble_claude_model: CLAUDE_DEFAULT_MODEL,
  model: "gpt-5.4",
  execution_model: "gpt-5.4",
  chat_model: "",
  planning_effort: "medium",
  model_preset: "",
  model_selection_mode: "slug",
  model_slug_input: "gpt-5.4",
  approval_mode: "never",
  sandbox_mode: "danger-full-access",
  checkpoint_interval_blocks: 1,
  codex_path: defaultCodexPath(),
  allow_push: true,
  require_checkpoint_approval: false,
  workflow_mode: "standard",
  ml_max_cycles: 3,
  execution_mode: "parallel",
  parallel_worker_mode: "auto",
  parallel_workers: 0,
  parallel_memory_per_worker_gib: 3,
  save_project_logs: false
};
function computePlanStats(plan = {}) {
  const steps = Array.isArray(plan?.steps) ? plan.steps : [];
  const completed = steps.filter((step) => step.status === "completed").length;
  const failed = steps.filter((step) => step.status === "failed").length;
  const running = steps.filter((step) => ["running", "integrating"].includes(String(step?.status || "").trim().toLowerCase())).length;
  return {
    total_steps: steps.length,
    completed_steps: completed,
    failed_steps: failed,
    running_steps: running,
    remaining_steps: Math.max(0, steps.length - completed)
  };
}
var RUN_STATE_STALE_AFTER_MS = 30 * 1e3;
function readyExecutionNodeIds(plan = {}) {
  const steps = Array.isArray(plan?.steps) ? plan.steps : [];
  const completedIds = new Set(steps.filter((step) => step.status === "completed").map((step) => step.step_id));
  return steps.filter(
    (step) => step.status !== "completed" && (step.depends_on || []).every((dependency) => completedIds.has(dependency))
  ).map((step) => step.step_id);
}
function executionStepsByStatus(plan = {}, statuses = []) {
  const allowed = new Set(statuses.map((status) => String(status || "").trim().toLowerCase()));
  const steps = Array.isArray(plan?.steps) ? plan.steps : [];
  return steps.filter((step) => allowed.has(String(step?.status || "").trim().toLowerCase()));
}
function runningExecutionSteps(plan = {}) {
  return executionStepsByStatus(plan, ["running", "integrating"]);
}
function activityLineSummary(line = "") {
  const parts = String(line || "").split("|").map((part) => part.trim()).filter(Boolean);
  if (!parts.length) {
    return "";
  }
  if (parts.length >= 3) {
    return parts.slice(2).join(" | ");
  }
  return parts[parts.length - 1];
}
function isDebuggingStatus(status = "") {
  const normalized = String(status || "").trim().toLowerCase();
  return normalized === "debugging" || normalized === "running:debugging" || normalized === "running:parallel-debugging";
}
function effectiveStepStatus(step = null, projectStatus = "") {
  const rawStepStatus = String(step?.status || "").trim().toLowerCase();
  if (!rawStepStatus) {
    return "";
  }
  const normalizedProjectStatus = String(projectStatus || "").trim().toLowerCase();
  if (isDebuggingStatus(normalizedProjectStatus) && rawStepStatus === "running") {
    return "running:debugging";
  }
  if (rawStepStatus === "failed" && isActiveExecutionStatus(normalizedProjectStatus)) {
    if (normalizedProjectStatus.startsWith("running:") || normalizedProjectStatus.startsWith("queued:")) {
      return normalizedProjectStatus;
    }
    return normalizedProjectStatus.startsWith("queued") ? "queued" : "running";
  }
  return String(step?.status || "").trim();
}
function normalizedCloseoutStatus(plan = null) {
  return String(plan?.closeout_status || "not_started").trim().toLowerCase();
}
function planProgressCounts(plan = null) {
  const steps = Array.isArray(plan?.steps) ? plan.steps : [];
  const completedStepCount = steps.filter((step) => String(step?.status || "").trim().toLowerCase() === "completed").length;
  const totalStepCount = steps.length;
  const closeoutStatus = normalizedCloseoutStatus(plan);
  const includesCloseout = totalStepCount > 0 || closeoutStatus !== "not_started";
  const totalCount = includesCloseout ? totalStepCount + 1 : 0;
  const completedCount = Math.min(totalCount, completedStepCount + (closeoutStatus === "completed" ? 1 : 0));
  return {
    steps,
    completedStepCount,
    totalStepCount,
    completedCount,
    totalCount,
    closeoutStatus
  };
}
function normalizePlanningProgress(raw = null) {
  if (!raw || typeof raw !== "object") {
    return null;
  }
  const stageCount = Math.max(0, Number.parseInt(String(raw.stage_count || 0), 10) || 0);
  const currentStageIndex = Math.max(0, Number.parseInt(String(raw.current_stage_index || 0), 10) || 0);
  const percent = Math.max(0, Math.min(100, Number.parseInt(String(raw.percent || 0), 10) || 0));
  const stages = Array.isArray(raw.stages) ? raw.stages.filter((stage) => stage && typeof stage === "object").map((stage, index) => ({
    key: String(stage.key || "").trim(),
    index: Math.max(1, Number.parseInt(String(stage.index || index + 1), 10) || index + 1),
    label: String(stage.label || "").trim(),
    status: String(stage.status || "pending").trim().toLowerCase() || "pending",
    agentLabel: String(stage.agent_label || "").trim()
  })) : [];
  const currentStage = stages.find((stage) => stage.index === currentStageIndex) || stages.find((stage) => stage.status === "running" || stage.status === "failed") || null;
  return {
    stageCount,
    completedStages: Math.max(0, Number.parseInt(String(raw.completed_stages || 0), 10) || 0),
    percent,
    stages,
    currentStageIndex,
    currentStageKey: String(raw.current_stage_key || "").trim(),
    currentStageLabel: String(raw.current_stage_label || currentStage?.label || "").trim(),
    currentStageStatus: String(raw.current_stage_status || currentStage?.status || "").trim().toLowerCase() || "pending",
    currentAgentLabel: String(raw.current_agent_label || currentStage?.agentLabel || "").trim(),
    message: String(raw.message || "").trim(),
    eventType: String(raw.event_type || "").trim()
  };
}
function planningProgressStatusValue(progress = null) {
  if (!progress || typeof progress !== "object") {
    return "";
  }
  return String(progress?.currentStageStatus ?? progress?.current_stage_status ?? "").trim().toLowerCase();
}
function isPlanningProgressRunning(progress = null) {
  return planningProgressStatusValue(progress) === "running";
}
function deriveExecutionProgress(detail = null, planDraft = null, activeJob = null) {
  const progressJob = visibleExecutionJob(activeJob);
  const detailPlan = detail?.plan && typeof detail.plan === "object" ? detail.plan : null;
  const fallbackPlan = planDraft && typeof planDraft === "object" ? planDraft : {};
  const plan = cloneValue(detailPlan || fallbackPlan) || {};
  const { steps, completedCount, totalCount, closeoutStatus } = planProgressCounts(plan);
  const stats = detail?.stats || computePlanStats(plan);
  const command = progressJob?.status === "running" ? String(progressJob?.command || "").trim() : "";
  const runningStepList = runningExecutionSteps(plan);
  const runningStep = runningStepList[0] || null;
  const nextStep = steps.find((step) => step.status !== "completed") || null;
  const readyIds = readyExecutionNodeIds(plan);
  const closeoutRunning = closeoutStatus === "running";
  const currentStatus = String(detail?.project?.current_status || "").trim();
  const status = currentStatus.toLowerCase();
  const debugging = isDebuggingStatus(currentStatus);
  const debuggingCommand = String(progressJob?.command || "").trim().toLowerCase() === "run-manual-debugger";
  const planningProgress = normalizePlanningProgress(detail?.planning_progress);
  const planningRunning = isPlanningProgressRunning(planningProgress);
  const recentActivity = (Array.isArray(detail?.activity) ? detail.activity : []).map((line) => activityLineSummary(line)).filter(Boolean).slice(0, 3);
  const isActive = progressJob?.status === "running" || runningStepList.length > 0 || closeoutRunning || planningRunning;
  let phase = "idle";
  if (command === "generate-plan" || planningRunning) {
    phase = "planning";
  } else if (command === "run-closeout" || closeoutRunning) {
    phase = "closeout";
  } else if (debuggingCommand || debugging && !progressJob) {
    phase = "debugging";
  } else if (command || runningStepList.length > 0 || nextStep) {
    phase = "step";
  }
  let percent = null;
  let visualPercent = 0;
  let indeterminate = false;
  if (isActive) {
    if (phase === "planning" && planningProgress?.stageCount) {
      percent = planningProgress.percent;
      visualPercent = percent > 0 ? percent : 6;
    } else if (phase === "planning" && !steps.length) {
      indeterminate = true;
    } else if (totalCount) {
      percent = Math.round(completedCount / totalCount * 100);
      visualPercent = percent > 0 ? percent : 6;
      if ((phase === "closeout" || runningStepList.length > 0 || command === "run-plan") && percent < 95) {
        visualPercent = Math.max(visualPercent, 10);
        visualPercent = Math.min(95, visualPercent);
      }
    } else {
      indeterminate = true;
    }
  }
  return {
    isActive,
    phase,
    command,
    status: currentStatus,
    debugging,
    plan,
    totalSteps: steps.length,
    completedSteps: Math.max(0, Number(stats?.completed_steps || 0)),
    totalProgressUnits: totalCount,
    completedProgressUnits: completedCount,
    failedSteps: Math.max(0, Number(stats?.failed_steps || 0)),
    runningSteps: Math.max(0, Number(stats?.running_steps || 0)),
    remainingSteps: Math.max(0, Number(stats?.remaining_steps || 0)),
    runningStepList,
    runningStep,
    nextStep,
    readyIds,
    planningProgress,
    planningStages: planningProgress?.stages || [],
    planningStageCount: planningProgress?.stageCount || 0,
    planningCurrentStage: planningProgress?.currentStageLabel ? {
      index: planningProgress.currentStageIndex,
      key: planningProgress.currentStageKey,
      label: planningProgress.currentStageLabel,
      status: planningProgress.currentStageStatus
    } : null,
    planningCurrentAgentLabel: planningProgress?.currentAgentLabel || "",
    recentActivity,
    headlineActivity: planningProgress?.message || recentActivity[0] || "",
    closeoutRunning,
    percent,
    visualPercent,
    indeterminate
  };
}
function normalizeExecutionFamilyToken(value = "") {
  const normalized = String(value || "").trim().toLowerCase();
  if (!normalized) {
    return "idle";
  }
  if (normalized === "syncing" || normalized === "inconsistent" || normalized === "stale") {
    return "syncing";
  }
  if (normalized === "debugging" || normalized === "running:debugging" || normalized === "running:parallel-debugging") {
    return "debugging";
  }
  if (normalized === "running:merging") {
    return "merging";
  }
  if (normalized === "running:closeout") {
    return "closeout";
  }
  if (normalized === "running:generate-plan") {
    return "planning";
  }
  if (normalized === "queued" || normalized.startsWith("queued:")) {
    return "queued";
  }
  if (normalized === "awaiting_review" || normalized === "awaiting_checkpoint_approval" || normalized === "checkpoint") {
    return "checkpoint";
  }
  if (normalized === "completed" || normalized === "closed_out" || normalized === "plan_completed") {
    return "completed";
  }
  if (normalized.includes("failed")) {
    return "failed";
  }
  if (normalized === "running" || normalized.startsWith("running:")) {
    return "running";
  }
  if (normalized === "ready" || normalized === "plan_ready" || normalized === "setup_ready" || normalized === "idle") {
    return "idle";
  }
  return normalized;
}
function executionFamilyFromCommand(command = "") {
  const normalized = String(command || "").trim().toLowerCase();
  if (!normalized) {
    return "idle";
  }
  if (normalized === "generate-plan") {
    return "planning";
  }
  if (normalized === "run-closeout") {
    return "closeout";
  }
  if (normalized === "run-manual-debugger") {
    return "debugging";
  }
  if (normalized === "run-manual-merger") {
    return "merging";
  }
  if (normalized === "run-plan") {
    return "running";
  }
  if (normalized === "send-chat-message") {
    return "idle";
  }
  return "running";
}
function executionFamilyFromJob(job = null) {
  const status = String(job?.status || "").trim().toLowerCase();
  const commandFamily = executionFamilyFromCommand(job?.command);
  if (!status) {
    return "idle";
  }
  if (status === "queued") {
    return commandFamily === "idle" ? "queued" : commandFamily;
  }
  if (status === "running") {
    return commandFamily === "idle" ? "running" : commandFamily;
  }
  return normalizeExecutionFamilyToken(status) || commandFamily || "idle";
}
function checkpointFamilyFromDetail(detail = null, activeJob = null) {
  const checkpointState = resolveCheckpointExecutionState(detail, activeJob);
  const projectStatus = String(detail?.project?.current_status || "").trim().toLowerCase();
  const closeoutStatus = String(detail?.plan?.closeout_status || "").trim().toLowerCase();
  const planSteps = Array.isArray(detail?.plan?.steps) ? detail.plan.steps : [];
  const terminalFailure = projectStatus.endsWith("failed") || closeoutStatus === "failed" || planSteps.some((step) => String(step?.status || "").trim().toLowerCase() === "failed");
  if (checkpointState.waitingForApproval) {
    return "checkpoint";
  }
  if (checkpointState.processActive && (checkpointState.currentCheckpointId || checkpointState.currentCheckpointLineageId)) {
    return "running";
  }
  if (terminalFailure) {
    return "failed";
  }
  const items = Array.isArray(checkpointState.items) ? checkpointState.items : [];
  if (items.length && items.every((item) => ["approved", "completed"].includes(String(item?.status || "").trim().toLowerCase()))) {
    return "completed";
  }
  if (!checkpointState.processActive && items.some((item) => String(item?.status || "").trim().toLowerCase().includes("failed"))) {
    return "failed";
  }
  return "idle";
}
function normalizeExecutionSurfaceStatus(signal = "") {
  return normalizeExecutionFamilyToken(signal);
}
function formatExecutionConsistencyLine(name, signal, raw = "") {
  const normalized = normalizeExecutionSurfaceStatus(signal);
  const rawText = String(raw || "").trim();
  return `${name}: ${normalized}${rawText && rawText !== normalized ? ` (${rawText})` : ""}`;
}
function resolveCheckpointExecutionState(detail = null, activeJob = null) {
  const checkpoints = detail?.checkpoints && typeof detail.checkpoints === "object" ? detail.checkpoints : null;
  const executionJob = visibleExecutionJob(activeJob);
  const processStatus = String(executionJob?.status || "").trim().toLowerCase();
  const processActive = Boolean(executionJob) && (processStatus === "running" || processStatus === "queued");
  const loopState = detail?.loop_state && typeof detail.loop_state === "object" ? detail.loop_state : {};
  const currentCheckpointId = String(loopState.current_checkpoint_id || checkpoints?.pending?.checkpoint_id || "").trim();
  const currentCheckpointLineageId = String(loopState.current_checkpoint_lineage_id || checkpoints?.pending?.lineage_id || "").trim();
  const hasCheckpointContext = Boolean(currentCheckpointId || currentCheckpointLineageId);
  const currentStatus = String(detail?.project?.current_status || "").trim().toLowerCase();
  const waitingForApproval = processActive && (Boolean(loopState.pending_checkpoint_approval) || currentStatus === "awaiting_checkpoint_approval");
  const items = Array.isArray(checkpoints?.items) ? checkpoints.items.filter((item) => item && typeof item === "object") : [];
  const matchesActiveCheckpoint = (item = null) => {
    if (!item || typeof item !== "object") {
      return false;
    }
    const itemCheckpointId = String(item.checkpoint_id || "").trim();
    const itemLineageId = String(item.lineage_id || "").trim();
    if (!currentCheckpointId || itemCheckpointId !== currentCheckpointId) {
      return false;
    }
    return !currentCheckpointLineageId || !itemLineageId || itemLineageId === currentCheckpointLineageId;
  };
  let changed = false;
  const normalizedItems = items.map((item) => {
    const nextItem = cloneValue(item);
    const status = String(nextItem.status || "").trim().toLowerCase();
    const matches = matchesActiveCheckpoint(nextItem);
    if (waitingForApproval && hasCheckpointContext && matches && status !== "awaiting_review") {
      nextItem.status = "awaiting_review";
      changed = true;
    } else if (processActive && hasCheckpointContext && matches && status !== "running") {
      nextItem.status = "running";
      changed = true;
    } else if (!processActive && ["running", "awaiting_review"].includes(status)) {
      nextItem.status = "pending";
      changed = true;
    }
    return nextItem;
  });
  let pending = null;
  if (waitingForApproval) {
    const pendingSource = checkpoints?.pending && typeof checkpoints.pending === "object" ? cloneValue(checkpoints.pending) : null;
    if (pendingSource) {
      pending = pendingSource;
    } else if (currentCheckpointId) {
      const matchingItem = normalizedItems.find((item) => matchesActiveCheckpoint(item)) || null;
      pending = matchingItem ? cloneValue(matchingItem) : { checkpoint_id: currentCheckpointId };
    }
    if (pending) {
      pending.checkpoint_id = String(pending.checkpoint_id || currentCheckpointId || "").trim();
      pending.status = "awaiting_review";
      if (!String(pending.checkpoint_id || "").trim() && currentCheckpointId) {
        pending.checkpoint_id = currentCheckpointId;
      }
    }
  }
  const hadExplicitChanges = String(checkpoints?.current_checkpoint_id || "") !== currentCheckpointId || String(checkpoints?.current_checkpoint_lineage_id || "") !== currentCheckpointLineageId || String(checkpoints?.pending?.checkpoint_id || "") !== String(pending?.checkpoint_id || "") || String(checkpoints?.pending?.status || "") !== String(pending?.status || "");
  return {
    executionJob,
    processActive,
    waitingForApproval,
    currentCheckpointId,
    currentCheckpointLineageId,
    hasCheckpointContext,
    items: changed || hadExplicitChanges ? normalizedItems : items,
    pending,
    hasActiveCheckpoint: Boolean(currentCheckpointId || currentCheckpointLineageId || pending)
  };
}
function deriveExecutionUiState(detail = null, planDraft = null, activeJob = null) {
  const executionJob = visibleExecutionJob(activeJob);
  const livePlan = resolveExecutionDisplayPlan(detail, planDraft, activeJob);
  const progress = deriveExecutionProgress(detail, planDraft, activeJob);
  const checkpointExecutionState = resolveCheckpointExecutionState(detail, executionJob);
  const checkpointPending = checkpointExecutionState.pending && typeof checkpointExecutionState.pending === "object" ? checkpointExecutionState.pending : null;
  const checkpointFamily = checkpointFamilyFromDetail(detail, executionJob);
  const projectStatus = String(detail?.project?.current_status || "").trim();
  const storedProjectFamily = normalizeExecutionSurfaceStatus(projectStatus);
  const processStatus = String(executionJob?.status || "").trim().toLowerCase();
  const processCommand = String(executionJob?.command || "").trim().toLowerCase();
  const processFamily = executionFamilyFromJob(executionJob);
  const processStatusValue = processStatus === "queued" ? `queued:${processCommand || "background-job"}` : processStatus === "running" ? processFamily === "debugging" ? "running:debugging" : `running:${processCommand || "background-job"}` : "";
  const terminalFailureFamily = (() => {
    if (processStatusValue) {
      return "";
    }
    const projectFamily = normalizeExecutionSurfaceStatus(projectStatus);
    const closeoutStatus = String(livePlan?.closeout_status || detail?.plan?.closeout_status || "").trim().toLowerCase();
    const planSteps = Array.isArray(livePlan?.steps) ? livePlan.steps : Array.isArray(detail?.plan?.steps) ? detail.plan.steps : [];
    if (projectFamily === "failed" || projectFamily === "closeout_failed" || projectStatus.toLowerCase().endsWith("failed")) {
      return "failed";
    }
    if (closeoutStatus === "failed") {
      return "failed";
    }
    if (planSteps.some((step) => String(step?.status || "").trim().toLowerCase() === "failed")) {
      return "failed";
    }
    return "";
  })();
  const shouldDowngradeStoredStatus = !processStatusValue && ["running", "queued", "planning", "closeout", "debugging", "merging", "checkpoint"].includes(storedProjectFamily);
  const resolvedProjectStatus = shouldDowngradeStoredStatus ? deriveIdleProjectStatus(
    livePlan,
    computePlanStats(livePlan || {}),
    projectStatus
  ) : processStatusValue || projectStatus;
  const rawProjectFamily = normalizeExecutionSurfaceStatus(resolvedProjectStatus);
  const planningRunning = isPlanningProgressRunning(detail?.planning_progress);
  let flowFamily = "idle";
  if (checkpointFamily === "checkpoint") {
    flowFamily = "checkpoint";
  } else if (progress.phase === "planning" || planningRunning) {
    flowFamily = "planning";
  } else if (progress.phase === "closeout" || progress.closeoutRunning) {
    flowFamily = "closeout";
  } else if ((progress.phase === "debugging" || isDebuggingStatus(progress.status)) && !executionJob) {
    flowFamily = "debugging";
  } else if (progress.status === "running:merging") {
    flowFamily = "merging";
  } else if (executionJob && processFamily !== "idle") {
    flowFamily = processFamily;
  } else if (progress.isActive) {
    flowFamily = normalizeExecutionSurfaceStatus(progress.status) || "running";
  } else if (rawProjectFamily !== "idle") {
    flowFamily = rawProjectFamily;
  }
  let toolbarFamily = rawProjectFamily;
  if (checkpointFamily === "checkpoint") {
    toolbarFamily = "checkpoint";
  } else if (planningRunning) {
    toolbarFamily = "planning";
  } else if (progress.phase === "planning") {
    toolbarFamily = "planning";
  } else if (progress.phase === "closeout" || progress.closeoutRunning) {
    toolbarFamily = "closeout";
  } else if ((progress.phase === "debugging" || isDebuggingStatus(projectStatus)) && !executionJob) {
    toolbarFamily = "debugging";
  } else if (executionJob && processFamily !== "idle") {
    toolbarFamily = processFamily;
  } else if (processFamily !== "idle") {
    toolbarFamily = processFamily;
  } else if (flowFamily !== "idle") {
    toolbarFamily = flowFamily;
  }
  const surfaces = {
    toolbar: toolbarFamily,
    flow: flowFamily,
    checkpoint: checkpointFamily,
    process: processFamily
  };
  const activeFamilies = Object.entries(surfaces).filter(([, family]) => family !== "idle").map(([, family]) => normalizeExecutionSurfaceStatus(family));
  const uniqueFamilies = [...new Set(activeFamilies)];
  const consistent = terminalFailureFamily ? true : uniqueFamilies.length <= 1;
  const displayFamily = terminalFailureFamily || (consistent ? uniqueFamilies[0] || "idle" : "syncing");
  let displayStatusValue = "idle";
  if (terminalFailureFamily) {
    displayStatusValue = "failed";
  } else if (processStatusValue) {
    displayStatusValue = processStatusValue;
  } else if (!consistent) {
    displayStatusValue = "syncing";
  } else if (checkpointFamily === "checkpoint") {
    displayStatusValue = String(checkpointPending?.status || "awaiting_checkpoint_approval").trim().toLowerCase() || "awaiting_checkpoint_approval";
  } else if (planningRunning || progress.phase === "planning") {
    displayStatusValue = "running:generate-plan";
  } else if (progress.phase === "closeout" || progress.closeoutRunning) {
    displayStatusValue = "running:closeout";
  } else if (progress.phase === "debugging" || !executionJob && isDebuggingStatus(progress.status)) {
    displayStatusValue = "running:debugging";
  } else if (progress.isActive) {
    if (processFamily === "queued") {
      const queuedCommand = String(executionJob?.command || "").trim().toLowerCase();
      displayStatusValue = queuedCommand ? `queued:${queuedCommand}` : "queued";
    } else if (processFamily === "merging") {
      displayStatusValue = "running:merging";
    } else if (processFamily === "running") {
      const runningCommand = String(executionJob?.command || "").trim().toLowerCase();
      displayStatusValue = runningCommand ? `running:${runningCommand}` : "running";
    } else {
      displayStatusValue = normalizeExecutionSurfaceStatus(progress.status) || "running";
    }
  } else if (resolvedProjectStatus.toLowerCase().startsWith("running:") || resolvedProjectStatus.toLowerCase().startsWith("queued:")) {
    displayStatusValue = resolvedProjectStatus.toLowerCase();
  } else if (resolvedProjectStatus) {
    displayStatusValue = String(resolvedProjectStatus).trim().toLowerCase();
  }
  const mismatchEntries = Object.entries(surfaces).filter(([, family]) => family !== "idle").map(([name, family]) => formatExecutionConsistencyLine(name, family));
  return {
    executionJob,
    livePlan,
    progress,
    checkpointExecutionState,
    checkpointPending,
    checkpointFamily,
    processFamily,
    flowFamily,
    toolbarFamily,
    projectStatus,
    displayFamily,
    displayStatusValue,
    consistent,
    activeFamilies: uniqueFamilies,
    surfaces,
    mismatchSummary: consistent ? "" : mismatchEntries.join(" | "),
    reportLines: [
      formatExecutionConsistencyLine("toolbar", toolbarFamily, resolvedProjectStatus),
      formatExecutionConsistencyLine("flow", flowFamily, progress.phase || progress.status),
      formatExecutionConsistencyLine("checkpoint", checkpointFamily, checkpointPending?.status || ""),
      formatExecutionConsistencyLine("process", processFamily, `${String(executionJob?.status || "").trim()} ${String(executionJob?.command || "").trim()}`.trim())
    ]
  };
}
function deriveIdleProjectStatus(plan = null, stats = null, currentStatus = "") {
  const normalizedCurrentStatus = String(currentStatus || "").trim().toLowerCase();
  const closeoutStatus = String(plan?.closeout_status || stats?.closeout_status || "").trim().toLowerCase();
  const effectiveStats = plan ? computePlanStats(plan) : stats || {};
  const totalSteps = Math.max(0, Number(effectiveStats?.total_steps || 0));
  const completedSteps = Math.max(0, Number(effectiveStats?.completed_steps || 0));
  const failedSteps = Math.max(0, Number(effectiveStats?.failed_steps || 0));
  if (closeoutStatus === "completed") {
    return "closed_out";
  }
  if (closeoutStatus === "failed") {
    return "closeout_failed";
  }
  if (normalizedCurrentStatus.endsWith("failed") || failedSteps > 0) {
    return "failed";
  }
  if (totalSteps <= 0) {
    return "setup_ready";
  }
  if (completedSteps >= totalSteps) {
    return "plan_completed";
  }
  return "plan_ready";
}
function resolveExecutionDisplayPlan(detail = null, planDraft = null, activeJob = null) {
  const livePlan = detail?.plan;
  const draftPlan = planDraft && typeof planDraft === "object" ? planDraft : null;
  const jobStatus = String(activeJob?.status || "").trim().toLowerCase();
  const command = String(activeJob?.command || "").trim().toLowerCase();
  const projectStatus = String(detail?.project?.current_status || "").trim().toLowerCase();
  const projectInFlight = projectStatus === "running" || projectStatus.startsWith("running:") || projectStatus === "queued" || projectStatus.startsWith("queued:");
  const planningInFlight = (jobStatus === "running" || jobStatus === "queued") && (command === "generate-plan" || isPlanningProgressRunning(detail?.planning_progress));
  if (planningInFlight && livePlan && typeof livePlan === "object") {
    return livePlan;
  }
  if (projectInFlight && livePlan && typeof livePlan === "object") {
    return livePlan;
  }
  if (jobStatus === "running" && livePlan && typeof livePlan === "object") {
    return livePlan;
  }
  if (draftPlan) {
    return draftPlan;
  }
  if (livePlan && typeof livePlan === "object") {
    return livePlan;
  }
  return draftPlan || livePlan || { steps: [] };
}
function statusTone(status) {
  const normalized = String(status || "").trim().toLowerCase();
  if (isDebuggingStatus(status)) {
    return "warning";
  }
  if (normalized === "syncing" || normalized === "inconsistent") {
    return "warning";
  }
  if (normalized === "awaiting_review" || normalized === "awaiting_checkpoint_approval") {
    return "warning";
  }
  if (normalized.startsWith("queued")) {
    return "info";
  }
  if (normalized.includes("cancelled")) {
    return "neutral";
  }
  if (normalized.includes("failed")) {
    return "danger";
  }
  if (normalized === "integrating") {
    return "info";
  }
  if (normalized.includes("running")) {
    return "info";
  }
  if (normalized === "completed") {
    return "success";
  }
  if (normalized.includes("paused")) {
    return "warning";
  }
  return "neutral";
}
var FAILURE_REASON_LABELS = {
  preflight_failed: {
    en: "Preflight failed",
    ko: "\uC2E4\uD589 \uC900\uBE44 \uC2E4\uD328"
  },
  agent_pass_failed: {
    en: "Agent pass failed",
    ko: "\uC5D0\uC774\uC804\uD2B8 \uC2E4\uD589 \uC2E4\uD328"
  },
  verification_test_failed: {
    en: "Verification tests failed",
    ko: "\uAC80\uC99D \uD14C\uC2A4\uD2B8 \uC2E4\uD328"
  },
  parallel_execution_failed: {
    en: "Parallel execution failed",
    ko: "\uBCD1\uB82C \uC2E4\uD589 \uC2E4\uD328"
  },
  parallel_merge_conflict: {
    en: "Parallel merge conflict",
    ko: "\uBCD1\uB82C \uBCD1\uD569 \uCDA9\uB3CC"
  },
  recovery_artifacts_missing: {
    en: "Recovery artifacts missing",
    ko: "\uBCF5\uAD6C \uC544\uD2F0\uD329\uD2B8 \uC5C6\uC74C"
  },
  merge_conflict_state_invalid: {
    en: "No active merge conflict",
    ko: "\uD65C\uC131 \uBCD1\uD569 \uCDA9\uB3CC \uC5C6\uC74C"
  },
  closeout_failed: {
    en: "Closeout failed",
    ko: "\uD074\uB85C\uC988\uC544\uC6C3 \uC2E4\uD328"
  }
};
function failureReasonLabelForCode(reasonCode, language = "en") {
  const normalized = String(reasonCode || "").trim().toLowerCase();
  if (!normalized) {
    return "";
  }
  const labels = FAILURE_REASON_LABELS[normalized];
  if (labels) {
    return language === "ko" ? labels.ko : labels.en;
  }
  return normalized.split("_").filter(Boolean).map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");
}
function failureReasonCode(value = null) {
  if (!value || typeof value !== "object") {
    return "";
  }
  if (typeof value.failure_reason_code === "string") {
    return value.failure_reason_code.trim().toLowerCase();
  }
  if (typeof value?.metadata?.failure_reason_code === "string") {
    return value.metadata.failure_reason_code.trim().toLowerCase();
  }
  return "";
}
function failureReasonLabel(value = null, language = "en") {
  return failureReasonLabelForCode(failureReasonCode(value), language);
}

// src/components/common/ExecutionFlowChart.jsx
import { jsx, jsxs } from "react/jsx-runtime";
var FONT_FAMILY = '"Segoe UI", "Malgun Gothic", sans-serif';
var BOX_WIDTH = 220;
var BOX_HEIGHT = 136;
var MARGIN_X = 48;
var MARGIN_Y = 72;
var GAP_X = 120;
var GAP_Y = 30;
var SPLIT_GAP = 44;
var MERGE_GAP = 38;
var PALETTE = {
  neutral: { fill: "#1f2937", stroke: "#475569", text: "#e5e7eb", meta: "#94a3b8" },
  info: { fill: "#172554", stroke: "#3b82f6", text: "#dbeafe", meta: "#93c5fd" },
  success: { fill: "#052e2b", stroke: "#14b8a6", text: "#ccfbf1", meta: "#5eead4" },
  warning: { fill: "#422006", stroke: "#f59e0b", text: "#fef3c7", meta: "#fcd34d" },
  danger: { fill: "#450a0a", stroke: "#ef4444", text: "#fee2e2", meta: "#fca5a5" }
};
var TOPOLOGY_CACHE_LIMIT = 24;
var chartTopologyCache = /* @__PURE__ */ new Map();
function compactChartText(value, maxChars) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text) {
    return "";
  }
  if (text.length <= maxChars) {
    return text;
  }
  return `${text.slice(0, Math.max(0, maxChars - 3)).trimEnd()}...`;
}
function wrapChartText(value, maxCharsPerLine, maxLines = 2) {
  const text = compactChartText(value, maxCharsPerLine * maxLines + 8);
  if (!text) {
    return [];
  }
  const words = text.split(/\s+/).filter(Boolean);
  const lines = [];
  let current = "";
  for (const word of words) {
    const candidate = current ? `${current} ${word}` : word;
    if (candidate.length <= maxCharsPerLine) {
      current = candidate;
      continue;
    }
    if (current) {
      lines.push(current);
    }
    current = word;
    if (lines.length >= maxLines - 1) {
      break;
    }
  }
  if (current && lines.length < maxLines) {
    lines.push(current);
  }
  if (!lines.length) {
    lines.push(text.slice(0, maxCharsPerLine));
  }
  const trimmed = lines.slice(0, maxLines);
  const usedText = trimmed.join(" ");
  if (text.length > usedText.length && trimmed.length) {
    trimmed[trimmed.length - 1] = compactChartText(trimmed[trimmed.length - 1], maxCharsPerLine);
  }
  return trimmed;
}
function SvgTextBlock({ x, y, lines, fill, fontSize, fontWeight = "400", lineHeight = 16 }) {
  const safeLines = Array.isArray(lines) ? lines.filter(Boolean) : [];
  if (!safeLines.length) {
    return null;
  }
  return /* @__PURE__ */ jsx("text", { x, y, fill, fontFamily: FONT_FAMILY, fontSize, fontWeight, children: safeLines.map((line, index) => /* @__PURE__ */ jsx("tspan", { x, dy: index === 0 ? 0 : lineHeight, children: line }, `${x}-${y}-${index}`)) });
}
function buildChartLevels(steps = []) {
  const orderedSteps = Array.isArray(steps) ? steps : [];
  if (!orderedSteps.length) {
    return [];
  }
  const usesDag = orderedSteps.some((step) => (step.depends_on || []).length || (step.owned_paths || []).length);
  if (!usesDag) {
    return orderedSteps.map((step) => [step]);
  }
  const stepById = new Map(orderedSteps.map((step) => [step.step_id, step]));
  const visited = /* @__PURE__ */ new Set();
  const levels = [];
  while (visited.size < orderedSteps.length) {
    const ready = orderedSteps.filter(
      (step) => !visited.has(step.step_id) && (step.depends_on || []).every((dependency) => visited.has(dependency) || !stepById.has(dependency))
    );
    const layer = ready.length ? ready : orderedSteps.filter((step) => !visited.has(step.step_id)).slice(0, 1);
    levels.push(layer);
    layer.forEach((step) => visited.add(step.step_id));
  }
  return levels;
}
function levelRowOrderSignature(level = []) {
  return level.map((step) => String(step?.step_id || "")).join("|");
}
function averageIndex(values = []) {
  if (!values.length) {
    return null;
  }
  return values.reduce((total, value) => total + value, 0) / values.length;
}
function orderChartLevels(levels = []) {
  const normalizedLevels = (levels || []).map((level) => [...level]);
  if (normalizedLevels.length <= 2) {
    return normalizedLevels;
  }
  let changed = true;
  let guard = 0;
  while (changed && guard < 6) {
    changed = false;
    guard += 1;
    for (let levelIndex = 1; levelIndex < normalizedLevels.length; levelIndex += 1) {
      const previousLevel = normalizedLevels[levelIndex - 1] || [];
      const indexByStepId = new Map(previousLevel.map((step, index) => [step.step_id, index]));
      const nextOrder = [...normalizedLevels[levelIndex]].sort((left, right) => {
        const leftParents = (left.depends_on || []).map((dependency) => indexByStepId.get(dependency)).filter((value) => Number.isFinite(value));
        const rightParents = (right.depends_on || []).map((dependency) => indexByStepId.get(dependency)).filter((value) => Number.isFinite(value));
        const leftScore = averageIndex(leftParents);
        const rightScore = averageIndex(rightParents);
        if (leftScore == null && rightScore == null) {
          return String(left.step_id || "").localeCompare(String(right.step_id || ""));
        }
        if (leftScore == null) {
          return 1;
        }
        if (rightScore == null) {
          return -1;
        }
        if (leftScore !== rightScore) {
          return leftScore - rightScore;
        }
        return String(left.step_id || "").localeCompare(String(right.step_id || ""));
      });
      if (levelRowOrderSignature(nextOrder) !== levelRowOrderSignature(normalizedLevels[levelIndex])) {
        normalizedLevels[levelIndex] = nextOrder;
        changed = true;
      }
    }
    for (let levelIndex = normalizedLevels.length - 2; levelIndex >= 0; levelIndex -= 1) {
      const nextLevel = normalizedLevels[levelIndex + 1] || [];
      const childIndexById = new Map(nextLevel.map((step, index) => [step.step_id, index]));
      const nextOrder = [...normalizedLevels[levelIndex]].sort((left, right) => {
        const leftChildren = nextLevel.filter((step) => (step.depends_on || []).includes(left.step_id)).map((step) => childIndexById.get(step.step_id)).filter((value) => Number.isFinite(value));
        const rightChildren = nextLevel.filter((step) => (step.depends_on || []).includes(right.step_id)).map((step) => childIndexById.get(step.step_id)).filter((value) => Number.isFinite(value));
        const leftScore = averageIndex(leftChildren);
        const rightScore = averageIndex(rightChildren);
        if (leftScore == null && rightScore == null) {
          return String(left.step_id || "").localeCompare(String(right.step_id || ""));
        }
        if (leftScore == null) {
          return 1;
        }
        if (rightScore == null) {
          return -1;
        }
        if (leftScore !== rightScore) {
          return leftScore - rightScore;
        }
        return String(left.step_id || "").localeCompare(String(right.step_id || ""));
      });
      if (levelRowOrderSignature(nextOrder) !== levelRowOrderSignature(normalizedLevels[levelIndex])) {
        normalizedLevels[levelIndex] = nextOrder;
        changed = true;
      }
    }
  }
  return normalizedLevels;
}
function orthogonalPath(startX, startY, endX, endY) {
  if (startX === endX && startY === endY) {
    return `M ${startX} ${startY}`;
  }
  if (startY === endY) {
    return `M ${startX} ${startY} H ${endX}`;
  }
  const middleX = Math.round(startX + (endX - startX) / 2);
  return `M ${startX} ${startY} H ${middleX} V ${endY} H ${endX}`;
}
function chartTopologySignature(steps = []) {
  return (steps || []).map((step) => [
    step?.step_id || "",
    (step?.depends_on || []).join(","),
    (step?.owned_paths || []).length
  ].join("|")).join("::");
}
function buildChartTopology(steps = []) {
  const levels = orderChartLevels(buildChartLevels(steps));
  const positions = /* @__PURE__ */ new Map();
  const maxRows = Math.max(1, ...levels.map((level) => level.length));
  const contentHeight = maxRows * BOX_HEIGHT + Math.max(0, maxRows - 1) * GAP_Y;
  const width = Math.max(960, MARGIN_X * 2 + levels.length * BOX_WIDTH + Math.max(0, levels.length - 1) * GAP_X);
  const height = Math.max(320, MARGIN_Y * 2 + contentHeight);
  levels.forEach((level, levelIndex) => {
    const x = MARGIN_X + levelIndex * (BOX_WIDTH + GAP_X);
    const levelHeight = level.length * BOX_HEIGHT + Math.max(0, level.length - 1) * GAP_Y;
    const offsetY = MARGIN_Y + Math.max(0, (contentHeight - levelHeight) / 2);
    level.forEach((step, rowIndex) => {
      const y = offsetY + rowIndex * (BOX_HEIGHT + GAP_Y);
      positions.set(step.step_id, { x, y });
    });
  });
  const incoming = new Map(steps.map((step) => [step.step_id, []]));
  const outgoing = new Map(steps.map((step) => [step.step_id, []]));
  steps.forEach((step) => {
    (step.depends_on || []).forEach((dependency) => {
      if (!positions.has(dependency)) {
        return;
      }
      incoming.get(step.step_id)?.push(dependency);
      outgoing.get(dependency)?.push(step.step_id);
    });
  });
  const nodes = steps.filter((step) => positions.has(step.step_id)).map((step) => {
    const { x, y } = positions.get(step.step_id);
    const failureReason = failureReasonLabel(step, "en");
    return {
      step,
      x,
      y,
      titleLines: wrapChartText(step.title, 24, 2),
      detailSource: failureReason || step.display_description || step.success_criteria || ((step.depends_on || []).length ? (step.depends_on || []).join(", ") : "") || ((step.owned_paths || []).length ? `${step.owned_paths.length} owned path(s)` : "No summary")
    };
  });
  const splitJunctions = [];
  const mergeJunctions = [];
  const nodeToSplitSegments = [];
  const mergeBusSegments = [];
  const mergeToNodeSegments = [];
  const edgeSegments = [];
  const splitById = /* @__PURE__ */ new Map();
  const mergeById = /* @__PURE__ */ new Map();
  steps.forEach((step) => {
    if (!positions.has(step.step_id)) {
      return;
    }
    const { x, y } = positions.get(step.step_id);
    const targets = outgoing.get(step.step_id) || [];
    const parents = incoming.get(step.step_id) || [];
    const centerY = y + BOX_HEIGHT / 2;
    if (targets.length > 1) {
      const junction = { x: x + BOX_WIDTH + SPLIT_GAP, y: centerY };
      splitById.set(step.step_id, junction);
      splitJunctions.push(junction);
      nodeToSplitSegments.push({
        key: `${step.step_id}-split`,
        d: `M ${x + BOX_WIDTH} ${centerY} H ${junction.x}`
      });
    }
    if (parents.length > 1) {
      const junction = { x: x - MERGE_GAP, y: centerY };
      mergeById.set(step.step_id, junction);
      mergeJunctions.push(junction);
      const parentCenterYs = parents.map((parentId) => positions.get(parentId)).filter(Boolean).map((position) => position.y + BOX_HEIGHT / 2);
      const mergeSpanYs = [...parentCenterYs, centerY];
      const minY = Math.min(...mergeSpanYs);
      const maxY = Math.max(...mergeSpanYs);
      if (Number.isFinite(minY) && Number.isFinite(maxY) && minY !== maxY) {
        mergeBusSegments.push({
          key: `${step.step_id}-merge-bus`,
          d: `M ${junction.x} ${minY} V ${maxY}`
        });
      }
      mergeToNodeSegments.push({
        key: `${step.step_id}-merge`,
        d: `M ${junction.x} ${junction.y} H ${x}`
      });
    }
  });
  steps.forEach((step) => {
    if (!positions.has(step.step_id)) {
      return;
    }
    const targets = outgoing.get(step.step_id) || [];
    const sourcePosition = positions.get(step.step_id);
    const sourceCenter = {
      x: sourcePosition.x + BOX_WIDTH,
      y: sourcePosition.y + BOX_HEIGHT / 2
    };
    const startPoint = splitById.get(step.step_id) || sourceCenter;
    targets.forEach((targetId) => {
      const targetPosition = positions.get(targetId);
      if (!targetPosition) {
        return;
      }
      const targetCenter = {
        x: targetPosition.x,
        y: targetPosition.y + BOX_HEIGHT / 2
      };
      const mergePoint = mergeById.get(targetId);
      edgeSegments.push({
        key: `${step.step_id}-${targetId}`,
        d: mergePoint ? `M ${startPoint.x} ${startPoint.y} H ${mergePoint.x}` : orthogonalPath(startPoint.x, startPoint.y, targetCenter.x, targetCenter.y),
        arrow: !mergePoint
      });
    });
  });
  return {
    width,
    height,
    nodes,
    edgeSegments,
    nodeToSplitSegments,
    mergeBusSegments,
    mergeToNodeSegments,
    splitJunctions,
    mergeJunctions
  };
}
function getChartTopology(steps = []) {
  const signature = chartTopologySignature(steps);
  const cached = chartTopologyCache.get(signature);
  if (cached) {
    return cached;
  }
  const topology = buildChartTopology(steps);
  if (chartTopologyCache.size >= TOPOLOGY_CACHE_LIMIT) {
    const oldestKey = chartTopologyCache.keys().next().value;
    chartTopologyCache.delete(oldestKey);
  }
  chartTopologyCache.set(signature, topology);
  return topology;
}
function effectiveChartStepStatus(step = null, projectStatus = "", activeLineageId = "", checkpointState = null, checkpointFamily = "") {
  const currentStatus = effectiveStepStatus(step, projectStatus);
  const normalizedStepStatus = String(step?.status || "").trim().toLowerCase();
  const normalizedProjectStatus = String(projectStatus || "").trim().toLowerCase();
  const stepLineageId = String(step?.metadata?.lineage_id || "").trim();
  const activeLineage = String(checkpointState?.currentCheckpointLineageId || activeLineageId || "").trim();
  const statusByStepId = checkpointState?.statusByStepId instanceof Map ? checkpointState.statusByStepId : null;
  const statusByLineageId = checkpointState?.statusByLineageId instanceof Map ? checkpointState.statusByLineageId : null;
  const checkpointStatus = statusByStepId && statusByStepId.get(String(step?.step_id || "").trim()) || statusByLineageId && statusByLineageId.get(stepLineageId) || "";
  if (checkpointStatus) {
    return checkpointStatus;
  }
  const lineageIsActive = Boolean(activeLineage) && Boolean(stepLineageId) && stepLineageId === activeLineage && (checkpointState?.hasActiveCheckpoint || checkpointFamily === "checkpoint" || checkpointFamily === "failed" || checkpointFamily === "completed" || normalizedProjectStatus.startsWith("running:") || normalizedProjectStatus === "running" || normalizedProjectStatus.startsWith("queued:") || normalizedProjectStatus === "queued" || normalizedProjectStatus === "awaiting_checkpoint_approval" || normalizedProjectStatus === "awaiting_review" || isDebuggingStatus(projectStatus));
  if (lineageIsActive) {
    if (checkpointState?.waitingForApproval || checkpointFamily === "checkpoint" || normalizedProjectStatus === "awaiting_checkpoint_approval" || normalizedProjectStatus === "awaiting_review") {
      return String(checkpointState?.pending?.status || "awaiting_review").trim().toLowerCase() || "awaiting_review";
    }
    if (checkpointFamily === "failed" || normalizedProjectStatus.endsWith("failed")) {
      return "failed";
    }
    if (checkpointFamily === "completed" || normalizedProjectStatus === "completed") {
      return "completed";
    }
    if (normalizedProjectStatus.startsWith("queued:") || normalizedProjectStatus === "queued") {
      return "queued";
    }
    if (isDebuggingStatus(projectStatus)) {
      return "running:debugging";
    }
    if (checkpointState?.processActive || normalizedProjectStatus.startsWith("running:") || normalizedProjectStatus === "running") {
      return "running";
    }
    return normalizedStepStatus || currentStatus || "pending";
  }
  return currentStatus;
}
function buildChartData(steps = [], projectStatus = "", language = "en", activeLineageId = "", checkpointState = null, checkpointFamily = "") {
  const statusByStepId = /* @__PURE__ */ new Map();
  const statusByLineageId = /* @__PURE__ */ new Map();
  const registerStatus = (key, status) => {
    const normalizedKey = String(key || "").trim();
    const normalizedStatus = String(status || "").trim().toLowerCase();
    if (!normalizedKey || !normalizedStatus) {
      return;
    }
    statusByStepId.set(normalizedKey, normalizedStatus);
  };
  const registerLineageStatus = (key, status) => {
    const normalizedKey = String(key || "").trim();
    const normalizedStatus = String(status || "").trim().toLowerCase();
    if (!normalizedKey || !normalizedStatus) {
      return;
    }
    statusByLineageId.set(normalizedKey, normalizedStatus);
  };
  const checkpointItems = Array.isArray(checkpointState?.items) ? checkpointState.items : [];
  for (const item of checkpointItems) {
    const itemStatus = String(item?.status || "").trim().toLowerCase();
    const lineageId = String(item?.lineage_id || "").trim();
    const planRefs = Array.isArray(item?.plan_refs) ? item.plan_refs : [];
    for (const ref of planRefs) {
      registerStatus(ref, itemStatus);
      if (lineageId) {
        registerLineageStatus(lineageId, itemStatus);
      }
    }
  }
  if (checkpointState?.pending && typeof checkpointState.pending === "object") {
    const pendingStatus = String(checkpointState.pending.status || "awaiting_review").trim().toLowerCase() || "awaiting_review";
    const pendingLineageId = String(checkpointState.pending.lineage_id || checkpointState.currentCheckpointLineageId || "").trim();
    const pendingRefs = Array.isArray(checkpointState.pending.plan_refs) ? checkpointState.pending.plan_refs : [];
    for (const ref of pendingRefs) {
      registerStatus(ref, pendingStatus);
      if (pendingLineageId) {
        registerLineageStatus(pendingLineageId, pendingStatus);
      }
    }
  }
  const checkpointLookup = {
    ...checkpointState,
    statusByStepId,
    statusByLineageId
  };
  const topology = getChartTopology(steps);
  return {
    ...topology,
    nodes: topology.nodes.map((node) => {
      const stepStatus = effectiveChartStepStatus(node.step, projectStatus, activeLineageId, checkpointLookup, checkpointFamily);
      const tone = statusTone(stepStatus);
      const palette = PALETTE[tone] || PALETTE.neutral;
      const failureReason = failureReasonLabel(node.step, language);
      return {
        ...node,
        stepStatus,
        tone,
        palette,
        detailLines: wrapChartText(
          String(stepStatus || "").trim().toLowerCase().includes("failed") ? failureReason || node.step.notes || node.detailSource : node.detailSource,
          28,
          2
        ),
        statusLabel: displayStatus(stepStatus, language),
        failureReason
      };
    })
  };
}
function ExecutionFlowChartComponent({ steps = [], detail = null, activeJob = null, language = "en", selectedStepId = "", onSelectStep = null }) {
  const arrowId = useId().replace(/:/g, "-");
  const executionState = useMemo(() => deriveExecutionUiState(detail, null, activeJob), [detail, activeJob]);
  const chart = useMemo(
    () => buildChartData(
      steps,
      executionState.displayStatusValue,
      language,
      String(executionState.checkpointExecutionState?.currentCheckpointLineageId || executionState.checkpointPending?.lineage_id || "").trim(),
      executionState.checkpointExecutionState,
      executionState.checkpointFamily
    ),
    [steps, executionState.displayStatusValue, language, executionState.checkpointExecutionState, executionState.checkpointFamily, executionState.checkpointPending?.lineage_id]
  );
  if (!steps.length) {
    return null;
  }
  return /* @__PURE__ */ jsx("div", { className: "history-flow", children: /* @__PURE__ */ jsx("div", { className: "history-flow__canvas", children: /* @__PURE__ */ jsxs(
    "svg",
    {
      "aria-label": "Execution flow chart",
      role: "img",
      viewBox: `0 0 ${chart.width} ${chart.height}`,
      width: chart.width,
      height: chart.height,
      children: [
        /* @__PURE__ */ jsx("defs", { children: /* @__PURE__ */ jsx(
          "marker",
          {
            id: arrowId,
            markerWidth: "10",
            markerHeight: "10",
            refX: "8",
            refY: "5",
            orient: "auto",
            markerUnits: "strokeWidth",
            children: /* @__PURE__ */ jsx("path", { d: "M 0 0 L 10 5 L 0 10 z", fill: "#64748b" })
          }
        ) }),
        chart.nodeToSplitSegments.map((segment) => /* @__PURE__ */ jsx("path", { d: segment.d, stroke: "#64748b", strokeWidth: "3", fill: "none", strokeLinecap: "round" }, segment.key)),
        chart.edgeSegments.map((segment) => /* @__PURE__ */ jsx(
          "path",
          {
            d: segment.d,
            stroke: "#64748b",
            strokeWidth: "3",
            fill: "none",
            strokeLinecap: "round",
            strokeLinejoin: "round",
            markerEnd: segment.arrow ? `url(#${arrowId})` : void 0
          },
          segment.key
        )),
        chart.mergeBusSegments.map((segment) => /* @__PURE__ */ jsx("path", { d: segment.d, stroke: "#64748b", strokeWidth: "3", fill: "none", strokeLinecap: "round" }, segment.key)),
        chart.mergeToNodeSegments.map((segment) => /* @__PURE__ */ jsx(
          "path",
          {
            d: segment.d,
            stroke: "#64748b",
            strokeWidth: "3",
            fill: "none",
            strokeLinecap: "round",
            markerEnd: `url(#${arrowId})`
          },
          segment.key
        )),
        chart.splitJunctions.map((junction, index) => /* @__PURE__ */ jsx("circle", { cx: junction.x, cy: junction.y, r: "5", fill: "#0f172a", stroke: "#64748b", strokeWidth: "2" }, `split-${index}`)),
        chart.mergeJunctions.map((junction, index) => /* @__PURE__ */ jsx("circle", { cx: junction.x, cy: junction.y, r: "5", fill: "#0f172a", stroke: "#64748b", strokeWidth: "2" }, `merge-${index}`)),
        chart.nodes.map((node) => {
          const selected = node.step.step_id === selectedStepId;
          const stroke = selected ? "#f8fafc" : node.palette.stroke;
          const strokeWidth = selected ? 3 : 2;
          return /* @__PURE__ */ jsxs(
            "g",
            {
              className: `execution-flow-chart__node execution-flow-chart__node--${node.tone} ${selected ? "selected" : ""}`,
              onClick: () => onSelectStep?.(node.step.step_id),
              style: { cursor: onSelectStep ? "pointer" : "default" },
              children: [
                /* @__PURE__ */ jsx("title", { children: `${node.step.step_id}: ${node.step.title}${node.failureReason ? `
Failure: ${node.failureReason}` : ""}` }),
                /* @__PURE__ */ jsx(
                  "rect",
                  {
                    x: node.x,
                    y: node.y,
                    rx: "22",
                    ry: "22",
                    width: BOX_WIDTH,
                    height: BOX_HEIGHT,
                    fill: node.palette.fill,
                    stroke,
                    strokeWidth
                  }
                ),
                /* @__PURE__ */ jsx(SvgTextBlock, { x: node.x + 18, y: node.y + 26, lines: [node.step.step_id], fill: node.palette.meta, fontSize: "13", fontWeight: "700" }),
                /* @__PURE__ */ jsx(SvgTextBlock, { x: node.x + 18, y: node.y + 50, lines: node.titleLines, fill: node.palette.text, fontSize: "13", fontWeight: "700", lineHeight: 16 }),
                /* @__PURE__ */ jsx(SvgTextBlock, { x: node.x + 18, y: node.y + 86, lines: node.detailLines, fill: node.palette.meta, fontSize: "11", lineHeight: 14 }),
                /* @__PURE__ */ jsx(SvgTextBlock, { x: node.x + 18, y: node.y + 120, lines: [node.statusLabel], fill: node.palette.text, fontSize: "11" })
              ]
            },
            node.step.step_id
          );
        })
      ]
    }
  ) }) });
}
var ExecutionFlowChart = memo(ExecutionFlowChartComponent);
var __executionFlowChartTestables = {
  buildChartLevels,
  orderChartLevels,
  buildChartTopology
};

// execution-flow-chart-topology.jsx
function buildTopology(steps) {
  return __executionFlowChartTestables.buildChartTopology(steps);
}
export {
  buildTopology
};
