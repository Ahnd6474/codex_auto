import {
  selectProjectDetail,
  selectProjectExecution,
  selectProjectListing,
  selectProjectStateTree,
  selectProjectUi,
  selectProjectWorkspaceStats,
} from "./projectStateSelectors.js";

export function reduceProjectListingState(input = {}) {
  const tree = selectProjectStateTree(input);
  return {
    tree,
    projects: selectProjectListing(tree),
    workspaceStats: selectProjectWorkspaceStats(tree),
  };
}

export function reduceProjectDetailState(input = {}) {
  const tree = selectProjectStateTree(input);
  return {
    tree,
    detail: selectProjectDetail(tree),
  };
}

export function reduceSelectedProjectState(input = {}) {
  const tree = selectProjectStateTree(input);
  const execution = selectProjectExecution(tree);
  const ui = selectProjectUi(tree);
  return {
    tree,
    projectJob: execution.selectedJob,
    activeJob: execution.activeJob,
    chatJob: execution.chatJob,
    stoppableJob: execution.stoppableJob,
    queuedJobs: execution.queuedJobs,
    busy: ui.busy,
    canRequestStop: ui.canRequestStop,
    canCancelReservation: ui.canCancelReservation,
  };
}
