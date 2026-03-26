from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

from .bridge_events import emit_bridge_event
from .codex_app_server import fetch_codex_backend_snapshot
from .model_constants import AUTO_MODEL_SLUG, DEFAULT_LOCAL_MODEL_PROVIDER, DEFAULT_MODEL_PROVIDER
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
from .process_supervisor import terminate_process, wait_for_condition
from .public_tunnel import public_tunnel_status_payload, start_cloudflare_quick_tunnel, stop_public_tunnel_process
from .runtime_services import CodexBackendSnapshotService
from .share import (
    DEFAULT_SHARE_HOST,
    DEFAULT_SHARE_PORT,
    DEFAULT_SHARE_PUBLIC_BASE_URL,
    DEFAULT_SHARE_TTL_MINUTES,
    ShareServerConfig,
    create_share_session,
    load_share_server_config,
    load_share_server_state,
    project_share_payload,
    public_session_summary,
    revoke_share_session,
    save_share_server_config,
    share_server_status_payload,
)
from .ui_bridge_payloads import (
    checkpoint_payload,
    config_payload,
    history_payload,
    list_projects_payload,
    managed_workspace_tree,
    progress_caption,
    project_detail_payload,
    report_payload,
)
from .utils import append_jsonl, normalize_workflow_mode, now_utc_iso, parse_json_text, read_json, write_json


DEFAULT_GUI_WORKSPACE_DIRNAME = ".jakal-flow-workspace"
LEGACY_GUI_WORKSPACE_DIRNAME = ".codex-auto-workspace"
SHARE_SERVER_START_TIMEOUT_SECS = 3.0
CODEX_SNAPSHOT_TTL_SECONDS = 15.0


_codex_snapshot_service = CodexBackendSnapshotService(
    fetcher=lambda codex_path="codex.cmd": fetch_codex_backend_snapshot(codex_path),
    ttl_seconds=CODEX_SNAPSHOT_TTL_SECONDS,
)


def default_workspace_root() -> Path:
    explicit = os.environ.get("JAKAL_FLOW_GUI_WORKSPACE") or os.environ.get("CODEX_AUTO_GUI_WORKSPACE")
    if explicit:
        return Path(explicit).expanduser().resolve()
    preferred = (Path.cwd() / DEFAULT_GUI_WORKSPACE_DIRNAME).resolve()
    if preferred.exists():
        return preferred
    legacy = (Path.cwd() / LEGACY_GUI_WORKSPACE_DIRNAME).resolve()
    if legacy.exists():
        return legacy
    return (Path.home() / DEFAULT_GUI_WORKSPACE_DIRNAME).resolve()


def bootstrap_payload(workspace_root: Path) -> dict[str, Any]:
    codex_status = _codex_snapshot_service.get_snapshot()
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
        "model_catalog": codex_status.model_catalog,
        "codex_status": codex_status.to_dict(),
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
    wait_for_condition(
        lambda: not bool(share_server_status_payload(workspace_root).get("running")),
        timeout_seconds=2.0,
        interval_seconds=0.1,
    )
    return share_server_status_payload(workspace_root)


def coerce_positive_int(value: Any, default: int, minimum: int = 1) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(minimum, parsed)


def coerce_nonnegative_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return default
    if parsed < 0:
        return default
    return parsed


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
        generate_word_report=True,
        max_blocks=5,
        workflow_mode="standard",
        ml_max_cycles=3,
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
    merged["parallel_workers"] = coerce_positive_int(
        merged.get("parallel_workers", 2),
        default=2,
    )
    merged["ml_max_cycles"] = coerce_positive_int(
        merged.get("ml_max_cycles", 3),
        default=3,
    )
    merged["allow_push"] = coerce_bool(merged.get("allow_push", True), True)
    merged["require_checkpoint_approval"] = coerce_bool(
        merged.get("require_checkpoint_approval", False),
        False,
    )
    merged["execution_mode"] = str(merged.get("execution_mode", "serial")).strip().lower()
    if merged["execution_mode"] not in {"serial", "parallel"}:
        merged["execution_mode"] = "serial"
    merged["workflow_mode"] = normalize_workflow_mode(merged.get("workflow_mode", "standard"))
    merged["test_cmd"] = str(merged.get("test_cmd", "python -m pytest")).strip() or "python -m pytest"
    merged["model_provider"] = normalize_model_provider(
        str(merged.get("model_provider", DEFAULT_MODEL_PROVIDER)),
        fallback=DEFAULT_MODEL_PROVIDER,
    )
    provider = provider_preset(merged["model_provider"])
    merged["local_model_provider"] = normalize_local_model_provider(
        str(merged.get("local_model_provider", "")),
        fallback="",
    )
    if merged["model_provider"] == "oss":
        if not merged["local_model_provider"]:
            merged["local_model_provider"] = DEFAULT_LOCAL_MODEL_PROVIDER
    else:
        merged["local_model_provider"] = ""
    merged["provider_base_url"] = str(merged.get("provider_base_url", "")).strip()
    if not merged["provider_base_url"] and provider.default_base_url:
        merged["provider_base_url"] = provider.default_base_url
    merged["provider_api_key_env"] = str(merged.get("provider_api_key_env", "")).strip()
    if not merged["provider_api_key_env"] and provider.default_api_key_env:
        merged["provider_api_key_env"] = provider.default_api_key_env
    merged["billing_mode"] = normalize_billing_mode(
        str(merged.get("billing_mode", "")),
        merged["model_provider"],
        fallback=provider.default_billing_mode,
    )
    merged["input_cost_per_million_usd"] = coerce_nonnegative_float(merged.get("input_cost_per_million_usd", 0.0))
    merged["cached_input_cost_per_million_usd"] = coerce_nonnegative_float(merged.get("cached_input_cost_per_million_usd", 0.0))
    merged["output_cost_per_million_usd"] = coerce_nonnegative_float(merged.get("output_cost_per_million_usd", 0.0))
    merged["reasoning_output_cost_per_million_usd"] = coerce_nonnegative_float(
        merged.get("reasoning_output_cost_per_million_usd", 0.0)
    )
    merged["per_pass_cost_usd"] = coerce_nonnegative_float(merged.get("per_pass_cost_usd", 0.0))
    merged["model"] = str(merged.get("model", "")).strip().lower()
    merged["model_preset"] = normalize_model_preset_id(str(merged.get("model_preset", "")), fallback="")
    merged["effort_selection_mode"] = str(merged.get("effort_selection_mode", "")).strip().lower()
    if merged["effort_selection_mode"] not in {"auto", "explicit"}:
        merged["effort_selection_mode"] = "explicit"
    merged["use_fast_mode"] = coerce_bool(merged.get("use_fast_mode", False), False)
    merged["generate_word_report"] = coerce_bool(merged.get("generate_word_report", True), True)
    raw_effort = str(merged.get("effort", "")).strip()
    merged["effort"] = raw_effort.lower()

    if not merged["model"]:
        preset = model_preset_by_id(merged["model_preset"] or DEFAULT_MODEL_PRESET_ID)
        merged["model"] = preset.model if provider_supports_auto_model(merged["model_provider"]) else ""
    preset = model_preset_by_id(merged["model_preset"] or DEFAULT_MODEL_PRESET_ID)
    if not merged["effort"]:
        merged["effort"] = preset.effort
    merged["effort"] = normalize_reasoning_effort(merged["effort"], fallback=preset.effort)
    if not provider_supports_auto_model(merged["model_provider"]) and merged["model"] == AUTO_MODEL_SLUG:
        merged["model"] = ""
    if provider_supports_auto_model(merged["model_provider"]) and merged["model"] == AUTO_MODEL_SLUG:
        if merged["model_preset"]:
            merged["effort"] = model_preset_by_id(merged["model_preset"]).effort
        else:
            merged["model_preset"] = "auto" if merged["effort"] == "medium" else merged["effort"]
        if merged["model_preset"] == "auto":
            merged["effort_selection_mode"] = "auto"
        elif merged["effort_selection_mode"] == "auto":
            merged["effort_selection_mode"] = "explicit"
    elif merged["model_preset"]:
        merged["model_preset"] = ""
    merged["model_selection_mode"] = str(merged.get("model_selection_mode", "slug")).strip() or "slug"
    merged["model_slug_input"] = str(merged.get("model_slug_input", merged["model"])).strip().lower() or merged["model"]
    if not merged["model"] and merged["model_slug_input"]:
        merged["model"] = merged["model_slug_input"]
    return RuntimeOptions(**merged)


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
    emit_bridge_event(
        "project.ui_event",
        {
            "repo_id": context.metadata.repo_id,
            "project_dir": str(context.metadata.repo_path),
            "project_status": context.metadata.current_status,
            "event": payload,
        },
    )


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

    def detail_payload(project: ProjectContext, **kwargs: Any) -> dict[str, Any]:
        return project_detail_payload(
            orchestrator,
            project,
            load_run_control=load_run_control,
            fetch_codex_status=lambda codex_path="codex.cmd": _codex_snapshot_service.get_snapshot(codex_path),
            **kwargs,
        )

    if command == "bootstrap":
        return bootstrap_payload(workspace_root)

    if command == "list-projects":
        return list_projects_payload(orchestrator)

    if command == "load-project":
        project = resolve_project(orchestrator, payload)
        if coerce_bool(payload.get("refresh_codex_status", True), True):
            _codex_snapshot_service.invalidate(project.runtime.codex_path)
        return detail_payload(
            project,
            refresh_codex_status=coerce_bool(payload.get("refresh_codex_status", True), True),
            detail_level=str(payload.get("detail_level", "full")).strip().lower() or "full",
        )

    if command == "load-project-core":
        project = resolve_project(orchestrator, payload)
        if coerce_bool(payload.get("refresh_codex_status", False), False):
            _codex_snapshot_service.invalidate(project.runtime.codex_path)
        return detail_payload(
            project,
            refresh_codex_status=coerce_bool(payload.get("refresh_codex_status", False), False),
            detail_level="core",
        )

    if command == "load-project-history":
        project = resolve_project(orchestrator, payload)
        return history_payload(project)

    if command == "load-project-reports":
        project = resolve_project(orchestrator, payload)
        return report_payload(project)

    if command == "load-project-config":
        project = resolve_project(orchestrator, payload)
        return config_payload(project)

    if command == "load-project-workspace":
        project = resolve_project(orchestrator, payload)
        return {"workspace_tree": managed_workspace_tree(project)}

    if command == "load-project-checkpoints":
        project = resolve_project(orchestrator, payload)
        return checkpoint_payload(project)

    if command == "load-project-share":
        project = resolve_project(orchestrator, payload)
        return {"share": project_share_payload(orchestrator.workspace.workspace_root, project)}

    if command == "delete-project":
        project = resolve_project(orchestrator, payload)
        repo_id = project.metadata.repo_id
        project_dir = str(project.metadata.repo_path)
        display_name = project.metadata.display_name or project.metadata.slug
        orchestrator.workspace.delete_project(repo_id)
        listing = list_projects_payload(orchestrator)
        return {
            "deleted": {
                "repo_id": repo_id,
                "project_dir": project_dir,
                "display_name": display_name,
            },
            "projects": listing["projects"],
            "workspace": listing["workspace"],
        }

    if command == "delete-all-projects":
        orchestrator.workspace.delete_all_projects()
        listing = list_projects_payload(orchestrator)
        return {
            "deleted_all": True,
            "projects": listing["projects"],
            "workspace": listing["workspace"],
        }

    if command == "get_share_server_status":
        return share_server_status_payload(workspace_root)

    if command == "get_public_tunnel_status":
        return public_tunnel_status_payload(workspace_root)

    if command == "save_share_server_config":
        config = save_share_server_config(
            workspace_root,
            ShareServerConfig(
                bind_host=str(payload.get("bind_host", DEFAULT_SHARE_HOST)).strip() or DEFAULT_SHARE_HOST,
                preferred_port=coerce_positive_int(payload.get("preferred_port", DEFAULT_SHARE_PORT), default=DEFAULT_SHARE_PORT, minimum=0),
                public_base_url=str(payload.get("public_base_url", DEFAULT_SHARE_PUBLIC_BASE_URL)).strip(),
            ),
        )
        result = share_server_status_payload(workspace_root)
        result["config"] = config.to_dict()
        return result

    if command == "start_share_server":
        host = str(payload.get("host", "")).strip() or None
        port = (
            coerce_positive_int(payload.get("port", DEFAULT_SHARE_PORT), default=DEFAULT_SHARE_PORT, minimum=0)
            if "port" in payload
            else None
        )
        public_base_url = str(payload.get("public_base_url", "")).strip() if "public_base_url" in payload else None
        return start_share_server_process(workspace_root, host=host, port=port, public_base_url=public_base_url)

    if command == "stop_share_server":
        return stop_share_server_process(workspace_root)

    if command == "start_public_tunnel":
        target_url = str(payload.get("target_url", "")).strip()
        if not target_url:
            status = share_server_status_payload(workspace_root)
            target_url = str(status.get("base_url") or "").strip()
        return start_cloudflare_quick_tunnel(workspace_root, target_url)

    if command == "stop_public_tunnel":
        return stop_public_tunnel_process(workspace_root)

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
        return detail_payload(project)

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
        return detail_payload(project)

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
        return detail_payload(project)

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
        return detail_payload(project)

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
        bind_host = str(payload.get("bind_host", "")).strip() or None
        preferred_port = (
            coerce_positive_int(payload.get("preferred_port", DEFAULT_SHARE_PORT), default=DEFAULT_SHARE_PORT, minimum=0)
            if "preferred_port" in payload
            else None
        )
        public_base_url = str(payload.get("public_base_url", "")).strip() if "public_base_url" in payload else None
        share_status = start_share_server_process(
            workspace_root,
            host=bind_host,
            port=preferred_port,
            public_base_url=public_base_url,
        )
        effective_bind_host = str(share_status.get("config", {}).get("bind_host", bind_host or "")).strip() or bind_host or ""
        should_start_quick_tunnel = (
            effective_bind_host == "0.0.0.0"
            and not public_base_url
            and bool(share_status.get("base_url"))
        )
        quick_tunnel_warning = ""
        if should_start_quick_tunnel:
            try:
                start_cloudflare_quick_tunnel(workspace_root, str(share_status["base_url"]))
            except Exception as exc:
                quick_tunnel_warning = str(exc).strip()
                append_ui_event(
                    project,
                    "share-tunnel-warning",
                    "Automatic public tunnel startup failed; the share session was created without a public URL.",
                    {"error": quick_tunnel_warning},
                )
        elif public_base_url or effective_bind_host != "0.0.0.0":
            stop_public_tunnel_process(workspace_root)
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
        detail = detail_payload(project)
        detail["created_share_session"] = public_session_summary(workspace_root, project, session, include_token=True)
        if quick_tunnel_warning:
            detail["share_tunnel_warning"] = quick_tunnel_warning
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
        detail = detail_payload(project)
        detail["revoked_share_session"] = public_session_summary(workspace_root, project, session, include_token=False)
        return detail

    if command == "approve-checkpoint":
        project = resolve_project(orchestrator, payload)
        review_notes = str(payload.get("review_notes", "")).strip()
        push = coerce_bool(payload.get("push", True), True)
        orchestrator.approve_checkpoint(
            project.metadata.repo_url,
            project.metadata.branch,
            review_notes=review_notes,
            push=push,
        )
        latest_project = orchestrator.workspace.load_project_by_id(project.metadata.repo_id)
        append_ui_event(latest_project, "checkpoint-approved", "Approved the pending checkpoint.", {"push": push})
        return detail_payload(latest_project)

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
            while True:
                latest_project = orchestrator.local_project(project_dir)
                if latest_project is None:
                    raise RuntimeError("The managed project could not be reloaded during execution.")
                current_plan = orchestrator.load_execution_plan_state(latest_project)
                batches = orchestrator.pending_execution_batches(current_plan)
                if not batches:
                    if normalize_workflow_mode(runtime.workflow_mode) == "ml":
                        saved = current_plan
                        project = latest_project
                        if str(current_plan.closeout_status).strip().lower() != "completed":
                            append_ui_event(project, "closeout-started", "Started ML cycle closeout.")
                            project, saved = orchestrator.run_execution_closeout(
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
                        project, saved, continued, reason = orchestrator.prepare_next_ml_cycle(
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
                if (
                    len(batch) > 1
                    and str(current_plan.execution_mode).strip().lower() == "parallel"
                    and runtime.parallel_workers > 1
                ):
                    step_ids = [item.step_id for item in batch]
                    append_ui_event(
                        latest_project,
                        "batch-started",
                        f"Running parallel batch: {', '.join(step_ids)}",
                        {"step_ids": step_ids, "execution_mode": "parallel"},
                    )
                    for step in batch:
                        append_ui_event(
                            latest_project,
                            "step-started",
                            f"Running {step.step_id}: {step.title}",
                            {"step_id": step.step_id, "title": step.title, "execution_mode": "parallel"},
                        )
                    project, saved, result_steps = orchestrator.run_parallel_execution_batch(
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
                return detail_payload(latest)
            return detail_payload(project)
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
        return detail_payload(project)

    raise ValueError(f"Unsupported bridge command: {command}")


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
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
