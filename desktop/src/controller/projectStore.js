import { defaultShareSettings, emptyPlanDraft, shareSettingsFromDetail } from "../controllerHelpers.js";
import { detailApplySignature } from "../domain/projectExecution.js";
import {
  blankProjectForm,
  cloneValue,
  CLOSEOUT_STEP_ID,
  mergeProjectDetailCodexStatus,
  mergeModelCatalogs,
  normalizedLocalModelProvider,
  normalizedModelProvider,
  projectFormFromDetail,
  visibleExecutionJob,
  shouldKeepUnsavedPlan,
} from "../utils.js";
import { reduceProjectDetailState, reduceProjectListingState } from "./projectStateReducer.js";

const PROJECT_DETAIL_SECTION_KEYS = ["reports", "workspace", "checkpoints", "history", "config", "chat"];
const PROJECT_RUNTIME_OVERRIDE_KEYS = [
  "model_provider",
  "local_model_provider",
  "chat_model_provider",
  "chat_local_model_provider",
  "provider_base_url",
  "provider_api_key_env",
  "billing_mode",
  "ensemble_openai_model",
  "ensemble_gemini_model",
  "ensemble_claude_model",
  "model",
  "execution_model",
  "chat_model",
  "chat_effort",
  "model_preset",
  "model_selection_mode",
  "model_slug_input",
  "codex_path",
  "effort",
  "planning_effort",
];

function enforceProgramModelDefaults(form = null, defaultRuntime = null) {
  const nextForm = form && typeof form === "object" ? cloneValue(form) : {};
  const nextRuntime = nextForm.runtime && typeof nextForm.runtime === "object" ? cloneValue(nextForm.runtime) : {};
  if (!String(nextRuntime.execution_model || "").trim()) {
    nextRuntime.execution_model = String(nextRuntime.model || defaultRuntime?.model || "").trim();
  }
  if (String(nextRuntime.execution_model || "").trim()) {
    nextRuntime.model = String(nextRuntime.execution_model || "").trim();
    nextRuntime.model_slug_input = String(nextRuntime.execution_model || "").trim();
  }
  return {
    ...nextForm,
    runtime: nextRuntime,
  };
}

function hasOwnValue(value, key) {
  return Boolean(value) && Object.prototype.hasOwnProperty.call(value, key);
}

function sameProjectDetail(left, right) {
  const leftRepoId = String(left?.project?.repo_id || "").trim();
  const rightRepoId = String(right?.project?.repo_id || "").trim();
  return Boolean(leftRepoId) && leftRepoId === rightRepoId;
}

function projectEventMatchesDetail(detail = null, project = null) {
  const detailRepoId = String(detail?.project?.repo_id || "").trim();
  const eventRepoId = String(project?.repo_id || "").trim();
  if (detailRepoId && eventRepoId) {
    return detailRepoId === eventRepoId;
  }
  const detailProjectDir = String(detail?.project?.repo_path || "").trim();
  const eventProjectDir = String(project?.project_dir || "").trim();
  return Boolean(detailProjectDir) && Boolean(eventProjectDir) && detailProjectDir === eventProjectDir;
}

function projectListKey(item = null) {
  if (!item || typeof item !== "object") {
    return "";
  }
  return String(
    item.archive_id
    || item.repo_id
    || item.repo_path
    || item.project_dir
    || item.slug
    || "",
  ).trim();
}

function shallowObjectEqual(left = null, right = null) {
  if (left === right) {
    return true;
  }
  if (!left || !right || typeof left !== "object" || typeof right !== "object") {
    return false;
  }
  const leftKeys = Object.keys(left);
  const rightKeys = Object.keys(right);
  if (leftKeys.length !== rightKeys.length) {
    return false;
  }
  return leftKeys.every((key) => Object.is(left[key], right[key]));
}

function shallowObjectEqualExcept(left = null, right = null, excludedKeys = []) {
  if (left === right) {
    return true;
  }
  if (!left || !right || typeof left !== "object" || typeof right !== "object") {
    return false;
  }
  const excluded = new Set(Array.isArray(excludedKeys) ? excludedKeys : []);
  const leftKeys = Object.keys(left).filter((key) => !excluded.has(key));
  const rightKeys = Object.keys(right).filter((key) => !excluded.has(key));
  if (leftKeys.length !== rightKeys.length) {
    return false;
  }
  return leftKeys.every((key) => Object.is(left[key], right[key]));
}

function workspaceTreeNodeKey(node = null, parentKey = "", index = 0) {
  const path = String(node?.path || "").trim();
  if (path) {
    return `path:${path}`;
  }
  const explicitId = String(node?.id || node?.key || "").trim();
  if (explicitId) {
    return `id:${explicitId}`;
  }
  const label = String(node?.label || "").trim() || "node";
  const kind = String(node?.kind || "").trim() || "node";
  return `${parentKey || "root"}::${kind}::${label}::${index}`;
}

function workspaceTreeNodesEqual(leftNodes = [], rightNodes = []) {
  if (leftNodes === rightNodes) {
    return true;
  }
  if (!Array.isArray(leftNodes) || !Array.isArray(rightNodes) || leftNodes.length !== rightNodes.length) {
    return false;
  }
  return leftNodes.every((leftNode, index) => {
    const rightNode = rightNodes[index];
    if (!leftNode || !rightNode) {
      return leftNode === rightNode;
    }
    return (
      leftNode.label === rightNode.label
      && leftNode.path === rightNode.path
      && leftNode.kind === rightNode.kind
      && workspaceTreeNodesEqual(leftNode.children || [], rightNode.children || [])
    );
  });
}

function mergeWorkspaceTreeNodes(previousNodes = [], nextNodes = [], parentKey = "") {
  const prior = Array.isArray(previousNodes) ? previousNodes : [];
  const incoming = Array.isArray(nextNodes) ? nextNodes : [];
  if (!incoming.length) {
    return incoming.length === prior.length ? prior : [];
  }
  if (prior.length && workspaceTreeNodesEqual(incoming, prior)) {
    return prior;
  }

  const previousByKey = new Map();
  prior.forEach((node, index) => {
    previousByKey.set(workspaceTreeNodeKey(node, parentKey, index), node);
  });

  let changed = prior.length !== incoming.length;
  const merged = incoming.map((nextNode, index) => {
    if (!nextNode || typeof nextNode !== "object") {
      if (!Object.is(prior[index], nextNode)) {
        changed = true;
      }
      return nextNode;
    }

    const nodeKey = workspaceTreeNodeKey(nextNode, parentKey, index);
    const previousNode = previousByKey.get(nodeKey) || null;
    const nextChildren = Array.isArray(nextNode.children)
      ? mergeWorkspaceTreeNodes(Array.isArray(previousNode?.children) ? previousNode.children : [], nextNode.children, nodeKey)
      : (Array.isArray(previousNode?.children) ? previousNode.children : nextNode.children);
    const candidate = Array.isArray(nextChildren)
      ? (
        nextChildren === nextNode.children
          ? nextNode
          : {
              ...nextNode,
              children: nextChildren,
            }
      )
      : nextNode;

    if (
      previousNode
      && shallowObjectEqualExcept(previousNode, candidate, ["children"])
      && workspaceTreeNodesEqual(Array.isArray(previousNode.children) ? previousNode.children : [], Array.isArray(candidate.children) ? candidate.children : [])
    ) {
      if (prior[index] !== previousNode) {
        changed = true;
      }
      return previousNode;
    }

    if (prior[index] !== candidate) {
      changed = true;
    }
    return candidate;
  });

  return changed ? merged : prior;
}

function resolveWorkspaceTree(nextWorkspaceTree, previousWorkspaceTree = []) {
  const previousTree = Array.isArray(previousWorkspaceTree) ? previousWorkspaceTree : [];
  const incomingTree = Array.isArray(nextWorkspaceTree) ? nextWorkspaceTree : [];
  if (!incomingTree.length) {
    return previousTree;
  }
  if (previousTree.length && workspaceTreeNodesEqual(incomingTree, previousTree)) {
    return previousTree;
  }
  return mergeWorkspaceTreeNodes(previousTree, incomingTree);
}

function mergeLoadedSections(currentSections = null, fallbackSections = null, detailLevel = "") {
  const nextSections = {
    ...(fallbackSections && typeof fallbackSections === "object" ? fallbackSections : {}),
    ...(currentSections && typeof currentSections === "object" ? currentSections : {}),
  };
  if (String(detailLevel || "").trim().toLowerCase() === "full") {
    PROJECT_DETAIL_SECTION_KEYS.forEach((key) => {
      nextSections[key] = true;
    });
  }
  return nextSections;
}

function preserveProjectIdentityForm(currentForm = null, nextForm = null) {
  const current = currentForm && typeof currentForm === "object" ? currentForm : {};
  const next = nextForm && typeof nextForm === "object" ? nextForm : {};
  if (String(next.project_dir || "").trim() || !String(current.project_dir || "").trim()) {
    return next;
  }
  return {
    ...next,
    project_dir: current.project_dir,
    display_name: next.display_name || current.display_name || "",
    branch: next.branch || current.branch || "main",
    origin_url: next.origin_url || current.origin_url || "",
    github_mode: next.github_mode || current.github_mode || "",
  };
}

function preserveProjectRuntimeOverrides(currentForm = null, nextForm = null, previousDetail = null, sameProject = false) {
  const current = currentForm && typeof currentForm === "object" ? currentForm : {};
  const next = nextForm && typeof nextForm === "object" ? nextForm : {};
  const currentRuntime = current.runtime && typeof current.runtime === "object" ? current.runtime : {};
  const nextRuntime = next.runtime && typeof next.runtime === "object" ? { ...next.runtime } : {};
  if (sameProject) {
    if (!String(current.project_dir || "").trim()) {
      return nextForm;
    }
    let changed = false;
    PROJECT_RUNTIME_OVERRIDE_KEYS.forEach((key) => {
      if (!hasOwnValue(currentRuntime, key)) {
        return;
      }
      const nextValue = cloneValue(currentRuntime[key]);
      if (!Object.is(nextRuntime[key], nextValue)) {
        changed = true;
      }
      nextRuntime[key] = nextValue;
    });
    if (!changed) {
      return nextForm;
    }
    return {
      ...next,
      runtime: nextRuntime,
    };
  }
  if (!String(current.project_dir || "").trim()) {
    return nextForm;
  }
  if (!previousDetail) {
    return nextForm;
  }
  const previousRuntime = previousDetail?.runtime && typeof previousDetail.runtime === "object" ? previousDetail.runtime : {};
  const currentProvider = normalizedModelProvider(currentRuntime);
  const nextProvider = normalizedModelProvider(nextRuntime);
  const currentLocalProvider = normalizedLocalModelProvider(currentRuntime);
  const nextLocalProvider = normalizedLocalModelProvider(nextRuntime);
  if (currentProvider !== nextProvider || currentLocalProvider !== nextLocalProvider) {
    return nextForm;
  }
  let changed = false;
  PROJECT_RUNTIME_OVERRIDE_KEYS.forEach((key) => {
    if (!hasOwnValue(currentRuntime, key)) {
      return;
    }
    const currentValue = cloneValue(currentRuntime[key]);
    if (Object.is(currentValue, previousRuntime[key])) {
      return;
    }
    if (!Object.is(nextRuntime[key], currentValue)) {
      changed = true;
    }
    nextRuntime[key] = currentValue;
  });
  if (!changed) {
    return nextForm;
  }
  return {
    ...next,
    runtime: nextRuntime,
  };
}

function preserveProjectChatSelection(currentForm = null, nextForm = null) {
  const current = currentForm && typeof currentForm === "object" ? currentForm : {};
  const next = nextForm && typeof nextForm === "object" ? nextForm : {};
  const currentRuntime = current.runtime && typeof current.runtime === "object" ? current.runtime : {};
  const nextRuntime = next.runtime && typeof next.runtime === "object" ? { ...next.runtime } : {};
  const currentChatProvider = String(currentRuntime.chat_model_provider || "").trim().toLowerCase();
  const currentChatLocalProvider = String(currentRuntime.chat_local_model_provider || "").trim().toLowerCase();
  const currentChatModel = String(currentRuntime.chat_model || "").trim().toLowerCase();
  const currentChatEffort = String(currentRuntime.chat_effort || "").trim().toLowerCase();
  const nextProvider = normalizedModelProvider(nextRuntime);
  const nextLocalProvider = String(nextRuntime.chat_local_model_provider || nextRuntime.local_model_provider || "").trim().toLowerCase();

  if (!currentChatProvider || !currentChatModel) {
    return nextForm;
  }
  if (currentChatProvider !== nextProvider || currentChatLocalProvider !== nextLocalProvider) {
    return nextForm;
  }

  const nextChatRuntime = {
    ...nextRuntime,
    chat_model_provider: currentChatProvider,
    chat_local_model_provider: currentChatLocalProvider,
    chat_model: currentChatModel,
    chat_effort: currentChatEffort,
  };
  if (
    Object.is(nextRuntime.chat_model_provider, nextChatRuntime.chat_model_provider)
    && Object.is(nextRuntime.chat_local_model_provider, nextChatRuntime.chat_local_model_provider)
    && Object.is(nextRuntime.chat_model, nextChatRuntime.chat_model)
    && Object.is(nextRuntime.chat_effort, nextChatRuntime.chat_effort)
  ) {
    return nextForm;
  }
  return {
    ...next,
    runtime: nextChatRuntime,
  };
}

function preserveProjectStepSelection(currentPlan = null, nextPlan = null, sameProject = false) {
  if (!sameProject) {
    return nextPlan;
  }
  const current = currentPlan && typeof currentPlan === "object" ? currentPlan : {};
  const next = nextPlan && typeof nextPlan === "object" ? nextPlan : {};
  const currentSteps = Array.isArray(current.steps) ? current.steps : [];
  const nextSteps = Array.isArray(next.steps) ? next.steps : [];
  if (!currentSteps.length || !nextSteps.length) {
    const mergedPlan = {
      ...next,
    };
    let changed = false;
    const preservedCloseoutFields = [
      "closeout_title",
      "closeout_display_description",
      "closeout_codex_description",
      "closeout_success_criteria",
      "closeout_deadline_at",
      "closeout_reasoning_effort",
      "closeout_model_provider",
      "closeout_model",
      "closeout_parallel_group",
      "closeout_depends_on",
      "closeout_owned_paths",
      "closeout_notes",
    ];
    preservedCloseoutFields.forEach((key) => {
      if (!hasOwnValue(current, key)) {
        return;
      }
      const currentValue = current[key];
      if (Array.isArray(currentValue)) {
        if (currentValue.length && !Array.isArray(mergedPlan[key])) {
          mergedPlan[key] = cloneValue(currentValue);
          changed = true;
        }
        return;
      }
      const currentText = String(currentValue || "").trim();
      if (!currentText) {
        return;
      }
      const nextText = String(mergedPlan[key] || "").trim();
      if (!nextText) {
        mergedPlan[key] = currentValue;
        changed = true;
      }
    });
    return changed ? mergedPlan : nextPlan;
  }

  const currentById = new Map(
    currentSteps
      .map((step) => [String(step?.step_id || "").trim(), step])
      .filter(([stepId]) => Boolean(stepId)),
  );
  const preservedFields = ["model_provider", "model", "reasoning_effort"];
  let changed = false;
  const mergedSteps = nextSteps.map((step) => {
    const stepId = String(step?.step_id || "").trim();
    if (!stepId) {
      return step;
    }
    const currentStep = currentById.get(stepId);
    if (!currentStep) {
      return step;
    }
    const mergedStep = { ...step };
    preservedFields.forEach((key) => {
      const currentValue = String(currentStep?.[key] || "").trim();
      if (!currentValue) {
        return;
      }
      const nextValue = String(mergedStep?.[key] || "").trim();
      if (nextValue && String(nextValue).toLowerCase() !== "auto") {
        return;
      }
      if (!Object.is(mergedStep[key], currentStep[key])) {
        mergedStep[key] = cloneValue(currentStep[key]);
        changed = true;
      }
    });
    return mergedStep;
  });

  if (!changed) {
    const mergedPlan = {
      ...next,
    };
    let closeoutChanged = false;
    const preservedCloseoutFields = [
      "closeout_title",
      "closeout_display_description",
      "closeout_codex_description",
      "closeout_success_criteria",
      "closeout_deadline_at",
      "closeout_reasoning_effort",
      "closeout_model_provider",
      "closeout_model",
      "closeout_parallel_group",
      "closeout_depends_on",
      "closeout_owned_paths",
      "closeout_notes",
    ];
    preservedCloseoutFields.forEach((key) => {
      if (!hasOwnValue(current, key)) {
        return;
      }
      const currentValue = current[key];
      if (Array.isArray(currentValue)) {
        const nextValue = Array.isArray(mergedPlan[key]) ? mergedPlan[key] : [];
        if (!nextValue.length && currentValue.length) {
          mergedPlan[key] = cloneValue(currentValue);
          closeoutChanged = true;
        }
        return;
      }
      const currentText = String(currentValue || "").trim();
      if (!currentText) {
        return;
      }
      const nextText = String(mergedPlan[key] || "").trim();
      if (!nextText) {
        mergedPlan[key] = currentValue;
        closeoutChanged = true;
      }
    });
    return closeoutChanged ? mergedPlan : nextPlan;
  }
  const mergedPlan = {
    ...next,
    steps: mergedSteps,
  };
  const preservedCloseoutFields = [
    "closeout_title",
    "closeout_display_description",
    "closeout_codex_description",
    "closeout_success_criteria",
    "closeout_deadline_at",
    "closeout_reasoning_effort",
    "closeout_model_provider",
    "closeout_model",
    "closeout_parallel_group",
    "closeout_depends_on",
    "closeout_owned_paths",
    "closeout_notes",
  ];
  let closeoutChanged = false;
  preservedCloseoutFields.forEach((key) => {
    if (!hasOwnValue(current, key)) {
      return;
    }
    const currentValue = current[key];
    if (Array.isArray(currentValue)) {
      const nextValue = Array.isArray(mergedPlan[key]) ? mergedPlan[key] : [];
      if (!nextValue.length && currentValue.length) {
        mergedPlan[key] = cloneValue(currentValue);
        closeoutChanged = true;
      }
      return;
    }
    const currentText = String(currentValue || "").trim();
    if (!currentText) {
      return;
    }
    const nextText = String(mergedPlan[key] || "").trim();
    if (!nextText) {
      mergedPlan[key] = currentValue;
      closeoutChanged = true;
    }
  });
  return mergedPlan;
}

function mergeReportsSection(primary = null, fallback = null, preserveSparse = false) {
  if (!primary && !fallback) {
    return primary ?? fallback;
  }
  const primaryReports = primary && typeof primary === "object" ? primary : {};
  const fallbackReports = fallback && typeof fallback === "object" ? fallback : {};
  const nextReports = {
    ...fallbackReports,
    ...primaryReports,
  };
  const textKeys = [
    "closeout_report_text",
    "ml_experiment_report_text",
    "attempt_history_text",
    "word_report_path",
    "ml_results_svg_path",
  ];
  textKeys.forEach((key) => {
    if (!hasOwnValue(primaryReports, key)) {
      nextReports[key] = fallbackReports?.[key] || "";
      return;
    }
    const primaryText = String(primaryReports?.[key] || "");
    const fallbackText = String(fallbackReports?.[key] || "");
    nextReports[key] = preserveSparse && !primaryText.trim() && fallbackText.trim() ? fallbackText : primaryText;
  });
  nextReports.word_report_enabled =
    primaryReports?.word_report_enabled ?? fallbackReports?.word_report_enabled ?? false;
  if (!hasOwnValue(primaryReports, "latest_failure")) {
    nextReports.latest_failure = fallbackReports?.latest_failure || {};
  } else {
    const primaryFailure = primaryReports?.latest_failure;
    nextReports.latest_failure = cloneValue(primaryFailure || {});
  }
  return nextReports;
}

function mergeCheckpointsSection(primary = null, fallback = null, preserveSparse = false) {
  if (!primary && !fallback) {
    return primary ?? fallback;
  }
  const primaryCheckpoints = primary && typeof primary === "object" ? primary : {};
  const fallbackCheckpoints = fallback && typeof fallback === "object" ? fallback : {};
  const nextCheckpoints = {
    ...fallbackCheckpoints,
    ...primaryCheckpoints,
  };
  if (!hasOwnValue(primaryCheckpoints, "items")) {
    nextCheckpoints.items = fallbackCheckpoints?.items || [];
  } else {
    const primaryItems = Array.isArray(primaryCheckpoints?.items) ? primaryCheckpoints.items : [];
    const fallbackItems = Array.isArray(fallbackCheckpoints?.items) ? fallbackCheckpoints.items : [];
    nextCheckpoints.items =
      preserveSparse && primaryItems.length === 0 && fallbackItems.length > 0
        ? fallbackItems
        : cloneValue(primaryItems);
  }
  if (!hasOwnValue(primaryCheckpoints, "pending")) {
    nextCheckpoints.pending = fallbackCheckpoints?.pending ?? null;
  } else {
    const primaryPending = primaryCheckpoints?.pending ?? null;
    nextCheckpoints.pending =
      preserveSparse && primaryPending == null && fallbackCheckpoints?.pending != null
        ? fallbackCheckpoints.pending
        : cloneValue(primaryPending);
  }
  if (!hasOwnValue(primaryCheckpoints, "timeline_markdown")) {
    nextCheckpoints.timeline_markdown = String(fallbackCheckpoints?.timeline_markdown || "");
  } else {
    const primaryTimeline = String(primaryCheckpoints?.timeline_markdown || "");
    const fallbackTimeline = String(fallbackCheckpoints?.timeline_markdown || "");
    nextCheckpoints.timeline_markdown =
      preserveSparse && !primaryTimeline.trim() && fallbackTimeline.trim() ? fallbackTimeline : primaryTimeline;
  }
  return nextCheckpoints;
}

function checkpointApprovalIsActive(detail = null, activeJob = null) {
  const processJob = visibleExecutionJob(activeJob);
  if (!processJob) {
    return false;
  }
  const processStatus = String(processJob.status || "").trim().toLowerCase();
  if (processStatus !== "running" && processStatus !== "queued") {
    return false;
  }
  const currentStatus = String(detail?.project?.current_status || "").trim().toLowerCase();
  return Boolean(detail?.loop_state?.pending_checkpoint_approval) || currentStatus === "awaiting_checkpoint_approval";
}

function mergeHistorySection(primary = null, fallback = null, preserveSparse = false) {
  if (!primary && !fallback) {
    return primary ?? fallback;
  }
  const primaryHistory = primary && typeof primary === "object" ? primary : {};
  const fallbackHistory = fallback && typeof fallback === "object" ? fallback : {};
  const nextHistory = {
    ...fallbackHistory,
    ...primaryHistory,
  };
  ["ui_events", "blocks", "passes", "test_runs"].forEach((key) => {
    if (!hasOwnValue(primaryHistory, key)) {
      nextHistory[key] = fallbackHistory?.[key] || [];
      return;
    }
    const primaryItems = Array.isArray(primaryHistory?.[key]) ? primaryHistory[key] : [];
    const fallbackItems = Array.isArray(fallbackHistory?.[key]) ? fallbackHistory[key] : [];
    nextHistory[key] =
      preserveSparse && primaryItems.length === 0 && fallbackItems.length > 0
        ? fallbackItems
        : cloneValue(primaryItems);
  });
  ["flow_svg_path", "flow_svg_text"].forEach((key) => {
    if (!hasOwnValue(primaryHistory, key)) {
      nextHistory[key] = String(fallbackHistory?.[key] || "");
      return;
    }
    const primaryText = String(primaryHistory?.[key] || "");
    const fallbackText = String(fallbackHistory?.[key] || "");
    nextHistory[key] = preserveSparse && !primaryText.trim() && fallbackText.trim() ? fallbackText : primaryText;
  });
  return nextHistory;
}

function mergeConfigSection(primary = null, fallback = null, preserveSparse = false) {
  if (!primary && !fallback) {
    return primary ?? fallback;
  }
  const primaryConfig = primary && typeof primary === "object" ? primary : {};
  const fallbackConfig = fallback && typeof fallback === "object" ? fallback : {};
  const primaryHasEntries = Object.keys(primaryConfig).length > 0;
  if (preserveSparse && !primaryHasEntries && Object.keys(fallbackConfig).length > 0) {
    return fallbackConfig;
  }
  return {
    ...fallbackConfig,
    ...primaryConfig,
  };
}

function mergeChatSection(primary = null, fallback = null, preserveSparse = false) {
  if (!primary && !fallback) {
    return primary ?? fallback;
  }
  const primaryChat = primary && typeof primary === "object" ? primary : {};
  const fallbackChat = fallback && typeof fallback === "object" ? fallback : {};
  const nextChat = {
    ...fallbackChat,
    ...primaryChat,
  };
  ["sessions", "messages"].forEach((key) => {
    if (!hasOwnValue(primaryChat, key)) {
      nextChat[key] = fallbackChat?.[key] || [];
      return;
    }
    const primaryItems = Array.isArray(primaryChat?.[key]) ? primaryChat[key] : [];
    const fallbackItems = Array.isArray(fallbackChat?.[key]) ? fallbackChat[key] : [];
    nextChat[key] =
      preserveSparse && primaryItems.length === 0 && fallbackItems.length > 0
        ? fallbackItems
        : cloneValue(primaryItems);
  });
  ["active_session_id", "summary_text", "summary_file", "transcript_file"].forEach((key) => {
    if (!hasOwnValue(primaryChat, key)) {
      nextChat[key] = String(fallbackChat?.[key] || "");
      return;
    }
    const primaryText = String(primaryChat?.[key] || "");
    const fallbackText = String(fallbackChat?.[key] || "");
    nextChat[key] = preserveSparse && !primaryText.trim() && fallbackText.trim() ? fallbackText : primaryText;
  });
  if (!hasOwnValue(primaryChat, "active_session")) {
    nextChat.active_session = fallbackChat?.active_session ?? null;
  } else {
    nextChat.active_session = cloneValue(primaryChat?.active_session ?? null);
  }
  nextChat.draft_session = primaryChat?.draft_session ?? fallbackChat?.draft_session ?? false;
  return nextChat;
}

export function preserveProjectDetailSupplement(detail, previousDetail = null) {
  if (!detail) {
    return detail;
  }
  const sameProject = sameProjectDetail(detail, previousDetail);
  const loadedSections = mergeLoadedSections(
    detail?.loaded_sections,
    sameProject ? previousDetail?.loaded_sections : null,
    detail?.detail_level,
  );
  const resolvedWorkspaceTree = loadedSections.workspace
    ? resolveWorkspaceTree(detail?.workspace_tree, sameProject ? previousDetail?.workspace_tree : [])
    : detail?.workspace_tree;
  if (!sameProject || String(detail?.detail_level || "").trim().toLowerCase() === "full") {
    return {
      ...detail,
      workspace_tree: resolvedWorkspaceTree,
      loaded_sections: loadedSections,
    };
  }
  return {
    ...detail,
    workspace_tree: resolvedWorkspaceTree,
    reports: loadedSections.reports
      ? mergeReportsSection(detail?.reports, previousDetail?.reports, true)
      : detail?.reports,
    checkpoints: loadedSections.checkpoints
      ? mergeCheckpointsSection(detail?.checkpoints, previousDetail?.checkpoints, true)
      : detail?.checkpoints,
    history: loadedSections.history
      ? mergeHistorySection(detail?.history, previousDetail?.history, true)
      : detail?.history,
    config: loadedSections.config
      ? mergeConfigSection(detail?.config, previousDetail?.config, true)
      : detail?.config,
    chat: loadedSections.chat
      ? mergeChatSection(detail?.chat, previousDetail?.chat, true)
      : detail?.chat,
    loaded_sections: loadedSections,
  };
}

export function mergeProjectDetailSupplement(detail, supplement = {}) {
  if (!detail) {
    return detail;
  }
  return {
    ...detail,
    ...(hasOwnValue(supplement, "workspace_tree")
      ? { workspace_tree: resolveWorkspaceTree(supplement.workspace_tree, detail?.workspace_tree) }
      : {}),
    ...(hasOwnValue(supplement, "reports")
      ? { reports: mergeReportsSection(supplement.reports, detail?.reports, false) }
      : {}),
    ...(hasOwnValue(supplement, "checkpoints")
      ? { checkpoints: mergeCheckpointsSection(supplement.checkpoints, detail?.checkpoints, false) }
      : {}),
    ...(hasOwnValue(supplement, "history")
      ? { history: mergeHistorySection(supplement.history, detail?.history, false) }
      : {}),
    ...(hasOwnValue(supplement, "config")
      ? { config: mergeConfigSection(supplement.config, detail?.config, false) }
      : {}),
    ...(hasOwnValue(supplement, "chat")
      ? { chat: mergeChatSection(supplement.chat, detail?.chat, false) }
      : {}),
    loaded_sections: mergeLoadedSections(
      supplement?.loaded_sections,
      detail?.loaded_sections,
      detail?.detail_level,
    ),
  };
}

export function reuseProjectListingItems(previousItems = [], nextItems = []) {
  const prior = Array.isArray(previousItems) ? previousItems : [];
  const incoming = Array.isArray(nextItems) ? nextItems : [];
  if (!incoming.length) {
    return [];
  }
  if (!prior.length) {
    return incoming;
  }

  const previousByKey = new Map(
    prior
      .map((item) => [projectListKey(item), item])
      .filter(([key]) => Boolean(key)),
  );

  let changed = incoming.length !== prior.length;
  const merged = incoming.map((item, index) => {
    const match = previousByKey.get(projectListKey(item));
    if (match && shallowObjectEqual(match, item)) {
      if (prior[index] !== match) {
        changed = true;
      }
      return match;
    }
    if (prior[index] !== item) {
      changed = true;
    }
    return item;
  });

  return changed ? merged : prior;
}

export function applyListingState({ listing, runningJob = null, setProjects, setWorkspaceStats }) {
  const listingState = reduceProjectListingState({
    projects: listing?.projects || [],
    runningJob,
  });
  setProjects(listingState.projects);
  setWorkspaceStats(listingState.workspaceStats);
  return listingState.projects;
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
  const listingState = reduceProjectListingState({
    projects: mergedProjects,
    runningJob,
  });
  setProjects(listingState.projects);
  setWorkspaceStats(listingState.workspaceStats);
  return listingState.projects;
}

export function applyProjectEventListingState({
  projects,
  project,
  runningJob = null,
  setProjects,
  setWorkspaceStats,
}) {
  const repoId = String(project?.repo_id || "").trim();
  const projectDir = String(project?.project_dir || "").trim();
  const status = String(project?.status || project?.project_status || "").trim();
  if (!repoId && !projectDir && !status) {
    return null;
  }

  let changed = false;
  const nextProjects = (projects || []).map((item) => {
    const sameRepoId = repoId && String(item?.repo_id || "").trim() === repoId;
    const sameProjectDir = projectDir && String(item?.repo_path || "").trim() === projectDir;
    if (!sameRepoId && !sameProjectDir) {
      return item;
    }
    changed = true;
    return {
      ...item,
      repo_id: repoId || item?.repo_id || "",
      repo_path: projectDir || item?.repo_path || "",
      status: status || item?.status || "",
      detail: item?.detail || (projectDir ? `Path ${projectDir}` : ""),
    };
  });

  if (!changed) {
    return null;
  }

  const listingState = reduceProjectListingState({
    projects: nextProjects,
    runningJob,
  });
  setProjects(listingState.projects);
  setWorkspaceStats(listingState.workspaceStats);
  return listingState.projects;
}

export function applyProjectEventDetailState(detail, project) {
  if (!detail || !projectEventMatchesDetail(detail, project)) {
    return null;
  }
  const nextStatus = String(project?.status || project?.project_status || "").trim();
  const nextRepoPath = String(project?.project_dir || "").trim();
  const currentStatus = String(detail?.project?.current_status || "").trim();
  const currentRepoPath = String(detail?.project?.repo_path || "").trim();
  if (!nextStatus && !nextRepoPath) {
    return null;
  }
  if (nextStatus === currentStatus && (!nextRepoPath || nextRepoPath === currentRepoPath)) {
    return detail;
  }

  const nextProject = {
    ...(detail?.project || {}),
    ...(nextStatus ? { current_status: nextStatus } : {}),
    ...(nextRepoPath ? { repo_path: nextRepoPath } : {}),
  };
  const nextSnapshotProject = detail?.snapshot?.project
    ? {
        ...detail.snapshot.project,
        ...(nextStatus ? { current_status: nextStatus } : {}),
        ...(nextRepoPath ? { repo_path: nextRepoPath } : {}),
      }
    : detail?.snapshot?.project;
  return {
    ...detail,
    project: nextProject,
    snapshot: detail?.snapshot
      ? {
          ...detail.snapshot,
          project: nextSnapshotProject,
        }
      : detail?.snapshot,
  };
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
  const preservedDetail = preserveProjectDetailSupplement(detail, state.projectDetail);
  const mergedDetail = mergeProjectDetailCodexStatus(preservedDetail, state.projectDetail?.codex_status, state.modelCatalog);
  const activeJob = options.runningJob ?? state.activeJob;
  const detailState = reduceProjectDetailState({
    detail: mergedDetail,
    runningJob: activeJob,
  });
  const normalizedDetail = detailState.detail;
  const applySignature = detailApplySignature(normalizedDetail, options.runningJob ?? state.activeJob);
  if (
    !options.force &&
    applySignature &&
    refs.lastAppliedDetailSignatureRef.current === applySignature &&
    normalizedDetail?.project?.repo_id === state.projectDetail?.project?.repo_id
  ) {
    setters.setLoadingProjectId("");
    return null;
  }
  const preserveDirtyPlan = shouldKeepUnsavedPlan(
    state.projectDetail?.project?.repo_id,
    normalizedDetail?.project?.repo_id,
    options.preserveDirtyPlan ?? state.planDirty,
  );
  const sameProject = sameProjectDetail(normalizedDetail, state.projectDetail);
  refs.lastAppliedDetailSignatureRef.current = applySignature;
  const preservedPlan = preserveProjectStepSelection(state.planDraft, normalizedDetail.plan, sameProject);
    setters.transition(() => {
      setters.setProjectDetail(normalizedDetail);
      setters.setModelCatalog(
        mergeModelCatalogs(
          normalizedDetail?.codex_status?.model_catalog || [],
          state.modelCatalog,
        ),
      );
      setters.setShareSettings(shareSettingsFromDetail(normalizedDetail));
      setters.setLoadingProjectId("");
    setters.setProjectForm((current) => {
      if (current.project_dir && preserveDirtyPlan) {
        return current;
      }
      const projectFormFromDetailState = preserveProjectIdentityForm(
        current,
        projectFormFromDetail(normalizedDetail, state.defaultRuntime),
      );
      const nextProjectForm = preserveProjectRuntimeOverrides(
        current,
        projectFormFromDetailState,
        state.projectDetail,
        sameProject,
      );
      const nextProjectFormWithChat = preserveProjectChatSelection(current, nextProjectForm);
      if (sameProject) {
        return nextProjectFormWithChat;
      }
      return enforceProgramModelDefaults(nextProjectFormWithChat, state.defaultRuntime);
    });
    if (!preserveDirtyPlan) {
      setters.setPlanDraft(cloneValue(preservedPlan));
      setters.setSelectedStepId((current) => {
        const currentStepId = String(current || "").trim();
        if (currentStepId === CLOSEOUT_STEP_ID) {
          return currentStepId;
        }
        const currentStep = (preservedPlan?.steps || []).find((step) => step?.step_id === currentStepId);
        if (currentStep && currentStep.status !== "completed") {
          return currentStepId;
        }
        return "";
      });
      setters.setPlanDirty(false);
    }
  });
  return normalizedDetail;
}

export function clearSelectedProjectState({
  defaultRuntime,
  nextProjectForm = null,
  refs,
  setters,
}) {
  refs.lastAppliedDetailSignatureRef.current = "";
  setters.setProjectDetail(null);
  setters.setSelectedProjectId("");
  setters.setSelectedStepId("");
  setters.setPlanDirty(false);
  setters.setLoadingProjectId("");
  setters.setProjectForm(nextProjectForm && typeof nextProjectForm === "object" ? cloneValue(nextProjectForm) : blankProjectForm(defaultRuntime));
  setters.setPlanDraft(emptyPlanDraft());
  setters.setShareSettings(defaultShareSettings());
}
