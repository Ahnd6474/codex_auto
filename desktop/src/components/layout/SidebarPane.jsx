import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { useI18n } from "../../i18n";
import { displayStatus } from "../../locale";
import { statusTone } from "../../utils";

/* ── Rail icons ── */
function SidebarExplorerIcon() {
  return (
    <svg aria-hidden="true" className="sidebar-icon__svg" viewBox="0 0 24 24" fill="none">
      <path
        d="M4.75 7.75a2 2 0 0 1 2-2h3.1l1.35 1.5H17.25a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H6.75a2 2 0 0 1-2-2v-8.5Z"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinejoin="round"
      />
      <path d="M4.75 9.25h14.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

function SidebarCheckpointsIcon() {
  return (
    <svg aria-hidden="true" className="sidebar-icon__svg" viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="7.25" stroke="currentColor" strokeWidth="1.7" />
      <path d="M12 8.25v4.25l2.75 1.75" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function SidebarProjectsIcon() {
  return (
    <svg aria-hidden="true" className="sidebar-icon__svg" viewBox="0 0 24 24" fill="none">
      <path d="M4 6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v11a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 17.5v-11Z" stroke="currentColor" strokeWidth="1.7" />
      <path d="M8 9h8M8 13h8M8 17h5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

function SidebarHistoryIcon() {
  return (
    <svg aria-hidden="true" className="sidebar-icon__svg" viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="7.25" stroke="currentColor" strokeWidth="1.7" />
      <path d="M12 8v4.5l3 1.75" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="11" cy="11" r="7.25" stroke="currentColor" strokeWidth="1.7" />
      <path d="M16.5 16.5l4 4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
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

function EmptyProjectsIcon() {
  return (
    <svg viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <rect x="8" y="12" width="32" height="28" rx="3" stroke="currentColor" strokeWidth="1.8" />
      <path d="M8 18h32" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <path d="M17 8h14" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <path d="M18 26h12M18 32h8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function EmptyHistoryIcon() {
  return (
    <svg viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <circle cx="24" cy="24" r="15" stroke="currentColor" strokeWidth="1.8" />
      <path d="M24 16v9l5 3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function EmptyWorkspaceIcon() {
  return (
    <svg viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <path
        d="M10 12a4 4 0 0 1 4-4h8l4 4h12a4 4 0 0 1 4 4v20a4 4 0 0 1-4 4H14a4 4 0 0 1-4-4V12z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path d="M18 28l4-4 4 4 6-6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function EmptyCheckpointsIcon() {
  return (
    <svg viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <circle cx="24" cy="24" r="15" stroke="currentColor" strokeWidth="1.8" />
      <path d="M17 24l5 5 9-9" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function SidebarChatIcon() {
  return (
    <svg aria-hidden="true" className="sidebar-icon__svg" viewBox="0 0 24 24" fill="none">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function SidebarReservationIcon() {
  return (
    <svg aria-hidden="true" className="sidebar-icon__svg" viewBox="0 0 24 24" fill="none">
      <rect x="3" y="4" width="18" height="18" rx="2" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
      <path d="M16 2v4M8 2v4M3 10h18" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
      <path d="M8 14h4M8 17h8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
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

/* ── Rail tab list ── */
function SidebarSectionTabs({ activeTab, onChange, tabs }) {
  return (
    <div className="sidebar-rail">
      {tabs.map(([value, icon, label], index) => (
        <button
          key={value}
          className={`sidebar-icon ${activeTab === value ? "active" : ""}`}
          onClick={() => onChange(value)}
          title={`${label} (Alt+${index + 1})`}
          type="button"
          aria-pressed={activeTab === value}
        >
          {icon}
        </button>
      ))}
    </div>
  );
}

/* ── Workspace file tree ── */
function sortTreeChildren(children = []) {
  return [...children].sort((left, right) => {
    const leftFolder = left.kind === "dir" || left.kind === "directory" || Boolean((left.children || []).length);
    const rightFolder = right.kind === "dir" || right.kind === "directory" || Boolean((right.children || []).length);
    if (leftFolder !== rightFolder) {
      return leftFolder ? -1 : 1;
    }
    return String(left.label || "").localeCompare(String(right.label || ""));
  });
}

function normalizeTree(node) {
  return {
    ...node,
    children: sortTreeChildren(node.children || []).map((child) => normalizeTree(child)),
  };
}

function filterPreparedTree(node, normalizedQuery) {
  if (!normalizedQuery) {
    return node;
  }
  const children = (node.children || [])
    .map((child) => filterPreparedTree(child, normalizedQuery))
    .filter(Boolean);
  const selfMatch =
    node.label.toLowerCase().includes(normalizedQuery) || String(node.path || "").toLowerCase().includes(normalizedQuery);
  if (selfMatch || children.length) {
    return { ...node, children };
  }
  return null;
}

function TreeNode({ node, depth = 0, filter = "" }) {
  const query = filter.trim().toLowerCase();
  const [open, setOpen] = useState(depth < 1);
  const isFolder = node.kind === "dir" || node.kind === "directory" || Boolean((node.children || []).length);
  const children = node.children || [];
  const visible = query ? true : open;

  useEffect(() => {
    if (query) {
      setOpen(true);
    }
  }, [query]);

  return (
    <div className="tree-node" style={{ "--tree-depth": depth }}>
      <button
        className={`tree-node__row tree-node__row--${node.kind || "file"} ${isFolder ? "tree-node__row--folder" : ""}`}
        onClick={() => {
          if (isFolder && !query) {
            setOpen((current) => !current);
          }
        }}
        type="button"
      >
        <span className="tree-node__prefix">{isFolder ? (visible ? "▾" : "▸") : "·"}</span>
        <span>{node.label}</span>
      </button>
      {children.length && visible ? (
        <div className="tree-node__children">
          {children.map((child) => (
            <TreeNode key={`${child.path}-${child.label}`} node={child} depth={depth + 1} filter={filter} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

/* ── Search input with icon ── */
function SearchInput({ value, onChange, placeholder }) {
  return (
    <div className="sidebar-search-wrapper">
      <SearchIcon />
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        type="search"
      />
    </div>
  );
}

/* ── Project card small icons ── */
function CardGithubIcon() {
  return <svg viewBox="0 0 24 24" fill="none"><path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}
function CardEditorIcon() {
  return <svg viewBox="0 0 24 24" fill="none"><rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" strokeWidth="1.6" /><path d="M9 9l3 3-3 3M13 15h3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}
function CardFolderIcon() {
  return <svg viewBox="0 0 24 24" fill="none"><path d="M4 6a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" /></svg>;
}

function queuedPosition(value) {
  return Math.max(1, Number.parseInt(String(value || 0), 10) || 1);
}

function reservationLabel(job, fallback) {
  return String(job?.display_name || "").trim() || String(job?.repo_id || "").trim() || fallback;
}

function ReservationsPanel({ queuedJobs, onCancelQueuedJob, language, t }) {
  return (
    <>
      <div className="sidebar-panel__header">
        <strong>{language === "ko" ? "예약 대기열" : "Job Queue"}</strong>
        {queuedJobs.length > 0 ? (
          <span className="sidebar-count-badge">{queuedJobs.length}</span>
        ) : null}
      </div>
      <div className="sidebar-list">
        {queuedJobs.length ? (
          queuedJobs.map((job) => (
            <div key={job.id} className="sidebar-item sidebar-reservation-item">
              <div className="sidebar-item__title">
                <strong style={{ fontSize: "12px" }}>#{queuedPosition(job?.queue_position)} {reservationLabel(job, t("project.none"))}</strong>
                <span className="status-badge status-badge--info" style={{ fontSize: "10px" }}>
                  {language === "ko" ? "대기 중" : "queued"}
                </span>
              </div>
              {job?.project_dir ? (
                <span style={{ fontSize: "11px", color: "var(--text-dim)", wordBreak: "break-all" }}>{job.project_dir}</span>
              ) : null}
              <button
                className="sidebar-cancel-btn"
                onClick={() => onCancelQueuedJob?.(job.id)}
                type="button"
              >
                {language === "ko" ? "예약 취소" : "Cancel"}
              </button>
            </div>
          ))
        ) : (
          <div className="empty-block">
            <SidebarReservationIcon />
            <span>{language === "ko" ? "대기 중인 작업이 없습니다." : "No queued jobs."}</span>
          </div>
        )}
      </div>
    </>
  );
}

function ChatPanel({
  chat,
  selectedChatSessionId,
  chatDraftSession,
  onSelectChatSession,
  onStartNewChatSession,
  onSendChatMessage,
  busy,
  language,
}) {
  const sessions = Array.isArray(chat?.sessions) ? chat.sessions : [];
  const remoteMessages = Array.isArray(chat?.messages) ? chat.messages : [];
  const activeSessionId = String(selectedChatSessionId || chat?.active_session_id || "").trim();
  const summaryFile = String(chat?.summary_file || "").trim();
  const [input, setInput] = useState("");
  const [pendingMode, setPendingMode] = useState("conversation");
  const [menuOpen, setMenuOpen] = useState(false);
  const [localMessages, setLocalMessages] = useState(remoteMessages);
  const bottomRef = useRef(null);
  const menuRef = useRef(null);

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
      return language === "ko" ? "사용자" : "You";
    }
    if (role === "system") {
      return language === "ko" ? "시스템" : "System";
    }
    return "AI";
  }

  function modeLabel(mode) {
    if (mode === "debugger") {
      return language === "ko" ? "디버거" : "Debugger";
    }
    if (mode === "merger") {
      return language === "ko" ? "머저" : "Merger";
    }
    return language === "ko" ? "대화" : "Conversation";
  }

  function sessionLabel(session) {
    const title = String(session?.title || "").trim() || (language === "ko" ? "대화" : "Conversation");
    const count = Number.parseInt(String(session?.message_count || 0), 10) || 0;
    return `${title} · ${count}`;
  }

  function handleSend() {
    const text = input.trim();
    if (!text || busy) return;
    const mode = pendingMode;
    const msg = {
      role: "user",
      text,
      mode,
      status: "pending",
      message_id: `local-${Date.now()}`,
    };
    setLocalMessages((prev) => [...prev, msg]);
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

  const selectedSessionValue = chatDraftSession ? "" : activeSessionId;

  return (
    <>
      <div className="sidebar-panel__header">
        <strong>{language === "ko" ? "AI 채팅" : "AI Chat"}</strong>
        <span style={{ fontSize: "11px", color: "var(--text-dim)" }}>
          {language === "ko" ? "대화 또는 수동 복구 호출" : "Conversation or manual recovery"}
        </span>
      </div>

      <div className="sidebar-chat-toolbar">
        <select
          className="sidebar-chat-session-select"
          value={selectedSessionValue}
          onChange={handleSessionChange}
          disabled={busy}
        >
          <option value="">{language === "ko" ? "새 대화" : "New conversation"}</option>
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
          {language === "ko" ? "새로" : "New"}
        </button>
      </div>

      <div className="sidebar-chat-summary-path">
        <strong>{language === "ko" ? "요약 txt" : "Summary txt"}</strong>
        <span title={summaryFile || ""}>
          {summaryFile || (language === "ko" ? "첫 메시지를 보내면 생성됩니다." : "Created after the first message.")}
        </span>
      </div>

      <div className="sidebar-chat-messages">
        {localMessages.length === 0 ? (
          <div className="sidebar-chat-empty">
            <SidebarChatIcon />
            <span>
              {language === "ko"
                ? "메시지를 보내면 대화 기록 txt를 만들고 이어서 응답합니다."
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
              <p>{msg.text}</p>
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
              title={language === "ko" ? "디버거 또는 머저 선택" : "Choose debugger or merger"}
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
              {language === "ko" ? "기본: 대화 모드" : "Default: conversation"}
            </span>
          ) : (
            <button
              className="sidebar-chat-mode-chip sidebar-chat-mode-chip--active"
              onClick={() => setPendingMode("conversation")}
              type="button"
            >
              {language === "ko" ? "다음 전송:" : "Next send:"} {modeLabel(pendingMode)}
            </button>
          )}
        </div>

        <div className="sidebar-chat-input-row">
          <textarea
            className="sidebar-chat-input"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={language === "ko" ? "메시지 입력... (Enter 전송)" : "Type a message... (Enter to send)"}
            disabled={busy}
            rows={2}
          />
          <button
            className="sidebar-chat-send"
            onClick={handleSend}
            type="button"
            disabled={busy || !input.trim()}
            title={language === "ko" ? "전송" : "Send"}
          >
            <SendIcon />
          </button>
        </div>
      </div>
    </>
  );
}

/* ── Checkpoints panel with expand/collapse ── */
function CheckpointsPanel({ checkpoints, visibleCheckpoints, language, t }) {
  const [expandedIds, setExpandedIds] = useState(new Set());

  function toggleExpand(id) {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  return (
    <>
      <div className="sidebar-panel__header">
        <strong>{t("sidebar.checkpoints")}</strong>
        {visibleCheckpoints.length > 0 ? (
          <span className="sidebar-count-badge">{visibleCheckpoints.length}</span>
        ) : null}
      </div>

      <div className="sidebar-group">
        <div className="sidebar-list">
          {visibleCheckpoints.length ? (
            visibleCheckpoints.map((checkpoint) => {
              const isPendingCheckpoint =
                checkpoint?.status === "awaiting_review" ||
                checkpoint?.checkpoint_id === checkpoints?.pending?.checkpoint_id;
              const tone = statusTone(checkpoint.status);
              const isExpanded = expandedIds.has(checkpoint.checkpoint_id);
              const hasDetails = checkpoint.title || checkpoint.target_block || checkpoint.deadline_at;

              return (
                <div
                  className={`sidebar-item sidebar-item--checkpoint ${isPendingCheckpoint ? "sidebar-item--checkpoint-live" : ""}`.trim()}
                  key={checkpoint.checkpoint_id}
                >
                  <button
                    type="button"
                    className="sidebar-checkpoint-row"
                    onClick={() => hasDetails && toggleExpand(checkpoint.checkpoint_id)}
                    style={{ cursor: hasDetails ? "pointer" : "default" }}
                    aria-expanded={isExpanded}
                  >
                    <span className="sidebar-checkpoint-row__arrow" aria-hidden="true">
                      {hasDetails ? (isExpanded ? "▾" : "▸") : "·"}
                    </span>
                    <strong className="sidebar-checkpoint-row__id">{checkpoint.checkpoint_id}</strong>
                    <span className={`status-badge status-badge--${tone} ${isPendingCheckpoint ? "status-badge--pulse" : ""}`.trim()}>
                      {displayStatus(checkpoint.status, language)}
                    </span>
                  </button>

                  {isExpanded && hasDetails ? (
                    <div className="sidebar-checkpoint-detail">
                      {checkpoint.title ? (
                        <span>{checkpoint.title}</span>
                      ) : null}
                      {checkpoint.target_block ? (
                        <span>{t("sidebar.targetBlock", { block: checkpoint.target_block })}</span>
                      ) : null}
                      {checkpoint.deadline_at ? (
                        <span>
                          {language === "ko" ? `마감 ${checkpoint.deadline_at}` : `Deadline ${checkpoint.deadline_at}`}
                        </span>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              );
            })
          ) : (
            <div className="empty-block">
              <EmptyCheckpointsIcon />
              <span>{t("sidebar.noRecordedCheckpoints")}</span>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

/* ── Main SidebarPane ── */
export function SidebarPane({
  activeTab,
  onChangeTab,
  projects = [],
  historyProjects = [],
  selectedProjectId = "",
  selectedHistoryId = "",
  loadingProjectId = "",
  projectFilter = "",
  workspaceFilter,
  onProjectFilterChange = () => {},
  onWorkspaceFilterChange,
  onSelectProject = () => {},
  onSelectHistory = () => {},
  onNewProject = () => {},
  workspaceTree,
  checkpoints,
  queuedJobs = [],
  onCancelQueuedJob,
  chatMessages = [],
  onSendChatMessage,
  busy = false,
  planPrompt = "",
}) {
  const { language, t } = useI18n();
  const deferredProjectFilter = useDeferredValue(projectFilter);
  const workspaceTabActive = activeTab === "workspace";
  const deferredWorkspaceFilter = useDeferredValue(workspaceFilter);
  const workspaceFilterCacheRef = useRef(new Map());
  const normalizedWorkspaceTree = useMemo(
    () => (workspaceTabActive ? (workspaceTree || []).map((node) => normalizeTree(node)) : []),
    [workspaceTabActive, workspaceTree],
  );

  const visibleCheckpoints = useMemo(() => {
    if (activeTab !== "plans") {
      return [];
    }
    const items = Array.isArray(checkpoints?.items) ? checkpoints.items.filter(Boolean) : [];
    const pending = checkpoints?.pending && typeof checkpoints.pending === "object" ? checkpoints.pending : null;
    if (!pending) return items;
    if (items.some((item) => item?.checkpoint_id === pending.checkpoint_id)) return items;
    return [pending, ...items];
  }, [activeTab, checkpoints]);

  useEffect(() => { workspaceFilterCacheRef.current.clear(); }, [normalizedWorkspaceTree]);

  const filteredWorkspaceTree = useMemo(() => {
    if (!workspaceTabActive) {
      return [];
    }
    const normalizedQuery = deferredWorkspaceFilter.trim().toLowerCase();
    const cached = workspaceFilterCacheRef.current.get(normalizedQuery);
    if (cached) return cached;
    const nextTree = normalizedQuery
      ? normalizedWorkspaceTree.map((node) => filterPreparedTree(node, normalizedQuery)).filter(Boolean)
      : normalizedWorkspaceTree;
    if (workspaceFilterCacheRef.current.size >= 12) {
      const oldestQuery = workspaceFilterCacheRef.current.keys().next().value;
      workspaceFilterCacheRef.current.delete(oldestQuery);
    }
    workspaceFilterCacheRef.current.set(normalizedQuery, nextTree);
    return nextTree;
  }, [deferredWorkspaceFilter, normalizedWorkspaceTree, workspaceTabActive]);

  const visibleHistoryProjects = useMemo(() => {
    const query = deferredProjectFilter.trim().toLowerCase();
    if (!query) {
      return historyProjects;
    }
    return (historyProjects || []).filter((project) =>
      [project.display_name, project.slug, project.status, project.detail, project.repo_path]
        .join(" ")
        .toLowerCase()
        .includes(query),
    );
  }, [deferredProjectFilter, historyProjects]);

  const tabs = [
    ["workspace", <SidebarExplorerIcon key="workspace-icon" />, t("sidebar.explorer")],
    ["plans", <SidebarCheckpointsIcon key="plans-icon" />, t("sidebar.checkpoints")],
    ["reservations", <SidebarReservationIcon key="reservations-icon" />, language === "ko" ? "예약" : "Queue"],
  ];

  return (
    <aside className="ide-sidebar">
      <SidebarSectionTabs activeTab={activeTab} onChange={onChangeTab} tabs={tabs} />

      {activeTab ? (
        <div className="sidebar-panel">

          {activeTab === "history" ? (
            <>
              <div className="sidebar-panel__header">
                <strong>{t("tab.history")}</strong>
              </div>

              <SearchInput
                value={projectFilter}
                onChange={onProjectFilterChange}
                placeholder={t("sidebar.searchProjects")}
              />

              <div className="sidebar-list">
                {visibleHistoryProjects.length ? (
                  visibleHistoryProjects.map((project) => {
                    const tone = statusTone(project?.status);
                    return (
                      <button
                        key={project.archive_id || project.display_name}
                        className={`sidebar-project sidebar-project--${tone} ${project.archive_id === selectedHistoryId ? "selected" : ""}`.trim()}
                        onClick={() => onSelectHistory(project.archive_id)}
                        type="button"
                      >
                        <div className="sidebar-project__fill" />
                        <div className="sidebar-project__title">
                          <strong>{project.display_name || project.slug || t("common.unknown")}</strong>
                          <span className={`status-badge status-badge--${tone} sidebar-project__status`}>
                            {displayStatus(project.status, language)}
                          </span>
                        </div>
                        {project.detail ? <span className="sidebar-project__detail" title={project.detail}>{project.detail}</span> : null}
                      </button>
                    );
                  })
                ) : (
                  <div className="empty-block">
                    <EmptyHistoryIcon />
                    <span>{language === "ko" ? "기록이 없습니다." : "No archived runs yet."}</span>
                  </div>
                )}
              </div>
            </>
          ) : null}

          {/* ── Workspace explorer tab ── */}
          {activeTab === "workspace" ? (
            <>
              <div className="sidebar-panel__header">
                <strong>{t("sidebar.explorer")}</strong>
              </div>

              <SearchInput
                value={workspaceFilter}
                onChange={onWorkspaceFilterChange}
                placeholder={t("sidebar.searchFiles")}
              />

              <div className="sidebar-tree">
                {filteredWorkspaceTree.length ? (
                  filteredWorkspaceTree.map((node) => (
                    <TreeNode key={node.path} node={node} filter={deferredWorkspaceFilter} />
                  ))
                ) : (
                  <div className="empty-block">
                    <EmptyWorkspaceIcon />
                    <span>{t("sidebar.emptyWorkspace")}</span>
                  </div>
                )}
              </div>
            </>
          ) : null}

          {/* ── Reservations tab ── */}
          {activeTab === "reservations" ? (
            <ReservationsPanel queuedJobs={queuedJobs} onCancelQueuedJob={onCancelQueuedJob} language={language} t={t} />
          ) : null}

          {/* ── AI Chat tab ── */}
          {activeTab === "chat" ? (
            <ChatPanel chatMessages={chatMessages} onSendChatMessage={onSendChatMessage} busy={busy} language={language} t={t} />
          ) : null}

          {/* ── Checkpoints tab ── */}
          {activeTab === "plans" ? (
            <CheckpointsPanel
              checkpoints={checkpoints}
              visibleCheckpoints={visibleCheckpoints}
              language={language}
              t={t}
            />
          ) : null}

        </div>
      ) : null}
    </aside>
  );
}
