from __future__ import annotations

from ..parallel_resources import build_parallel_resource_plan
from ..utils import normalize_workflow_mode
from .context import BridgeCommandContext, BridgeCommandHandler


def build_run_command_handlers(
    *,
    resolve_project,
    common_project_inputs,
    parse_plan_state,
    append_ui_event,
    save_run_control,
    default_run_control,
    request_stop_after_current_step,
    stop_requested,
    coerce_bool,
) -> dict[str, BridgeCommandHandler]:
    def request_stop(ctx: BridgeCommandContext) -> dict:
        project = resolve_project(ctx.orchestrator, ctx.payload)
        control = request_stop_after_current_step(
            project,
            request_source=str(ctx.payload.get("source", "desktop-ui")).strip() or "desktop-ui",
        )
        return {
            "repo_id": project.metadata.repo_id,
            "project_dir": str(project.metadata.repo_path),
            "run_control": control,
        }

    def approve_checkpoint(ctx: BridgeCommandContext) -> dict:
        project = resolve_project(ctx.orchestrator, ctx.payload)
        review_notes = str(ctx.payload.get("review_notes", "")).strip()
        push = coerce_bool(ctx.payload.get("push", True), True)
        ctx.orchestrator.approve_checkpoint(
            project.metadata.repo_url,
            project.metadata.branch,
            review_notes=review_notes,
            push=push,
        )
        latest_project = ctx.orchestrator.workspace.load_project_by_id(project.metadata.repo_id)
        append_ui_event(latest_project, "checkpoint-approved", "Approved the pending checkpoint.", {"push": push})
        return ctx.detail_payload(latest_project)

    def run_plan(ctx: BridgeCommandContext) -> dict:
        project_dir, runtime, branch, origin_url, _display_name = common_project_inputs(ctx.payload)
        raw_plan = ctx.payload.get("plan", {})
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
        save_run_control(project, default_run_control())
        append_ui_event(project, "run-started", "Started running the remaining execution steps.")
        try:
            while True:
                latest_project = ctx.orchestrator.local_project(project_dir)
                if latest_project is None:
                    raise RuntimeError("The managed project could not be reloaded during execution.")
                current_plan = ctx.orchestrator.load_execution_plan_state(latest_project)
                batches = ctx.orchestrator.pending_execution_batches(current_plan)
                if not batches:
                    if normalize_workflow_mode(runtime.workflow_mode) == "ml":
                        saved = current_plan
                        project = latest_project
                        if str(current_plan.closeout_status).strip().lower() != "completed":
                            append_ui_event(project, "closeout-started", "Started ML cycle closeout.")
                            project, saved = ctx.orchestrator.run_execution_closeout(
                                project_dir=project_dir,
                                runtime=runtime,
                                branch=branch,
                                origin_url=origin_url,
                            )
                            append_ui_event(
                                project,
                                "closeout-finished",
                                f"ML cycle closeout finished with status {saved.closeout_status}.",
                                {"status": saved.closeout_status, "commit_hash": saved.closeout_commit_hash},
                            )
                            if saved.closeout_status != "completed":
                                break
                        project, saved, continued, reason = ctx.orchestrator.prepare_next_ml_cycle(
                            project_dir=project_dir,
                            runtime=runtime,
                            branch=branch,
                            origin_url=origin_url,
                        )
                        if continued:
                            append_ui_event(
                                project,
                                "plan-generated",
                                f"Generated the next ML execution cycle with {len(saved.steps)} step(s).",
                                {"workflow_mode": "ml", "step_count": len(saved.steps)},
                            )
                            continue
                        append_ui_event(
                            project,
                            "ml-cycle-stopped",
                            f"ML loop stopped: {reason}.",
                            {"reason": reason},
                        )
                    break
                if stop_requested(latest_project):
                    append_ui_event(latest_project, "run-paused", "Paused before the next step because a stop was requested.")
                    break
                batch = batches[0]
                parallel_plan = build_parallel_resource_plan(
                    getattr(runtime, "parallel_worker_mode", "auto"),
                    getattr(runtime, "parallel_workers", 0),
                )
                if (
                    len(batch) > 1
                    and str(current_plan.execution_mode).strip().lower() == "parallel"
                    and parallel_plan.recommended_workers > 1
                ):
                    step_ids = [item.step_id for item in batch]
                    append_ui_event(
                        latest_project,
                        "batch-started",
                        f"Running parallel batch: {', '.join(step_ids)}",
                        {
                            "step_ids": step_ids,
                            "execution_mode": "parallel",
                            "parallel_workers": parallel_plan.recommended_workers,
                            "parallel_worker_mode": parallel_plan.worker_mode,
                        },
                    )
                    for step in batch:
                        append_ui_event(
                            latest_project,
                            "step-started",
                            f"Running {step.step_id}: {step.title}",
                            {"step_id": step.step_id, "title": step.title, "execution_mode": "parallel"},
                        )
                    project, saved, result_steps = ctx.orchestrator.run_parallel_execution_batch(
                        project_dir=project_dir,
                        runtime=runtime,
                        step_ids=step_ids,
                        branch=branch,
                        origin_url=origin_url,
                    )
                    for result_step in result_steps:
                        append_ui_event(
                            project,
                            "step-finished",
                            f"{result_step.step_id} finished with status {result_step.status}.",
                            {
                                "step_id": result_step.step_id,
                                "status": result_step.status,
                                "commit_hash": result_step.commit_hash,
                            },
                        )
                    append_ui_event(
                        project,
                        "batch-finished",
                        f"Parallel batch finished for {', '.join(step_ids)}.",
                        {
                            "step_ids": step_ids,
                            "statuses": {item.step_id: item.status for item in result_steps},
                        },
                    )
                    if any(item.status != "completed" for item in result_steps):
                        break
                    continue
                step = batch[0]
                append_ui_event(
                    latest_project,
                    "step-started",
                    f"Running {step.step_id}: {step.title}",
                    {"step_id": step.step_id, "title": step.title},
                )
                project, saved, result_step = ctx.orchestrator.run_saved_execution_step(
                    project_dir=project_dir,
                    runtime=runtime,
                    step_id=step.step_id,
                    branch=branch,
                    origin_url=origin_url,
                )
                append_ui_event(
                    project,
                    "step-finished",
                    f"{result_step.step_id} finished with status {result_step.status}.",
                    {
                        "step_id": result_step.step_id,
                        "status": result_step.status,
                        "commit_hash": result_step.commit_hash,
                    },
                )
                if result_step.status != "completed":
                    break
            latest = ctx.orchestrator.local_project(project_dir)
            if latest is not None:
                append_ui_event(latest, "run-finished", "Finished the run loop for the current project.")
                return ctx.detail_payload(latest)
            return ctx.detail_payload(project)
        finally:
            latest = ctx.orchestrator.local_project(project_dir)
            if latest is not None:
                save_run_control(latest, default_run_control())

    def run_closeout(ctx: BridgeCommandContext) -> dict:
        project_dir, runtime, branch, origin_url, _display_name = common_project_inputs(ctx.payload)
        raw_plan = ctx.payload.get("plan", {})
        if not isinstance(raw_plan, dict):
            raise ValueError("plan payload must be an object.")
        plan_state = parse_plan_state(raw_plan)
        project, _saved = ctx.orchestrator.update_execution_plan(
            project_dir=project_dir,
            runtime=runtime,
            plan_state=plan_state,
            branch=branch,
            origin_url=origin_url,
        )
        append_ui_event(project, "closeout-started", "Started project closeout.")
        project, saved = ctx.orchestrator.run_execution_closeout(
            project_dir=project_dir,
            runtime=runtime,
            branch=branch,
            origin_url=origin_url,
        )
        append_ui_event(
            project,
            "closeout-finished",
            f"Closeout finished with status {saved.closeout_status}.",
            {"status": saved.closeout_status, "commit_hash": saved.closeout_commit_hash},
        )
        return ctx.detail_payload(project)

    return {
        "request-stop": request_stop,
        "approve-checkpoint": approve_checkpoint,
        "run-plan": run_plan,
        "run-closeout": run_closeout,
    }
