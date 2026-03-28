import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { useI18n } from "../../i18n";
import { displayStatus } from "../../locale";
import { statusTone } from "../../utils";

/* ── Rail icons ── */
function SidebarProjectsIcon() {
  return (
    <svg aria-hidden="true" className="sidebar-icon__svg" viewBox="0 0 24 24" fill="none">
      <path
        d="M4.75 7.25A2.5 2.5 0 0 1 7.25 4.75h5.1c.66 0 1.3.26 1.77.73l5.15 5.15c.47.47.73 1.1.73 1.77v4.35a2.5 2.5 0 0 1-2.5 2.5h-10a2.5 2.5 0 0 1-2.5-2.5v-9.5Z"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinejoin="round"
      />
      <path d="M13 4.9v5.35a1 1 0 0 0 1 1h5.1" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
      <path d="M8.5 14.25h7" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
      <path d="M8.5 17.25h5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

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

/* ── Rail tab list ── */
function SidebarSectionTabs({ activeTab, onChange, tabs }) {
  return (
    <div className="sidebar-rail">
      {tabs.map(([value, icon, label]) => (
        <button
          key={value}
          className={`sidebar-icon ${activeTab === value ? "active" : ""}`}
          onClick={() => onChange(value)}
          title={label}
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

/* ── Main SidebarPane ── */
export function SidebarPane({
  activeTab,
  onChangeTab,
  projects,
  historyProjects,
  selectedProjectId,
  selectedHistoryId,
  loadingProjectId,
  projectFilter,
  workspaceFilter,
  onProjectFilterChange,
  onWorkspaceFilterChange,
  onSelectProject,
  onSelectHistory,
  onNewProject,
  onArchiveProject,
  onDeleteProject,
  onDeleteHistoryEntry,
  workspaceTree,
  checkpoints,
  github,
}) {
  const { language, t } = useI18n();
  const [contextMenu, setContextMenu] = useState(null);
  const deferredWorkspaceFilter = useDeferredValue(workspaceFilter);
  const workspaceFilterCacheRef = useRef(new Map());
  const normalizedWorkspaceTree = useMemo(() => (workspaceTree || []).map((node) => normalizeTree(node)), [workspaceTree]);

  const visibleCheckpoints = useMemo(() => {
    const items = Array.isArray(checkpoints?.items) ? checkpoints.items.filter(Boolean) : [];
    const pending = checkpoints?.pending && typeof checkpoints.pending === "object" ? checkpoints.pending : null;
    if (!pending) return items;
    if (items.some((item) => item?.checkpoint_id === pending.checkpoint_id)) return items;
    return [pending, ...items];
  }, [checkpoints]);

  useEffect(() => {
    workspaceFilterCacheRef.current.clear();
  }, [normalizedWorkspaceTree]);

  const filteredWorkspaceTree = useMemo(() => {
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
  }, [deferredWorkspaceFilter, normalizedWorkspaceTree]);

  useEffect(() => {
    function handlePointerDown() {
      setContextMenu(null);
    }
    function handleKeyDown(event) {
      if (event.key === "Escape") setContextMenu(null);
    }
    window.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  const tabs = [
    ["projects", <SidebarProjectsIcon key="projects-icon" />, t("common.project")],
    ["history", <SidebarHistoryIcon key="history-icon" />, t("tab.history")],
    ["workspace", <SidebarExplorerIcon key="workspace-icon" />, t("sidebar.explorer")],
    ["plans", <SidebarCheckpointsIcon key="plans-icon" />, t("sidebar.checkpoints")],
  ];

  return (
    <aside className="ide-sidebar">
      <SidebarSectionTabs activeTab={activeTab} onChange={onChangeTab} tabs={tabs} />

      {activeTab ? (
        <div className="sidebar-panel">

          {/* ── Projects tab ── */}
          {activeTab === "projects" ? (
            <>
              <div className="sidebar-panel__header">
                <strong>{t("common.project")}</strong>
                {projects.length > 0 ? (
                  <span className="sidebar-count-badge">{projects.length}</span>
                ) : null}
              </div>

              <SearchInput
                value={projectFilter}
                onChange={onProjectFilterChange}
                placeholder={t("sidebar.searchProjects")}
              />

              <button className="sidebar-add-btn" onClick={onNewProject} type="button">
                <PlusIcon />
                {t("action.new")}
              </button>

              <div className="sidebar-list">
                {projects.length ? (
                  projects.map((project) => {
                    const tone = statusTone(project.status);
                    const stats = project.stats || {};
                    const total = stats.total_steps || 0;
                    const completed = stats.completed_steps || 0;
                    const fillPct = total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : 0;
                    return (
                      <button
                        key={project.repo_id}
                        className={`sidebar-project sidebar-project--${tone} ${project.repo_id === selectedProjectId ? "selected" : ""} ${
                          project.repo_id === loadingProjectId ? "loading" : ""
                        }`}
                        onClick={() => onSelectProject(project.repo_id)}
                        onContextMenu={(event) => {
                          event.preventDefault();
                          setContextMenu({ kind: "project", id: project.repo_id, x: event.clientX, y: event.clientY });
                        }}
                        title={t("sidebar.projectContextDelete")}
                        type="button"
                      >
                        {fillPct > 0 ? (
                          <span
                            className="sidebar-project__fill"
                            aria-hidden="true"
                            style={{ width: `${fillPct}%` }}
                          />
                        ) : null}
                        <div className="sidebar-project__title">
                          <strong>{project.display_name}</strong>
                          <span className={`status-badge status-badge--${tone}`}>
                            {displayStatus(project.status, language)}
                          </span>
                        </div>
                        {project.detail ? <span style={{ fontSize: "11.5px", color: "var(--text-dim)" }}>{project.detail}</span> : null}
                        {total > 0 ? (
                          <div className="sidebar-project__steps">
                            <div className="sidebar-project__steps-bar">
                              <div className="sidebar-project__steps-fill" style={{ width: `${fillPct}%` }} />
                            </div>
                            <span>{completed}/{total}</span>
                          </div>
                        ) : null}
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

              {/* GitHub info */}
              <div className="sidebar-item">
                <div className="sidebar-item__title">
                  <strong>{t("sidebar.repositoryLink")}</strong>
                  <span className={`status-badge status-badge--${github?.connected ? "success" : "neutral"}`}>
                    {github?.connected ? t("common.connected") : t("common.localOnly")}
                  </span>
                </div>
                <span style={{ fontSize: "11.5px", wordBreak: "break-all" }}>{github?.origin_url || t("sidebar.noGithubOrigin")}</span>
              </div>
              <div className="sidebar-item">
                <strong>{t("common.branch")}</strong>
                <span style={{ fontSize: "11.5px" }}>{github?.branch || t("common.unknown")}</span>
              </div>
              <div className="sidebar-item">
                <strong>{t("common.repoUrl")}</strong>
                <span style={{ fontSize: "11.5px", wordBreak: "break-all" }}>{github?.repo_url || t("common.unavailable")}</span>
              </div>

              {contextMenu?.kind === "project" ? (
                <div
                  className="context-menu"
                  style={{ left: `${contextMenu.x}px`, top: `${contextMenu.y}px` }}
                  onPointerDown={(event) => event.stopPropagation()}
                >
                  <button
                    className="context-menu__item"
                    onClick={() => {
                      const repoId = contextMenu.id;
                      setContextMenu(null);
                      onArchiveProject(repoId);
                    }}
                    type="button"
                  >
                    {t("action.archiveProject")}
                  </button>
                  <button
                    className="context-menu__item"
                    onClick={() => {
                      const repoId = contextMenu.id;
                      setContextMenu(null);
                      onDeleteProject(repoId);
                    }}
                    type="button"
                    style={{ color: "var(--danger)" }}
                  >
                    {t("action.deleteProject")}
                  </button>
                </div>
              ) : null}
            </>
          ) : null}

          {/* ── History tab ── */}
          {activeTab === "history" ? (
            <>
              <div className="sidebar-panel__header">
                <strong>{t("tab.history")}</strong>
                {historyProjects.length > 0 ? (
                  <span className="sidebar-count-badge">{historyProjects.length}</span>
                ) : null}
              </div>

              <SearchInput
                value={projectFilter}
                onChange={onProjectFilterChange}
                placeholder={t("sidebar.searchProjects")}
              />

              <div className="sidebar-list">
                {historyProjects.length ? (
                  historyProjects.map((project) => {
                    const tone = statusTone(project.status);
                    const stats = project.stats || {};
                    const total = stats.total_steps || 0;
                    const completed = stats.completed_steps || 0;
                    const fillPct = total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : 0;
                    return (
                      <button
                        key={project.archive_id || project.repo_id}
                        className={`sidebar-project sidebar-project--${tone} ${project.archive_id === selectedHistoryId ? "selected" : ""}`}
                        onClick={() => onSelectHistory(project.archive_id)}
                        onContextMenu={(event) => {
                          event.preventDefault();
                          setContextMenu({ kind: "history", id: project.archive_id, x: event.clientX, y: event.clientY });
                        }}
                        title={t("sidebar.projectContextDelete")}
                        type="button"
                      >
                        {fillPct > 0 ? (
                          <span
                            className="sidebar-project__fill"
                            aria-hidden="true"
                            style={{ width: `${fillPct}%` }}
                          />
                        ) : null}
                        <div className="sidebar-project__title">
                          <strong>{project.display_name}</strong>
                          <span className={`status-badge status-badge--${tone}`}>
                            {displayStatus(project.status, language)}
                          </span>
                        </div>
                        {project.detail ? <span style={{ fontSize: "11.5px", color: "var(--text-dim)" }}>{project.detail}</span> : null}
                        {total > 0 ? (
                          <div className="sidebar-project__steps">
                            <div className="sidebar-project__steps-bar">
                              <div className="sidebar-project__steps-fill" style={{ width: `${fillPct}%` }} />
                            </div>
                            <span>{completed}/{total}</span>
                          </div>
                        ) : null}
                      </button>
                    );
                  })
                ) : (
                  <div className="empty-block">
                    <EmptyHistoryIcon />
                    <span>{t("history.noSavedRuns")}</span>
                  </div>
                )}
              </div>

              {contextMenu?.kind === "history" ? (
                <div
                  className="context-menu"
                  style={{ left: `${contextMenu.x}px`, top: `${contextMenu.y}px` }}
                  onPointerDown={(event) => event.stopPropagation()}
                >
                  <button
                    className="context-menu__item"
                    onClick={() => {
                      const archiveId = contextMenu.id;
                      setContextMenu(null);
                      onDeleteHistoryEntry(archiveId);
                    }}
                    type="button"
                    style={{ color: "var(--danger)" }}
                  >
                    {t("action.deleteArchivedRun")}
                  </button>
                </div>
              ) : null}
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
