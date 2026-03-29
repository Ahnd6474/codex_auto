import { useEffect, useRef, useState } from "react";
import { openInSystem } from "../../api";
import { ChatMessageContent } from "../../chatMarkdown";
import { useI18n } from "../../i18n";
import { displayStatus } from "../../locale";
import { effectiveStepStatus, reasoningEffortLabel, runtimeSummary, statusTone, visibleExecutionJob } from "../../utils";

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

function OpenFolderIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" width="12" height="12">
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
      <polyline points="15 3 21 3 21 9" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
      <line x1="10" y1="14" x2="21" y2="3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

function WordDocIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" width="20" height="20">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <polyline points="14 2 14 8 20 8" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M8 13l2 6 2-4 2 4 2-6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function PptDocIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" width="20" height="20">
      <rect x="2" y="4" width="20" height="14" rx="2" stroke="currentColor" strokeWidth="1.6" />
      <path d="M8 18v2M16 18v2M6 20h12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M9 8h3a2 2 0 0 1 0 4H9V8z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
    </svg>
  );
}

function WebDocIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" width="20" height="20">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.6" />
      <path d="M2 12h20M12 3c-2.5 3-4 5.5-4 9s1.5 6 4 9M12 3c2.5 3 4 5.5 4 9s-1.5 6-4 9" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

function MarkdownDocIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" width="20" height="20">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <polyline points="14 2 14 8 20 8" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M8 13h8M8 17h6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

function OutputCard({ icon, title, description, enabled, checked, onChange, busy, allowWhileRunning = false, comingSoon, language }) {
  return (
    <div className={`output-card ${!enabled ? "output-card--disabled" : ""}`}>
      <div className="output-card__icon">{icon}</div>
      <div className="output-card__body">
        <div className="output-card__title">
          <strong>{title}</strong>
          {comingSoon ? (
            <span className="output-card__badge">{language === "ko" ? "Coming soon" : "Coming soon"}</span>
          ) : null}
        </div>
        <p className="output-card__desc">{description}</p>
      </div>
      <label className={`output-card__toggle ${!enabled ? "output-card__toggle--disabled" : ""}`}>
        <span className={`toggle-track ${checked ? "toggle-track--on" : ""}`}>
          <input
            type="checkbox"
            checked={checked}
            onChange={onChange}
            disabled={!enabled || (busy && !allowWhileRunning)}
          />
          <span className="toggle-thumb" />
        </span>
      </label>
    </div>
  );
}

function ReportFileCard({ title, kind, icon, path, available, onOpen, language }) {
  return (
    <div className={`rsb-file-card${available ? " rsb-file-card--ready" : ""}`}>
      <div className="rsb-file-card__icon">{icon}</div>
      <div className="rsb-file-card__info">
        <strong>{title}</strong>
        <span className="rsb-file-card__kind">{kind}</span>
        {path ? (
          <span className="rsb-file-card__path" title={path}>{path}</span>
        ) : (
          <span className="rsb-file-card__path rsb-file-card__path--empty">
            {language === "ko" ? "Not generated yet" : "Not generated yet"}
          </span>
        )}
      </div>
      <div className="rsb-file-card__actions">
        <span className={`status-badge status-badge--${available ? "success" : "neutral"}`}>
          {available ? (language === "ko" ? "Ready" : "Ready") : (language === "ko" ? "Pending" : "Pending")}
        </span>
        {available && path ? (
          <button
            className="rsb-file-card__open-btn"
            onClick={() => onOpen(path)}
            type="button"
            title={language === "ko" ? "Open file" : "Open file"}
          >
            <OpenFolderIcon />
            <span>{language === "ko" ? "Open" : "Open"}</span>
          </button>
        ) : null}
      </div>
    </div>
  );
}

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

function ProjectChatPane({
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
  busy,
  language,
}) {
  const sessions = Array.isArray(chat?.sessions) ? chat.sessions : [];
  const remoteMessages = Array.isArray(chat?.messages) ? chat.messages : [];
  const activeSessionId = String(selectedChatSessionId || chat?.active_session_id || "").trim();
  const summaryFile = String(chat?.summary_file || "").trim();
  const selectedChatProvider = String(chatSettings?.chat_model_provider || "").trim().toLowerCase();
  const selectedChatLocalProvider = String(chatSettings?.chat_local_model_provider || "").trim().toLowerCase();
  const selectedChatModel = String(chatSettings?.chat_model || "").trim().toLowerCase();
  const projectRuntime = detail?.runtime || {};
  const [input, setInput] = useState("");
  const [pendingMode, setPendingMode] = useState("conversation");
  const [menuOpen, setMenuOpen] = useState(false);
  const [localMessages, setLocalMessages] = useState(remoteMessages);
  const bottomRef = useRef(null);
  const menuRef = useRef(null);
  const availableChatModels = (Array.isArray(modelCatalog) ? modelCatalog : []).filter((item) => {
    const model = String(item?.model || "").trim();
    return Boolean(model) && !item?.hidden;
  });
  const selectedChatValue = selectedChatModel ? [selectedChatProvider || "openai", selectedChatLocalProvider, selectedChatModel].join("::") : "";
  const selectedChatEntry =
    availableChatModels.find((item) => chatModelOptionValue(item) === selectedChatValue)
    || (selectedChatModel
      ? {
          model: selectedChatModel,
          display_name: selectedChatModel,
          provider: selectedChatProvider || "openai",
          local_provider: selectedChatLocalProvider,
        }
      : null);
  const projectDefaultSummary = runtimeSummary(projectRuntime, modelPresets, language, modelCatalog);
  const chatTargetSummary = selectedChatEntry
    ? `${selectedChatEntry.display_name || selectedChatEntry.model} · ${chatProviderLabel(selectedChatEntry.provider, selectedChatEntry.local_provider, language)}`
    : `${language === "ko" ? "Project default" : "Project default"} · ${projectDefaultSummary}`;

  useEffect(() => {
    setLocalMessages(remoteMessages);
  }, [remoteMessages, activeSessionId, chatDraftSession]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [localMessages]);

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

  function roleLabel(role) {
    if (role === "user") {
      return language === "ko" ? "You" : "You";
    }
    if (role === "system") {
      return language === "ko" ? "System" : "System";
    }
    return "AI";
  }

  function modeLabel(mode) {
    if (mode === "debugger") {
      return language === "ko" ? "Debugger" : "Debugger";
    }
    if (mode === "merger") {
      return language === "ko" ? "Merger" : "Merger";
    }
    return language === "ko" ? "Conversation" : "Conversation";
  }

  function sessionLabel(session) {
    const title = String(session?.title || "").trim() || (language === "ko" ? "Conversation" : "Conversation");
    const count = Number.parseInt(String(session?.message_count || 0), 10) || 0;
    return `${title} · ${count}`;
  }

  function handleSend() {
    const text = input.trim();
    if (!text || busy) {
      return;
    }
    const mode = pendingMode;
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
    setInput("");
    setPendingMode("conversation");
    setMenuOpen(false);
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

  const selectedSessionValue = chatDraftSession ? "" : activeSessionId;

  return (
    <div className="rsb-chat">
      <div className="sidebar-panel__header" style={{ padding: "10px 10px 0" }}>
        <strong>{language === "ko" ? "AI Chat" : "AI Chat"}</strong>
        <span style={{ fontSize: "11px", color: "var(--text-dim)" }}>
          {language === "ko" ? "Conversation or manual recovery" : "Conversation or manual recovery"}
        </span>
      </div>

      <div className="sidebar-chat-config" style={{ margin: "8px 10px 0" }}>
        <div className="sidebar-chat-config__header">
          <strong>{language === "ko" ? "Chat model" : "Chat model"}</strong>
          <span>{chatTargetSummary}</span>
        </div>
        <select
          className="sidebar-chat-config__select"
          value={selectedChatValue}
          onChange={handleChatModelChange}
        >
          <option value="">{language === "ko" ? "Project default" : "Project default"}</option>
          {selectedChatEntry && !availableChatModels.some((item) => chatModelOptionValue(item) === selectedChatValue) ? (
            <option value={selectedChatValue}>
              {selectedChatEntry.display_name || selectedChatEntry.model} · {chatProviderLabel(selectedChatEntry.provider, selectedChatEntry.local_provider, language)}
            </option>
          ) : null}
          {availableChatModels.map((item) => (
            <option key={chatModelOptionValue(item)} value={chatModelOptionValue(item)}>
              {(item.display_name || item.model) + " · " + chatProviderLabel(item.provider, item.local_provider, language)}
            </option>
          ))}
        </select>
      </div>

      <div className="sidebar-chat-toolbar" style={{ padding: "0 10px" }}>
        <select
          className="sidebar-chat-session-select"
          value={selectedSessionValue}
          onChange={handleSessionChange}
          disabled={busy}
        >
          <option value="">{language === "ko" ? "New conversation" : "New conversation"}</option>
          {sessions.map((session) => (
            <option key={session.session_id} value={session.session_id}>
              {sessionLabel(session)}
            </option>
          ))}
        </select>
        <button
          className="sidebar-chat-new"
          onClick={() => {
            setPendingMode("conversation");
            setMenuOpen(false);
            onStartNewChatSession?.();
          }}
          type="button"
          disabled={busy}
        >
          {language === "ko" ? "New" : "New"}
        </button>
      </div>

      <div className="sidebar-chat-summary-path" style={{ margin: "0 10px" }}>
        <strong>{language === "ko" ? "Summary txt" : "Summary txt"}</strong>
        <span title={summaryFile || ""}>
          {summaryFile || (language === "ko" ? "Created after the first message." : "Created after the first message.")}
        </span>
      </div>

      <div className="sidebar-chat-messages rsb-chat__messages">
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
          localMessages.map((msg, index) => (
            <div
              key={msg.message_id || msg.id || `${msg.role || "assistant"}-${index}`}
              className={`sidebar-chat-bubble sidebar-chat-bubble--${msg.role || "assistant"}`}
            >
              <span className="sidebar-chat-bubble__role">
                {roleLabel(msg.role)}
                {msg.mode && String(msg.mode).trim().toLowerCase() !== "conversation" ? ` · ${modeLabel(msg.mode)}` : ""}
              </span>
              <ChatMessageContent role={msg.role} text={msg.text} />
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>

      <div className="sidebar-chat-composer">
        <div className="sidebar-chat-modebar" ref={menuRef}>
          <div className="sidebar-chat-mode-picker">
            <button
              className="sidebar-chat-plus"
              onClick={() => setMenuOpen((current) => !current)}
              type="button"
              disabled={busy}
              title={language === "ko" ? "Choose debugger or merger" : "Choose debugger or merger"}
            >
              <PlusIcon />
            </button>
            {menuOpen ? (
              <div className="sidebar-chat-mode-menu">
                <button
                  type="button"
                  onClick={() => {
                    setPendingMode("debugger");
                    setMenuOpen(false);
                  }}
                >
                  {modeLabel("debugger")}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setPendingMode("merger");
                    setMenuOpen(false);
                  }}
                >
                  {modeLabel("merger")}
                </button>
              </div>
            ) : null}
          </div>

          {pendingMode === "conversation" ? (
            <span className="sidebar-chat-mode-chip">
              {language === "ko" ? "Default: conversation" : "Default: conversation"}
            </span>
          ) : (
            <button
              className="sidebar-chat-mode-chip sidebar-chat-mode-chip--active"
              onClick={() => setPendingMode("conversation")}
              type="button"
            >
              {language === "ko" ? "Next send:" : "Next send:"} {modeLabel(pendingMode)}
            </button>
          )}
        </div>

        <div className="sidebar-chat-input-row">
          <textarea
            className="sidebar-chat-input"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={language === "ko" ? "Type a message... (Enter to send)" : "Type a message... (Enter to send)"}
            disabled={busy}
            rows={2}
          />
          <button
            className="sidebar-chat-send"
            onClick={handleSend}
            type="button"
            disabled={busy || !input.trim()}
            title={language === "ko" ? "Send" : "Send"}
          >
            <SendIcon />
          </button>
        </div>
      </div>
    </div>
  );
}

export function RightSidebarPane({
  activeTab = "chat",
  collapsed = false,
  onChangeTab,
  detail,
  planDraft,
  selectedStepId,
  modelPresets,
  modelCatalog = [],
  form,
  activeJob,
  busy,
  onChangeForm,
  chat,
  chatSettings = {},
  selectedChatSessionId,
  chatDraftSession,
  onSelectChatSession,
  onStartNewChatSession,
  onSendChatMessage,
  onChangeChatModelSelection,
}) {
  const { language, t } = useI18n();
  const outputRef = useRef(null);

  const processOutput = detail?.subprocess_output || detail?.agent_output || detail?.process_log || "";
  const selectedStep = (planDraft?.steps || []).find((step) => step.step_id === selectedStepId) || null;
  const pendingCheckpoint = detail?.checkpoints?.pending || null;
  const selectedStepStatus = effectiveStepStatus(selectedStep, detail?.project?.current_status || "");
  const executionJob = visibleExecutionJob(activeJob);
  const liveRuntimeEditable = ["running", "queued"].includes(String(executionJob?.status || "").trim().toLowerCase());

  const closeoutPath = String(detail?.files?.closeout_report_file || "").trim();
  const wordPath = String(detail?.reports?.word_report_path || detail?.files?.word_report_file || "").trim();
  const pptPath = String(
    detail?.reports?.powerpoint_report_path
    || detail?.reports?.powerpoint_report_target_path
    || detail?.files?.powerpoint_report_file
    || "",
  ).trim();
  const webpagePath = String(detail?.reports?.webpage_path || detail?.files?.webpage_file || "").trim();
  const mlReportPath = String(detail?.files?.ml_experiment_report_file || "").trim();
  const spineReport = detail?.reports?.spine || {};
  const commonRequirements = detail?.reports?.common_requirements || {};
  const lineageManifestSummary = detail?.reports?.lineage_manifest_summary || {};
  const lineageManifests = Array.isArray(detail?.reports?.lineage_manifests) ? detail.reports.lineage_manifests : [];
  const openCommonRequirements = Array.isArray(commonRequirements?.open_items) ? commonRequirements.open_items : [];
  const resolvedCommonRequirements = Array.isArray(commonRequirements?.resolved_items) ? commonRequirements.resolved_items : [];
  const spineHistory = Array.isArray(spineReport?.recent_history) ? spineReport.recent_history : [];
  const selectedStepContracts = Array.isArray(selectedStep?.shared_contracts) ? selectedStep.shared_contracts : [];
  const selectedPrimaryScope = Array.isArray(selectedStep?.primary_scope_paths) ? selectedStep.primary_scope_paths : [];
  const selectedSharedReviewed = Array.isArray(selectedStep?.shared_reviewed_paths) ? selectedStep.shared_reviewed_paths : [];
  const selectedForbiddenCore = Array.isArray(selectedStep?.forbidden_core_paths) ? selectedStep.forbidden_core_paths : [];
  const sharedContractsText = String(detail?.reports?.shared_contracts_text || "").trim();
  const spinePath = String(detail?.files?.spine_file || detail?.reports?.spine?.path || "").trim();
  const commonRequirementsPath = String(detail?.files?.common_requirements_file || detail?.reports?.common_requirements?.path || "").trim();
  const sharedContractsPath = String(detail?.files?.shared_contracts_file || detail?.reports?.shared_contracts_path || "").trim();
  const lineageManifestsDir = String(detail?.files?.lineage_manifests_dir || detail?.reports?.lineage_manifests_dir || "").trim();
  const contractAttention =
    Number(commonRequirements?.open_count || 0) > 0
    || Number(lineageManifestSummary?.yellow_count || 0) > 0
    || Number(lineageManifestSummary?.red_count || 0) > 0;

  useEffect(() => {
    if (activeTab === "output" && outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [processOutput, activeTab]);

  function handleOpenFile(path) {
    if (path) {
      openInSystem(path).catch(() => {});
    }
  }

  const hasOutput = Boolean(processOutput);
  const hasFiles = Boolean(closeoutPath || wordPath || pptPath || webpagePath || mlReportPath);

  const railTabs = [
    {
      id: "chat",
      icon: <RailChatIcon />,
      title: language === "ko" ? "AI Chat" : "AI Chat",
      dot: false,
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
  ];

  return (
    <aside className={`details-pane rsb ${collapsed ? "rsb--collapsed" : ""}`.trim()}>
      {collapsed ? null : (
        <div className="rsb-panel">
        {activeTab === "chat" ? (
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
            busy={busy}
            language={language}
          />
        ) : null}

        {activeTab === "output" ? (
          <div className="details-output-panel rsb-output">
            {processOutput ? (
              <pre ref={outputRef} className="details-output-pre">{processOutput}</pre>
            ) : (
              <div className="details-output-empty">
                <RailTerminalIcon />
                <span>{language === "ko" ? "No output yet." : "No output yet."}</span>
              </div>
            )}
          </div>
        ) : null}

        {activeTab === "files" ? (
          <div className="rsb-files">
            <div className="rsb-files__section-label">
              {language === "ko" ? "Document Generation" : "Document Generation"}
            </div>

            <div className="rsb-files__generation">
              <OutputCard
                icon={<WordDocIcon />}
                title="Word Report"
                description={language === "ko" ? "Save execution results as a Word (.docx) report." : "Save execution results as a Word (.docx) report."}
                enabled={Boolean(onChangeForm)}
                checked={Boolean(form?.runtime?.generate_word_report)}
                onChange={(event) =>
                  onChangeForm?.((current) => ({
                    ...current,
                    runtime: { ...current.runtime, generate_word_report: event.target.checked },
                  }))
                }
                busy={busy}
                allowWhileRunning={liveRuntimeEditable}
                language={language}
              />
              <OutputCard
                icon={<PptDocIcon />}
                title="PowerPoint"
                description={language === "ko" ? "Auto-generate result slides as a PowerPoint presentation." : "Auto-generate result slides as a PowerPoint presentation."}
                enabled={false}
                checked={false}
                onChange={() => {}}
                busy={busy}
                comingSoon={true}
                language={language}
              />
              <OutputCard
                icon={<WebDocIcon />}
                title={language === "ko" ? "Website" : "Website"}
                description={language === "ko" ? "Export results as a static HTML website." : "Export results as a static HTML website."}
                enabled={false}
                checked={false}
                onChange={() => {}}
                busy={busy}
                comingSoon={true}
                language={language}
              />
            </div>

            <div className="rsb-files__section-label">
              {language === "ko" ? "Reports & Outputs" : "Reports & Outputs"}
            </div>

            <ReportFileCard
              title={language === "ko" ? "Closeout Report" : "Closeout Report"}
              kind="Markdown"
              icon={<MarkdownDocIcon />}
              path={closeoutPath}
              available={Boolean(detail?.reports?.closeout_report_text && closeoutPath)}
              onOpen={handleOpenFile}
              language={language}
            />
            <ReportFileCard
              title="Word Report"
              kind=".docx"
              icon={<WordDocIcon />}
              path={wordPath}
              available={Boolean(wordPath)}
              onOpen={handleOpenFile}
              language={language}
            />
            <ReportFileCard
              title="PowerPoint"
              kind=".pptx"
              icon={<PptDocIcon />}
              path={pptPath}
              available={Boolean(pptPath)}
              onOpen={handleOpenFile}
              language={language}
            />
            {webpagePath ? (
              <ReportFileCard
                title="Webpage"
                kind=".html"
                icon={<WebDocIcon />}
                path={webpagePath}
                available={true}
                onOpen={handleOpenFile}
                language={language}
              />
            ) : null}
            {mlReportPath ? (
              <ReportFileCard
                title="ML Experiment Report"
                kind="Markdown"
                icon={<MarkdownDocIcon />}
                path={mlReportPath}
                available={true}
                onOpen={handleOpenFile}
                language={language}
              />
            ) : null}

            {detail?.reports?.latest_failure?.artifact_files?.length ? (
              <>
                <div className="rsb-files__section-label" style={{ marginTop: "12px" }}>
                  {language === "ko" ? "Failure Artifacts" : "Failure Artifacts"}
                </div>
                {(detail.reports.latest_failure.artifact_files || []).slice(0, 6).map((path) => (
                  <div key={path} className="rsb-artifact-row">
                    <span className="rsb-artifact-row__path" title={path}>{path}</span>
                    <button
                      className="rsb-file-card__open-btn"
                      onClick={() => handleOpenFile(path)}
                      type="button"
                      title={language === "ko" ? "Open" : "Open"}
                    >
                      <OpenFolderIcon />
                    </button>
                  </div>
                ))}
              </>
            ) : null}
          </div>
        ) : null}

        {activeTab === "contracts" ? (
          <div className="rsb-inspector">
            <section className="details-card">
              <div className="details-card__header">
                <strong>{language === "ko" ? "Contract Wave" : "Contract Wave"}</strong>
                <span className={`status-badge status-badge--${contractAttention ? "warning" : "success"}`}>
                  {contractAttention ? (language === "ko" ? "Needs review" : "Needs review") : (language === "ko" ? "Stable" : "Stable")}
                </span>
              </div>
              <dl className="details-list">
                <div>
                  <dt>{language === "ko" ? "Spine" : "Spine"}</dt>
                  <dd>{String(spineReport?.current_version || "spine-v1")}</dd>
                </div>
                <div>
                  <dt>{language === "ko" ? "Open CRRs" : "Open CRRs"}</dt>
                  <dd>{Number(commonRequirements?.open_count || 0)}</dd>
                </div>
                <div>
                  <dt>{language === "ko" ? "Resolved CRRs" : "Resolved CRRs"}</dt>
                  <dd>{Number(commonRequirements?.resolved_count || 0)}</dd>
                </div>
                <div>
                  <dt>{language === "ko" ? "Manifests" : "Manifests"}</dt>
                  <dd>{Number(lineageManifestSummary?.total || 0)}</dd>
                </div>
                <div>
                  <dt>{language === "ko" ? "Promotion mix" : "Promotion mix"}</dt>
                  <dd>
                    G {Number(lineageManifestSummary?.green_count || 0)} / Y {Number(lineageManifestSummary?.yellow_count || 0)} / R {Number(lineageManifestSummary?.red_count || 0)}
                  </dd>
                </div>
              </dl>
            </section>

            <section className="details-card">
              <div className="details-card__header">
                <strong>{language === "ko" ? "Artifacts" : "Artifacts"}</strong>
              </div>
              <div style={{ display: "grid", gap: "10px" }}>
                <ReportFileCard
                  title="SPINE.json"
                  kind=".json"
                  icon={<MarkdownDocIcon />}
                  path={spinePath}
                  available={Boolean(spinePath)}
                  onOpen={handleOpenFile}
                  language={language}
                />
                <ReportFileCard
                  title="COMMON_REQUIREMENTS.json"
                  kind=".json"
                  icon={<MarkdownDocIcon />}
                  path={commonRequirementsPath}
                  available={Boolean(commonRequirementsPath)}
                  onOpen={handleOpenFile}
                  language={language}
                />
                <ReportFileCard
                  title="SHARED_CONTRACTS.md"
                  kind="Markdown"
                  icon={<MarkdownDocIcon />}
                  path={sharedContractsPath}
                  available={Boolean(sharedContractsPath)}
                  onOpen={handleOpenFile}
                  language={language}
                />
                <ReportFileCard
                  title={language === "ko" ? "Lineage manifests" : "Lineage manifests"}
                  kind={language === "ko" ? "Directory" : "Directory"}
                  icon={<OpenFolderIcon />}
                  path={lineageManifestsDir}
                  available={Boolean(lineageManifestsDir)}
                  onOpen={handleOpenFile}
                  language={language}
                />
              </div>
            </section>

            {selectedStep ? (
              <section className="details-card">
                <div className="details-card__header">
                  <strong>{language === "ko" ? "Selected Step Policy" : "Selected Step Policy"}</strong>
                  <span className={`status-badge status-badge--${statusTone(selectedStep.promotion_class || "pending")}`}>
                    {String(selectedStep.promotion_class || "-").toUpperCase()}
                  </span>
                </div>
                <div className="details-text">
                  <strong>{selectedStep.step_id}: {selectedStep.title}</strong>
                  <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>
                    {language === "ko" ? "Step type" : "Step type"}: {selectedStep.step_type || "feature"} · {language === "ko" ? "Scope" : "Scope"}: {selectedStep.scope_class || "free_owned"} · {language === "ko" ? "Spine" : "Spine"}: {selectedStep.spine_version || spineReport?.current_version || "spine-v1"}
                  </p>
                  <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>
                    Contracts: {selectedStepContracts.length ? selectedStepContracts.join(", ") : "none"}
                  </p>
                  <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>
                    Primary: {selectedPrimaryScope.length ? selectedPrimaryScope.join(", ") : "none"}
                  </p>
                  <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>
                    Shared-reviewed: {selectedSharedReviewed.length ? selectedSharedReviewed.join(", ") : "none"}
                  </p>
                  <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>
                    Forbidden-core: {selectedForbiddenCore.length ? selectedForbiddenCore.join(", ") : "none"}
                  </p>
                </div>
              </section>
            ) : null}

            <section className="details-card">
              <div className="details-card__header">
                <strong>{language === "ko" ? "Open Common Requirements" : "Open Common Requirements"}</strong>
              </div>
              {openCommonRequirements.length ? (
                <div style={{ display: "grid", gap: "10px" }}>
                  {openCommonRequirements.slice(0, 6).map((item) => (
                    <div key={item.request_id} className="details-text">
                      <strong>{item.request_id} · {item.title || (language === "ko" ? "Shared requirement review" : "Shared requirement review")}</strong>
                      <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>
                        {String(item.promotion_class || "").toUpperCase()} · {item.spine_version || spineReport?.current_version || "spine-v1"} · {item.lineage_id || "n/a"} / {item.step_id || "n/a"}
                      </p>
                      <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>{item.reason || item.notes || "-"}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="details-text" style={{ color: "var(--text-dim)", fontSize: "11px" }}>
                  {language === "ko" ? "No open CRRs." : "No open CRRs."}
                </div>
              )}
            </section>

            <section className="details-card">
              <div className="details-card__header">
                <strong>{language === "ko" ? "Recent Manifests" : "Recent Manifests"}</strong>
              </div>
              {lineageManifests.length ? (
                <div style={{ display: "grid", gap: "10px" }}>
                  {lineageManifests.slice(0, 6).map((item) => (
                    <div key={item.manifest_id || `${item.lineage_id}-${item.step_id}`} className="details-text">
                      <strong>{item.lineage_id || "LN?"} / {item.step_id || "ST?"}</strong>
                      <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>
                        {String(item.promotion_class || "-").toUpperCase()} · {item.step_type || "feature"} · {item.scope_class || "free_owned"}
                      </p>
                      <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>
                        {item.promotion_reason || "-"}
                      </p>
                      <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>
                        Helpers: {Array.isArray(item.helper_symbol_changes) && item.helper_symbol_changes.length ? item.helper_symbol_changes.length : 0} · APIs: {Array.isArray(item.public_symbol_changes) && item.public_symbol_changes.length ? item.public_symbol_changes.length : 0}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="details-text" style={{ color: "var(--text-dim)", fontSize: "11px" }}>
                  {language === "ko" ? "No lineage manifests recorded yet." : "No lineage manifests recorded yet."}
                </div>
              )}
            </section>

            {spineHistory.length ? (
              <section className="details-card">
                <div className="details-card__header">
                  <strong>{language === "ko" ? "Recent Spine Checkpoints" : "Recent Spine Checkpoints"}</strong>
                </div>
                <div style={{ display: "grid", gap: "10px" }}>
                  {spineHistory.slice(0, 5).map((item) => (
                    <div key={`${item.version}-${item.created_at}`} className="details-text">
                      <strong>{item.version}</strong>
                      <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>
                        {item.created_at || "-"} · {item.lineage_id || "n/a"} / {item.step_id || "n/a"}
                      </p>
                      <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>{item.notes || "-"}</p>
                    </div>
                  ))}
                </div>
              </section>
            ) : null}

            {sharedContractsText ? (
              <section className="details-card">
                <div className="details-card__header">
                  <strong>{language === "ko" ? "Shared Contracts Snapshot" : "Shared Contracts Snapshot"}</strong>
                </div>
                <div className="details-text">
                  <pre style={{ whiteSpace: "pre-wrap", fontSize: "11px" }}>{sharedContractsText}</pre>
                </div>
              </section>
            ) : null}

            {resolvedCommonRequirements.length ? (
              <section className="details-card">
                <div className="details-card__header">
                  <strong>{language === "ko" ? "Resolved Common Requirements" : "Resolved Common Requirements"}</strong>
                </div>
                <div style={{ display: "grid", gap: "10px" }}>
                  {resolvedCommonRequirements.slice(0, 4).map((item) => (
                    <div key={item.request_id} className="details-text">
                      <strong>{item.request_id} · {item.title || "-"}</strong>
                      <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>
                        {item.resolved_at || "-"} · {item.lineage_id || "n/a"} / {item.step_id || "n/a"}
                      </p>
                    </div>
                  ))}
                </div>
              </section>
            ) : null}
          </div>
        ) : null}

        {activeTab === "inspector" ? (
          <div className="rsb-inspector">
            <section className="details-card">
              <div className="details-card__header">
                <strong>{t("common.project")}</strong>
                <span className={`status-badge status-badge--${statusTone(detail?.project?.current_status)}`}>
                  {displayStatus(detail?.project?.current_status || "idle", language)}
                </span>
              </div>
              <dl className="details-list">
                <div>
                  <dt>{t("common.name")}</dt>
                  <dd>{detail?.project?.display_name || detail?.project?.slug || t("project.none")}</dd>
                </div>
                <div>
                  <dt>{t("common.branch")}</dt>
                  <dd>{detail?.project?.branch || t("common.unknown")}</dd>
                </div>
                <div>
                  <dt>Path</dt>
                  <dd>{detail?.project?.repo_path || t("common.unknown")}</dd>
                </div>
                <div>
                  <dt>Model</dt>
                  <dd>{runtimeSummary(detail?.runtime || {}, modelPresets)}</dd>
                </div>
                <div>
                  <dt>Revision</dt>
                  <dd>{detail?.project?.current_safe_revision || "-"}</dd>
                </div>
              </dl>
            </section>

            <section className="details-card">
              <div className="details-card__header">
                <strong>Step</strong>
                <span className={`status-badge status-badge--${statusTone(selectedStepStatus)}`}>
                  {selectedStep ? displayStatus(selectedStepStatus, language) : "-"}
                </span>
              </div>
              {selectedStep ? (
                <div className="details-text">
                  <strong>{selectedStep.step_id}: {selectedStep.title}</strong>
                  <p style={{ margin: "4px 0", color: "var(--text-muted)" }}>{selectedStep.display_description}</p>
                  <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>
                    Effort: {reasoningEffortLabel(selectedStep.reasoning_effort || detail?.runtime?.effort || "high")}
                  </p>
                  {selectedStep.success_criteria ? (
                    <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>{selectedStep.success_criteria}</p>
                  ) : null}
                  {selectedStep.deadline_at ? (
                    <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>
                      Deadline: {selectedStep.deadline_at}
                    </p>
                  ) : null}
                </div>
              ) : (
                <div className="details-text" style={{ color: "var(--text-dim)", fontSize: "11px" }}>
                  {language === "ko" ? "Select a block to inspect." : "Select a block to inspect."}
                </div>
              )}
            </section>

            {pendingCheckpoint ? (
              <section className="details-card">
                <div className="details-card__header">
                  <strong>Checkpoint</strong>
                  <span className={`status-badge status-badge--${statusTone(pendingCheckpoint.status)}`}>
                    {displayStatus(pendingCheckpoint.status || "pending", language)}
                  </span>
                </div>
                <div className="details-text">
                  <strong>{pendingCheckpoint.checkpoint_id}</strong>
                  {pendingCheckpoint.title ? <p style={{ margin: "4px 0" }}>{pendingCheckpoint.title}</p> : null}
                  {pendingCheckpoint.target_block ? (
                    <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>
                      Block {pendingCheckpoint.target_block}
                    </p>
                  ) : null}
                  {pendingCheckpoint.deadline_at ? (
                    <p style={{ margin: "4px 0", fontSize: "11px", color: "var(--text-dim)" }}>
                      Deadline: {pendingCheckpoint.deadline_at}
                    </p>
                  ) : null}
                </div>
              </section>
            ) : null}

            {detail?.reports?.closeout_report_text ? (
              <section className="details-card">
                <div className="details-card__header">
                  <strong>Report</strong>
                </div>
                <div className="details-text">
                  <pre style={{ whiteSpace: "pre-wrap", fontSize: "11px" }}>{detail.reports.closeout_report_text}</pre>
                </div>
              </section>
            ) : null}
          </div>
        ) : null}
        </div>
      )}

      <div className="rsb-rail">
        {railTabs.map(({ id, icon, title, dot }) => (
          <button
            key={id}
            className={`sidebar-icon${!collapsed && activeTab === id ? " active" : ""}`}
            onClick={() => onChangeTab?.(id)}
            title={title}
            type="button"
            aria-pressed={!collapsed && activeTab === id}
          >
            {icon}
            {dot ? <span className="rsb-rail__dot" /> : null}
          </button>
        ))}
      </div>
    </aside>
  );
}
