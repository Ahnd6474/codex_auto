from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import ExecutionPlanState, LoopState, ProjectContext
from .status_views import effective_project_status


def _planning_progress_is_running(planning_progress: dict[str, Any] | None) -> bool:
    if not isinstance(planning_progress, dict):
        return False
    current_stage_status = str(
        planning_progress.get("current_stage_status", planning_progress.get("currentStageStatus", ""))
    ).strip().lower()
    return current_stage_status == "running"


@dataclass(slots=True, frozen=True)
class ProjectExecutionSnapshot:
    raw_status: str
    current_status: str
    display_status: str
    waiting_for_checkpoint_approval: bool
    planning_running: bool
    is_running: bool


def project_execution_snapshot(
    raw_status: str | None,
    plan_state: ExecutionPlanState,
    loop_state: LoopState,
    planning_progress: dict[str, Any] | None = None,
    *,
    prefer_raw_running_display: bool = False,
) -> ProjectExecutionSnapshot:
    normalized_raw_status = str(raw_status or "").strip()
    current_status = effective_project_status(
        normalized_raw_status,
        plan_state,
        loop_state,
        planning_progress=planning_progress,
    )
    display_status = current_status
    if prefer_raw_running_display and normalized_raw_status.lower().startswith("running:") and not current_status.startswith("running:"):
        display_status = normalized_raw_status
    planning_running = _planning_progress_is_running(planning_progress)
    return ProjectExecutionSnapshot(
        raw_status=normalized_raw_status,
        current_status=current_status,
        display_status=display_status,
        waiting_for_checkpoint_approval=bool(loop_state.pending_checkpoint_approval),
        planning_running=planning_running,
        is_running=current_status.startswith("running:"),
    )


def context_execution_snapshot(
    context: ProjectContext,
    plan_state: ExecutionPlanState,
    planning_progress: dict[str, Any] | None = None,
    *,
    prefer_raw_running_display: bool = False,
) -> ProjectExecutionSnapshot:
    return project_execution_snapshot(
        context.metadata.current_status,
        plan_state,
        context.loop_state,
        planning_progress,
        prefer_raw_running_display=prefer_raw_running_display,
    )
