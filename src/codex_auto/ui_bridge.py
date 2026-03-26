from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any

from .model_selection import DEFAULT_MODEL_PRESET_ID, MODEL_PRESETS, model_preset_by_id
from .models import ExecutionPlanState, ProjectContext, RuntimeOptions
from .orchestrator import Orchestrator
from .share import (
    DEFAULT_SHARE_HOST,
    DEFAULT_SHARE_PORT,
    DEFAULT_SHARE_TTL_MINUTES,
    create_share_session,
    project_share_payload,
    public_session_summary,
    revoke_share_session,
    share_server_status_payload,
)
from .utils import append_jsonl, compact_text, now_utc_iso, parse_json_text, read_json, read_jsonl_tail, read_last_jsonl, read_text, write_json


DEFAULT_GUI_WORKSPACE_DIRNAME = ".codex-auto-workspace"
SHARE_SERVER_START_TIMEOUT_SECS = 3.0


def default_workspace_root() -> Path:
    explicit = os.environ.get("CODEX_AUTO_GUI_WORKSPACE")
    if explicit:
        return Path(explicit).expanduser().resolve()
    legacy = (Path.cwd() / DEFAULT_GUI_WORKSPACE_DIRNAME).resolve()
    if legacy.exists():
        return legacy
    return (Path.home() / DEFAULT_GUI_WORKSPACE_DIRNAME).resolve()


def bootstrap_payload(workspace_root: Path) -> dict[str, Any]:
    return {
        "workspace_root": str(workspace_root),
        "model_presets": [
            {
                "preset_id": preset.preset_id,
                "label": preset.label,
                "model": preset.model,
                "effort": preset.effort,
                "description": preset.description,
                "summary": preset.summary(),
            }
            for preset in MODEL_PRESETS
        ],
        "default_runtime": runtime_from_payload({}).to_dict(),
    }


def orchestrator_for(workspace_root: Path) -> Orchestrator:
    return Orchestrator(workspace_root)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def build_pythonpath(root: Path) -> str:
    items = [str(root / "src")]
    existing = os.environ.get("PYTHONPATH", "").strip()
    if existing:
        items.append(existing)
    return os.pathsep.join(items)


def start_share_server_process(workspace_root: Path, host: str = DEFAULT_SHARE_HOST, port: int = DEFAULT_SHARE_PORT) -> dict[str, Any]:
    current = share_server_status_payload(workspace_root)
    if current.get("running"):
        return current

    root = repo_root()
    env = os.environ.copy()
    env["PYTHONPATH"] = build_pythonpath(root)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    command = [
        sys.executable,
        "-m",
        "codex_auto.share_server",
        "--workspace-root",
        str(workspace_root),
        "--host",
        host,
        "--port",
        str(max(0, int(port))),
    ]
    creationflags = 0
    if os.name == "nt":
        creationflags = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
    subprocess.Popen(
        command,
        cwd=root,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
        close_fds=True,
    )

    deadline = time.monotonic() + SHARE_SERVER_START_TIMEOUT_SECS
    while time.monotonic() < deadline:
        status = share_server_status_payload(workspace_root)
        if status.get("running"):
            return status
        time.sleep(0.1)
    raise RuntimeError("Share server did not start in time.")


def stop_share_server_process(workspace_root: Path) -> dict[str, Any]:
    status = share_server_status_payload(workspace_root)
    pid = int(status.get("pid") or 0)
    if pid <= 0:
        return share_server_status_payload(workspace_root)
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        current = share_server_status_payload(workspace_root)
        if not current.get("running"):
            return current
        time.sleep(0.1)
    return share_server_status_payload(workspace_root)


def coerce_positive_int(value: Any, default: int, minimum: int = 1) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(minimum, parsed)


def coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, (int, float)):
        return str(value)
    return None


def normalize_run_control(payload: Any) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    return {
        "stop_after_current_step": coerce_bool(data.get("stop_after_current_step", False), False),
        "requested_at": optional_text(data.get("requested_at")),
        "request_source": optional_text(data.get("request_source")),
    }


def runtime_from_payload(payload: dict[str, Any]) -> RuntimeOptions:
    base = RuntimeOptions(
        approval_mode="never",
        sandbox_mode="danger-full-access",
        allow_push=True,
        checkpoint_interval_blocks=1,
        require_checkpoint_approval=False,
        max_blocks=5,
    ).to_dict()
    merged = {**base, **payload}
    merged["max_blocks"] = coerce_positive_int(merged.get("max_blocks", 5), default=5)
    merged["no_progress_limit"] = coerce_positive_int(merged.get("no_progress_limit", 3), default=3)
    merged["regression_limit"] = coerce_positive_int(merged.get("regression_limit", 3), default=3)
    merged["empty_cycle_limit"] = coerce_positive_int(merged.get("empty_cycle_limit", 3), default=3)
    merged["checkpoint_interval_blocks"] = coerce_positive_int(
        merged.get("checkpoint_interval_blocks", 1),
        default=1,
    )
    merged["allow_push"] = coerce_bool(merged.get("allow_push", True), True)
    merged["require_checkpoint_approval"] = coerce_bool(
        merged.get("require_checkpoint_approval", False),
        False,
    )
    merged["test_cmd"] = str(merged.get("test_cmd", "python -m pytest")).strip() or "python -m pytest"
    merged["model"] = str(merged.get("model", "")).strip()
    merged["model_preset"] = str(merged.get("model_preset", "")).strip()
    merged["effort"] = str(merged.get("effort", "")).strip()

    if not merged["model"]:
        preset = model_preset_by_id(merged["model_preset"] or DEFAULT_MODEL_PRESET_ID)
        merged["model"] = preset.model
    if not merged["effort"]:
        preset = model_preset_by_id(merged["model_preset"] or DEFAULT_MODEL_PRESET_ID)
        merged["effort"] = preset.effort
    if merged["model_preset"] not in {preset.preset_id for preset in MODEL_PRESETS}:
        merged["model_preset"] = ""
    merged["model_selection_mode"] = str(merged.get("model_selection_mode", "slug")).strip() or "slug"
    merged["model_slug_input"] = str(merged.get("model_slug_input", merged["model"])).strip() or merged["model"]
    return RuntimeOptions(**merged)


def parse_plan_state(payload: dict[str, Any]) -> ExecutionPlanState:
    state = ExecutionPlanState.from_dict(payload)
    state.default_test_command = payload.get("default_test_command", state.default_test_command) or state.default_test_command
    return state


def resolve_project(
    orchestrator: Orchestrator,
    payload: dict[str, Any],
) -> ProjectContext:
    repo_id = str(payload.get("repo_id", "")).strip()
    project_dir = str(payload.get("project_dir", "")).strip()
    if repo_id:
        return orchestrator.workspace.load_project_by_id(repo_id)
    if project_dir:
        project = orchestrator.local_project(Path(project_dir))
        if project is None:
            raise KeyError(f"No managed project exists for {project_dir}.")
        return project
    raise ValueError("Either repo_id or project_dir is required.")


def default_run_control() -> dict[str, Any]:
    return {
        "stop_after_current_step": False,
        "requested_at": None,
        "request_source": None,
    }


def load_run_control(context: ProjectContext) -> dict[str, Any]:
    data = read_json(context.paths.ui_control_file, default=None)
    return normalize_run_control(data)


def save_run_control(context: ProjectContext, payload: dict[str, Any]) -> dict[str, Any]:
    state = normalize_run_control(payload)
    write_json(context.paths.ui_control_file, state)
    return state


def clear_stop_request(context: ProjectContext) -> dict[str, Any]:
    state = save_run_control(context, default_run_control())
    append_ui_event(context, "stop-cleared", "Stop-after-step request cleared.")
    return state


def request_stop_after_current_step(context: ProjectContext, request_source: str = "desktop-ui") -> dict[str, Any]:
    state = save_run_control(
        context,
        {
            "stop_after_current_step": True,
            "requested_at": now_utc_iso(),
            "request_source": request_source,
        },
    )
    append_ui_event(context, "stop-requested", "Stop requested after the current step.", state)
    return state


def stop_requested(context: ProjectContext) -> bool:
    return bool(load_run_control(context).get("stop_after_current_step"))


def append_ui_event(context: ProjectContext, event_type: str, message: str, details: dict[str, Any] | None = None) -> None:
    payload = {
        "timestamp": now_utc_iso(),
        "event_type": event_type,
        "message": message,
        "details": details or {},
    }
    append_jsonl(context.paths.ui_event_log_file, payload)


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
    next_step = next((step.step_id for step in plan_state.steps if step.status != "completed"), "done")
    return f"Completed {completed}/{total} steps, next: {next_step}"


def project_summary(orchestrator: Orchestrator, project: ProjectContext, plan_state: ExecutionPlanState | None = None) -> str:
    plan = plan_state or orchestrator.load_execution_plan_state(project)
    remaining = [step.step_id for step in plan.steps if step.status != "completed"]
    recent_blocks = read_jsonl_tail(project.paths.block_log_file, 5)
    recent_statuses = [str(item.get("status", "")) for item in recent_blocks][-3:]
    lines = [
        f"Name: {project.metadata.display_name or project.metadata.slug}",
        f"Directory: {project.metadata.repo_path}",
        f"GitHub: {project.metadata.origin_url or 'Not connected'}",
        f"Branch: {project.metadata.branch}",
        f"Status: {project.metadata.current_status}",
        f"Model: {project.runtime.model}  ({project.runtime.effort})",
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
        "latest_report_json": safe_json(context.paths.reports_dir / "latest_report.json", default={}) or {},
        "closeout_report_text": preview_text(
            context.paths.closeout_report_file,
            default="# Closeout Report\n\nNo closeout has been run yet.\n",
        ),
        "block_review_text": preview_text(context.paths.block_review_file, default="No block review recorded yet.\n"),
        "attempt_history_text": preview_text(context.paths.attempt_history_file, default="No attempt history recorded yet.\n"),
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


def bottom_panel_payload(context: ProjectContext, plan_state: ExecutionPlanState) -> dict[str, Any]:
    latest_block = read_last_jsonl(context.paths.block_log_file) or {}
    latest_pass = read_last_jsonl(context.paths.pass_log_file) or {}
    return {
        "execution_log_lines": build_activity_lines(context, plan_state),
        "event_json": {
            "latest_block": latest_block,
            "latest_pass": latest_pass,
            "run_control": safe_json(context.paths.ui_control_file, default={}) or {},
            "loop_state": safe_json(context.paths.loop_state_file, default={}) or {},
        },
        "token_usage": recent_usage(context),
        "test_runs": read_jsonl_tail(context.paths.logs_dir / "test_runs.jsonl", 12),
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
        "output_tokens": 0,
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


def project_detail_payload(orchestrator: Orchestrator, project: ProjectContext) -> dict[str, Any]:
    plan_state = orchestrator.load_execution_plan_state(project)
    recent_blocks = read_jsonl_tail(project.paths.block_log_file, 8)
    recent_passes = read_jsonl_tail(project.paths.pass_log_file, 12)
    control = load_run_control(project)
    reports = report_payload(project)
    history = history_payload(project)
    checkpoints = checkpoint_payload(project)
    config = config_payload(project)
    workspace_tree = managed_workspace_tree(project)
    bottom_panels = bottom_panel_payload(project, plan_state)
    snapshot = {
        "project": project.metadata.to_dict(),
        "runtime": project.runtime.to_dict(),
        "loop_state": project.loop_state.to_dict(),
        "plan": plan_state.to_dict(),
        "recent_blocks": recent_blocks,
        "recent_passes": recent_passes,
        "recent_usage": recent_usage(project),
        "run_control": control,
        "latest_block": read_last_jsonl(project.paths.block_log_file),
        "latest_pass": read_last_jsonl(project.paths.pass_log_file),
    }
    return {
        "project": project.metadata.to_dict(),
        "runtime": project.runtime.to_dict(),
        "loop_state": project.loop_state.to_dict(),
        "plan": plan_state.to_dict(),
        "summary": project_summary(orchestrator, project, plan_state),
        "progress": progress_caption(plan_state),
        "stats": project_stats(plan_state),
        "activity": build_activity_lines(project, plan_state),
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


def list_projects_payload(orchestrator: Orchestrator) -> dict[str, Any]:
    projects = sorted(orchestrator.list_projects(), key=lambda item: item.metadata.created_at, reverse=True)
    return {
        "projects": [project_list_item_payload(orchestrator, project) for project in projects],
        "workspace": workspace_snapshot(projects),
    }


def common_project_inputs(payload: dict[str, Any]) -> tuple[Path, RuntimeOptions, str, str, str]:
    project_dir_value = str(payload.get("project_dir", "")).strip()
    if not project_dir_value:
        raise ValueError("project_dir is required.")
    project_dir = Path(project_dir_value).expanduser().resolve()
    runtime_payload = payload.get("runtime", {})
    if not isinstance(runtime_payload, dict):
        raise ValueError("runtime payload must be an object.")
    runtime = runtime_from_payload(runtime_payload)
    branch = str(payload.get("branch", "main")).strip() or "main"
    origin_url = str(payload.get("origin_url", "")).strip()
    display_name = str(payload.get("display_name", "")).strip()
    return project_dir, runtime, branch, origin_url, display_name


def run_command(command: str, workspace_root: Path, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    orchestrator = orchestrator_for(workspace_root)

    if command == "bootstrap":
        return bootstrap_payload(workspace_root)

    if command == "list-projects":
        return list_projects_payload(orchestrator)

    if command == "load-project":
        project = resolve_project(orchestrator, payload)
        return project_detail_payload(orchestrator, project)

    if command == "get_share_server_status":
        return share_server_status_payload(workspace_root)

    if command == "start_share_server":
        host = str(payload.get("host", DEFAULT_SHARE_HOST)).strip() or DEFAULT_SHARE_HOST
        port = coerce_positive_int(payload.get("port", DEFAULT_SHARE_PORT), default=DEFAULT_SHARE_PORT, minimum=0)
        return start_share_server_process(workspace_root, host=host, port=port)

    if command == "stop_share_server":
        return stop_share_server_process(workspace_root)

    if command == "save-project-setup":
        project_dir, runtime, branch, origin_url, display_name = common_project_inputs(payload)
        project = orchestrator.setup_local_project(
            project_dir=project_dir,
            runtime=runtime,
            branch=branch,
            origin_url=origin_url,
            display_name=display_name,
        )
        save_run_control(project, default_run_control())
        append_ui_event(project, "project-saved", "Saved project setup from the desktop shell.")
        return project_detail_payload(orchestrator, project)

    if command == "generate-plan":
        project_dir, runtime, branch, origin_url, _display_name = common_project_inputs(payload)
        prompt = str(payload.get("prompt", "")).strip()
        if not prompt:
            raise ValueError("prompt is required.")
        max_steps = max(1, int(str(payload.get("max_steps", runtime.max_blocks) or runtime.max_blocks)))
        existing = orchestrator.local_project(project_dir)
        project, plan_state = orchestrator.generate_execution_plan(
            project_dir=project_dir,
            runtime=runtime,
            project_prompt=prompt,
            branch=branch,
            max_steps=max_steps,
            origin_url=origin_url,
        )
        append_ui_event(
            project,
            "plan-generated",
            f"Generated a new execution plan with {len(plan_state.steps)} step(s).",
            {"max_steps": max_steps},
        )
        if existing is None and payload.get("display_name"):
            project.metadata.display_name = str(payload.get("display_name")).strip()
            orchestrator.workspace.save_project(project)
        return project_detail_payload(orchestrator, project)

    if command == "save-plan":
        project_dir, runtime, branch, origin_url, _display_name = common_project_inputs(payload)
        raw_plan = payload.get("plan", {})
        if not isinstance(raw_plan, dict):
            raise ValueError("plan payload must be an object.")
        plan_state = parse_plan_state(raw_plan)
        project, _saved = orchestrator.update_execution_plan(
            project_dir=project_dir,
            runtime=runtime,
            plan_state=plan_state,
            branch=branch,
            origin_url=origin_url,
        )
        append_ui_event(project, "plan-saved", "Saved the edited execution plan.")
        return project_detail_payload(orchestrator, project)

    if command == "reset-plan":
        project_dir, runtime, branch, origin_url, _display_name = common_project_inputs(payload)
        plan_state = ExecutionPlanState(default_test_command=runtime.test_cmd)
        project, _saved = orchestrator.update_execution_plan(
            project_dir=project_dir,
            runtime=runtime,
            plan_state=plan_state,
            branch=branch,
            origin_url=origin_url,
        )
        append_ui_event(project, "plan-reset", "Reset the execution plan and cleared the prompt.")
        return project_detail_payload(orchestrator, project)

    if command == "request-stop":
        project = resolve_project(orchestrator, payload)
        control = request_stop_after_current_step(project, request_source=str(payload.get("source", "desktop-ui")).strip() or "desktop-ui")
        return {
            "repo_id": project.metadata.repo_id,
            "project_dir": str(project.metadata.repo_path),
            "run_control": control,
        }

    if command == "create_share_session":
        project = resolve_project(orchestrator, payload)
        expires_in_minutes = coerce_positive_int(
            payload.get("expires_in_minutes", DEFAULT_SHARE_TTL_MINUTES),
            default=DEFAULT_SHARE_TTL_MINUTES,
        )
        start_share_server_process(workspace_root)
        session = create_share_session(
            project,
            expires_in_minutes=expires_in_minutes,
            created_by=str(payload.get("created_by", "desktop-ui")).strip() or "desktop-ui",
        )
        append_ui_event(
            project,
            "share-session-created",
            "Created a temporary read-only share session.",
            {"session_id": session.session_id, "expires_at": session.expires_at},
        )
        detail = project_detail_payload(orchestrator, project)
        detail["created_share_session"] = public_session_summary(workspace_root, project, session, include_token=True)
        return detail

    if command == "revoke_share_session":
        project = resolve_project(orchestrator, payload)
        session_id = str(payload.get("session_id", "")).strip()
        if not session_id:
            raise ValueError("session_id is required.")
        session = revoke_share_session(project, session_id)
        append_ui_event(
            project,
            "share-session-revoked",
            "Revoked a temporary read-only share session.",
            {"session_id": session.session_id},
        )
        detail = project_detail_payload(orchestrator, project)
        detail["revoked_share_session"] = public_session_summary(workspace_root, project, session, include_token=False)
        return detail

    if command == "approve-checkpoint":
        project = resolve_project(orchestrator, payload)
        review_notes = str(payload.get("review_notes", "")).strip()
        push = bool(payload.get("push", True))
        orchestrator.approve_checkpoint(
            project.metadata.repo_url,
            project.metadata.branch,
            review_notes=review_notes,
            push=push,
        )
        latest_project = orchestrator.workspace.load_project_by_id(project.metadata.repo_id)
        append_ui_event(latest_project, "checkpoint-approved", "Approved the pending checkpoint.", {"push": push})
        return project_detail_payload(orchestrator, latest_project)

    if command == "run-plan":
        project_dir, runtime, branch, origin_url, _display_name = common_project_inputs(payload)
        raw_plan = payload.get("plan", {})
        if not isinstance(raw_plan, dict):
            raise ValueError("plan payload must be an object.")
        plan_state = parse_plan_state(raw_plan)
        project, saved = orchestrator.update_execution_plan(
            project_dir=project_dir,
            runtime=runtime,
            plan_state=plan_state,
            branch=branch,
            origin_url=origin_url,
        )
        save_run_control(project, default_run_control())
        append_ui_event(project, "run-started", "Started running the remaining execution steps.")
        try:
            for step in [item for item in saved.steps if item.status != "completed"]:
                latest_project = orchestrator.local_project(project_dir)
                if latest_project is None:
                    raise RuntimeError("The managed project could not be reloaded during execution.")
                if stop_requested(latest_project):
                    append_ui_event(latest_project, "run-paused", "Paused before the next step because a stop was requested.")
                    break
                append_ui_event(
                    latest_project,
                    "step-started",
                    f"Running {step.step_id}: {step.title}",
                    {"step_id": step.step_id, "title": step.title},
                )
                project, saved, result_step = orchestrator.run_saved_execution_step(
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
            latest = orchestrator.local_project(project_dir)
            if latest is not None:
                append_ui_event(latest, "run-finished", "Finished the run loop for the current project.")
                return project_detail_payload(orchestrator, latest)
            return project_detail_payload(orchestrator, project)
        finally:
            latest = orchestrator.local_project(project_dir)
            if latest is not None:
                save_run_control(latest, default_run_control())

    if command == "run-closeout":
        project_dir, runtime, branch, origin_url, _display_name = common_project_inputs(payload)
        raw_plan = payload.get("plan", {})
        if not isinstance(raw_plan, dict):
            raise ValueError("plan payload must be an object.")
        plan_state = parse_plan_state(raw_plan)
        project, _saved = orchestrator.update_execution_plan(
            project_dir=project_dir,
            runtime=runtime,
            plan_state=plan_state,
            branch=branch,
            origin_url=origin_url,
        )
        append_ui_event(project, "closeout-started", "Started project closeout.")
        project, saved = orchestrator.run_execution_closeout(
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
        return project_detail_payload(orchestrator, project)

    raise ValueError(f"Unsupported bridge command: {command}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="JSON bridge for the codex-auto React/Tauri desktop shell")
    parser.add_argument("command", help="Bridge command to execute")
    parser.add_argument(
        "--workspace-root",
        default=str(default_workspace_root()),
        help="Workspace root for managed projects",
    )
    return parser.parse_args(argv)


def load_stdin_payload() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    payload = parse_json_text(raw)
    if not isinstance(payload, dict):
        raise ValueError("Bridge stdin payload must be a JSON object.")
    return payload


def configure_stdio() -> None:
    # Force UTF-8 for the desktop bridge so Windows locale encodings do not
    # break JSON payloads or error messages coming from the Python process.
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = parse_args(argv)
    try:
        payload = load_stdin_payload()
        result = run_command(args.command, Path(args.workspace_root).expanduser().resolve(), payload)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
