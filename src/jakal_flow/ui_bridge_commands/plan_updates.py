from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ..models import ExecutionPlanState, ProjectContext, RuntimeOptions
from .context import BridgeCommandContext


@dataclass(frozen=True, slots=True)
class PlanUpdateResult:
    project_dir: Path
    runtime: RuntimeOptions
    branch: str
    origin_url: str
    plan_state: ExecutionPlanState
    project: ProjectContext
    saved: ExecutionPlanState


def update_project_plan_from_payload(
    ctx: BridgeCommandContext,
    *,
    common_project_inputs,
    parse_plan_state,
    payload: Mapping[str, Any] | None = None,
) -> PlanUpdateResult:
    source_payload = dict(ctx.payload if payload is None else payload)
    project_dir, runtime, branch, origin_url, _display_name = common_project_inputs(source_payload, ctx.orchestrator)
    raw_plan = source_payload.get("plan", {})
    if not isinstance(raw_plan, dict):
        raise ValueError("plan payload must be an object.")
    plan_state = parse_plan_state(raw_plan)
    project, saved = ctx.orchestrator.update_execution_plan(
        project_dir=project_dir,
        runtime=runtime,
        plan_state=plan_state,
        branch=branch,
        origin_url=origin_url,
    )
    return PlanUpdateResult(
        project_dir=project_dir,
        runtime=runtime,
        branch=branch,
        origin_url=origin_url,
        plan_state=plan_state,
        project=project,
        saved=saved,
    )
