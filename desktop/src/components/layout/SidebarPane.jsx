import { useEffect, useMemo, useState } from "react";
import { useI18n } from "../../i18n";
import { displayStatus } from "../../locale";
import { statusTone } from "../../utils";

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
  selectedProjectSummary,
  projectFilter,
  workspaceFilter,
  onProjectFilterChange,
  onWorkspaceFilterChange,
  onSelectProject,
  onNewProject,
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
    ["projects", "P", t("common.project")],
    ["workspace", "F", t("sidebar.explorer")],
    ["plans", "C", t("sidebar.checkpoints")],
  ];

  return (
    <aside className="ide-sidebar">
      <SidebarSectionTabs activeTab={activeTab} onChange={onChangeTab} tabs={tabs} />

      <div className="sidebar-panel">
        {activeTab === "projects" ? (
          <>
            <div className="sidebar-panel__header">
              <strong>{t("common.project")}</strong>
              <button className="toolbar-button toolbar-button--ghost" onClick={onNewProject} type="button">
                {t("action.new")}
              </button>
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
                    className={`sidebar-project ${project.repo_id === selectedProjectId ? "selected" : ""}`}
                    onClick={() => onSelectProject(project.repo_id)}
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
            <div className="sidebar-summary">
              <span>{t("sidebar.selectedSummary")}</span>
              <pre>{selectedProjectSummary || t("sidebar.noProjectSummary")}</pre>
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
