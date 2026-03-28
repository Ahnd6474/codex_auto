from __future__ import annotations

from ..parallel_resources import build_parallel_resource_plan
from ..utils import normalize_workflow_mode, read_json
from .context import BridgeCommandContext, BridgeCommandHandler


def build_run_command_handlers(
    *,
    resolve_project,
    common_project_inputs,
    parse_plan_state,
    append_ui_event,
    save_run_control,
    default_run_control,
    request_stop_immediately,
    stop_requested,
    immediate_stop_requested,
    execution_scope_id,
    execution_stop_registry,
    coerce_bool,
) -> dict[str, BridgeCommandHandler]:
    def closeout_finished_event_payload(project, saved) -> tuple[str, dict]:
        details = {
            "status": saved.closeout_status,
            "commit_hash": saved.closeout_commit_hash,
            "notes": str(saved.closeout_notes or "").strip(),
        }
        word_report_path = ""
        report_path = getattr(project.paths, "closeout_report_docx_file", None)
        if report_path is not None and report_path.exists():
            word_report_path = str(report_path)
            details["word_report_path"] = word_report_path
        latest_failure_status = read_json(project.paths.reports_dir / "latest_pr_failure_status.json", default={})
        if isinstance(latest_failure_status, dict):
            latest_failure_report = str(latest_failure_status.get("report_markdown_file", "")).strip()
            latest_failure_json = str(latest_failure_status.get("report_json_file", "")).strip()
            if latest_failure_report:
                details["failure_report_markdown_file"] = latest_failure_report
            if latest_failure_json:
                details["failure_report_json_file"] = latest_failure_json
        message = f"Closeout finished with status {saved.closeout_status}."
        if saved.closeout_status == "completed" and word_report_path:
            message = f"{message} Word report: {word_report_path}"
        elif saved.closeout_status == "failed" and details.get("failure_report_markdown_file"):
            message = f"{message} Failure report: {details['failure_report_markdown_file']}"
        return message, details

    def raise_closeout_failure(ctx: BridgeCommandContext, project_dir, exc: Exception) -> None:
        latest_project = ctx.orchestrator.local_project(project_dir)
        if latest_project is None:
            raise RuntimeError(str(exc).strip() or "Closeout failed.") from exc
        latest_saved = ctx.orchestrator.load_execution_plan_state(latest_project)
        event_message, event_details = closeout_finished_event_payload(latest_project, latest_saved)
        append_ui_event(latest_project, "closeout-finished", event_message, event_details)
        note = str(latest_saved.closeout_notes or "").strip() or str(exc).strip() or "Closeout failed."
        failure_report = str(event_details.get("failure_report_markdown_file", "")).strip()
        if failure_report:
            raise RuntimeError(f"{note} Failure report: {failure_report}") from exc
        raise RuntimeError(note) from exc

    def request_stop(ctx: BridgeCommandContext) -> dict:
        project = resolve_project(ctx.orchestrator, ctx.payload)
        control = request_stop_immediately(
            project,
            request_source=str(ctx.payload.get("source", "desktop-ui")).strip() or "desktop-ui",
        )
        execution_stop_registry.request_stop(execution_scope_id(project))
        append_ui_event(project, "stop-requested", "Immediate stop requested. The current step will be ignored.", control)
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
        scope_id = execution_scope_id(project)
        execution_stop_registry.clear(scope_id)
        save_run_control(project, default_run_control())
        append_ui_event(project, "run-started", "Started running the remaining execution steps.")
        try:
            def run_closeout_pass(latest_project, closeout_message: str):
                append_ui_event(latest_project, "closeout-started", closeout_message)
                try:
                    next_project, next_saved = ctx.orchestrator.run_execution_closeout(
                        project_dir=project_dir,
                        runtime=runtime,
                        branch=branch,
                        origin_url=origin_url,
                    )
                except Exception as exc:
                    raise_closeout_failure(ctx, project_dir, exc)
                event_message, event_details = closeout_finished_event_payload(next_project, next_saved)
                append_ui_event(
                    next_project,
                    "closeout-finished",
                    event_message,
                    event_details,
                )
                return next_project, next_saved

            while True:
                latest_project = ctx.orchestrator.local_project(project_dir)
                if latest_project is None:
                    raise RuntimeError("The managed project could not be reloaded during execution.")
                if immediate_stop_requested(latest_project):
                    append_ui_event(latest_project, "run-paused", "Paused immediately because an immediate stop was requested.")
                    break
                current_plan = ctx.orchestrator.load_execution_plan_state(latest_project)
                batches = ctx.orchestrator.pending_execution_batches(current_plan)
                if not batches:
                    workflow_mode = normalize_workflow_mode(runtime.workflow_mode)
                    saved = current_plan
                    project = latest_project
                    if str(current_plan.closeout_status).strip().lower() != "completed":
                        closeout_message = "Started ML cycle closeout." if workflow_mode == "ml" else "Started project closeout."
                        project, saved = run_closeout_pass(latest_project, closeout_message)
                        if saved.closeout_status != "completed":
                            break
                    if workflow_mode == "ml":
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
                hybrid_lineages = ctx.orchestrator._plan_uses_hybrid_lineages(current_plan)
                step_kind = ctx.orchestrator._step_kind(batch[0]) if batch else "task"
                parallel_plan = build_parallel_resource_plan(
                    getattr(runtime, "parallel_worker_mode", "auto"),
                    getattr(runtime, "parallel_workers", 0),
                    getattr(runtime, "parallel_memory_per_worker_gib", 3),
                )
                if hybrid_lineages and step_kind in {"join", "barrier"}:
                    step = batch[0]
                    append_ui_event(
                        latest_project,
                        "step-started",
                        f"Running {step.step_id}: {step.title}",
                        {"step_id": step.step_id, "title": step.title, "step_kind": step_kind},
                    )
                    project, saved, result_step = ctx.orchestrator.run_join_execution_step(
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
                            "step_kind": step_kind,
                        },
                    )
                    if result_step.status == "paused":
                        append_ui_event(project, "run-paused", "Paused immediately because an immediate stop was requested.")
                    if result_step.status != "completed":
                        break
                    continue
                if hybrid_lineages:
                    step_ids = [item.step_id for item in batch]
                    if len(batch) > 1:
                        append_ui_event(
                            latest_project,
                            "batch-started",
                            f"Running lineage batch: {', '.join(step_ids)}",
                            {
                                "step_ids": step_ids,
                                "execution_mode": "parallel",
                                "parallel_workers": parallel_plan.recommended_workers,
                                "parallel_worker_mode": parallel_plan.worker_mode,
                                "hybrid_lineages": True,
                            },
                        )
                    for step in batch:
                        append_ui_event(
                            latest_project,
                            "step-started",
                            f"Running {step.step_id}: {step.title}",
                            {"step_id": step.step_id, "title": step.title, "execution_mode": "parallel", "hybrid_lineages": True},
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
                    if len(batch) > 1:
                        append_ui_event(
                            project,
                            "batch-finished",
                            f"Lineage batch finished for {', '.join(step_ids)}.",
                            {
                                "step_ids": step_ids,
                                "statuses": {item.step_id: item.status for item in result_steps},
                                "hybrid_lineages": True,
                            },
                        )
                    if any(item.status == "paused" for item in result_steps):
                        append_ui_event(project, "run-paused", "Paused immediately because an immediate stop was requested.")
                    if any(item.status != "completed" for item in result_steps):
                        break
                    continue
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
                    if any(item.status == "paused" for item in result_steps):
                        append_ui_event(project, "run-paused", "Paused immediately because an immediate stop was requested.")
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
                if result_step.status == "paused":
                    append_ui_event(project, "run-paused", "Paused immediately because an immediate stop was requested.")
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
                execution_stop_registry.clear(execution_scope_id(latest))

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
        execution_stop_registry.clear(execution_scope_id(project))
        try:
            append_ui_event(project, "closeout-started", "Started project closeout.")
            try:
                project, saved = ctx.orchestrator.run_execution_closeout(
                    project_dir=project_dir,
                    runtime=runtime,
                    branch=branch,
                    origin_url=origin_url,
                )
            except Exception as exc:
                raise_closeout_failure(ctx, project_dir, exc)
            event_message, event_details = closeout_finished_event_payload(project, saved)
            append_ui_event(
                project,
                "closeout-finished",
                event_message,
                event_details,
            )
            return ctx.detail_payload(project)
        finally:
            latest = ctx.orchestrator.local_project(project_dir)
            if latest is not None:
                save_run_control(latest, default_run_control())
                execution_stop_registry.clear(execution_scope_id(latest))

    return {
        "request-stop": request_stop,
        "approve-checkpoint": approve_checkpoint,
        "run-plan": run_plan,
        "run-closeout": run_closeout,
    }
