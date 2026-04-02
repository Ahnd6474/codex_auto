import { memo, useEffect, useMemo, useRef, useState } from "react";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import { useI18n } from "../../i18n";
import { useVirtualWindow } from "../../hooks/useVirtualWindow";
import { displayStatus } from "../../locale";
import { deriveExecutionUiState, formatCheckpointDisplayId, isActiveExecutionStatus, isPlanningProgressRunning, statusTone, toolbarProgressCaptionDisplay } from "../../utils";

function RefreshIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M1 4v6h6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M23 20v-6h-6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function RunIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <polygon points="5 3 19 12 5 21 5 3" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" fill="currentColor" fillOpacity="0.18" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <polyline points="20 6 9 17 4 12" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function SettingsIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="3" stroke="currentColor" />
      <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" stroke="currentColor" />
    </svg>
  );
}

function ChevronRight() {
  return (
    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="9 18 15 12 9 6" />
    </svg>
  );
}

function ChevronDown() {
  return (
    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

function PlusSmIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden="true">
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

function FolderIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4 6a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4 7h16" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
      <path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M7 7l1 12a2 2 0 0 0 2 2h4a2 2 0 0 0 2-2l1-12" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M10 11v5M14 11v5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

function ProjectSelector({
  projects,
  selectedProjectId,
  onSelectProject = () => {},
  onNewProject = () => {},
  onDeleteSelectedProject = () => {},
  onDeleteProject = () => {},
  defaultOpen = false,
}) {
  const { language, t } = useI18n();
  const [open, setOpen] = useState(defaultOpen);
  const [filter, setFilter] = useState("");
  const containerRef = useRef(null);
  const inputRef = useRef(null);
  const listRef = useRef(null);
  const debouncedFilter = useDebouncedValue(filter, 140);

  const selectedProject = (projects || []).find((project) => project.repo_id === selectedProjectId);
  const filtered = useMemo(() => {
    const query = String(debouncedFilter || "").trim().toLowerCase();
    if (!query) {
      return projects || [];
    }
    return (projects || []).filter((project) => (project.display_name || "").toLowerCase().includes(query));
  }, [debouncedFilter, projects]);
  const shouldVirtualizeProjects = filtered.length > 40;
  const {
    visibleItems: visibleProjects,
    topSpacerHeight,
    bottomSpacerHeight,
  } = useVirtualWindow(filtered, {
    containerRef: listRef,
    itemHeight: 36,
    overscan: 6,
    enabled: open && shouldVirtualizeProjects,
    defaultViewportHeight: 220,
  });

  useEffect(() => {
    if (!open) {
      setFilter("");
      return;
    }
    const timer = setTimeout(() => inputRef.current?.focus(), 30);
    return () => clearTimeout(timer);
  }, [open]);

  useEffect(() => {
    function onPointerDown(event) {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setOpen(false);
      }
    }

    function onKeyDown(event) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }

    if (open) {
      window.addEventListener("pointerdown", onPointerDown);
      window.addEventListener("keydown", onKeyDown);
    }

    return () => {
      window.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const selectProjectLabel = language === "ko" ? "프로젝트 선택" : "Select project";
  const selectProjectPlaceholder = language === "ko" ? "프로젝트 선택..." : "Select project...";
  const searchProjectsPlaceholder = language === "ko" ? "프로젝트 검색..." : "Search projects...";
  const noProjectsLabel = language === "ko" ? "프로젝트 없음" : "No projects yet";
  const selectedProjectName = selectedProject?.display_name || selectProjectPlaceholder;
  const selectedProjectStatus = String(selectedProject?.status || "").trim();
  const deleteSelectedProjectTitle = isActiveExecutionStatus(selectedProjectStatus)
    ? (language === "ko" ? "실행 중인 프로젝트는 삭제할 수 없습니다." : "Cannot delete a running project.")
    : t("action.deleteProject");

  function handleNewProject() {
    setOpen(false);
    onNewProject();
  }

  function handleSelectProject(repoId) {
    onSelectProject(repoId);
    setOpen(false);
  }

  function handleDeleteProject(event, repoId) {
    event.stopPropagation();
    onDeleteProject(repoId);
  }

  function handleDeleteSelectedProject(event) {
    event.stopPropagation();
    onDeleteSelectedProject();
  }

  return (
    <div className="project-selector project-selector--primary" ref={containerRef}>
      <div className="project-selector__controls">
        <button
          className="project-selector__btn project-selector__btn--primary"
          onClick={() => setOpen((value) => !value)}
          type="button"
          title={selectedProjectName}
        >
          <span className="project-selector__btn-main">
            <FolderIcon />
            <span className="project-selector__btn-copy">
              <span className="project-selector__btn-label">{selectProjectLabel}</span>
              <strong className="project-selector__btn-name">{selectedProjectName}</strong>
            </span>
          </span>
          <span className="project-selector__btn-trailing">
            {open ? <ChevronDown /> : <ChevronRight />}
          </span>
        </button>
        <button
          className="project-selector__btn project-selector__btn--icon project-selector__btn--delete"
          onClick={handleDeleteSelectedProject}
          type="button"
          title={deleteSelectedProjectTitle}
          aria-label={selectedProjectId ? `${selectedProjectName} ${t("action.deleteProject")}` : t("action.deleteProject")}
          disabled={!selectedProjectId || isActiveExecutionStatus(selectedProjectStatus)}
        >
          <TrashIcon />
        </button>
      </div>

      {open ? (
        <div className="project-selector__dropdown">
          <div className="project-selector__search">
            <input
              ref={inputRef}
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              placeholder={searchProjectsPlaceholder}
              type="search"
            />
          </div>
          <button className="project-selector__new" onClick={handleNewProject} type="button">
            <PlusSmIcon /> {t("action.new")}
          </button>
          <div className="project-selector__list" ref={listRef}>
            {filtered.length ? (
              <>
                {topSpacerHeight > 0 ? <div aria-hidden="true" style={{ height: `${topSpacerHeight}px` }} /> : null}
                {(shouldVirtualizeProjects ? visibleProjects : filtered).map((project) => (
              <div
                key={project.repo_id}
                className={`project-selector__item${project.repo_id === selectedProjectId ? " active" : ""}`}
              >
                <button
                  className="project-selector__item-main"
                  onClick={() => handleSelectProject(project.repo_id)}
                  type="button"
                >
                  <span className="project-selector__item-name">{project.display_name}</span>
                  <span className={`chip-dot chip-dot--${statusTone(project.status)}`} />
                </button>
                <button
                  className="project-selector__item-delete"
                  onClick={(event) => handleDeleteProject(event, project.repo_id)}
                  type="button"
                  title={
                    isActiveExecutionStatus(project.status)
                      ? (language === "ko" ? "실행 중인 프로젝트는 삭제할 수 없습니다." : "Cannot delete a running project.")
                      : t("action.deleteProject")
                  }
                  aria-label={`${project.display_name || project.repo_id} ${t("action.deleteProject")}`}
                  disabled={isActiveExecutionStatus(project.status)}
                >
                  <TrashIcon />
                </button>
              </div>
                ))}
                {bottomSpacerHeight > 0 ? <div aria-hidden="true" style={{ height: `${bottomSpacerHeight}px` }} /> : null}
              </>
            ) : (
              <div className="project-selector__empty">{noProjectsLabel}</div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}

export const __toolbarTestables = {
  ProjectSelector,
};

const MemoProjectSelector = memo(ProjectSelector, (prevProps, nextProps) => {
  if (prevProps.selectedProjectId !== nextProps.selectedProjectId) {
    return false;
  }
  const prevProjects = Array.isArray(prevProps.projects) ? prevProps.projects : [];
  const nextProjects = Array.isArray(nextProps.projects) ? nextProps.projects : [];
  if (prevProjects.length !== nextProjects.length) {
    return false;
  }
  for (let index = 0; index < prevProjects.length; index += 1) {
    const prevProject = prevProjects[index];
    const nextProject = nextProjects[index];
    if (
      prevProject?.repo_id !== nextProject?.repo_id
      || prevProject?.display_name !== nextProject?.display_name
      || prevProject?.status !== nextProject?.status
    ) {
      return false;
    }
  }
  return true;
});

function sameToolbarProjects(previousProjects = [], nextProjects = []) {
  if (previousProjects === nextProjects) {
    return true;
  }
  if (!Array.isArray(previousProjects) || !Array.isArray(nextProjects) || previousProjects.length !== nextProjects.length) {
    return false;
  }
  for (let index = 0; index < previousProjects.length; index += 1) {
    const previousProject = previousProjects[index];
    const nextProject = nextProjects[index];
    if (
      previousProject?.repo_id !== nextProject?.repo_id
      || previousProject?.display_name !== nextProject?.display_name
      || previousProject?.status !== nextProject?.status
    ) {
      return false;
    }
  }
  return true;
}

function planToolbarSignature(plan = null) {
  const normalizedPlan = plan && typeof plan === "object" ? plan : {};
  const steps = Array.isArray(normalizedPlan.steps) ? normalizedPlan.steps : [];
  return [
    String(normalizedPlan.closeout_status || ""),
    steps.map((step) => {
      const dependencies = Array.isArray(step?.depends_on) ? step.depends_on.join(",") : "";
      return [step?.step_id || "", step?.status || "", dependencies].join(":");
    }).join("|"),
  ].join("|");
}

function samePlanningProgress(previousProgress = null, nextProgress = null) {
  if (previousProgress === nextProgress) {
    return true;
  }
  return (
    String(previousProgress?.status || previousProgress?.planningStatus || "") === String(nextProgress?.status || nextProgress?.planningStatus || "")
    && String(previousProgress?.current_stage || previousProgress?.currentStage || "") === String(nextProgress?.current_stage || nextProgress?.currentStage || "")
    && Number(previousProgress?.current_stage_index ?? previousProgress?.currentStageIndex ?? 0) === Number(nextProgress?.current_stage_index ?? nextProgress?.currentStageIndex ?? 0)
    && Number(previousProgress?.total_stages ?? previousProgress?.totalStages ?? 0) === Number(nextProgress?.total_stages ?? nextProgress?.totalStages ?? 0)
  );
}

function RemoteLinkIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function EditorIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" strokeWidth="1.7" />
      <path d="M9 9l3 3-3 3M13 15h3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function GithubIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export const IdeToolbar = memo(function IdeToolbar({
  projects,
  selectedProjectId,
  onSelectProject,
  onNewProject,
  onDeleteSelectedProject,
  onDeleteProject,
  projectDetail,
  planDraft,
  pendingCheckpoint,
  busy,
  activeJob,
  runActionDisabled,
  runActionRunning,
  activeCenterTab,
  projectPath,
  githubUrl,
  shareUrl,
  shareBusy,
  onRefresh,
  onOpenSettings,
  onRunPlan,
  onApproveCheckpoint,
  onSmartShareLink,
  onOpenFolder,
  onOpenVsCode,
  onOpenGithub,
}) {
  const executionState = useMemo(
    () => deriveExecutionUiState(projectDetail, planDraft, activeJob),
    [activeJob, planDraft, projectDetail],
  );
  const executionJob = executionState.executionJob;
  const livePlan = executionState.livePlan;
  const { language, t } = useI18n();
  const statusLabel = displayStatus(executionState.displayStatusValue, language);

  const planStatusLabel = toolbarProgressCaptionDisplay(livePlan, language, {
    activeJob: executionJob,
    planningProgress: projectDetail?.planning_progress,
  });

  const tone = statusTone(executionState.displayStatusValue);
  const resolvedRunActionRunning = typeof runActionRunning === "boolean"
    ? runActionRunning
    : isActiveExecutionStatus(executionState.displayStatusValue);
  const resolvedRunActionDisabled = typeof runActionDisabled === "boolean"
    ? runActionDisabled
    :
    busy
    || !executionState.consistent
    || resolvedRunActionRunning
    || isPlanningProgressRunning(projectDetail?.planning_progress)
    || executionState.checkpointFamily === "checkpoint";
  const runActionLabel = resolvedRunActionRunning ? displayStatus("running", language) : t("action.run");
  const repoPath = String(projectPath || "").trim();
  const remoteUrl = String(githubUrl || "").trim();

  return (
    <header className="ide-toolbar">
      <div className="ide-toolbar__group ide-toolbar__group--utility">
        <button
          className="toolbar-btn toolbar-btn--icon"
          onClick={onRefresh}
          title={t("action.refresh")}
          type="button"
          aria-label={t("action.refresh")}
        >
          <RefreshIcon />
        </button>
      </div>

      <MemoProjectSelector
        projects={projects}
        selectedProjectId={selectedProjectId}
        onSelectProject={onSelectProject}
        onNewProject={onNewProject}
        onDeleteSelectedProject={onDeleteSelectedProject}
        onDeleteProject={onDeleteProject}
      />

      <nav className="ide-toolbar__breadcrumb" aria-label="Navigation">
        <span className={`breadcrumb-segment breadcrumb-segment--${tone}`}>
          <span className={`chip-dot chip-dot--${tone}`} />
          {statusLabel}
        </span>
        {planStatusLabel ? (
          <>
            <ChevronRight />
            <span className="breadcrumb-segment breadcrumb-segment--dim">{planStatusLabel}</span>
          </>
        ) : null}
        {pendingCheckpoint ? (
          <>
            <ChevronRight />
            <span className="breadcrumb-segment breadcrumb-segment--warning">
              <span className="chip-dot chip-dot--warning" />
              {formatCheckpointDisplayId(pendingCheckpoint.checkpoint_id) || t("dashboard.checkpointPending")}
            </span>
          </>
        ) : null}
      </nav>

      <div className="ide-toolbar__group ide-toolbar__group--actions">

        <button
          className={`toolbar-btn ${activeCenterTab === "app-settings" ? "toolbar-btn--active" : ""}`}
          onClick={onOpenSettings}
          title={t("toolbar.programSettings")}
          type="button"
          aria-label={t("toolbar.programSettings")}
        >
          <SettingsIcon />
          <span>{t("toolbar.programSettings")}</span>
        </button>

        <div className="toolbar-divider" />

        <button
          className="toolbar-btn toolbar-btn--icon"
          onClick={onOpenFolder}
          type="button"
          title={language === "ko" ? "폴더 열기" : "Open folder"}
          disabled={!repoPath}
        >
          <FolderIcon />
        </button>
        <button
          className="toolbar-btn toolbar-btn--icon"
          onClick={onOpenVsCode}
          type="button"
          title={language === "ko" ? "외부 편집기에서 열기" : "Open in external editor"}
          disabled={!repoPath}
        >
          <EditorIcon />
        </button>
        <button
          className="toolbar-btn toolbar-btn--icon"
          onClick={onOpenGithub}
          type="button"
          title="Open on GitHub"
          disabled={!remoteUrl}
        >
          <GithubIcon />
        </button>

        <div className="toolbar-divider" />

        <button
          className={`toolbar-btn toolbar-btn--icon toolbar-btn--remote${shareUrl ? " toolbar-btn--active" : ""}`}
          onClick={onSmartShareLink}
          type="button"
          disabled={shareBusy}
          title={shareUrl ? `Copy share link: ${shareUrl}` : "Generate Remote Control link"}
          aria-label={shareUrl ? "Copy share link" : "Remote Control"}
        >
          <RemoteLinkIcon />
        </button>

        <div className="toolbar-divider" />
        <button
          className="toolbar-btn toolbar-btn--accent"
          onClick={onRunPlan}
          type="button"
          disabled={resolvedRunActionDisabled}
          title={runActionLabel}
        >
          <RunIcon />
          <span>{runActionLabel}</span>
        </button>

        {pendingCheckpoint ? (
          <button
            className="toolbar-btn toolbar-btn--accent"
            onClick={onApproveCheckpoint}
            type="button"
            disabled={busy}
            title={t("action.approveCheckpoint")}
          >
            <CheckIcon />
            <span>{t("action.approveCheckpoint")}</span>
          </button>
        ) : null}
      </div>
    </header>
  );
}, (previousProps, nextProps) => {
  if (!sameToolbarProjects(previousProps.projects, nextProps.projects)) {
    return false;
  }
  return (
    previousProps.selectedProjectId === nextProps.selectedProjectId
    && previousProps.pendingCheckpoint?.checkpoint_id === nextProps.pendingCheckpoint?.checkpoint_id
    && previousProps.busy === nextProps.busy
    && previousProps.activeCenterTab === nextProps.activeCenterTab
    && previousProps.projectPath === nextProps.projectPath
    && previousProps.githubUrl === nextProps.githubUrl
    && previousProps.shareUrl === nextProps.shareUrl
    && previousProps.shareBusy === nextProps.shareBusy
    && previousProps.activeJob?.id === nextProps.activeJob?.id
    && previousProps.activeJob?.status === nextProps.activeJob?.status
    && previousProps.activeJob?.command === nextProps.activeJob?.command
    && previousProps.projectDetail?.project?.current_status === nextProps.projectDetail?.project?.current_status
    && samePlanningProgress(previousProps.projectDetail?.planning_progress, nextProps.projectDetail?.planning_progress)
    && planToolbarSignature(previousProps.planDraft) === planToolbarSignature(nextProps.planDraft)
    && planToolbarSignature(previousProps.projectDetail?.plan) === planToolbarSignature(nextProps.projectDetail?.plan)
    && previousProps.onRefresh === nextProps.onRefresh
    && previousProps.onOpenSettings === nextProps.onOpenSettings
    && previousProps.onGeneratePlan === nextProps.onGeneratePlan
    && previousProps.onRunPlan === nextProps.onRunPlan
    && previousProps.onApproveCheckpoint === nextProps.onApproveCheckpoint
    && previousProps.onSmartShareLink === nextProps.onSmartShareLink
    && previousProps.onOpenFolder === nextProps.onOpenFolder
    && previousProps.onOpenVsCode === nextProps.onOpenVsCode
    && previousProps.onOpenGithub === nextProps.onOpenGithub
    && previousProps.onSelectProject === nextProps.onSelectProject
    && previousProps.onNewProject === nextProps.onNewProject
    && previousProps.onDeleteSelectedProject === nextProps.onDeleteSelectedProject
    && previousProps.onDeleteProject === nextProps.onDeleteProject
  );
});
