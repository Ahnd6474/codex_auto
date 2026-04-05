from __future__ import annotations

from dataclasses import dataclass, field

from .models import ExecutionPlanState


_DIRECT_DEBUG_MARKERS = (
    "fix",
    "debug",
    "bug",
    "broken",
    "failing",
    "failure",
    "issue",
    "error",
    "regression",
    "repair",
)

_DIRECT_SMALL_SCOPE_MARKERS = (
    "test",
    "parser",
    "prompt",
    "path",
    "import",
    "label",
    "copy",
    "message",
    "config",
    "setting",
    "log",
    "readme",
    "docs",
    "typo",
    "rename",
    "remove",
    "adjust",
    "tweak",
    "update",
    "align",
    "wire",
)

_DIRECT_BROAD_SCOPE_MARKERS = (
    "new feature",
    "new screen",
    "new page",
    "new workflow",
    "redesign",
    "architecture",
    "migrate",
    "multi-step",
    "end-to-end",
    "from scratch",
    "overhaul",
    "dashboard",
    "desktop app",
    "tauri",
    "system design",
    "cross-repo",
    "multi-repo",
)

_DIRECT_COMPLEXITY_MARKERS = (
    " and ",
    " then ",
    " also ",
    " plus ",
    " across ",
    "together",
)


@dataclass(slots=True)
class DirectExecutionAssessment:
    score: int
    threshold: int
    should_bypass: bool
    step_type: str
    reasons: list[str] = field(default_factory=list)
    positive_markers: list[str] = field(default_factory=list)
    negative_markers: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)


def classify_direct_execution_step_type(project_prompt: str) -> str:
    normalized_prompt = _normalize_prompt(project_prompt)
    return "debug" if any(marker in normalized_prompt for marker in _DIRECT_DEBUG_MARKERS) else "feature"


def assess_direct_execution_bypass(
    *,
    repo_inputs: dict[str, str],
    project_prompt: str,
    previous_plan_state: ExecutionPlanState,
    max_steps: int,
    planning_effort: str,
    workflow_mode: str,
) -> DirectExecutionAssessment:
    normalized_prompt = _normalize_prompt(project_prompt)
    token_count = len(normalized_prompt.split())
    repo_size = sum(len(str(repo_inputs.get(key, ""))) for key in ("readme", "agents", "docs", "source"))
    score = 50
    reasons: list[str] = []
    positive_markers = [marker for marker in (*_DIRECT_DEBUG_MARKERS, *_DIRECT_SMALL_SCOPE_MARKERS) if marker in normalized_prompt]
    negative_markers = [marker for marker in (*_DIRECT_BROAD_SCOPE_MARKERS, *_DIRECT_COMPLEXITY_MARKERS) if marker in normalized_prompt]
    blockers: list[str] = []

    if not normalized_prompt:
        blockers.append("empty_prompt")
        score = 0

    if workflow_mode == "ml":
        blockers.append("ml_workflow")
        score -= 50
        reasons.append("ML workflow keeps the full planner path.")
    if planning_effort not in {"low", "medium"}:
        blockers.append("high_planning_effort")
        score -= 25
        reasons.append("Planning effort is high enough to prefer the planner.")
    if max_steps > 3:
        blockers.append("wide_step_budget")
        score -= 20
        reasons.append("Allowed step budget is wide enough to justify planning.")

    if token_count <= 8:
        score += 18
        reasons.append("Prompt is very short and likely narrow.")
    elif token_count <= 16:
        score += 10
        reasons.append("Prompt length still looks compact.")
    elif token_count > 24:
        score -= 18
        reasons.append("Prompt wording suggests a broader task.")
    if len(normalized_prompt) > 160:
        score -= 12
        reasons.append("Prompt text is long enough to deserve planning.")

    if positive_markers:
        score += min(18, 6 + (len(positive_markers) * 3))
        reasons.append("Prompt contains targeted fix/update markers.")
    else:
        score -= 15
        reasons.append("Prompt lacks explicit narrow-task markers.")

    if negative_markers:
        score -= min(28, 8 + (len(negative_markers) * 4))
        reasons.append("Prompt contains broad-scope or multi-part markers.")

    if repo_size <= 3_500:
        score += 8
        reasons.append("Repository context is compact enough for direct handling.")
    elif repo_size <= 7_500:
        score += 3
        reasons.append("Repository context is still small enough for a direct pass.")
    elif repo_size > 12_000:
        score -= 10
        reasons.append("Repository context is large enough to benefit from planning.")

    if any(step.status in {"running", "integrating"} for step in previous_plan_state.steps):
        blockers.append("active_execution")
        score -= 35
        reasons.append("An active execution state already exists.")

    if len(previous_plan_state.steps) > 8:
        score -= 8
        reasons.append("Existing plan history is large enough to prefer planner alignment.")

    score = max(0, min(100, score))
    threshold = 70
    should_bypass = score >= threshold and not blockers
    if should_bypass:
        reasons.append("Score cleared the direct-execution threshold.")
    return DirectExecutionAssessment(
        score=score,
        threshold=threshold,
        should_bypass=should_bypass,
        step_type=classify_direct_execution_step_type(project_prompt),
        reasons=reasons,
        positive_markers=positive_markers,
        negative_markers=negative_markers,
        blockers=blockers,
    )


def _normalize_prompt(project_prompt: str) -> str:
    return " ".join(str(project_prompt or "").split()).strip().lower()
