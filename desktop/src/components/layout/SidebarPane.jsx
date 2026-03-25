import { useEffect, useState } from "react";
import { statusTone } from "../../utils";

function SidebarSectionTabs({ activeTab, onChange }) {
  const tabs = [
    ["projects", "P", "Project"],
    ["workspace", "F", "Explorer"],
    ["plans", "C", "Checkpoints"],
  ];
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

function filterTree(node, query) {
  const normalized = query.trim().toLowerCase();
  const sortedChildren = [...(node.children || [])].sort((left, right) => {
    const leftFolder = left.kind === "dir" || left.kind === "directory" || Boolean((left.children || []).length);
    const rightFolder = right.kind === "dir" || right.kind === "directory" || Boolean((right.children || []).length);
    if (leftFolder !== rightFolder) {
      return leftFolder ? -1 : 1;
    }
    return String(left.label || "").localeCompare(String(right.label || ""));
  });
  if (!normalized) {
    return {
      ...node,
      children: sortedChildren,
    };
  }
  const children = sortedChildren
    .map((child) => filterTree(child, normalized))
    .filter(Boolean);
  const selfMatch = node.label.toLowerCase().includes(normalized) || String(node.path || "").toLowerCase().includes(normalized);
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
        <span className="tree-node__prefix">{isFolder ? (visible ? "-" : "+") : "·"}</span>
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
  const filteredWorkspaceTree = (workspaceTree || []).map((node) => filterTree(node, workspaceFilter)).filter(Boolean);

  return (
    <aside className="ide-sidebar">
      <SidebarSectionTabs activeTab={activeTab} onChange={onChangeTab} />

      <div className="sidebar-panel">
        {activeTab === "projects" ? (
          <>
            <div className="sidebar-panel__header">
              <strong>Project</strong>
              <button className="toolbar-button toolbar-button--ghost" onClick={onNewProject} type="button">
                New
              </button>
            </div>
            <label className="sidebar-search">
              <span>Filter</span>
              <input value={projectFilter} onChange={(event) => onProjectFilterChange(event.target.value)} placeholder="Search projects" />
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
                    <span>{project.status}</span>
                    <span>{project.detail}</span>
                  </button>
                ))
              ) : (
                <div className="empty-block">No managed projects.</div>
              )}
            </div>
            <div className="sidebar-summary">
              <span>Selected summary</span>
              <pre>{selectedProjectSummary || "Pick a project to inspect its managed state."}</pre>
            </div>
            <div className="sidebar-item">
              <div className="sidebar-item__title">
                <strong>Repository Link</strong>
                <span className={`status-badge status-badge--${github?.connected ? "success" : "neutral"}`}>{github?.connected ? "connected" : "local-only"}</span>
              </div>
              <span>{github?.origin_url || "No GitHub origin configured for this project."}</span>
            </div>
            <div className="sidebar-item">
              <strong>Branch</strong>
              <span>{github?.branch || "Unknown"}</span>
            </div>
            <div className="sidebar-item">
              <strong>Repo URL</strong>
              <span>{github?.repo_url || "Unavailable"}</span>
            </div>
          </>
        ) : null}

        {activeTab === "workspace" ? (
          <>
            <div className="sidebar-panel__header">
              <strong>Explorer</strong>
            </div>
            <label className="sidebar-search">
              <span>Filter</span>
              <input value={workspaceFilter} onChange={(event) => onWorkspaceFilterChange(event.target.value)} placeholder="Search files" />
            </label>
            <div className="sidebar-tree">
              {filteredWorkspaceTree.length ? filteredWorkspaceTree.map((node) => <TreeNode key={node.path} node={node} filter={workspaceFilter} />) : <div className="empty-block">No workspace tree yet.</div>}
            </div>
          </>
        ) : null}

        {activeTab === "plans" ? (
          <>
            <div className="sidebar-panel__header">
              <strong>Checkpoints</strong>
            </div>
            <div className="sidebar-group">
              <div className="sidebar-list">
                {(checkpoints?.items || []).length ? (
                  checkpoints.items.map((checkpoint) => (
                    <div className="sidebar-item" key={checkpoint.checkpoint_id}>
                      <div className="sidebar-item__title">
                        <strong>{checkpoint.checkpoint_id}</strong>
                        <span className={`status-badge status-badge--${statusTone(checkpoint.status)}`}>{checkpoint.status}</span>
                      </div>
                      <span>{checkpoint.title}</span>
                      <span>Target block {checkpoint.target_block}</span>
                    </div>
                  ))
                ) : (
                  <div className="empty-block">No checkpoints recorded.</div>
                )}
              </div>
            </div>
          </>
        ) : null}
      </div>
    </aside>
  );
}
