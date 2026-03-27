import { defaultShareSettings, emptyPlanDraft, shareSettingsFromDetail } from "../controllerHelpers.js";
import {
  blankProjectForm,
  cloneValue,
  detailApplySignature,
  firstSelectableStepId,
  mergeProjectDetailCodexStatus,
  projectFormFromDetail,
  sanitizeProjectDetailForJobState,
  sanitizeProjectListForJobState,
  shouldKeepUnsavedPlan,
  workspaceStatsFromProjects,
} from "../utils.js";

export function applyListingState({ listing, runningJob = null, setProjects, setWorkspaceStats }) {
  const nextProjects = sanitizeProjectListForJobState(listing?.projects || [], runningJob);
  setProjects(nextProjects);
  setWorkspaceStats(workspaceStatsFromProjects(nextProjects));
  return nextProjects;
}

function projectListItemFromDetail(detail, fallbackProject = null) {
  const project = detail?.project || {};
  const branch = project.branch || fallbackProject?.branch || "";
  return {
    ...fallbackProject,
    repo_id: project.repo_id || fallbackProject?.repo_id || "",
    slug: project.slug || fallbackProject?.slug || "",
    display_name: project.display_name || project.slug || fallbackProject?.display_name || "",
    repo_path: project.repo_path || fallbackProject?.repo_path || "",
    origin_url: project.origin_url || fallbackProject?.origin_url || "",
    branch,
    status: project.current_status || fallbackProject?.status || "",
    detail: project.origin_url || `Branch ${branch}`,
    created_at: project.created_at || fallbackProject?.created_at || "",
    last_run_at: project.last_run_at || fallbackProject?.last_run_at || "",
    summary: detail?.summary || fallbackProject?.summary || "",
    progress: detail?.progress || fallbackProject?.progress || "",
    stats: cloneValue(detail?.stats || fallbackProject?.stats || {}),
    closeout_status: detail?.plan?.closeout_status || fallbackProject?.closeout_status || "",
  };
}

export function applyProjectDetailListingState({
  projects,
  detail,
  runningJob = null,
  setProjects,
  setWorkspaceStats,
}) {
  const repoId = String(detail?.project?.repo_id || "").trim();
  if (!repoId) {
    return null;
  }
  let matched = false;
  const nextProjects = (projects || []).map((project) => {
    if (String(project?.repo_id || "").trim() !== repoId) {
      return project;
    }
    matched = true;
    return projectListItemFromDetail(detail, project);
  });
  const mergedProjects = matched ? nextProjects : [projectListItemFromDetail(detail), ...(projects || [])];
  const sanitizedProjects = sanitizeProjectListForJobState(mergedProjects, runningJob);
  setProjects(sanitizedProjects);
  setWorkspaceStats(workspaceStatsFromProjects(sanitizedProjects));
  return sanitizedProjects;
}

export function applyActiveJobState({
  jobSnapshot,
  setActiveJobId,
  setActiveJob,
  activeJobRef,
}) {
  const nextActiveJob = jobSnapshot?.activeJob || null;
  const nextActiveJobId = jobSnapshot?.activeJobId || "";
  setActiveJobId(nextActiveJobId);
  setActiveJob(nextActiveJob);
  activeJobRef.current = nextActiveJob;
  return jobSnapshot?.runningJob || null;
}

export function applyProjectDetailState({
  detail,
  options = {},
  refs,
  state,
  setters,
}) {
  const mergedDetail = mergeProjectDetailCodexStatus(detail, state.projectDetail?.codex_status, state.modelCatalog);
  const normalizedDetail = sanitizeProjectDetailForJobState(mergedDetail, options.runningJob ?? state.activeJob);
  const applySignature = detailApplySignature(normalizedDetail, options.runningJob ?? state.activeJob);
  if (
    !options.force &&
    applySignature &&
    refs.lastAppliedDetailSignatureRef.current === applySignature &&
    normalizedDetail?.project?.repo_id === state.projectDetail?.project?.repo_id
  ) {
    setters.setLoadingProjectId("");
    return false;
  }
  const preserveDirtyPlan = shouldKeepUnsavedPlan(
    state.projectDetail?.project?.repo_id,
    normalizedDetail?.project?.repo_id,
    options.preserveDirtyPlan ?? state.planDirty,
  );
  refs.lastAppliedDetailSignatureRef.current = applySignature;
  setters.transition(() => {
    setters.setProjectDetail(normalizedDetail);
    setters.setModelCatalog(normalizedDetail?.codex_status?.model_catalog || state.modelCatalog);
    setters.setShareSettings(shareSettingsFromDetail(normalizedDetail));
    setters.setLoadingProjectId("");
    setters.setProjectForm((current) => {
      if (current.project_dir && preserveDirtyPlan) {
        return current;
      }
      return projectFormFromDetail(normalizedDetail, state.defaultRuntime);
    });
    if (!preserveDirtyPlan) {
      setters.setPlanDraft(cloneValue(normalizedDetail.plan));
      if (options.preserveSelectedStep) {
        setters.setSelectedStepId((current) => current || firstSelectableStepId(normalizedDetail.plan));
      } else {
        setters.setSelectedStepId(firstSelectableStepId(normalizedDetail.plan));
      }
      setters.setPlanDirty(false);
    }
  });
  return true;
}

export function clearSelectedProjectState({
  defaultRuntime,
  refs,
  setters,
}) {
  refs.lastAppliedDetailSignatureRef.current = "";
  setters.setProjectDetail(null);
  setters.setSelectedProjectId("");
  setters.setSelectedStepId("");
  setters.setPlanDirty(false);
  setters.setLoadingProjectId("");
  setters.setProjectForm(blankProjectForm(defaultRuntime));
  setters.setPlanDraft(emptyPlanDraft());
  setters.setShareSettings(defaultShareSettings());
}
