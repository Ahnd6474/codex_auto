import { useDeferredValue, useEffect, useMemo, useRef } from "react";
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

/* ── Main SidebarPane ── */
export function SidebarPane({
  activeTab,
  onChangeTab,
  workspaceFilter,
  onWorkspaceFilterChange,
  workspaceTree,
  checkpoints,
}) {
  const { language, t } = useI18n();
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

  const tabs = [
    ["workspace", <SidebarExplorerIcon key="workspace-icon" />, t("sidebar.explorer")],
    ["plans", <SidebarCheckpointsIcon key="plans-icon" />, t("sidebar.checkpoints")],
  ];

  return (
    <aside className="ide-sidebar">
      <SidebarSectionTabs activeTab={activeTab} onChange={onChangeTab} tabs={tabs} />

      {activeTab ? (
        <div className="sidebar-panel">

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
