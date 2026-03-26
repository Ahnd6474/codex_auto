from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from .codex_app_server import fetch_codex_backend_snapshot
from .model_providers import normalize_local_model_provider, normalize_model_provider, provider_preset
from .models import ExecutionPlanState, ProjectContext
from .orchestrator import Orchestrator
from .runtime_insights import build_runtime_insights
from .share import project_share_payload
from .utils import compact_text, read_json, read_jsonl_tail, read_last_jsonl, read_text, write_json


DETAIL_CACHE_VERSION = 1


def _path_signature(path: Path) -> str:
    if not path.exists():
        return f"{path.name}:missing"
    try:
        stat = path.stat()
    except OSError:
        return f"{path.name}:unavailable"
    kind = "dir" if path.is_dir() else "file"
    return f"{path.name}:{kind}:{stat.st_size}:{stat.st_mtime_ns}"


def _preview_tree_signature(path: Path, max_entries: int = 16, child_limit: int = 8) -> str:
    if not path.exists() or not path.is_dir():
        return f"{path.name}:missing"
    try:
        children = sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
    except OSError:
        return f"{path.name}:unavailable"
    digest = hashlib.sha1()
    digest.update(str(path).encode("utf-8"))
    for child in children[:max_entries]:
        digest.update(_path_signature(child).encode("utf-8"))
        digest.update(str(child.name).encode("utf-8"))
        if child.is_dir():
            try:
                grandchildren = sorted(child.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
            except OSError:
                digest.update(b"grandchildren:unavailable")
            else:
                for grandchild in grandchildren[:child_limit]:
                    digest.update(_path_signature(grandchild).encode("utf-8"))
                    digest.update(str(grandchild.name).encode("utf-8"))
    digest.update(f"count:{len(children)}".encode("utf-8"))
    return digest.hexdigest()


def project_detail_content_signature(project: ProjectContext, detail_level: str) -> str:
    digest = hashlib.sha1()
    digest.update(f"detail-cache-v{DETAIL_CACHE_VERSION}:{detail_level}".encode("utf-8"))
    digest.update(str(project.metadata.current_status).encode("utf-8"))
    digest.update(str(project.metadata.last_run_at or "").encode("utf-8"))
    digest.update(str(project.metadata.current_safe_revision or "").encode("utf-8"))
    digest.update(str(project.loop_state.current_task or "").encode("utf-8"))
    tracked_files = [
        project.paths.metadata_file,
        project.paths.project_config_file,
        project.paths.loop_state_file,
        project.paths.execution_plan_file,
        project.paths.ui_control_file,
        project.paths.block_log_file,
        project.paths.pass_log_file,
        project.paths.logs_dir / "test_runs.jsonl",
        project.paths.ui_event_log_file,
        project.paths.checkpoint_state_file,
        project.paths.checkpoint_timeline_file,
        project.paths.attempt_history_file,
        project.paths.closeout_report_file,
        project.paths.block_review_file,
        project.paths.execution_flow_svg_file,
    ]
    if str(detail_level).strip().lower() == "full":
        tracked_files.extend(
            [
                project.paths.active_task_file,
                project.paths.mid_term_plan_file,
                project.paths.scope_guard_file,
                project.paths.research_notes_file,
                project.paths.closeout_report_docx_file,
            ]
        )
    for path in tracked_files:
        digest.update(_path_signature(path).encode("utf-8"))
    if str(detail_level).strip().lower() == "full":
        for path in [
            project.paths.repo_dir,
            project.paths.docs_dir,
            project.paths.reports_dir,
            project.paths.state_dir,
            project.paths.logs_dir,
            project.paths.memory_dir,
        ]:
            digest.update(_preview_tree_signature(path).encode("utf-8"))
    return digest.hexdigest()


def _detail_cache_file(project: ProjectContext, detail_level: str) -> Path:
    normalized_detail_level = "core" if str(detail_level).strip().lower() == "core" else "full"
    return project.paths.state_dir / f"PROJECT_DETAIL_CACHE_{normalized_detail_level.upper()}.json"


def _detail_signature(content_signature: str, codex_status: dict[str, Any]) -> str:
    digest = hashlib.sha1()
    digest.update(content_signature.encode("utf-8"))
    digest.update(json.dumps(codex_status, sort_keys=True).encode("utf-8"))
    return digest.hexdigest()


def progress_caption(plan_state: ExecutionPlanState) -> str:
    completed = len([step for step in plan_state.steps if step.status == "completed"])
    total = len(plan_state.steps)
    if total == 0:
        return "No plan yet"
    if completed == total:
        if plan_state.closeout_status == "completed":
            return f"Completed {completed}/{total} steps, closeout completed"
        if plan_state.closeout_status == "running":
            return f"Completed {completed}/{total} steps, closeout running"
        if plan_state.closeout_status == "failed":
            return f"Completed {completed}/{total} steps, closeout failed"
        return f"Completed {completed}/{total} steps, closeout pending"
    uses_dag = (
        str(plan_state.execution_mode).strip().lower() == "parallel"
        and any(step.depends_on or step.owned_paths for step in plan_state.steps)
    )
    if uses_dag:
        completed_ids = {step.step_id for step in plan_state.steps if step.status == "completed"}
        ready = [
            step.step_id
            for step in plan_state.steps
            if step.status != "completed"
            and all(dependency in completed_ids for dependency in step.depends_on)
        ]
        return f"Completed {completed}/{total} steps, ready: {', '.join(ready) if ready else 'blocked'}"
    next_step = next((step.step_id for step in plan_state.steps if step.status != "completed"), "done")
    return f"Completed {completed}/{total} steps, next: {next_step}"


def project_summary(orchestrator: Orchestrator, project: ProjectContext, plan_state: ExecutionPlanState | None = None) -> str:
    plan = plan_state or orchestrator.load_execution_plan_state(project)
    remaining = [step.step_id for step in plan.steps if step.status != "completed"]
    recent_blocks = read_jsonl_tail(project.paths.block_log_file, 5)
    recent_statuses = [str(item.get("status", "")) for item in recent_blocks][-3:]
    runtime_provider = normalize_model_provider(str(getattr(project.runtime, "model_provider", "openai") or "openai").strip())
    local_provider = normalize_local_model_provider(str(getattr(project.runtime, "local_model_provider", "") or "").strip())
    preset = provider_preset(runtime_provider)
    if runtime_provider == "oss":
        provider_summary = f"{preset.display_name}/{local_provider or 'oss'}"
    else:
        provider_summary = preset.display_name
    lines = [
        f"Name: {project.metadata.display_name or project.metadata.slug}",
        f"Directory: {project.metadata.repo_path}",
        f"GitHub: {project.metadata.origin_url or 'Not connected'}",
        f"Branch: {project.metadata.branch}",
        f"Status: {project.metadata.current_status}",
        f"Model: {project.runtime.model}  ({project.runtime.effort}) [{provider_summary}]",
        f"Verification: {plan.default_test_command or project.runtime.test_cmd}",
        f"Remaining Steps: {', '.join(remaining) if remaining else 'None'}",
        f"Closeout: {plan.closeout_status}",
    ]
    if plan.plan_title.strip():
        lines.append(f"Plan Title: {plan.plan_title.strip()}")
    if project.metadata.last_run_at:
        lines.append(f"Last Run: {project.metadata.last_run_at}")
    if recent_statuses:
        lines.append(f"Recent Blocks: {', '.join(recent_statuses)}")
    return "\n".join(lines)


def project_stats(plan_state: ExecutionPlanState) -> dict[str, Any]:
    completed = len([step for step in plan_state.steps if step.status == "completed"])
    failed = len([step for step in plan_state.steps if step.status == "failed"])
    running = len([step for step in plan_state.steps if step.status == "running"])
    return {
        "total_steps": len(plan_state.steps),
        "completed_steps": completed,
        "failed_steps": failed,
        "running_steps": running,
        "remaining_steps": max(0, len(plan_state.steps) - completed),
    }


def workspace_snapshot(projects: list[ProjectContext]) -> dict[str, Any]:
    running = 0
    ready = 0
    failed = 0
    for project in projects:
        status = project.metadata.current_status
        if status.startswith("running:"):
            running += 1
        elif status in {"setup_ready", "plan_ready", "plan_completed", "closed_out", "ready"}:
            ready += 1
        elif status.endswith("failed") or status in {"failed", "closeout_failed"}:
            failed += 1
    return {
        "project_count": len(projects),
        "ready_like": ready,
        "running": running,
        "failed": failed,
    }


def safe_json(path: Path, default: Any = None) -> Any:
    try:
        return read_json(path, default=default)
    except Exception:
        return default


def safe_text(path: Path, default: str = "") -> str:
    try:
        return read_text(path, default=default)
    except Exception:
        return default


def preview_text(path: Path, default: str = "", max_chars: int = 12_000) -> str:
    return compact_text(safe_text(path, default=default), max_chars=max_chars)


def preview_tree(path: Path, max_entries: int = 16) -> list[dict[str, Any]]:
    if not path.exists() or not path.is_dir():
        return []
    try:
        children = sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
    except OSError:
        return [{"label": "Directory unavailable", "path": str(path), "kind": "meta"}]
    entries: list[dict[str, Any]] = []
    for child in children[:max_entries]:
        item = {
            "label": child.name,
            "path": str(child),
            "kind": "dir" if child.is_dir() else "file",
        }
        if child.is_dir():
            try:
                grandchildren = sorted(child.iterdir(), key=lambda entry: (not entry.is_dir(), entry.name.lower()))
            except OSError:
                item["children"] = [{"label": "Directory unavailable", "path": str(child), "kind": "meta"}]
            else:
                item["children"] = [
                    {
                        "label": grandchild.name,
                        "path": str(grandchild),
                        "kind": "dir" if grandchild.is_dir() else "file",
                    }
                    for grandchild in grandchildren[:8]
                ]
        entries.append(item)
    if len(children) > max_entries:
        entries.append({"label": f"+{len(children) - max_entries} more", "path": str(path), "kind": "meta"})
    return entries


def managed_workspace_tree(context: ProjectContext) -> list[dict[str, Any]]:
    sections = [
        ("Repository", context.paths.repo_dir),
        ("Docs", context.paths.docs_dir),
        ("Reports", context.paths.reports_dir),
        ("State", context.paths.state_dir),
        ("Logs", context.paths.logs_dir),
        ("Memory", context.paths.memory_dir),
    ]
    return [
        {
            "label": label,
            "path": str(path),
            "kind": "dir",
            "children": preview_tree(path),
        }
        for label, path in sections
    ]


def report_payload(context: ProjectContext) -> dict[str, Any]:
    return {
        "closeout_report_text": preview_text(
            context.paths.closeout_report_file,
            default="# Closeout Report\n\nNo closeout has been run yet.\n",
        ),
        "attempt_history_text": preview_text(context.paths.attempt_history_file, default="No attempt history recorded yet.\n"),
        "word_report_enabled": bool(context.runtime.generate_word_report),
        "word_report_path": str(context.paths.closeout_report_docx_file) if context.paths.closeout_report_docx_file.exists() else "",
    }


def history_payload(context: ProjectContext) -> dict[str, Any]:
    return {
        "ui_events": read_jsonl_tail(context.paths.ui_event_log_file, 40),
        "blocks": read_jsonl_tail(context.paths.block_log_file, 20),
        "passes": read_jsonl_tail(context.paths.pass_log_file, 30),
        "test_runs": read_jsonl_tail(context.paths.logs_dir / "test_runs.jsonl", 20),
    }


def checkpoint_payload(context: ProjectContext) -> dict[str, Any]:
    raw = safe_json(context.paths.checkpoint_state_file, default={"checkpoints": []})
    raw_items = raw.get("checkpoints", []) if isinstance(raw, dict) else []
    checkpoints = [item for item in raw_items if isinstance(item, dict)]
    pending = next((item for item in checkpoints if item.get("status") == "awaiting_review"), None)
    if pending is None and context.loop_state.current_checkpoint_id:
        pending = next(
            (item for item in checkpoints if item.get("checkpoint_id") == context.loop_state.current_checkpoint_id),
            None,
        )
    return {
        "items": checkpoints,
        "pending": pending,
        "timeline_markdown": preview_text(context.paths.checkpoint_timeline_file, default="No checkpoints recorded yet.\n"),
    }


def config_payload(context: ProjectContext) -> dict[str, Any]:
    return {
        "metadata_json": safe_json(context.paths.metadata_file, default={}) or {},
        "runtime_json": safe_json(context.paths.project_config_file, default={}) or {},
        "loop_state_json": safe_json(context.paths.loop_state_file, default={}) or {},
        "run_control_json": safe_json(context.paths.ui_control_file, default={}) or {},
    }


def bottom_panel_payload(
    context: ProjectContext,
    plan_state: ExecutionPlanState,
    codex_status: dict[str, Any],
    *,
    detail_level: str = "full",
) -> dict[str, Any]:
    latest_block = read_last_jsonl(context.paths.block_log_file) or {}
    latest_pass = read_last_jsonl(context.paths.pass_log_file) or {}
    usage = recent_usage(context)
    return {
        "execution_log_lines": build_activity_lines(context, plan_state) if detail_level == "full" else [],
        "event_json": {
            "latest_block": latest_block,
            "latest_pass": latest_pass,
            "run_control": safe_json(context.paths.ui_control_file, default={}) or {},
            "loop_state": safe_json(context.paths.loop_state_file, default={}) or {},
        },
        "token_usage": usage,
        "runtime_insights": build_runtime_insights(context, plan_state, usage),
        "codex_status": codex_status,
        "test_runs": read_jsonl_tail(context.paths.logs_dir / "test_runs.jsonl", 12 if detail_level == "full" else 5),
        "git_status": {
            "branch": context.metadata.branch,
            "repo_kind": context.metadata.repo_kind,
            "origin_url": context.metadata.origin_url,
            "current_status": context.metadata.current_status,
            "safe_revision": context.metadata.current_safe_revision,
            "last_commit_hash": context.loop_state.last_commit_hash,
            "current_checkpoint_id": context.loop_state.current_checkpoint_id,
            "pending_checkpoint_approval": context.loop_state.pending_checkpoint_approval,
        },
    }


def recent_usage(context: ProjectContext) -> dict[str, int]:
    usage: dict[str, int] = {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_output_tokens": 0,
        "total_tokens": 0,
    }
    for item in read_jsonl_tail(context.paths.pass_log_file, 25):
        raw = item.get("usage", {})
        if not isinstance(raw, dict):
            continue
        for key in usage:
            value = raw.get(key, 0)
            if isinstance(value, int):
                usage[key] += value
    if usage["total_tokens"] <= 0:
        usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"] + usage["reasoning_output_tokens"]
    return usage


def build_activity_lines(context: ProjectContext, plan_state: ExecutionPlanState) -> list[str]:
    lines: list[str] = []
    for event in reversed(read_jsonl_tail(context.paths.ui_event_log_file, 30)):
        timestamp = str(event.get("timestamp", "")).strip()
        message = str(event.get("message", "")).strip()
        event_type = str(event.get("event_type", "")).strip()
        details = event.get("details", {})
        detail_suffix = ""
        if isinstance(details, dict):
            step_id = str(details.get("step_id", "")).strip()
            if step_id:
                detail_suffix = f" [{step_id}]"
        lines.append(f"{timestamp} | {event_type}{detail_suffix} | {message}")
    if lines:
        return lines

    if str(context.metadata.current_status).strip().lower().startswith("running:debug"):
        latest_pass = read_last_jsonl(context.paths.pass_log_file)
        if isinstance(latest_pass, dict) and latest_pass:
            title = compact_text(str(latest_pass.get("selected_task", "")).strip(), max_chars=120)
            test_results = latest_pass.get("test_results", {})
            summary = ""
            if isinstance(test_results, dict):
                summary = compact_text(str(test_results.get("summary", "")).strip(), max_chars=120)
            rollback = str(latest_pass.get("rollback_status", "")).strip() or "debugger_invoked"
            lines.append(
                f"debugger | {rollback} | Debugging {title or 'current task'} | "
                f"{summary or 'Inspecting the failing verification logs and preparing a recovery fix.'}"
            )
            return lines
        lines.append(
            "debugger | running | Debugging current task | Inspecting the failing verification logs and preparing a recovery fix."
        )
        return lines

    for block in reversed(read_jsonl_tail(context.paths.block_log_file, 12)):
        block_index = block.get("block_index", "?")
        status = block.get("status", "unknown")
        title = compact_text(str(block.get("selected_task", "")).strip(), max_chars=120)
        summary = compact_text(str(block.get("test_summary", "")).strip(), max_chars=120)
        lines.append(f"block {block_index} | {status} | {title} | {summary}")
    if lines:
        return lines

    if plan_state.steps:
        lines.append(f"Plan loaded with {len(plan_state.steps)} step(s).")
    else:
        lines.append("No plan has been generated yet.")
    return lines


def project_list_item_payload(orchestrator: Orchestrator, project: ProjectContext) -> dict[str, Any]:
    plan_state = orchestrator.load_execution_plan_state(project)
    detail = project.metadata.origin_url or f"Branch {project.metadata.branch}"
    return {
        "repo_id": project.metadata.repo_id,
        "slug": project.metadata.slug,
        "display_name": project.metadata.display_name or project.metadata.slug,
        "repo_path": str(project.metadata.repo_path),
        "origin_url": project.metadata.origin_url,
        "branch": project.metadata.branch,
        "status": project.metadata.current_status,
        "detail": detail,
        "created_at": project.metadata.created_at,
        "last_run_at": project.metadata.last_run_at,
        "summary": project_summary(orchestrator, project, plan_state),
        "progress": progress_caption(plan_state),
        "stats": project_stats(plan_state),
        "closeout_status": plan_state.closeout_status,
    }


def _build_project_detail_base_payload(
    orchestrator: Orchestrator,
    project: ProjectContext,
    normalized_detail_level: str,
    load_run_control: Callable[[ProjectContext], dict[str, Any]],
) -> dict[str, Any]:
    plan_state = orchestrator.load_execution_plan_state(project)
    control = load_run_control(project)
    recent_usage_payload = recent_usage(project)
    runtime_insights = build_runtime_insights(project, plan_state, recent_usage_payload)
    if normalized_detail_level == "full":
        recent_blocks = read_jsonl_tail(project.paths.block_log_file, 8)
        recent_passes = read_jsonl_tail(project.paths.pass_log_file, 12)
        reports = report_payload(project)
        history = history_payload(project)
        checkpoints = checkpoint_payload(project)
        config = config_payload(project)
        workspace_tree = managed_workspace_tree(project)
        activity = build_activity_lines(project, plan_state)
        latest_block = read_last_jsonl(project.paths.block_log_file)
        latest_pass = read_last_jsonl(project.paths.pass_log_file)
    else:
        recent_blocks = []
        recent_passes = []
        pending_checkpoint = checkpoint_payload(project).get("pending")
        reports = {}
        history = {
            "ui_events": [],
            "blocks": [],
            "passes": [],
            "test_runs": [],
        }
        checkpoints = {
            "items": [],
            "pending": pending_checkpoint,
            "timeline_markdown": "",
        }
        config = {}
        workspace_tree = []
        activity = build_activity_lines(project, plan_state)[:8]
        latest_block = None
        latest_pass = None
    bottom_panels = bottom_panel_payload(
        project,
        plan_state,
        {},
        detail_level=normalized_detail_level,
    )
    snapshot = {
        "project": project.metadata.to_dict(),
        "runtime": project.runtime.to_dict(),
        "loop_state": project.loop_state.to_dict(),
        "plan": plan_state.to_dict(),
        "recent_blocks": recent_blocks,
        "recent_passes": recent_passes,
        "recent_usage": recent_usage_payload,
        "runtime_insights": runtime_insights,
        "codex_status": {},
        "run_control": control,
        "latest_block": latest_block,
        "latest_pass": latest_pass,
    }
    return {
        "detail_level": normalized_detail_level,
        "project": project.metadata.to_dict(),
        "runtime": project.runtime.to_dict(),
        "loop_state": project.loop_state.to_dict(),
        "plan": plan_state.to_dict(),
        "summary": project_summary(orchestrator, project, plan_state),
        "progress": progress_caption(plan_state),
        "stats": project_stats(plan_state),
        "codex_status": {},
        "activity": activity,
        "runtime_insights": runtime_insights,
        "snapshot": snapshot,
        "run_control": control,
        "recent_blocks": recent_blocks,
        "recent_passes": recent_passes,
        "workspace_tree": workspace_tree,
        "reports": reports,
        "history": history,
        "checkpoints": checkpoints,
        "config": config,
        "files": {
            "project_root": str(project.paths.project_root),
            "repo_dir": str(project.paths.repo_dir),
            "execution_plan_file": str(project.paths.execution_plan_file),
            "ui_control_file": str(project.paths.ui_control_file),
            "ui_event_log_file": str(project.paths.ui_event_log_file),
        },
        "bottom_panels": bottom_panels,
        "github": {
            "connected": bool(project.metadata.origin_url),
            "origin_url": project.metadata.origin_url,
            "repo_url": project.metadata.repo_url,
            "branch": project.metadata.branch,
        },
        "share": project_share_payload(orchestrator.workspace.workspace_root, project),
    }


def _cached_project_detail_base_payload(
    orchestrator: Orchestrator,
    project: ProjectContext,
    normalized_detail_level: str,
    load_run_control: Callable[[ProjectContext], dict[str, Any]],
) -> tuple[dict[str, Any], str, bool]:
    content_signature = project_detail_content_signature(project, normalized_detail_level)
    cache_file = _detail_cache_file(project, normalized_detail_level)
    cached = read_json(cache_file, default=None)
    if isinstance(cached, dict):
        cached_signature = str(cached.get("content_signature", "")).strip()
        cached_payload = cached.get("payload")
        if (
            int(cached.get("version", 0) or 0) == DETAIL_CACHE_VERSION
            and cached_signature == content_signature
            and isinstance(cached_payload, dict)
        ):
            payload = deepcopy(cached_payload)
            payload["content_signature"] = content_signature
            payload["payload_cache_hit"] = True
            return payload, content_signature, True
    payload = _build_project_detail_base_payload(orchestrator, project, normalized_detail_level, load_run_control)
    payload["content_signature"] = content_signature
    payload["payload_cache_hit"] = False
    write_json(
        cache_file,
        {
            "version": DETAIL_CACHE_VERSION,
            "content_signature": content_signature,
            "payload": payload,
        },
    )
    return deepcopy(payload), content_signature, False


def _finalize_project_detail_payload(
    base_payload: dict[str, Any],
    *,
    content_signature: str,
    codex_status: dict[str, Any],
    payload_cache_hit: bool,
) -> dict[str, Any]:
    payload = deepcopy(base_payload)
    payload["codex_status"] = codex_status
    payload["content_signature"] = content_signature
    payload["detail_signature"] = _detail_signature(content_signature, codex_status)
    payload["payload_cache_hit"] = payload_cache_hit
    snapshot = payload.get("snapshot")
    if isinstance(snapshot, dict):
        snapshot["codex_status"] = codex_status
    bottom_panels = payload.get("bottom_panels")
    if isinstance(bottom_panels, dict):
        bottom_panels["codex_status"] = codex_status
    return payload


def project_detail_payload(
    orchestrator: Orchestrator,
    project: ProjectContext,
    *,
    load_run_control: Callable[[ProjectContext], dict[str, Any]],
    fetch_codex_status: Callable[[str], Any] = fetch_codex_backend_snapshot,
    refresh_codex_status: bool = True,
    detail_level: str = "full",
) -> dict[str, Any]:
    normalized_detail_level = "core" if str(detail_level).strip().lower() == "core" else "full"
    base_payload, content_signature, payload_cache_hit = _cached_project_detail_base_payload(
        orchestrator,
        project,
        normalized_detail_level,
        load_run_control,
    )
    codex_status = (
        fetch_codex_status(project.runtime.codex_path).to_dict()
        if refresh_codex_status
        else {}
    )
    return _finalize_project_detail_payload(
        base_payload,
        content_signature=content_signature,
        codex_status=codex_status,
        payload_cache_hit=payload_cache_hit,
    )


def list_projects_payload(orchestrator: Orchestrator) -> dict[str, Any]:
    projects = sorted(orchestrator.list_projects(), key=lambda item: item.metadata.created_at, reverse=True)
    return {
        "projects": [project_list_item_payload(orchestrator, project) for project in projects],
        "workspace": workspace_snapshot(projects),
    }
