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

function ChatPanel({ chatMessages, onSendChatMessage, busy, language, t }) {
  const [input, setInput] = useState("");
  const [localMessages, setLocalMessages] = useState(Array.isArray(chatMessages) ? chatMessages : []);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [localMessages]);

  function handleSend() {
    const text = input.trim();
    if (!text) return;
    const msg = { role: "user", text, id: Date.now() };
    setLocalMessages((prev) => [...prev, msg]);
    setInput("");
    onSendChatMessage?.(text);
  }

  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSend();
    }
  }

  return (
    <>
      <div className="sidebar-panel__header">
        <strong>{language === "ko" ? "AI 채팅" : "AI Chat"}</strong>
        <span style={{ fontSize: "11px", color: "var(--text-dim)" }}>
          {language === "ko" ? "실행 중 개입 가능" : "Intervene anytime"}
        </span>
      </div>

      <div className="sidebar-chat-messages">
        {localMessages.length === 0 ? (
          <div className="sidebar-chat-empty">
            <SidebarChatIcon />
            <span>{language === "ko" ? "메시지를 입력하여 AI에 지시하세요." : "Send a message to guide the AI."}</span>
          </div>
        ) : (
          localMessages.map((msg) => (
            <div key={msg.id} className={`sidebar-chat-bubble sidebar-chat-bubble--${msg.role}`}>
              <span className="sidebar-chat-bubble__role">
                {msg.role === "user" ? (language === "ko" ? "나" : "You") : "AI"}
              </span>
              <p>{msg.text}</p>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>

      <div className="sidebar-chat-input-row">
        <textarea
          className="sidebar-chat-input"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={language === "ko" ? "메시지 입력... (Enter로 전송)" : "Type a message… (Enter to send)"}
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

  const visibleProjects = useMemo(() => {
    const query = deferredProjectFilter.trim().toLowerCase();
    if (!query) {
      return projects;
    }
    return (projects || []).filter((project) =>
      [project.display_name, project.slug, project.status, project.detail, project.repo_path]
        .join(" ")
        .toLowerCase()
        .includes(query),
    );
  }, [deferredProjectFilter, projects]);

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
    ["projects", <SidebarProjectsIcon key="projects-icon" />, t("common.project")],
    ["workspace", <SidebarExplorerIcon key="workspace-icon" />, t("sidebar.explorer")],
    ["plans", <SidebarCheckpointsIcon key="plans-icon" />, t("sidebar.checkpoints")],
    ["reservations", <SidebarReservationIcon key="reservations-icon" />, language === "ko" ? "예약" : "Queue"],
  ];

  return (
    <aside className="ide-sidebar">
      <SidebarSectionTabs activeTab={activeTab} onChange={onChangeTab} tabs={tabs} />

      {activeTab ? (
        <div className="sidebar-panel">

          {activeTab === "projects" ? (
            <>
              <div className="sidebar-panel__header">
                <strong>{t("common.project")}</strong>
              </div>

              {planPrompt ? (
                <div className="sidebar-prompt-card">
                  <span className="sidebar-prompt-card__label">
                    {language === "ko" ? "프롬프트" : "Prompt"}
                  </span>
                  <p className="sidebar-prompt-card__text">
                    {planPrompt.length > 120 ? `${planPrompt.slice(0, 120)}\u2026` : planPrompt}
                  </p>
                </div>
              ) : null}

              <SearchInput
                value={projectFilter}
                onChange={onProjectFilterChange}
                placeholder={t("sidebar.searchProjects")}
              />

              <button className="sidebar-add-btn" onClick={onNewProject} type="button">
                <PlusIcon />
                <span>{t("action.new")}</span>
              </button>

              <div className="sidebar-list">
                {visibleProjects.length ? (
                  visibleProjects.map((project) => {
                    const tone = statusTone(project?.status);
                    return (
                      <button
                        key={project.repo_id || project.display_name}
                        className={`sidebar-project sidebar-project--${tone} ${project.repo_id === selectedProjectId ? "selected" : ""} ${project.repo_id === loadingProjectId ? "loading" : ""}`.trim()}
                        onClick={() => onSelectProject(project.repo_id)}
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
                    <EmptyProjectsIcon />
                    <span>{t("sidebar.emptyProjects")}</span>
                  </div>
                )}
              </div>
            </>
          ) : null}

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
                      return (
                        <div
                          className={`sidebar-item ${isPendingCheckpoint ? "sidebar-item--checkpoint-live" : ""}`}
                          key={checkpoint.checkpoint_id}
                        >
                          <div className="sidebar-item__title">
                            <strong style={{ fontSize: "12px" }}>{checkpoint.checkpoint_id}</strong>
                            <span className={`status-badge status-badge--${tone} ${isPendingCheckpoint ? "status-badge--pulse" : ""}`}>
                              {displayStatus(checkpoint.status, language)}
                            </span>
                          </div>
                          {checkpoint.title ? (
                            <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>{checkpoint.title}</span>
                          ) : null}
                          <span style={{ fontSize: "11px", color: "var(--text-dim)" }}>
                            {t("sidebar.targetBlock", { block: checkpoint.target_block })}
                          </span>
                          {checkpoint.deadline_at ? (
                            <span style={{ fontSize: "11px", color: "var(--text-dim)" }}>
                              {language === "ko" ? `마감 ${checkpoint.deadline_at}` : `Deadline ${checkpoint.deadline_at}`}
                            </span>
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
          ) : null}

        </div>
      ) : null}
    </aside>
  );
}
