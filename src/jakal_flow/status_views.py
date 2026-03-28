from __future__ import annotations

from .models import ExecutionPlanState, LoopState


_SPECIAL_RUNNING_STATUSES = {
    "running:generate-plan",
    "running:debugging",
    "running:parallel-debugging",
}
_ACTIVE_STEP_STATUSES = {"running", "integrating"}
_READY_LIKE_STATUSES = {
    "initialized",
    "ready",
    "setup_ready",
    "plan_ready",
    "plan_completed",
    "closed_out",
    "closeout_failed",
}


def status_from_plan_state(plan_state: ExecutionPlanState) -> str:
    if not plan_state.steps:
        return "setup_ready"
    active_steps = [step for step in plan_state.steps if step.status in _ACTIVE_STEP_STATUSES]
    if active_steps:
        if len(active_steps) == 1 and active_steps[0].status == "running":
            return f"running:{active_steps[0].step_id.lower()}"
        return "running:parallel"
    if any(step.status != "completed" for step in plan_state.steps):
        return "plan_ready"
    if plan_state.closeout_status == "completed":
        return "closed_out"
    if plan_state.closeout_status == "running":
        return "running:closeout"
    if plan_state.closeout_status == "failed":
        return "closeout_failed"
    return "plan_completed"


def _should_prefer_plan_status(raw_status: str, plan_status: str) -> bool:
    normalized_raw = str(raw_status or "").strip().lower()
    normalized_plan = str(plan_status or "").strip().lower()
    if not normalized_plan:
        return False
    if not normalized_raw or normalized_raw == "awaiting_checkpoint_approval":
        return True
    if normalized_raw in _SPECIAL_RUNNING_STATUSES:
        return False
    if normalized_plan in {"running:parallel", "running:closeout"}:
        return normalized_raw != normalized_plan
    if normalized_raw.startswith("running:") and not normalized_plan.startswith("running:"):
        return True
    if normalized_plan.startswith("running:") and normalized_raw in _READY_LIKE_STATUSES:
        return True
    return False


def effective_project_status(
    raw_status: str | None,
    plan_state: ExecutionPlanState,
    loop_state: LoopState,
) -> str:
    normalized = str(raw_status or "").strip()
    plan_status = status_from_plan_state(plan_state)
    if loop_state.pending_checkpoint_approval:
        return "awaiting_checkpoint_approval"
    if _should_prefer_plan_status(normalized, plan_status):
        return plan_status
    return normalized or plan_status
