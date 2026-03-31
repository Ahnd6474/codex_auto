import { Suspense, lazy, memo, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { ChatMessageContent } from "../../chatMarkdown";
import { useI18n } from "../../i18n";
import { usePersistentState } from "../../hooks/usePersistentState";
import {
  MODEL_REASONING_OPTIONS,
  formatChatSessionTitle,
  formatDurationCompact,
  reasoningEffortLabel,
  resolveExecutionDisplayPlan,
  visibleExecutionJob,
} from "../../utils";

function RailChatIcon() {
  return (
    <svg aria-hidden="true" className="sidebar-icon__svg" viewBox="0 0 24 24" fill="none">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function RailTerminalIcon() {
  return (
    <svg aria-hidden="true" className="sidebar-icon__svg" viewBox="0 0 24 24" fill="none">
      <rect x="2" y="4" width="20" height="16" rx="2" stroke="currentColor" strokeWidth="1.6" />
      <path d="M6 9l4 3-4 3M13 15h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function RailFilesIcon() {
  return (
    <svg aria-hidden="true" className="sidebar-icon__svg" viewBox="0 0 24 24" fill="none">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <polyline points="14 2 14 8 20 8" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
    </svg>
  );
}

function RailInspectorIcon() {
  return (
    <svg aria-hidden="true" className="sidebar-icon__svg" viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" />
      <path d="M12 8v4M12 16h.01" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function RailContractsIcon() {
  return (
    <svg aria-hidden="true" className="sidebar-icon__svg" viewBox="0 0 24 24" fill="none">
      <circle cx="6" cy="12" r="2.2" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="18" cy="6" r="2.2" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="18" cy="18" r="2.2" stroke="currentColor" strokeWidth="1.5" />
      <path d="M8 12h4M14.5 7.5l-3 3M14.5 16.5l-3-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function RailFlowIcon() {
  return (
    <svg aria-hidden="true" className="sidebar-icon__svg" viewBox="0 0 24 24" fill="none">
      <rect x="3" y="10" width="5" height="5" rx="1.4" stroke="currentColor" strokeWidth="1.6" />
      <rect x="16" y="4" width="5" height="5" rx="1.4" stroke="currentColor" strokeWidth="1.6" />
      <rect x="16" y="15" width="5" height="5" rx="1.4" stroke="currentColor" strokeWidth="1.6" />
      <path d="M8 12.5h4m0 0V6.5m0 6v6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M12 6.5h4M12 18.5h4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M22 2L11 13M22 2L15 22l-4-9-9-4 20-7z" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function lazyNamedExport(loader, exportName) {
  return lazy(() => loader().then((module) => ({ default: module[exportName] })));
}

const LazyOutputPanel = lazyNamedExport(() => import("./RightSidebarDetailPanels"), "OutputPanel");
const LazyFilesPanel = lazyNamedExport(() => import("./RightSidebarDetailPanels"), "FilesPanel");
const LazyContractsPanel = lazyNamedExport(() => import("./RightSidebarDetailPanels"), "ContractsPanel");
const LazyInspectorPanel = lazyNamedExport(() => import("./RightSidebarDetailPanels"), "InspectorPanel");
const LazyFlowWorkspaceView = lazyNamedExport(() => import("../views/FlowWorkspaceView"), "FlowWorkspaceView");

function chatModelOptionValue(item = {}) {
  const provider = String(item?.provider || "openai").trim().toLowerCase() || "openai";
  const localProvider = String(item?.local_provider || "").trim().toLowerCase();
  const model = String(item?.model || "").trim().toLowerCase();
  return model ? [provider, localProvider, model].join("::") : "";
}

function parseChatModelOptionValue(value = "") {
  const [provider = "", localProvider = "", model = ""] = String(value || "").split("::");
  return {
    provider: String(provider || "").trim().toLowerCase(),
    localProvider: String(localProvider || "").trim().toLowerCase(),
    model: String(model || "").trim().toLowerCase(),
  };
}

function chatProviderLabel(provider = "", localProvider = "", language = "en") {
  const normalizedProvider = String(provider || "").trim().toLowerCase();
  const normalizedLocalProvider = String(localProvider || "").trim().toLowerCase();
  if (normalizedProvider === "openai") return "OpenAI";
  if (normalizedProvider === "claude") return "Claude";
  if (normalizedProvider === "gemini") return "Gemini";
  if (normalizedProvider === "ensemble") return language === "ko" ? "Ensemble" : "Ensemble";
  if (normalizedProvider === "ollama") return "Ollama";
  if (normalizedProvider === "oss") {
    return normalizedLocalProvider === "lmstudio" ? "LM Studio" : "Ollama";
  }
  if (normalizedProvider === "qwen_code") return "Qwen Code";
  if (normalizedProvider === "deepseek") return "DeepSeek";
  if (normalizedProvider === "kimi") return "Kimi";
  if (normalizedProvider === "minimax") return "MiniMax";
  if (normalizedProvider === "glm") return "GLM";
  if (normalizedProvider === "openrouter") return "OpenRouter";
  if (normalizedProvider === "opencdk") return "OpenCDK";
  if (normalizedProvider === "local_openai") return "Local OpenAI";
  return normalizedProvider || "OpenAI";
}

function sameChatMessages(previousMessages = [], nextMessages = []) {
  if (previousMessages === nextMessages) {
    return true;
  }
  if (!Array.isArray(previousMessages) || !Array.isArray(nextMessages) || previousMessages.length !== nextMessages.length) {
    return false;
  }
  const previousLast = previousMessages[previousMessages.length - 1] || null;
  const nextLast = nextMessages[nextMessages.length - 1] || null;
  return (
    previousLast?.message_id === nextLast?.message_id
    && previousLast?.text === nextLast?.text
    && previousLast?.role === nextLast?.role
  );
}

function sameArtifactFiles(previousFiles = [], nextFiles = []) {
  if (previousFiles === nextFiles) {
    return true;
  }
  if (!Array.isArray(previousFiles) || !Array.isArray(nextFiles) || previousFiles.length !== nextFiles.length) {
    return false;
  }
  return previousFiles.every((value, index) => value === nextFiles[index]);
}

function sameQueuedJobs(previousJobs = [], nextJobs = []) {
  if (previousJobs === nextJobs) {
    return true;
  }
  if (!Array.isArray(previousJobs) || !Array.isArray(nextJobs) || previousJobs.length !== nextJobs.length) {
    return false;
  }
  for (let index = 0; index < previousJobs.length; index += 1) {
    const previousJob = previousJobs[index];
    const nextJob = nextJobs[index];
    if (
      previousJob?.id !== nextJob?.id
      || previousJob?.status !== nextJob?.status
      || previousJob?.queue_position !== nextJob?.queue_position
    ) {
      return false;
    }
  }
  return true;
}

function rightRailTabIds(includeChatTab = true) {
  return includeChatTab
    ? ["chat", "flow", "output", "files", "contracts", "inspector"]
    : ["flow", "output", "files", "contracts", "inspector"];
}

function effectiveRightSidebarTab(activeTab = "chat", includeChatTab = true) {
  const requestedTab = String(activeTab || "").trim();
  const availableTabs = rightRailTabIds(includeChatTab);
  return availableTabs.includes(requestedTab) ? requestedTab : (availableTabs[0] || "");
}

function rightSidebarPanePropsEqual(previousProps, nextProps) {
  const previousActiveTab = effectiveRightSidebarTab(previousProps.activeTab, previousProps.includeChatTab);
  const nextActiveTab = effectiveRightSidebarTab(nextProps.activeTab, nextProps.includeChatTab);
  if (previousActiveTab !== nextActiveTab || previousProps.collapsed !== nextProps.collapsed) {
    return false;
  }
  if (previousProps.chatCenterMode !== nextProps.chatCenterMode) {
    return false;
  }
  if (previousProps.includeChatTab !== nextProps.includeChatTab) {
    return false;
  }

  const previousProcessOutput = previousProps.detail?.subprocess_output || previousProps.detail?.agent_output || previousProps.detail?.process_log || "";
  const nextProcessOutput = nextProps.detail?.subprocess_output || nextProps.detail?.agent_output || nextProps.detail?.process_log || "";
  const previousHasFiles = Boolean(
    previousProps.detail?.files?.closeout_report_file
    || previousProps.detail?.reports?.word_report_path
    || previousProps.detail?.reports?.powerpoint_report_path
    || previousProps.detail?.reports?.webpage_path
    || previousProps.detail?.files?.ml_experiment_report_file,
  );
  const nextHasFiles = Boolean(
    nextProps.detail?.files?.closeout_report_file
    || nextProps.detail?.reports?.word_report_path
    || nextProps.detail?.reports?.powerpoint_report_path
    || nextProps.detail?.reports?.webpage_path
    || nextProps.detail?.files?.ml_experiment_report_file,
  );
  const previousContractAttention =
    Number(previousProps.detail?.reports?.common_requirements?.open_count || 0) > 0
    || Number(previousProps.detail?.reports?.lineage_manifest_summary?.yellow_count || 0) > 0
    || Number(previousProps.detail?.reports?.lineage_manifest_summary?.red_count || 0) > 0;
  const nextContractAttention =
    Number(nextProps.detail?.reports?.common_requirements?.open_count || 0) > 0
    || Number(nextProps.detail?.reports?.lineage_manifest_summary?.yellow_count || 0) > 0
    || Number(nextProps.detail?.reports?.lineage_manifest_summary?.red_count || 0) > 0;

  if (
    previousProcessOutput !== nextProcessOutput
    || previousHasFiles !== nextHasFiles
    || previousContractAttention !== nextContractAttention
  ) {
    return false;
  }

  switch (nextActiveTab) {
    case "chat":
      return (
        previousProps.chat === nextProps.chat
        && previousProps.chatJob === nextProps.chatJob
        && previousProps.chatSettings === nextProps.chatSettings
        && previousProps.selectedChatSessionId === nextProps.selectedChatSessionId
        && previousProps.chatDraftSession === nextProps.chatDraftSession
        && previousProps.busy === nextProps.busy
        && previousProps.detail?.runtime === nextProps.detail?.runtime
        && previousProps.modelCatalog === nextProps.modelCatalog
        && previousProps.modelPresets === nextProps.modelPresets
      );
    case "flow":
      return (
        previousProps.detail === nextProps.detail
        && previousProps.form === nextProps.form
        && previousProps.planDraft === nextProps.planDraft
        && previousProps.activeJob === nextProps.activeJob
        && previousProps.autoRunAfterPlan === nextProps.autoRunAfterPlan
        && previousProps.selectedStepId === nextProps.selectedStepId
        && previousProps.busy === nextProps.busy
        && previousProps.canRequestStop === nextProps.canRequestStop
        && previousProps.canCancelReservation === nextProps.canCancelReservation
        && sameQueuedJobs(previousProps.queuedJobs, nextProps.queuedJobs)
      );
    case "output":
      return true;
    case "files":
      return (
        previousProps.detail?.files === nextProps.detail?.files
        && previousProps.form?.runtime?.generate_word_report === nextProps.form?.runtime?.generate_word_report
        && previousProps.activeJob?.status === nextProps.activeJob?.status
        && previousProps.busy === nextProps.busy
        && previousProps.detail?.reports?.word_report_path === nextProps.detail?.reports?.word_report_path
        && previousProps.detail?.reports?.powerpoint_report_path === nextProps.detail?.reports?.powerpoint_report_path
        && previousProps.detail?.reports?.powerpoint_report_target_path === nextProps.detail?.reports?.powerpoint_report_target_path
        && previousProps.detail?.reports?.webpage_path === nextProps.detail?.reports?.webpage_path
        && sameArtifactFiles(
          previousProps.detail?.reports?.latest_failure?.artifact_files,
          nextProps.detail?.reports?.latest_failure?.artifact_files,
        )
      );
    case "contracts":
      return (
        previousProps.detail?.reports === nextProps.detail?.reports
        && previousProps.detail?.files === nextProps.detail?.files
        && previousProps.detail?.plan === nextProps.detail?.plan
        && previousProps.detail?.history?.ui_events === nextProps.detail?.history?.ui_events
        && previousProps.planDraft === nextProps.planDraft
        && previousProps.activeJob === nextProps.activeJob
        && previousProps.selectedStepId === nextProps.selectedStepId
        && previousProps.busy === nextProps.busy
      );
    case "inspector":
      return (
        previousProps.detail?.project === nextProps.detail?.project
        && previousProps.detail?.runtime === nextProps.detail?.runtime
        && previousProps.detail?.plan === nextProps.detail?.plan
        && previousProps.detail?.history?.ui_events === nextProps.detail?.history?.ui_events
        && previousProps.detail?.reports?.closeout_report_text === nextProps.detail?.reports?.closeout_report_text
        && previousProps.detail?.checkpoints?.pending === nextProps.detail?.checkpoints?.pending
        && previousProps.planDraft === nextProps.planDraft
        && previousProps.activeJob === nextProps.activeJob
        && previousProps.selectedStepId === nextProps.selectedStepId
      );
    default:
      return false;
  }
}

function sameChatSessions(previousSessions = [], nextSessions = []) {
  if (previousSessions === nextSessions) {
    return true;
  }
  if (!Array.isArray(previousSessions) || !Array.isArray(nextSessions) || previousSessions.length !== nextSessions.length) {
    return false;
  }
  for (let index = 0; index < previousSessions.length; index += 1) {
    const previousSession = previousSessions[index];
    const nextSession = nextSessions[index];
    if (
      previousSession?.session_id !== nextSession?.session_id
      || previousSession?.title !== nextSession?.title
      || previousSession?.message_count !== nextSession?.message_count
    ) {
      return false;
    }
  }
  return true;
}

const MAX_VISIBLE_CHAT_MESSAGES = 120;
const CHAT_MESSAGE_BATCH = 100;
const CHAT_ESTIMATED_ROW_HEIGHT = 92;
const CHAT_OVERSCAN_ROWS = 6;
const CHAT_DEFAULT_VIEWPORT_HEIGHT = 520;
const DEFAULT_CHAT_MODE = "review";
const RIGHT_SIDEBAR_CHAT_MODE_KEY = "jakal-flow:right-sidebar-chat-mode";

function chatRoleLabel(role, language = "en") {
  if (role === "user") {
    return language === "ko" ? "You" : "You";
  }
  if (role === "system") {
    return language === "ko" ? "System" : "System";
  }
  return "AI";
}

function chatModeLabel(mode, language = "en") {
  if (mode === "review") {
    return language === "ko" ? "Code Review" : "Code Review";
  }
  if (mode === "plan") {
    return language === "ko" ? "Plan" : "Plan";
  }
  if (mode === "debugger") {
    return language === "ko" ? "Debugger" : "Debugger";
  }
  if (mode === "merger") {
    return language === "ko" ? "Merger" : "Merger";
  }
  return language === "ko" ? "Conversation" : "Conversation";
}

function normalizeChatMode(mode, fallbackMode = DEFAULT_CHAT_MODE) {
  const normalizedMode = String(mode || "").trim().toLowerCase();
  if (["review", "conversation", "plan", "debugger", "merger"].includes(normalizedMode)) {
    return normalizedMode;
  }
  return fallbackMode;
}

const ChatMessageBubble = memo(function ChatMessageBubble({
  message,
  fallbackKey,
  language,
}) {
  const role = String(message?.role || "assistant").trim().toLowerCase() || "assistant";
  const mode = String(message?.mode || "").trim().toLowerCase();
  return (
    <div
      className={`sidebar-chat-bubble sidebar-chat-bubble--${role}`}
      data-testid="chat-message-bubble"
    >
      <span className="sidebar-chat-bubble__role">
        {chatRoleLabel(role, language)}
      </span>
      <ChatMessageContent role={role} text={message?.text} />
    </div>
  );
}, (previousProps, nextProps) => (
  previousProps.fallbackKey === nextProps.fallbackKey
  && previousProps.language === nextProps.language
  && previousProps.message?.message_id === nextProps.message?.message_id
  && previousProps.message?.role === nextProps.message?.role
  && previousProps.message?.mode === nextProps.message?.mode
  && previousProps.message?.text === nextProps.message?.text
));

const ProjectChatPane = memo(function ProjectChatPane({
  chat,
  detail,
  modelCatalog = [],
  modelPresets = [],
  chatSettings = {},
  selectedChatSessionId,
  chatDraftSession,
  onSelectChatSession,
  onStartNewChatSession,
  onSendChatMessage,
  onChangeChatModelSelection,
  onChangeChatReasoningEffort,
  chatJob,
  busy,
  language,
  centerMode = false,
  onGeneratePlan,
  onRequestStop,
}) {
  const sessions = Array.isArray(chat?.sessions) ? chat.sessions : [];
  const remoteMessages = Array.isArray(chat?.messages) ? chat.messages : [];
  const deferredSessions = useDeferredValue(sessions);
  const deferredRemoteMessages = useDeferredValue(remoteMessages);
  const activeSessionId = String(selectedChatSessionId || chat?.active_session_id || "").trim();
  const summaryFile = String(chat?.summary_file || "").trim();
  const selectedChatProvider = String(chatSettings?.chat_model_provider || "").trim().toLowerCase();
  const selectedChatLocalProvider = String(chatSettings?.chat_local_model_provider || "").trim().toLowerCase();
  const selectedChatModel = String(chatSettings?.chat_model || "").trim().toLowerCase();
  const selectedChatEffort = String(chatSettings?.chat_effort || "").trim().toLowerCase();
  const chatJobStatus = String(chatJob?.status || "").trim().toLowerCase();
  void onGeneratePlan;
  const [input, setInput] = useState("");
  const [storedPendingMode, setStoredPendingMode] = usePersistentState(RIGHT_SIDEBAR_CHAT_MODE_KEY, DEFAULT_CHAT_MODE);
  const pendingMode = normalizeChatMode(storedPendingMode);
  const [menuOpen, setMenuOpen] = useState(false);
  const [localMessages, setLocalMessages] = useState(deferredRemoteMessages);
  const [visibleMessageCount, setVisibleMessageCount] = useState(MAX_VISIBLE_CHAT_MESSAGES);
  const messagesRef = useRef(null);
  const menuRef = useRef(null);
  const scrollFrameRef = useRef(0);
  const pendingScrollTopRef = useRef(0);
  const shouldStickToBottomRef = useRef(true);
  const [messageScrollTop, setMessageScrollTop] = useState(0);
  const [messageViewportHeight, setMessageViewportHeight] = useState(CHAT_DEFAULT_VIEWPORT_HEIGHT);
  const [chatElapsedSeconds, setChatElapsedSeconds] = useState(() => {
    if (chatJobStatus !== "running") {
      return 0;
    }
    const parsedStartedAt = Date.parse(String(chatJob?.started_at || "").trim());
    const startedAtMs = Number.isFinite(parsedStartedAt) ? parsedStartedAt : Date.now();
    return Math.max(0, Math.floor((Date.now() - startedAtMs) / 1000));
  });
  const availableChatModels = useMemo(
    () => (modelCatalog || []).filter((item) => {
      const model = String(item?.model || "").trim();
      return Boolean(model) && !item?.hidden;
    }),
    [modelCatalog],
  );
  const selectedChatKey = useMemo(
    () => (selectedChatModel ? [selectedChatProvider, selectedChatLocalProvider, selectedChatModel].join("::") : ""),
    [selectedChatLocalProvider, selectedChatModel, selectedChatProvider],
  );
  const selectedChatValue = useMemo(
    () => selectedChatKey,
    [selectedChatKey],
  );
  const selectedChatEntry = useMemo(
    () => (
      (modelCatalog || []).find((item) => chatModelOptionValue(item) === selectedChatValue)
      || null
    ),
    [modelCatalog, selectedChatValue],
  );
  const availableChatEfforts = useMemo(
    () => MODEL_REASONING_OPTIONS,
    [],
  );
  const effectiveChatEffort = useMemo(
    () => selectedChatEffort,
    [selectedChatEffort],
  );
  const projectDefaultLabel = language === "ko" ? "프로젝트 실행 모델" : "Project execution model";
  const chatTargetSummary = useMemo(
    () => (
      selectedChatEntry
        ? `${selectedChatEntry.display_name || selectedChatEntry.model} / ${chatProviderLabel(selectedChatEntry.provider, selectedChatEntry.local_provider, language)}`
        : projectDefaultLabel
    ),
    [language, projectDefaultLabel, selectedChatEntry],
  );
  const projectDefaultOptionLabel = useMemo(
    () => projectDefaultLabel,
    [projectDefaultLabel],
  );
  const visibleMessages = useMemo(() => {
    if (localMessages.length <= visibleMessageCount) {
      return localMessages;
    }
    return localMessages.slice(localMessages.length - visibleMessageCount);
  }, [localMessages, visibleMessageCount]);
  const hiddenMessageCount = Math.max(0, localMessages.length - visibleMessages.length);
  const virtualizationEnabled = visibleMessages.length > 36;
  const initialVirtualScrollTop = Math.max(
    0,
    (visibleMessages.length * CHAT_ESTIMATED_ROW_HEIGHT) - CHAT_DEFAULT_VIEWPORT_HEIGHT,
  );
  const effectiveMessageScrollTop = typeof window === "undefined" ? initialVirtualScrollTop : messageScrollTop;
  const { virtualTopSpacer, virtualBottomSpacer, renderedMessages } = useMemo(() => {
    if (!virtualizationEnabled) {
      return {
        virtualTopSpacer: 0,
        virtualBottomSpacer: 0,
        renderedMessages: visibleMessages,
      };
    }
    const safeViewportHeight = Math.max(CHAT_ESTIMATED_ROW_HEIGHT * 4, messageViewportHeight || CHAT_DEFAULT_VIEWPORT_HEIGHT);
    const startIndex = Math.max(0, Math.floor(effectiveMessageScrollTop / CHAT_ESTIMATED_ROW_HEIGHT) - CHAT_OVERSCAN_ROWS);
    const visibleRowCount = Math.ceil(safeViewportHeight / CHAT_ESTIMATED_ROW_HEIGHT) + (CHAT_OVERSCAN_ROWS * 2);
    const endIndex = Math.min(visibleMessages.length, startIndex + visibleRowCount);
    return {
      virtualTopSpacer: startIndex * CHAT_ESTIMATED_ROW_HEIGHT,
      virtualBottomSpacer: Math.max(0, (visibleMessages.length - endIndex) * CHAT_ESTIMATED_ROW_HEIGHT),
      renderedMessages: visibleMessages.slice(startIndex, endIndex),
    };
  }, [effectiveMessageScrollTop, messageViewportHeight, virtualizationEnabled, visibleMessages]);

  useEffect(() => {
    setLocalMessages(deferredRemoteMessages);
  }, [deferredRemoteMessages, activeSessionId, chatDraftSession]);

  useEffect(() => {
    if (chatJobStatus !== "running") {
      setChatElapsedSeconds(0);
      return undefined;
    }
    const parsedStartedAt = Date.parse(String(chatJob?.started_at || "").trim());
    const startedAtMs = Number.isFinite(parsedStartedAt) ? parsedStartedAt : Date.now();
    const syncElapsed = () => {
      setChatElapsedSeconds(Math.max(0, Math.floor((Date.now() - startedAtMs) / 1000)));
    };
    syncElapsed();
    const intervalId = window.setInterval(syncElapsed, 1000);
    return () => window.clearInterval(intervalId);
  }, [chatJob?.started_at, chatJobStatus]);

  useEffect(() => {
    setVisibleMessageCount(MAX_VISIBLE_CHAT_MESSAGES);
  }, [activeSessionId, chatDraftSession]);

  useEffect(() => {
    if (!virtualizationEnabled || !messagesRef.current || typeof ResizeObserver === "undefined") {
      return undefined;
    }
    const node = messagesRef.current;
    const observer = new ResizeObserver((entries) => {
      const nextHeight = Math.max(CHAT_ESTIMATED_ROW_HEIGHT * 4, Math.round(entries[0]?.contentRect?.height || CHAT_DEFAULT_VIEWPORT_HEIGHT));
      setMessageViewportHeight(nextHeight);
    });
    observer.observe(node);
    setMessageViewportHeight(Math.max(CHAT_ESTIMATED_ROW_HEIGHT * 4, Math.round(node.clientHeight || CHAT_DEFAULT_VIEWPORT_HEIGHT)));
    return () => observer.disconnect();
  }, [virtualizationEnabled]);

  useEffect(() => {
    const node = messagesRef.current;
    if (!node) {
      return undefined;
    }
    const scrollToBottom = () => {
      node.scrollTop = node.scrollHeight;
      pendingScrollTopRef.current = node.scrollTop;
      setMessageScrollTop(node.scrollTop);
    };
    if (typeof window === "undefined") {
      return undefined;
    }
    const handle = window.requestAnimationFrame(scrollToBottom);
    return () => window.cancelAnimationFrame(handle);
  }, [activeSessionId, chatDraftSession, virtualizationEnabled]);

  useEffect(() => {
    const node = messagesRef.current;
    if (!node || typeof window === "undefined") {
      return undefined;
    }
    if (!shouldStickToBottomRef.current) {
      return undefined;
    }
    const handle = window.requestAnimationFrame(() => {
      node.scrollTop = node.scrollHeight;
      pendingScrollTopRef.current = node.scrollTop;
      setMessageScrollTop(node.scrollTop);
    });
    return () => window.cancelAnimationFrame(handle);
  }, [localMessages, virtualizationEnabled]);

  useEffect(() => () => {
    if (scrollFrameRef.current && typeof window !== "undefined") {
      window.cancelAnimationFrame(scrollFrameRef.current);
    }
  }, []);

  useEffect(() => {
    if (!menuOpen) {
      return undefined;
    }

    function handlePointerDown(event) {
      if (!menuRef.current?.contains(event.target)) {
        setMenuOpen(false);
      }
    }

    window.addEventListener("mousedown", handlePointerDown);
    return () => {
      window.removeEventListener("mousedown", handlePointerDown);
    };
  }, [menuOpen]);

  function sessionLabel(session) {
    return formatChatSessionTitle(
      session?.title,
      language === "ko" ? "Conversation" : "Conversation",
    );
  }

  function handleMessagesScroll(event) {
    const node = event.currentTarget;
    const distanceToBottom = node.scrollHeight - node.clientHeight - node.scrollTop;
    shouldStickToBottomRef.current = distanceToBottom < CHAT_ESTIMATED_ROW_HEIGHT * 2;
    pendingScrollTopRef.current = node.scrollTop;
    if (!virtualizationEnabled) {
      setMessageScrollTop(node.scrollTop);
      return;
    }
    if (scrollFrameRef.current) {
      return;
    }
    scrollFrameRef.current = window.requestAnimationFrame(() => {
      scrollFrameRef.current = 0;
      setMessageScrollTop(pendingScrollTopRef.current);
    });
  }

  function handleSend() {
    const text = input.trim();
    if (!text || chatJobActive || executionBlocksPendingMode) {
      return;
    }
    const mode = pendingMode;
    if (mode === "plan") {
      setInput("");
      setStoredPendingMode(DEFAULT_CHAT_MODE);
      setMenuOpen(false);
      void Promise.resolve(onSendChatMessage?.(text, mode)).catch(() => {});
      return;
    }
    setInput("");
    setStoredPendingMode(DEFAULT_CHAT_MODE);
    setMenuOpen(false);
    setLocalMessages((prev) => [
      ...prev,
      {
        role: "user",
        text,
        mode,
        status: "pending",
        message_id: `local-${Date.now()}`,
      },
    ]);
    void Promise.resolve(onSendChatMessage?.(text, mode)).catch(() => {});
  }

  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSend();
    }
  }

  function handleSessionChange(event) {
    const nextSessionId = String(event.target.value || "").trim();
    if (!nextSessionId) {
      onStartNewChatSession?.();
      return;
    }
    void Promise.resolve(onSelectChatSession?.(nextSessionId)).catch(() => {});
  }

  function handleChatModelChange(event) {
    const nextValue = String(event.target.value || "").trim();
    if (!nextValue) {
      onChangeChatModelSelection?.(null);
      return;
    }
    onChangeChatModelSelection?.(parseChatModelOptionValue(nextValue));
  }

  function handleChatEffortChange(event) {
    onChangeChatReasoningEffort?.(event.target.value);
  }

  const selectedSessionValue = chatDraftSession ? "" : activeSessionId;
  const chatJobActive = ["queued", "running"].includes(chatJobStatus);
  const showRespondingState = chatJobStatus === "running";
  const executionBlocksPendingMode = busy && !["conversation", "review"].includes(pendingMode);
  const chatControlsDisabled = chatJobActive;
  const respondingLabel = language === "ko" ? "응답 중" : "Responding";
  const stopLabel = language === "ko" ? "중단" : "Stop";
  const composerPlaceholder =
    pendingMode === "plan"
      ? (language === "ko" ? "계획 프롬프트 입력... (Enter로 생성)" : "Plan prompt... (Enter to generate)")
      : pendingMode === "review"
        ? (language === "ko" ? "코드나 변경 내용을 입력하세요 (Enter로 전송)" : "Paste code or change... (Enter to send)")
      : (language === "ko" ? "메시지 입력 (Enter로 전송)" : "Message... (Enter to send)");
  const sendButtonTitle =
    pendingMode === "plan"
      ? (language === "ko" ? "계획 생성" : "Generate Plan")
      : pendingMode === "review"
        ? (language === "ko" ? "코드 리뷰 보내기" : "Send code review")
        : (language === "ko" ? "Send" : "Send");
  const chatModelSelect = (
    <select
      className={centerMode ? "chat-center__runtime-select" : "sidebar-chat-config__select"}
      value={selectedChatValue}
      onChange={handleChatModelChange}
    >
      <option value="">{projectDefaultOptionLabel}</option>
      {selectedChatEntry && !availableChatModels.some((item) => chatModelOptionValue(item) === selectedChatValue) ? (
        <option value={selectedChatValue}>
          {selectedChatEntry.display_name || selectedChatEntry.model} / {chatProviderLabel(selectedChatEntry.provider, selectedChatEntry.local_provider, language)}
        </option>
      ) : null}
      {availableChatModels.map((item) => (
        <option key={chatModelOptionValue(item)} value={chatModelOptionValue(item)}>
          {(item.display_name || item.model) + " / " + chatProviderLabel(item.provider, item.local_provider, language)}
        </option>
      ))}
    </select>
  );
  const chatEffortSelect = (
    <select
      className={centerMode ? "chat-center__runtime-select" : "sidebar-chat-config__select"}
      value={effectiveChatEffort}
      onChange={handleChatEffortChange}
    >
      <option value="">{language === "ko" ? "Project default" : "Project default"}</option>
      {availableChatEfforts.map((effort) => (
        <option key={effort} value={effort}>
          {reasoningEffortLabel(effort, language)}
        </option>
      ))}
    </select>
  );

  return (
    <div className={centerMode ? "rsb-chat rsb-chat--center" : "rsb-chat"}>
      {!centerMode ? (
        <div className="sidebar-panel__header" style={{ padding: "10px 10px 0" }}>
          <strong>{language === "ko" ? "AI Chat" : "AI Chat"}</strong>
          <span style={{ fontSize: "11px", color: "var(--text-dim)" }}>
            {language === "ko" ? "Code review or manual recovery" : "Code review or manual recovery"}
          </span>
        </div>
      ) : (
        <div className="chat-center__header">
          <div className="chat-center__title-row">
            <RailChatIcon />
            <strong>{language === "ko" ? "AI Chat" : "AI Chat"}</strong>
          </div>
          <div className="chat-center__toolbar">
            <select
              className="sidebar-chat-session-select chat-center__session-select"
              value={selectedSessionValue}
              onChange={handleSessionChange}
              disabled={chatControlsDisabled}
            >
              <option value="">{language === "ko" ? "New conversation" : "New conversation"}</option>
              {deferredSessions.map((session) => (
                <option key={session.session_id} value={session.session_id}>
                  {sessionLabel(session)}
                </option>
              ))}
            </select>
            <button
              className="sidebar-chat-new"
              onClick={() => { setStoredPendingMode(DEFAULT_CHAT_MODE); setMenuOpen(false); onStartNewChatSession?.(); }}
              type="button"
              disabled={chatControlsDisabled}
            >
              {language === "ko" ? "New" : "New"}
            </button>
          </div>
        </div>
      )}

      {!centerMode ? (
        <>
          <div className="sidebar-chat-config" style={{ margin: "8px 10px 0" }}>
            <div className="sidebar-chat-config__header">
              <strong>{language === "ko" ? "실행 모델" : "Execution model"}</strong>
              <span>{chatTargetSummary}</span>
            </div>
            {chatModelSelect}
          </div>

          <div className="sidebar-chat-config" style={{ margin: "8px 10px 0" }}>
            <div className="sidebar-chat-config__header">
              <strong>{language === "ko" ? "Chat reasoning" : "Chat reasoning"}</strong>
              <span>
                {effectiveChatEffort
                  ? reasoningEffortLabel(effectiveChatEffort, language)
                  : (language === "ko" ? "Project default" : "Project default")}
              </span>
            </div>
            {chatEffortSelect}
          </div>
        </>
      ) : null}

      {!centerMode ? (
        <div className="sidebar-chat-toolbar" style={{ padding: "0 10px" }}>
          <select
            className="sidebar-chat-session-select"
            value={selectedSessionValue}
            onChange={handleSessionChange}
            disabled={chatControlsDisabled}
          >
            <option value="">{language === "ko" ? "New conversation" : "New conversation"}</option>
            {deferredSessions.map((session) => (
              <option key={session.session_id} value={session.session_id}>
                {sessionLabel(session)}
              </option>
            ))}
          </select>
          <button
            className="sidebar-chat-new"
            onClick={() => {
              setStoredPendingMode(DEFAULT_CHAT_MODE);
              setMenuOpen(false);
              onStartNewChatSession?.();
            }}
            type="button"
            disabled={chatControlsDisabled}
          >
            {language === "ko" ? "New" : "New"}
          </button>
        </div>
      ) : null}

      <div className="sidebar-chat-summary-path" style={{ margin: "0 10px" }}>
        <strong>{language === "ko" ? "Summary txt" : "Summary txt"}</strong>
        <span title={summaryFile || ""}>
          {summaryFile || (language === "ko" ? "Created after the first message." : "Created after the first message.")}
        </span>
      </div>

      <div className="sidebar-chat-messages rsb-chat__messages" ref={messagesRef} onScroll={handleMessagesScroll}>
        {localMessages.length === 0 ? (
          <div className="sidebar-chat-empty">
            <RailChatIcon />
            <span>
              {language === "ko"
                ? "Send a message to continue the session from the saved txt history."
                : "Send a message to continue the session from the saved txt history."}
            </span>
          </div>
        ) : (
          <>
            {hiddenMessageCount > 0 ? (
              <button
                className="sidebar-chat-history-button"
                onClick={() => setVisibleMessageCount((current) => current + CHAT_MESSAGE_BATCH)}
                type="button"
              >
                {language === "ko"
                  ? `이전 메시지 ${Math.min(hiddenMessageCount, CHAT_MESSAGE_BATCH)}개 보기`
                  : `Show ${Math.min(hiddenMessageCount, CHAT_MESSAGE_BATCH)} earlier messages`}
              </button>
            ) : null}
            {virtualTopSpacer > 0 ? <div aria-hidden="true" style={{ height: `${virtualTopSpacer}px` }} /> : null}
            {renderedMessages.map((msg, index) => (
              <ChatMessageBubble
                key={msg.message_id || msg.id || `${msg.role || "assistant"}-${hiddenMessageCount + index}-${msg.text || ""}`}
                message={msg}
                fallbackKey={`${msg.role || "assistant"}-${hiddenMessageCount + index}-${msg.message_id || msg.id || ""}`}
                language={language}
              />
            ))}
            {virtualBottomSpacer > 0 ? <div aria-hidden="true" style={{ height: `${virtualBottomSpacer}px` }} /> : null}
          </>
        )}
      </div>

      <div className="sidebar-chat-composer">
        <div className="sidebar-chat-modebar" ref={menuRef}>
          <div className="sidebar-chat-mode-picker">
            <button
              className="sidebar-chat-plus"
              onClick={() => setMenuOpen((current) => !current)}
              type="button"
              disabled={chatControlsDisabled}
              title={language === "ko" ? "채팅 모드 선택" : "Choose chat mode"}
            >
              <PlusIcon />
            </button>
            {menuOpen ? (
              <div className="sidebar-chat-mode-menu">
                <button
                  type="button"
                  onClick={() => {
                    setStoredPendingMode("review");
                    setMenuOpen(false);
                  }}
                >
                  {chatModeLabel("review", language)}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setStoredPendingMode("conversation");
                    setMenuOpen(false);
                  }}
                >
                  {chatModeLabel("conversation", language)}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setStoredPendingMode("plan");
                    setMenuOpen(false);
                  }}
                >
                  {chatModeLabel("plan", language)}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setStoredPendingMode("debugger");
                    setMenuOpen(false);
                  }}
                >
                  {chatModeLabel("debugger", language)}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setStoredPendingMode("merger");
                    setMenuOpen(false);
                  }}
                >
                  {chatModeLabel("merger", language)}
                </button>
              </div>
            ) : null}
          </div>

          {pendingMode === DEFAULT_CHAT_MODE ? (
            <span className="sidebar-chat-mode-chip">
              {language === "ko" ? "Default: code review" : "Default: code review"}
            </span>
          ) : (
            <button
              className="sidebar-chat-mode-chip sidebar-chat-mode-chip--active"
              onClick={() => setStoredPendingMode(DEFAULT_CHAT_MODE)}
              type="button"
            >
              {language === "ko" ? "Next send:" : "Next send:"} {chatModeLabel(pendingMode, language)}
            </button>
          )}
        </div>

        {centerMode ? (
        <div className="chat-center__runtime-row">
          <div className="chat-center__runtime-field">
              <span className="chat-center__runtime-label">{language === "ko" ? "실행 모델" : "Execution model"}</span>
              {chatModelSelect}
            </div>
            <div className="chat-center__runtime-field">
              <span className="chat-center__runtime-label">{language === "ko" ? "Reasoning" : "Reasoning"}</span>
              {chatEffortSelect}
            </div>
          </div>
        ) : null}

        {showRespondingState ? (
          <div className="sidebar-chat-status" role="status" aria-live="polite">
            <span className="sidebar-chat-status__dot" aria-hidden="true" />
            <span>{respondingLabel}</span>
            <strong>{formatDurationCompact(chatElapsedSeconds, language)}</strong>
            <button className="toolbar-button toolbar-button--ghost" onClick={() => onRequestStop?.()} type="button">
              {stopLabel}
            </button>
          </div>
        ) : null}

        <div className={centerMode ? "chat-center__input-row" : "sidebar-chat-input-row"}>
          <textarea
            className={centerMode ? "chat-center__textarea" : "sidebar-chat-input"}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={composerPlaceholder}
            disabled={chatControlsDisabled}
            rows={centerMode ? 3 : 2}
          />
          <button
            className={centerMode ? "chat-center__send-btn" : "sidebar-chat-send"}
            onClick={handleSend}
            type="button"
            disabled={chatJobActive || executionBlocksPendingMode || !input.trim()}
            title={sendButtonTitle}
          >
            <SendIcon />
          </button>
        </div>
      </div>
    </div>
  );
}, (previousProps, nextProps) => (
  previousProps.selectedChatSessionId === nextProps.selectedChatSessionId
  && previousProps.chatDraftSession === nextProps.chatDraftSession
  && previousProps.busy === nextProps.busy
  && previousProps.detail?.runtime === nextProps.detail?.runtime
  && previousProps.chatSettings?.model_provider === nextProps.chatSettings?.model_provider
  && previousProps.chatSettings?.local_model_provider === nextProps.chatSettings?.local_model_provider
  && previousProps.chatSettings?.model === nextProps.chatSettings?.model
  && previousProps.chatSettings?.chat_model_provider === nextProps.chatSettings?.chat_model_provider
  && previousProps.chatSettings?.chat_local_model_provider === nextProps.chatSettings?.chat_local_model_provider
  && previousProps.chatSettings?.chat_model === nextProps.chatSettings?.chat_model
  && previousProps.chatSettings?.chat_effort === nextProps.chatSettings?.chat_effort
  && previousProps.chatJob?.id === nextProps.chatJob?.id
  && previousProps.chatJob?.status === nextProps.chatJob?.status
  && previousProps.chatJob?.started_at === nextProps.chatJob?.started_at
  && previousProps.modelCatalog === nextProps.modelCatalog
  && previousProps.modelPresets === nextProps.modelPresets
  && previousProps.chat?.active_session_id === nextProps.chat?.active_session_id
  && previousProps.chat?.summary_file === nextProps.chat?.summary_file
  && sameChatSessions(previousProps.chat?.sessions, nextProps.chat?.sessions)
  && sameChatMessages(previousProps.chat?.messages, nextProps.chat?.messages)
  && previousProps.centerMode === nextProps.centerMode
  && previousProps.onRequestStop === nextProps.onRequestStop
));

export const RightSidebarPane = memo(function RightSidebarPane({
  activeTab = "chat",
  collapsed = false,
  chatCenterMode = false,
  includeChatTab = true,
  onChangeTab,
  detail,
  planDraft,
  selectedStepId,
  modelPresets,
  modelCatalog = [],
  form,
  activeJob,
  chatJob,
  busy,
  autoRunAfterPlan = false,
  canRequestStop = false,
  canCancelReservation = false,
  queuedJobs = [],
  onChangeForm,
  chat,
  chatSettings = {},
  selectedChatSessionId,
  chatDraftSession,
  onSelectChatSession,
  onStartNewChatSession,
  onSendChatMessage,
  onChangeChatModelSelection,
  onChangeChatReasoningEffort,
  onResolveCommonRequirement,
  onReopenCommonRequirement,
  onRecordSpineCheckpoint,
  onUpdateCommonRequirement,
  onDeleteCommonRequirement,
  onUpdateSpineCheckpoint,
  onDeleteSpineCheckpoint,
  onGeneratePlan,
  onPromptChange,
  onSavePlan,
  onResetPlan,
  onRunPlan,
  onRunManualDebugger,
  onRunManualMerger,
  onRequestStop,
  onCancelQueuedJob,
  onChangeAutoRunAfterPlan,
  onSelectStep,
  onUpdateStepField,
  onSaveStepLocal,
  onAddStep,
  onDeleteStep,
}) {
  const { language } = useI18n();
  const processOutput = detail?.subprocess_output || detail?.agent_output || detail?.process_log || "";
  const effectivePlan = useMemo(() => resolveExecutionDisplayPlan(detail, planDraft, activeJob), [detail, planDraft, activeJob]);
  const selectedStep = (effectivePlan?.steps || []).find((step) => step.step_id === selectedStepId) || null;
  const executionJob = visibleExecutionJob(activeJob);
  const liveRuntimeEditable = ["running", "queued"].includes(String(executionJob?.status || "").trim().toLowerCase());
  const hasFiles = Boolean(
    detail?.files?.closeout_report_file
    || detail?.reports?.word_report_path
    || detail?.reports?.powerpoint_report_path
    || detail?.reports?.webpage_path
    || detail?.files?.webpage_file
  );
  const contractAttention =
    Number(detail?.reports?.common_requirements?.open_count || 0) > 0
    || Number(detail?.reports?.lineage_manifest_summary?.yellow_count || 0) > 0
    || Number(detail?.reports?.lineage_manifest_summary?.red_count || 0) > 0;

  const hasOutput = Boolean(processOutput);

  const railTabs = [
    {
      id: "chat",
      icon: <RailChatIcon />,
      title: language === "ko" ? "AI Chat" : "AI Chat",
      dot: false,
    },
    {
      id: "flow",
      icon: <RailFlowIcon />,
      title: language === "ko" ? "Flow" : "Flow",
      dot: Array.isArray(effectivePlan?.steps) && effectivePlan.steps.length > 0,
    },
    {
      id: "output",
      icon: <RailTerminalIcon />,
      title: language === "ko" ? "Process Output" : "Process Output",
      dot: hasOutput,
    },
    {
      id: "files",
      icon: <RailFilesIcon />,
      title: language === "ko" ? "Reports & Files" : "Reports & Files",
      dot: hasFiles,
    },
    {
      id: "contracts",
      icon: <RailContractsIcon />,
      title: language === "ko" ? "Contract Wave" : "Contract Wave",
      dot: contractAttention,
    },
    {
      id: "inspector",
      icon: <RailInspectorIcon />,
      title: "Inspector",
      dot: false,
    },
  ].filter((item) => includeChatTab || item.id !== "chat");
  const effectiveActiveTab = effectiveRightSidebarTab(activeTab, includeChatTab);

  if (chatCenterMode) {
    return (
      <div className="chat-center-pane">
        <ProjectChatPane
          chat={chat}
          detail={detail}
          modelCatalog={modelCatalog}
          modelPresets={modelPresets}
          chatSettings={chatSettings}
          selectedChatSessionId={selectedChatSessionId}
          chatDraftSession={chatDraftSession}
          onSelectChatSession={onSelectChatSession}
          onStartNewChatSession={onStartNewChatSession}
          onSendChatMessage={onSendChatMessage}
          onChangeChatModelSelection={onChangeChatModelSelection}
          onChangeChatReasoningEffort={onChangeChatReasoningEffort}
          chatJob={chatJob}
          busy={busy}
          language={language}
          centerMode
          onGeneratePlan={onGeneratePlan}
          onRequestStop={onRequestStop}
        />
      </div>
    );
  }

  return (
    <aside className={`details-pane rsb ${collapsed ? "rsb--collapsed" : ""}`.trim()}>
      {collapsed ? null : (
        <div className="rsb-panel">
        {effectiveActiveTab === "chat" ? (
          <ProjectChatPane
            chat={chat}
            detail={detail}
            modelCatalog={modelCatalog}
            modelPresets={modelPresets}
            chatSettings={chatSettings}
            selectedChatSessionId={selectedChatSessionId}
            chatDraftSession={chatDraftSession}
            onSelectChatSession={onSelectChatSession}
            onStartNewChatSession={onStartNewChatSession}
            onSendChatMessage={onSendChatMessage}
            onChangeChatModelSelection={onChangeChatModelSelection}
            onChangeChatReasoningEffort={onChangeChatReasoningEffort}
            chatJob={chatJob}
            busy={busy}
            language={language}
            onRequestStop={onRequestStop}
          />
        ) : null}

        {effectiveActiveTab === "flow" ? (
          <Suspense fallback={<div className="rsb-panel__loading" aria-hidden="true" />}>
            <LazyFlowWorkspaceView
              detail={detail}
              form={form}
              modelCatalog={modelCatalog}
              planDraft={planDraft}
              activeJob={activeJob}
              autoRunAfterPlan={autoRunAfterPlan}
              selectedStepId={selectedStepId}
              busy={busy}
              canRequestStop={canRequestStop}
              canCancelReservation={canCancelReservation}
              queuedJobs={queuedJobs}
              onPromptChange={onPromptChange}
              onChangeForm={onChangeForm}
              onGeneratePlan={onGeneratePlan}
              onSavePlan={onSavePlan}
              onResetPlan={onResetPlan}
              onRunPlan={onRunPlan}
              onRunManualDebugger={onRunManualDebugger}
              onRunManualMerger={onRunManualMerger}
              onRequestStop={onRequestStop}
              onCancelQueuedJob={onCancelQueuedJob}
              onChangeAutoRunAfterPlan={onChangeAutoRunAfterPlan}
              onSelectStep={onSelectStep}
              onUpdateStepField={onUpdateStepField}
              onSaveStepLocal={onSaveStepLocal}
              onAddStep={onAddStep}
              onDeleteStep={onDeleteStep}
            />
          </Suspense>
        ) : null}

        {effectiveActiveTab === "output" ? (
          <Suspense fallback={<div className="rsb-panel__loading" aria-hidden="true" />}>
            <LazyOutputPanel processOutput={processOutput} language={language} />
          </Suspense>
        ) : null}

        {effectiveActiveTab === "files" ? (
          <Suspense fallback={<div className="rsb-panel__loading" aria-hidden="true" />}>
            <LazyFilesPanel
              detail={detail}
              form={form}
              busy={busy}
              onChangeForm={onChangeForm}
              liveRuntimeEditable={liveRuntimeEditable}
              language={language}
            />
          </Suspense>
        ) : null}

        {effectiveActiveTab === "contracts" ? (
          <Suspense fallback={<div className="rsb-panel__loading" aria-hidden="true" />}>
            <LazyContractsPanel
              detail={detail}
              selectedStep={selectedStep}
              busy={busy}
              onResolveCommonRequirement={onResolveCommonRequirement}
              onReopenCommonRequirement={onReopenCommonRequirement}
              onRecordSpineCheckpoint={onRecordSpineCheckpoint}
              onUpdateCommonRequirement={onUpdateCommonRequirement}
              onDeleteCommonRequirement={onDeleteCommonRequirement}
              onUpdateSpineCheckpoint={onUpdateSpineCheckpoint}
              onDeleteSpineCheckpoint={onDeleteSpineCheckpoint}
              language={language}
            />
          </Suspense>
        ) : null}

        {effectiveActiveTab === "inspector" ? (
          <Suspense fallback={<div className="rsb-panel__loading" aria-hidden="true" />}>
            <LazyInspectorPanel
              detail={detail}
              selectedStep={selectedStep}
              modelPresets={modelPresets}
              activeJob={activeJob}
              language={language}
            />
          </Suspense>
        ) : null}
        </div>
      )}

      <div className="rsb-rail">
        {railTabs.map(({ id, icon, title, dot }) => (
          <button
            key={id}
            className={`sidebar-icon${!collapsed && effectiveActiveTab === id ? " active" : ""}`}
            onClick={() => onChangeTab?.(id)}
            title={title}
            type="button"
            aria-pressed={!collapsed && effectiveActiveTab === id}
          >
            {icon}
            {dot ? <span className="rsb-rail__dot" /> : null}
          </button>
        ))}
      </div>
    </aside>
  );
}, rightSidebarPanePropsEqual);


