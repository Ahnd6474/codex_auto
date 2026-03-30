from __future__ import annotations

from ..chat_sessions import (
    chat_payload,
    execute_conversation_turn,
    rebuild_chat_session_files,
    resolve_chat_session,
    save_chat_message,
)
from ..execution_control import ImmediateStopRequested
from ..errors import HANDLED_OPERATION_EXCEPTIONS
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
    def chat_project_payload(project) -> dict:
        return {
            "repo_id": project.metadata.repo_id,
            "repo_path": str(project.metadata.repo_path),
            "current_status": str(project.metadata.current_status or "").strip(),
        }

    def closeout_finished_event_payload(project, saved) -> tuple[str, dict]:
        details = {
            "status": saved.closeout_status,
            "commit_hash": saved.closeout_commit_hash,
            "notes": str(saved.closeout_notes or "").strip(),
        }
        word_report_path = ""
        report_path = getattr(project.paths, "closeout_report_docx_file", None)
        if bool(getattr(project.runtime, "generate_word_report", False)) and report_path is not None and report_path.exists():
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
        project_dir, runtime, branch, origin_url, _display_name = common_project_inputs(ctx.payload, ctx.orchestrator)
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
        ctx.orchestrator.clear_latest_failure_status(project)
        append_ui_event(project, "run-started", "Started running the remaining execution steps.")
        pending_started_steps: list[dict[str, str]] = []
        pending_batch_details: dict[str, object] | None = None

        def clear_pending_events() -> None:
            pending_started_steps.clear()
            nonlocal pending_batch_details
            pending_batch_details = None

        def mark_pending_steps_failed(latest_project, error_message: str) -> None:
            nonlocal pending_batch_details
            if not pending_started_steps:
                return
            for item in pending_started_steps:
                step_id = str(item.get("step_id", "")).strip()
                title = str(item.get("title", "")).strip()
                details = {
                    "step_id": step_id,
                    "status": "failed",
                }
                execution_mode = str(item.get("execution_mode", "")).strip()
                if execution_mode:
                    details["execution_mode"] = execution_mode
                if str(item.get("hybrid_lineages", "")).strip():
                    details["hybrid_lineages"] = True
                step_kind = str(item.get("step_kind", "")).strip()
                if step_kind:
                    details["step_kind"] = step_kind
                append_ui_event(
                    latest_project,
                    "step-finished",
                    f"{step_id} finished with status failed.",
                    details,
                )
            if pending_batch_details is not None:
                step_ids = [
                    str(value).strip()
                    for value in pending_batch_details.get("step_ids", [])
                    if str(value).strip()
                ]
                if len(step_ids) > 1:
                    details = {
                        "step_ids": step_ids,
                        "statuses": {step_id: "failed" for step_id in step_ids},
                    }
                    execution_mode = str(pending_batch_details.get("execution_mode", "")).strip()
                    if execution_mode:
                        details["execution_mode"] = execution_mode
                    parallel_workers = pending_batch_details.get("parallel_workers")
                    if parallel_workers is not None:
                        details["parallel_workers"] = parallel_workers
                    parallel_worker_mode = str(pending_batch_details.get("parallel_worker_mode", "")).strip()
                    if parallel_worker_mode:
                        details["parallel_worker_mode"] = parallel_worker_mode
                    if bool(pending_batch_details.get("hybrid_lineages", False)):
                        details["hybrid_lineages"] = True
                    append_ui_event(
                        latest_project,
                        "batch-finished",
                        f"Batch failed for {', '.join(step_ids)}. Cause: {error_message}",
                        details,
                    )
            clear_pending_events()

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
                except HANDLED_OPERATION_EXCEPTIONS as exc:
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
                    pending_started_steps = [
                        {
                            "step_id": step.step_id,
                            "title": step.title,
                            "step_kind": step_kind,
                        }
                    ]
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
                    clear_pending_events()
                    if result_step.status == "paused":
                        append_ui_event(project, "run-paused", "Paused immediately because an immediate stop was requested.")
                    if result_step.status != "completed":
                        break
                    continue
                if hybrid_lineages:
                    step_ids = [item.step_id for item in batch]
                    pending_started_steps = [
                        {
                            "step_id": step.step_id,
                            "title": step.title,
                            "execution_mode": "parallel",
                            "hybrid_lineages": "true",
                        }
                        for step in batch
                    ]
                    pending_batch_details = {
                        "step_ids": step_ids,
                        "execution_mode": "parallel",
                        "parallel_workers": parallel_plan.recommended_workers,
                        "parallel_worker_mode": parallel_plan.worker_mode,
                        "hybrid_lineages": True,
                    }
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
                    clear_pending_events()
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
                    pending_started_steps = [
                        {
                            "step_id": step.step_id,
                            "title": step.title,
                            "execution_mode": "parallel",
                        }
                        for step in batch
                    ]
                    pending_batch_details = {
                        "step_ids": step_ids,
                        "execution_mode": "parallel",
                        "parallel_workers": parallel_plan.recommended_workers,
                        "parallel_worker_mode": parallel_plan.worker_mode,
                    }
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
                    clear_pending_events()
                    if any(item.status == "paused" for item in result_steps):
                        append_ui_event(project, "run-paused", "Paused immediately because an immediate stop was requested.")
                    if any(item.status != "completed" for item in result_steps):
                        break
                    continue
                step = batch[0]
                pending_started_steps = [{"step_id": step.step_id, "title": step.title}]
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
                clear_pending_events()
                if result_step.status == "paused":
                    append_ui_event(project, "run-paused", "Paused immediately because an immediate stop was requested.")
                if result_step.status != "completed":
                    break
            latest = ctx.orchestrator.local_project(project_dir)
            if latest is not None:
                append_ui_event(latest, "run-finished", "Finished the run loop for the current project.")
                return ctx.detail_payload(latest)
            return ctx.detail_payload(project)
        except HANDLED_OPERATION_EXCEPTIONS:
            latest = ctx.orchestrator.local_project(project_dir) or project
            failure_message = str(latest.loop_state.stop_reason or "").strip()
            if not failure_message:
                failure_message = "Run failed."
            mark_pending_steps_failed(latest, failure_message)
            raise
        finally:
            latest = ctx.orchestrator.local_project(project_dir)
            if latest is not None:
                save_run_control(latest, default_run_control())
                execution_stop_registry.clear(execution_scope_id(latest))

    def run_closeout(ctx: BridgeCommandContext) -> dict:
        project_dir, runtime, branch, origin_url, _display_name = common_project_inputs(ctx.payload, ctx.orchestrator)
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
        ctx.orchestrator.clear_latest_failure_status(project)
        try:
            append_ui_event(project, "closeout-started", "Started project closeout.")
            try:
                project, saved = ctx.orchestrator.run_execution_closeout(
                    project_dir=project_dir,
                    runtime=runtime,
                    branch=branch,
                    origin_url=origin_url,
                )
            except HANDLED_OPERATION_EXCEPTIONS as exc:
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

    def run_manual_debugger(ctx: BridgeCommandContext) -> dict:
        project_dir, runtime, branch, origin_url, _display_name = common_project_inputs(ctx.payload, ctx.orchestrator)
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
        append_ui_event(project, "manual-debugger-started", "Started manual debugger recovery.")
        try:
            project, saved, result = ctx.orchestrator.run_manual_debugger_recovery(
                project_dir=project_dir,
                runtime=runtime,
                branch=branch,
                origin_url=origin_url,
            )
        except ImmediateStopRequested as exc:
            latest_project = ctx.orchestrator.local_project(project_dir) or project
            append_ui_event(
                latest_project,
                "manual-debugger-finished",
                str(exc).strip() or "Manual debugger stopped by user.",
                {"status": "paused"},
            )
            return ctx.detail_payload(latest_project)
        except HANDLED_OPERATION_EXCEPTIONS as exc:
            latest_project = ctx.orchestrator.local_project(project_dir)
            if latest_project is not None:
                append_ui_event(
                    latest_project,
                    "manual-debugger-finished",
                    f"Manual debugger failed: {str(exc).strip() or 'unknown error'}",
                    {"status": "failed"},
                )
            raise
        append_ui_event(
            project,
            "manual-debugger-finished",
            f"Manual debugger finished. {str(result.get('summary', '')).strip()}",
            {
                "status": "completed",
                "pass_name": result.get("pass_name", ""),
                "commit_hash": result.get("commit_hash", ""),
            },
        )
        return ctx.detail_payload(project)

    def run_manual_merger(ctx: BridgeCommandContext) -> dict:
        project_dir, runtime, branch, origin_url, _display_name = common_project_inputs(ctx.payload, ctx.orchestrator)
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
        append_ui_event(project, "manual-merger-started", "Started manual merger recovery.")
        try:
            project, saved, result = ctx.orchestrator.run_manual_merger_recovery(
                project_dir=project_dir,
                runtime=runtime,
                branch=branch,
                origin_url=origin_url,
            )
        except ImmediateStopRequested as exc:
            latest_project = ctx.orchestrator.local_project(project_dir) or project
            append_ui_event(
                latest_project,
                "manual-merger-finished",
                str(exc).strip() or "Manual merger stopped by user.",
                {"status": "paused"},
            )
            return ctx.detail_payload(latest_project)
        except HANDLED_OPERATION_EXCEPTIONS as exc:
            latest_project = ctx.orchestrator.local_project(project_dir)
            if latest_project is not None:
                append_ui_event(
                    latest_project,
                    "manual-merger-finished",
                    f"Manual merger failed: {str(exc).strip() or 'unknown error'}",
                    {"status": "failed"},
                )
            raise
        append_ui_event(
            project,
            "manual-merger-finished",
            f"Manual merger finished. {str(result.get('summary', '')).strip()}",
            {
                "status": "completed",
                "pass_name": result.get("pass_name", ""),
                "commit_hash": result.get("commit_hash", ""),
            },
        )
        return ctx.detail_payload(project)

    def send_chat_message(ctx: BridgeCommandContext) -> dict:
        project = resolve_project(ctx.orchestrator, ctx.payload)
        message = str(ctx.payload.get("message", "")).strip()
        if not message:
            raise ValueError("message is required.")
        chat_mode = str(ctx.payload.get("chat_mode", "conversation")).strip().lower()
        if chat_mode not in {"conversation", "review", "debugger", "merger"}:
            chat_mode = "conversation"
        session_id = str(ctx.payload.get("session_id", "")).strip()
        create_new_session = coerce_bool(ctx.payload.get("create_new_session", False), False)

        if chat_mode in {"conversation", "review"}:
            plan_state = ctx.orchestrator.load_execution_plan_state(project)
            try:
                result = execute_conversation_turn(
                    project,
                    plan_state=plan_state,
                    user_message=message,
                    mode=chat_mode,
                    session_id=session_id,
                    create_new_session=create_new_session,
                )
                return {
                    **result,
                    "chat_mode": chat_mode,
                    "project": chat_project_payload(project),
                    "emit_project_changed": False,
                }
            finally:
                execution_stop_registry.clear(execution_scope_id(project))
                save_run_control(project, default_run_control())

        runtime_payload = ctx.payload.get("runtime", {})
        runtime_payload = runtime_payload if isinstance(runtime_payload, dict) else {}
        payload_with_prompt = {
            **ctx.payload,
            "runtime": {
                **runtime_payload,
                "extra_prompt": message,
            },
        }
        project_dir, runtime, branch, origin_url, _display_name = common_project_inputs(payload_with_prompt, ctx.orchestrator)
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
        session = resolve_chat_session(
            project,
            session_id=session_id,
            create_new=create_new_session,
            title_hint=message,
        )
        save_chat_message(
            project,
            session.session_id,
            role="user",
            text=message,
            mode=chat_mode,
        )

        error = ""
        detail = None
        assistant_text = ""
        metadata: dict[str, object] = {
            "command": "run-manual-debugger" if chat_mode == "debugger" else "run-manual-merger",
        }

        if chat_mode == "debugger":
            append_ui_event(project, "manual-debugger-started", "Started manual debugger recovery from chat.")
            try:
                project, _saved, result = ctx.orchestrator.run_manual_debugger_recovery(
                    project_dir=project_dir,
                    runtime=runtime,
                    branch=branch,
                    origin_url=origin_url,
                )
                assistant_text = f"Manual debugger finished. {str(result.get('summary', '')).strip()}".strip()
                metadata.update(
                    {
                        "pass_name": str(result.get("pass_name", "")).strip(),
                        "commit_hash": str(result.get("commit_hash", "")).strip(),
                    }
                )
                append_ui_event(
                    project,
                    "manual-debugger-finished",
                    assistant_text,
                    {
                        "status": "completed",
                        "pass_name": metadata.get("pass_name", ""),
                        "commit_hash": metadata.get("commit_hash", ""),
                        "source": "chat",
                    },
                )
                detail = ctx.detail_payload(project)
            except ImmediateStopRequested as exc:
                assistant_text = str(exc).strip() or "Manual debugger stopped."
                metadata["interrupted"] = True
                append_ui_event(
                    project,
                    "manual-debugger-finished",
                    assistant_text,
                    {"status": "paused", "source": "chat"},
                )
            except HANDLED_OPERATION_EXCEPTIONS as exc:
                error = str(exc).strip() or "Manual debugger recovery failed."
                assistant_text = error
                append_ui_event(
                    project,
                    "manual-debugger-finished",
                    f"Manual debugger failed: {assistant_text}",
                    {"status": "failed", "source": "chat"},
                )
        else:
            append_ui_event(project, "manual-merger-started", "Started manual merger recovery from chat.")
            try:
                project, _saved, result = ctx.orchestrator.run_manual_merger_recovery(
                    project_dir=project_dir,
                    runtime=runtime,
                    branch=branch,
                    origin_url=origin_url,
                )
                assistant_text = f"Manual merger finished. {str(result.get('summary', '')).strip()}".strip()
                metadata.update(
                    {
                        "pass_name": str(result.get("pass_name", "")).strip(),
                        "commit_hash": str(result.get("commit_hash", "")).strip(),
                    }
                )
                append_ui_event(
                    project,
                    "manual-merger-finished",
                    assistant_text,
                    {
                        "status": "completed",
                        "pass_name": metadata.get("pass_name", ""),
                        "commit_hash": metadata.get("commit_hash", ""),
                        "source": "chat",
                    },
                )
                detail = ctx.detail_payload(project)
            except ImmediateStopRequested as exc:
                assistant_text = str(exc).strip() or "Manual merger stopped."
                metadata["interrupted"] = True
                append_ui_event(
                    project,
                    "manual-merger-finished",
                    assistant_text,
                    {"status": "paused", "source": "chat"},
                )
            except HANDLED_OPERATION_EXCEPTIONS as exc:
                error = str(exc).strip() or "Manual merger recovery failed."
                assistant_text = error
                append_ui_event(
                    project,
                    "manual-merger-finished",
                    f"Manual merger failed: {assistant_text}",
                    {"status": "failed", "source": "chat"},
                )

        save_chat_message(
            project,
            session.session_id,
            role="system" if error or metadata.get("interrupted") else "assistant",
            text=assistant_text or ("Recovery finished." if not error else error),
            mode=chat_mode,
            status="cancelled" if metadata.get("interrupted") else ("failed" if error else "completed"),
            metadata=metadata,
        )
        rebuild_chat_session_files(project, session.session_id)
        return {
            "chat": chat_payload(project, session_id=session.session_id, activate=True),
            "chat_mode": chat_mode,
            "project": chat_project_payload(project),
            "detail": detail,
            "error": error,
            "emit_project_changed": not bool(error),
        }

    return {
        "request-stop": request_stop,
        "approve-checkpoint": approve_checkpoint,
        "run-plan": run_plan,
        "run-closeout": run_closeout,
        "run-manual-debugger": run_manual_debugger,
        "run-manual-merger": run_manual_merger,
        "send-chat-message": send_chat_message,
    }
