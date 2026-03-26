import { useEffect, useMemo, useState } from "react";
import { useI18n } from "../../i18n";
import { displayStatus } from "../../locale";
import { statusTone } from "../../utils";

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
        >
          {icon}
        </button>
      ))}
    </div>
  );
}

function filterTree(node, normalizedQuery) {
  const sortedChildren = [...(node.children || [])].sort((left, right) => {
    const leftFolder = left.kind === "dir" || left.kind === "directory" || Boolean((left.children || []).length);
    const rightFolder = right.kind === "dir" || right.kind === "directory" || Boolean((right.children || []).length);
    if (leftFolder !== rightFolder) {
      return leftFolder ? -1 : 1;
    }
    return String(left.label || "").localeCompare(String(right.label || ""));
  });
  if (!normalizedQuery) {
    return {
      ...node,
      children: sortedChildren,
    };
  }
  const children = sortedChildren
    .map((child) => filterTree(child, normalizedQuery))
    .filter(Boolean);
  const selfMatch =
    node.label.toLowerCase().includes(normalizedQuery) || String(node.path || "").toLowerCase().includes(normalizedQuery);
  if (selfMatch || children.length) {
    return {
      ...node,
      children,
    };
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
        <span className="tree-node__prefix">{isFolder ? (visible ? "-" : "+") : "."}</span>
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

export function SidebarPane({
  activeTab,
  onChangeTab,
  projects,
  selectedProjectId,
  loadingProjectId,
  projectFilter,
  workspaceFilter,
  onProjectFilterChange,
  onWorkspaceFilterChange,
  onSelectProject,
  onNewProject,
  onDeleteProject,
  onDeleteAllProjects,
  workspaceTree,
  checkpoints,
  github,
}) {
  const { language, t } = useI18n();
  const filteredWorkspaceTree = useMemo(() => {
    const normalizedQuery = workspaceFilter.trim().toLowerCase();
    return (workspaceTree || []).map((node) => filterTree(node, normalizedQuery)).filter(Boolean);
  }, [workspaceFilter, workspaceTree]);
  const tabs = [
    ["projects", <SidebarProjectsIcon key="projects-icon" />, t("common.project")],
    ["workspace", <SidebarExplorerIcon key="workspace-icon" />, t("sidebar.explorer")],
    ["plans", <SidebarCheckpointsIcon key="plans-icon" />, t("sidebar.checkpoints")],
  ];

  return (
    <aside className="ide-sidebar">
      <SidebarSectionTabs activeTab={activeTab} onChange={onChangeTab} tabs={tabs} />

      <div className="sidebar-panel">
        {activeTab === "projects" ? (
          <>
            <div className="sidebar-panel__header">
              <strong>{t("common.project")}</strong>
              <div className="action-row">
                <button className="toolbar-button toolbar-button--ghost" onClick={onDeleteAllProjects} type="button" disabled={!projects.length}>
                  {t("action.deleteAll")}
                </button>
                <button className="toolbar-button toolbar-button--ghost" onClick={onNewProject} type="button">
                  {t("action.new")}
                </button>
              </div>
            </div>
            <label className="sidebar-search">
              <span>{t("common.filter")}</span>
              <input value={projectFilter} onChange={(event) => onProjectFilterChange(event.target.value)} placeholder={t("sidebar.searchProjects")} />
            </label>
            <div className="sidebar-list">
              {projects.length ? (
                projects.map((project) => (
                  <button
                    key={project.repo_id}
                    className={`sidebar-project ${project.repo_id === selectedProjectId ? "selected" : ""} ${
                      project.repo_id === loadingProjectId ? "loading" : ""
                    }`}
                    onClick={() => onSelectProject(project.repo_id)}
                    onContextMenu={(event) => {
                      event.preventDefault();
                      onDeleteProject(project.repo_id);
                    }}
                    title={t("sidebar.projectContextDelete")}
                    type="button"
                  >
                    <div className="sidebar-project__title">
                      <strong>{project.display_name}</strong>
                      <span className={`status-dot status-dot--${statusTone(project.status)}`} />
                    </div>
                    <span>{displayStatus(project.status, language)}</span>
                    <span>{project.detail}</span>
                  </button>
                ))
              ) : (
                <div className="empty-block">{t("sidebar.emptyProjects")}</div>
              )}
            </div>
            <div className="sidebar-item">
              <div className="sidebar-item__title">
                <strong>{t("sidebar.repositoryLink")}</strong>
                <span className={`status-badge status-badge--${github?.connected ? "success" : "neutral"}`}>{github?.connected ? t("common.connected") : t("common.localOnly")}</span>
              </div>
              <span>{github?.origin_url || t("sidebar.noGithubOrigin")}</span>
            </div>
            <div className="sidebar-item">
              <strong>{t("common.branch")}</strong>
              <span>{github?.branch || t("common.unknown")}</span>
            </div>
            <div className="sidebar-item">
              <strong>{t("common.repoUrl")}</strong>
              <span>{github?.repo_url || t("common.unavailable")}</span>
            </div>
          </>
        ) : null}

        {activeTab === "workspace" ? (
          <>
            <div className="sidebar-panel__header">
              <strong>{t("sidebar.explorer")}</strong>
            </div>
            <label className="sidebar-search">
              <span>{t("common.filter")}</span>
              <input value={workspaceFilter} onChange={(event) => onWorkspaceFilterChange(event.target.value)} placeholder={t("sidebar.searchFiles")} />
            </label>
            <div className="sidebar-tree">
              {filteredWorkspaceTree.length ? filteredWorkspaceTree.map((node) => <TreeNode key={node.path} node={node} filter={workspaceFilter} />) : <div className="empty-block">{t("sidebar.emptyWorkspace")}</div>}
            </div>
          </>
        ) : null}

        {activeTab === "plans" ? (
          <>
            <div className="sidebar-panel__header">
              <strong>{t("sidebar.checkpoints")}</strong>
            </div>
            <div className="sidebar-group">
              <div className="sidebar-list">
                {(checkpoints?.items || []).length ? (
                  checkpoints.items.map((checkpoint) => (
                    <div className="sidebar-item" key={checkpoint.checkpoint_id}>
                      <div className="sidebar-item__title">
                        <strong>{checkpoint.checkpoint_id}</strong>
                        <span className={`status-badge status-badge--${statusTone(checkpoint.status)}`}>{displayStatus(checkpoint.status, language)}</span>
                      </div>
                      <span>{checkpoint.title}</span>
                      <span>{t("sidebar.targetBlock", { block: checkpoint.target_block })}</span>
                    </div>
                  ))
                ) : (
                  <div className="empty-block">{t("sidebar.noRecordedCheckpoints")}</div>
                )}
              </div>
            </div>
          </>
        ) : null}
      </div>
    </aside>
  );
}
