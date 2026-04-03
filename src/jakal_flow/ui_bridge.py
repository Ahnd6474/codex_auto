from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from threading import Lock, RLock
from time import perf_counter
from typing import Any

from .bridge_events import emit_bridge_event
from .codex_app_server import fetch_codex_backend_snapshot
from .errors import HANDLED_OPERATION_EXCEPTIONS
from .failure_logs import write_runtime_failure_log
from .model_constants import AUTO_MODEL_SLUG, DEFAULT_LOCAL_MODEL_PROVIDER, DEFAULT_MODEL_PROVIDER
from .execution_control import EXECUTION_STOP_REGISTRY, chat_execution_scope_id, execution_scope_id
from .model_selection import (
    DEFAULT_MODEL_PRESET_ID,
    MODEL_PRESETS,
    model_preset_by_id,
    normalize_model_preset_id,
    normalize_reasoning_effort,
)
from .model_providers import (
    normalize_billing_mode,
    normalize_local_model_provider,
    normalize_model_provider,
    provider_preset,
    provider_supports_auto_model,
)
from .models import ExecutionPlanState, ProjectContext, RuntimeOptions
from .orchestrator import Orchestrator
from .parallel_resources import normalize_parallel_worker_mode
from .platform_defaults import default_codex_path
from .process_supervisor import terminate_process, wait_for_condition
from .public_tunnel import public_tunnel_status_payload, start_cloudflare_quick_tunnel, stop_public_tunnel_process
from .run_control import (
    clear_stop_request,
    default_run_control,
    immediate_stop_requested,
    load_run_control,
    normalize_run_control,
    request_stop_immediately,
    request_stop_after_current_step,
    save_run_control,
    stop_requested,
)
from .runtime_config import (
    coerce_bool,
    coerce_positive_int,
    desktop_runtime_defaults,
    runtime_from_payload as normalize_runtime_from_payload,
)
from .runtime_services import CodexBackendSnapshotService
from .share import (
    DEFAULT_SHARE_HOST,
    DEFAULT_SHARE_PORT,
    ShareServerConfig,
    load_share_server_config,
    load_share_server_state,
    save_share_server_config,
    share_server_status_payload,
)
from .step_models import (
    CLAUDE_DEFAULT_MODEL,
    DEEPSEEK_DEFAULT_MODEL,
    GEMINI_DEFAULT_MODEL,
    GLM_DEFAULT_MODEL,
    KIMI_DEFAULT_MODEL,
    MINIMAX_DEFAULT_MODEL,
    QWEN_CODE_DEFAULT_MODEL,
)
from .ui_bridge_commands import (
    BridgeCommandContext,
    build_contract_command_handlers,
    build_project_command_handlers,
    build_read_model_handlers,
    build_run_command_handlers,
    build_share_command_handlers,
    build_tooling_command_handlers,
    tooling_snapshot_payload,
)
from .ui_bridge_payloads import progress_caption, project_detail_payload
from .utils import append_jsonl, normalize_workflow_mode, now_utc_iso, parse_json_text, read_json, write_json


DEFAULT_GUI_WORKSPACE_DIRNAME = ".jakal-flow-workspace"
SHARE_SERVER_START_TIMEOUT_SECS = 3.0
CODEX_SNAPSHOT_TTL_SECONDS = 15.0


_codex_snapshot_service = CodexBackendSnapshotService(
    fetcher=lambda codex_path="": fetch_codex_backend_snapshot(codex_path),
    ttl_seconds=CODEX_SNAPSHOT_TTL_SECONDS,
)
_orchestrator_cache: dict[str, Orchestrator] = {}
_orchestrator_cache_lock = Lock()
_bridge_command_handlers_cache: dict[str, Any] | None = None
_bridge_command_handlers_cache_token: tuple[int, ...] | None = None
_bridge_command_handlers_cache_lock = Lock()
_bridge_perf_aggregate_cache: dict[str, dict[str, Any]] = {}
_bridge_perf_cache_lock = RLock()
_BRIDGE_PERF_AGGREGATE_WINDOW_SECONDS = 1.0
_BRIDGE_PERF_AGGREGATE_SAMPLE_LIMIT = 10
_BRIDGE_PERF_AGGREGATE_COMMANDS = frozenset({"list-projects", "load-project", "load-project-core", "load-visible-project-state"})


def default_workspace_root() -> Path:
    explicit = os.environ.get("JAKAL_FLOW_GUI_WORKSPACE")
    if explicit:
        return Path(explicit).expanduser().resolve()
    repo_preferred = (repo_root() / DEFAULT_GUI_WORKSPACE_DIRNAME).resolve()
    if repo_preferred.exists():
        return repo_preferred
    preferred = (Path.cwd() / DEFAULT_GUI_WORKSPACE_DIRNAME).resolve()
    if preferred.exists():
        return preferred
    return (Path.home() / DEFAULT_GUI_WORKSPACE_DIRNAME).resolve()


def bootstrap_payload(workspace_root: Path) -> dict[str, Any]:
    tooling_snapshot = tooling_snapshot_payload(
        codex_snapshot_service=_codex_snapshot_service,
        force_refresh=False,
        prefer_cached=True,
    )
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
        "model_catalog": tooling_snapshot["model_catalog"],
        "codex_status": tooling_snapshot["codex_status"],
        "tooling_statuses": tooling_snapshot["tooling_statuses"],
        "default_runtime": runtime_from_payload({}).to_dict(),
    }


def orchestrator_for(workspace_root: Path) -> Orchestrator:
    resolved_root = workspace_root.expanduser().resolve()
    cache_key = str(resolved_root)
    with _orchestrator_cache_lock:
        cached = _orchestrator_cache.get(cache_key)
        if cached is not None:
            return cached
        orchestrator = Orchestrator(resolved_root)
        _orchestrator_cache[cache_key] = orchestrator
        return orchestrator


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def build_pythonpath(root: Path) -> str:
    items = [str(root / "src")]
    existing = os.environ.get("PYTHONPATH", "").strip()
    if existing:
        items.append(existing)
    return os.pathsep.join(items)


def start_share_server_process(
    workspace_root: Path,
    host: str | None = None,
    port: int | None = None,
    public_base_url: str | None = None,
) -> dict[str, Any]:
    current_config = load_share_server_config(workspace_root)
    updated_config = save_share_server_config(
        workspace_root,
        ShareServerConfig(
            bind_host=(host or current_config.bind_host or DEFAULT_SHARE_HOST),
            preferred_port=current_config.preferred_port if port is None else max(0, int(port)),
            public_base_url=(
                current_config.public_base_url
                if public_base_url is None
                else str(public_base_url).strip()
            ),
            access_token=current_config.access_token,
        ),
    )
    current_state = load_share_server_state(workspace_root)
    current = share_server_status_payload(workspace_root)
    should_restart = bool(
        current.get("running")
        and current_state is not None
        and (
            current_state.host != updated_config.bind_host
            or (
                updated_config.preferred_port > 0
                and int(current_state.port) != int(updated_config.preferred_port)
            )
        )
    )
    if should_restart:
        stop_public_tunnel_process(workspace_root)
        stop_share_server_process(workspace_root)
        current = share_server_status_payload(workspace_root)
    if current.get("running"):
        return current

    root = repo_root()
    env = os.environ.copy()
    env["PYTHONPATH"] = build_pythonpath(root)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    def launch_server(candidate_port: int) -> dict[str, Any] | None:
        command = [
            sys.executable,
            "-m",
            "jakal_flow.share_server",
            "--workspace-root",
            str(workspace_root),
            "--host",
            updated_config.bind_host,
            "--port",
            str(candidate_port),
        ]
        creationflags = 0
        if os.name == "nt":
            creationflags = (
                getattr(subprocess, "DETACHED_PROCESS", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
            if os.environ.get("PYTEST_CURRENT_TEST"):
                creationflags = 0
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
        if wait_for_condition(
            lambda: load_share_server_state(workspace_root) is not None,
            timeout_seconds=SHARE_SERVER_START_TIMEOUT_SECS,
            interval_seconds=0.1,
        ):
            state = load_share_server_state(workspace_root)
            if state is None:
                return None
            status = share_server_status_payload(workspace_root)
            if status.get("running"):
                return status
            tunnel = public_tunnel_status_payload(workspace_root)
            config_payload = load_share_server_config(workspace_root).to_dict()
            return {
                "running": True,
                "host": state.host,
                "port": state.port,
                "pid": state.pid,
                "started_at": state.started_at,
                "base_url": state.base_url,
                "viewer_path": state.viewer_path,
                "config": config_payload,
                "share_base_url": config_payload.get("public_base_url") or tunnel.get("public_url") or state.base_url,
                "share_base_url_source": (
                    "config"
                    if config_payload.get("public_base_url")
                    else ("quick_tunnel" if tunnel.get("public_url") else "local")
                ),
                "public_tunnel": tunnel,
            }
        return None

    started = launch_server(int(updated_config.preferred_port))
    if started is not None:
        return started
    if int(updated_config.preferred_port) > 0:
        started = launch_server(0)
        if started is not None:
            append_jsonl(
                workspace_root / "share_server_fallbacks.jsonl",
                {
                    "timestamp": now_utc_iso(),
                    "event_type": "share-server-port-fallback",
                    "requested_port": int(updated_config.preferred_port),
                    "fallback_port": started.get("port"),
                },
            )
            return started
    raise RuntimeError("Share server did not start in time.")


def stop_share_server_process(workspace_root: Path) -> dict[str, Any]:
    stop_public_tunnel_process(workspace_root)
    status = share_server_status_payload(workspace_root)
    pid = int(status.get("pid") or 0)
    if pid <= 0:
        return share_server_status_payload(workspace_root)
    terminate_process(pid)
    stopped = wait_for_condition(
        lambda: not bool(share_server_status_payload(workspace_root).get("running")),
        timeout_seconds=2.0,
        interval_seconds=0.1,
    )
    if not stopped and os.name != "nt":
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
        wait_for_condition(
            lambda: not bool(share_server_status_payload(workspace_root).get("running")),
            timeout_seconds=1.0,
            interval_seconds=0.1,
        )
    return share_server_status_payload(workspace_root)


def runtime_from_payload(payload: dict[str, Any]) -> RuntimeOptions:
    defaults = desktop_runtime_defaults()
    defaults["codex_path"] = default_codex_path()
    return normalize_runtime_from_payload(
        payload,
        defaults=defaults,
        force_execution_mode="parallel",
    )


def parse_plan_state(payload: dict[str, Any]) -> ExecutionPlanState:
    state = ExecutionPlanState.from_dict(payload)
    if "execution_mode" not in payload:
        state.execution_mode = ""
    if "workflow_mode" not in payload:
        state.workflow_mode = ""
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


def resolve_history_project(
    orchestrator: Orchestrator,
    payload: dict[str, Any],
) -> ProjectContext:
    archive_id = str(payload.get("archive_id", "")).strip()
    if archive_id:
        return orchestrator.workspace.load_history_by_id(archive_id)
    raise ValueError("archive_id is required.")


def best_effort_project(
    orchestrator: Orchestrator,
    payload: dict[str, Any],
) -> ProjectContext | None:
    try:
        return resolve_project(orchestrator, payload)
    except (KeyError, ValueError, FileNotFoundError):
        return None


def append_ui_event(context: ProjectContext, event_type: str, message: str, details: dict[str, Any] | None = None) -> None:
    payload = {
        "timestamp": now_utc_iso(),
        "event_type": event_type,
        "message": message,
        "details": details or {},
    }
    append_jsonl(context.paths.ui_event_log_file, payload)
    if getattr(context.runtime, "save_project_logs", False):
        append_jsonl(
            context.paths.logs_dir / "project_activity.jsonl",
            {
                "timestamp": payload["timestamp"],
                "repo_id": context.metadata.repo_id,
                "project_dir": str(context.metadata.repo_path),
                "event_type": event_type,
                "message": message,
                "details": payload["details"],
            },
        )
    emit_bridge_event(
        "project.ui_event",
        {
            "repo_id": context.metadata.repo_id,
            "project_dir": str(context.metadata.repo_path),
            "project_status": context.metadata.current_status,
            "event": payload,
        },
    )


def common_project_inputs(
    payload: dict[str, Any],
    orchestrator: Orchestrator | None = None,
) -> tuple[Path, RuntimeOptions, str, str, str]:
    project_dir_value = str(payload.get("project_dir", "")).strip()
    if project_dir_value:
        project_dir = Path(project_dir_value).expanduser().resolve()
    else:
        repo_id = str(payload.get("repo_id", "")).strip()
        if not repo_id or orchestrator is None:
            raise ValueError("project_dir is required.")
        project_dir = orchestrator.workspace.load_project_by_id(repo_id).metadata.repo_path.resolve()
    runtime_payload = payload.get("runtime", {})
    if not isinstance(runtime_payload, dict):
        raise ValueError("runtime payload must be an object.")
    runtime = runtime_from_payload(runtime_payload)
    branch = str(payload.get("branch", "main")).strip() or "main"
    origin_url = str(payload.get("origin_url", "")).strip()
    display_name = str(payload.get("display_name", "")).strip()
    return project_dir, runtime, branch, origin_url, display_name


def bridge_command_handlers() -> dict[str, Any]:
    global _bridge_command_handlers_cache, _bridge_command_handlers_cache_token
    cache_token = (
        id(resolve_project),
        id(resolve_history_project),
        id(common_project_inputs),
        id(parse_plan_state),
        id(append_ui_event),
        id(save_run_control),
        id(default_run_control),
        id(clear_stop_request),
        id(EXECUTION_STOP_REGISTRY),
        id(start_share_server_process),
        id(stop_share_server_process),
        id(save_share_server_config),
        id(_codex_snapshot_service),
    )
    with _bridge_command_handlers_cache_lock:
        if _bridge_command_handlers_cache is not None and _bridge_command_handlers_cache_token == cache_token:
            return _bridge_command_handlers_cache
        _bridge_command_handlers_cache_token = cache_token
        _bridge_command_handlers_cache = {
            **build_read_model_handlers(
                bootstrap_payload=bootstrap_payload,
                resolve_project=resolve_project,
                resolve_history_project=resolve_history_project,
                coerce_bool=coerce_bool,
                codex_snapshot_service=_codex_snapshot_service,
            ),
            **build_project_command_handlers(
                resolve_project=resolve_project,
                resolve_history_project=resolve_history_project,
                common_project_inputs=common_project_inputs,
                parse_plan_state=parse_plan_state,
                append_ui_event=append_ui_event,
                save_run_control=save_run_control,
                default_run_control=default_run_control,
                clear_stop_request=clear_stop_request,
                execution_scope_id=execution_scope_id,
                execution_stop_registry=EXECUTION_STOP_REGISTRY,
            ),
            **build_contract_command_handlers(
                resolve_project=resolve_project,
                append_ui_event=append_ui_event,
            ),
            **build_share_command_handlers(
                resolve_project=resolve_project,
                coerce_positive_int=coerce_positive_int,
                append_ui_event=append_ui_event,
                start_share_server_process=start_share_server_process,
                stop_share_server_process=stop_share_server_process,
                start_public_tunnel=lambda workspace_root, target_url: start_cloudflare_quick_tunnel(workspace_root, target_url),
                stop_public_tunnel=lambda workspace_root: stop_public_tunnel_process(workspace_root),
                save_share_server_config=save_share_server_config,
            ),
            **build_run_command_handlers(
                resolve_project=resolve_project,
                common_project_inputs=common_project_inputs,
                parse_plan_state=parse_plan_state,
                append_ui_event=append_ui_event,
                save_run_control=save_run_control,
                default_run_control=default_run_control,
                request_stop_immediately=request_stop_immediately,
                stop_requested=stop_requested,
                immediate_stop_requested=immediate_stop_requested,
                chat_execution_scope_id=chat_execution_scope_id,
                execution_scope_id=execution_scope_id,
                execution_stop_registry=EXECUTION_STOP_REGISTRY,
                coerce_bool=coerce_bool,
            ),
            **build_tooling_command_handlers(
                coerce_bool=coerce_bool,
                codex_snapshot_service=_codex_snapshot_service,
            ),
        }
        return _bridge_command_handlers_cache


def _payload_size_bytes(value: Any) -> int:
    def estimate(item: Any, *, depth: int = 0, max_items: int = 64) -> int:
        if item is None:
            return 4
        if isinstance(item, bool):
            return 4 if item else 5
        if isinstance(item, (int, float)):
            return len(str(item))
        if isinstance(item, str):
            return len(item.encode("utf-8")) + 2
        if depth >= 3:
            return 16
        if isinstance(item, dict):
            total = 2
            for index, (key, value) in enumerate(item.items()):
                if index >= max_items:
                    return total + 3
                total += len(str(key).encode("utf-8")) + 3
                total += estimate(value, depth=depth + 1, max_items=max_items)
            return total
        if isinstance(item, (list, tuple)):
            total = 2
            for index, value in enumerate(item):
                if index >= max_items:
                    return total + 3
                total += estimate(value, depth=depth + 1, max_items=max_items)
            return total
        return len(str(item).encode("utf-8"))

    return estimate(value)


def _bridge_perf_entry(command: str, payload: dict[str, Any], result: Any, duration_ms: float) -> dict[str, Any]:
    return {
        "timestamp": now_utc_iso(),
        "command": command,
        "repo_id": str(payload.get("repo_id", "")).strip(),
        "project_dir": str(payload.get("project_dir", "")).strip(),
        "archive_id": str(payload.get("archive_id", "")).strip(),
        "detail_level": str(payload.get("detail_level", "")).strip().lower(),
        "refresh_codex_status": coerce_bool(payload.get("refresh_codex_status", False), False),
        "duration_ms": round(duration_ms, 3),
        "payload_size_bytes": _payload_size_bytes(payload),
        "result_size_bytes": _payload_size_bytes(result),
        "result_keys": sorted(result.keys()) if isinstance(result, dict) else [],
        "payload_cache_hit": bool(result.get("payload_cache_hit")) if isinstance(result, dict) else False,
        "content_signature": str(result.get("content_signature", "")).strip() if isinstance(result, dict) else "",
        "detail_signature": str(result.get("detail_signature", "")).strip() if isinstance(result, dict) else "",
    }


def _bridge_perf_hot_entry(command: str, payload: dict[str, Any], result: Any, duration_ms: float) -> dict[str, Any]:
    return {
        "timestamp": now_utc_iso(),
        "command": command,
        "repo_id": str(payload.get("repo_id", "")).strip(),
        "project_dir": str(payload.get("project_dir", "")).strip(),
        "archive_id": str(payload.get("archive_id", "")).strip(),
        "detail_level": str(payload.get("detail_level", "")).strip().lower(),
        "refresh_codex_status": coerce_bool(payload.get("refresh_codex_status", False), False),
        "duration_ms": round(duration_ms, 3),
        "payload_size_bytes": _payload_size_bytes(payload),
        "result_size_bytes": _payload_size_bytes(result),
        "result_keys": sorted(result.keys()) if isinstance(result, dict) else [],
        "payload_cache_hit": True,
        "content_signature": str(result.get("content_signature", "")).strip() if isinstance(result, dict) else "",
        "detail_signature": str(result.get("detail_signature", "")).strip() if isinstance(result, dict) else "",
    }


def _write_bridge_perf_entry(workspace_root: Path, entry: dict[str, Any]) -> None:
    payload = dict(entry)
    payload["workspace_root"] = str(workspace_root)
    append_jsonl(workspace_root / "bridge_perf.jsonl", payload)


def _flush_bridge_perf_aggregates(workspace_root: Path | None = None, *, force: bool = False) -> None:
    with _bridge_perf_cache_lock:
        now_monotonic = time.monotonic()
        flush_keys: list[str] = []
        for key, aggregate in _bridge_perf_aggregate_cache.items():
            if workspace_root is not None and aggregate.get("workspace_root") != str(workspace_root):
                continue
            if force or (now_monotonic - float(aggregate.get("started_monotonic", now_monotonic))) >= _BRIDGE_PERF_AGGREGATE_WINDOW_SECONDS:
                flush_keys.append(key)
        for key in flush_keys:
            aggregate = _bridge_perf_aggregate_cache.pop(key, None)
            if aggregate is None:
                continue
            entry = dict(aggregate["entry"])
            sample_count = int(aggregate.get("sample_count", 1) or 1)
            total_duration_ms = float(aggregate.get("total_duration_ms", entry.get("duration_ms", 0.0)) or 0.0)
            entry["sample_count"] = sample_count
            entry["duration_ms_avg"] = round(total_duration_ms / sample_count, 3)
            entry["duration_ms_max"] = round(float(aggregate.get("max_duration_ms", entry.get("duration_ms", 0.0)) or 0.0), 3)
            entry["payload_size_bytes_avg"] = int(entry.get("payload_size_bytes", 0))
            entry["result_size_bytes_avg"] = int(entry.get("result_size_bytes", 0))
            _write_bridge_perf_entry(Path(str(aggregate["workspace_root"])), entry)


def _bridge_perf_log(workspace_root: Path, command: str, payload: dict[str, Any], result: Any, duration_ms: float) -> None:
    with _bridge_perf_cache_lock:
        _flush_bridge_perf_aggregates(workspace_root)
        payload_cache_hit = bool(result.get("payload_cache_hit")) if isinstance(result, dict) else False
        if (
            command not in _BRIDGE_PERF_AGGREGATE_COMMANDS
            or not payload_cache_hit
            or duration_ms >= 25.0
        ):
            entry = _bridge_perf_entry(command, payload, result, duration_ms)
            _write_bridge_perf_entry(workspace_root, entry)
            return

        aggregate_key = "|".join(
            [
                str(workspace_root),
                command,
                str(payload.get("repo_id", "")).strip(),
                str(payload.get("project_dir", "")).strip(),
                str(payload.get("detail_level", "")).strip().lower(),
                str(coerce_bool(payload.get("refresh_codex_status", False), False)).lower(),
            ]
        )
        aggregate = _bridge_perf_aggregate_cache.get(aggregate_key)
        if aggregate is None:
            entry = _bridge_perf_hot_entry(command, payload, result, duration_ms)
            _bridge_perf_aggregate_cache[aggregate_key] = {
                "workspace_root": str(workspace_root),
                "entry": entry,
                "sample_count": 1,
                "total_duration_ms": float(entry["duration_ms"]),
                "max_duration_ms": float(entry["duration_ms"]),
                "started_monotonic": time.monotonic(),
            }
            return
        aggregate["sample_count"] = int(aggregate.get("sample_count", 1) or 1) + 1
        aggregate["total_duration_ms"] = float(aggregate.get("total_duration_ms", 0.0) or 0.0) + float(duration_ms)
        aggregate["max_duration_ms"] = max(float(aggregate.get("max_duration_ms", 0.0) or 0.0), float(duration_ms))
        aggregate["entry"]["timestamp"] = now_utc_iso()
        aggregate["entry"]["duration_ms"] = round(duration_ms, 3)
        if isinstance(result, dict):
            aggregate["entry"]["content_signature"] = str(result.get("content_signature", "")).strip()
            aggregate["entry"]["detail_signature"] = str(result.get("detail_signature", "")).strip()
        if int(aggregate["sample_count"]) >= _BRIDGE_PERF_AGGREGATE_SAMPLE_LIMIT:
            _flush_bridge_perf_aggregates(workspace_root, force=True)


def run_command(command: str, workspace_root: Path, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    command_started_at = perf_counter()
    orchestrator = orchestrator_for(workspace_root)

    def detail_payload(project: ProjectContext, **kwargs: Any) -> dict[str, Any]:
        execution_processes = kwargs.pop(
            "execution_processes",
            EXECUTION_STOP_REGISTRY.active_processes(execution_scope_id(project)),
        )
        return project_detail_payload(
            orchestrator,
            project,
            load_run_control=load_run_control,
            fetch_codex_status=lambda codex_path="": _codex_snapshot_service.get_snapshot(codex_path),
            execution_processes=execution_processes,
            **kwargs,
        )

    handler = bridge_command_handlers().get(command)
    if handler is None:
        raise ValueError(f"Unsupported bridge command: {command}")
    try:
        result = handler(
            BridgeCommandContext(
                workspace_root=workspace_root,
                payload=payload,
                orchestrator=orchestrator,
                detail_payload=detail_payload,
            )
        )
    except HANDLED_OPERATION_EXCEPTIONS as exc:
        write_runtime_failure_log(
            workspace_root,
            source="ui-bridge",
            command=command,
            exc=exc,
            payload=payload,
            project=best_effort_project(orchestrator, payload),
        )
        raise
    _bridge_perf_log(workspace_root, command, payload, result, (perf_counter() - command_started_at) * 1000.0)
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="JSON bridge for the jakal-flow React/Tauri desktop shell")
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
    except HANDLED_OPERATION_EXCEPTIONS as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
