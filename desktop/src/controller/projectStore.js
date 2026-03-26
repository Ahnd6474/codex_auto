import { defaultShareSettings, emptyPlanDraft, shareSettingsFromDetail } from "../controllerHelpers";
import {
  applyProgramSettingsToForm,
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
} from "../utils";

export function applyListingState({ listing, runningJob = null, setProjects, setWorkspaceStats }) {
  const nextProjects = sanitizeProjectListForJobState(listing?.projects || [], runningJob);
  setProjects(nextProjects);
  setWorkspaceStats(workspaceStatsFromProjects(nextProjects));
  return nextProjects;
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
      return applyProgramSettingsToForm(projectFormFromDetail(normalizedDetail, state.defaultRuntime), state.storedProgramSettings);
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
