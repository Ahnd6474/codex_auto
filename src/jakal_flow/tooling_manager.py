from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from .codex_app_server import resolve_codex_path
from .lru_ttl_cache import LruTtlCache
from .model_providers import default_local_model
from .platform_defaults import (
    OLLAMA_MODELS_ENV_VAR,
    configured_ollama_model_store_root,
    default_codex_path,
    default_ollama_model_store_root,
)
from .subprocess_utils import run_subprocess
from .utils import append_jsonl, now_utc_iso

_NPM_PACKAGES: dict[str, str] = {
    "codex": "@openai/codex",
    "gemini": "@google/gemini-cli",
    "claude": "@anthropic-ai/claude-code",
}
_DISPLAY_NAMES: dict[str, str] = {
    "codex": "Codex CLI",
    "gemini": "Gemini CLI",
    "claude": "Claude Code",
    "ollama": "Ollama",
    "npm": "Node.js / npm",
}
_OLLAMA_API_ROOT = "http://127.0.0.1:11434"
_OLLAMA_INSTALLER_URL = "https://ollama.com/download/OllamaSetup.exe"
_TOOLING_EVENT_LOG = "tooling_events.jsonl"
_CLI_VERSION_TIMEOUT_SECONDS = 12.0
_INSTALL_TIMEOUT_SECONDS = 900.0
_OLLAMA_CONNECT_TIMEOUT_SECONDS = 20.0
_DEFAULT_OLLAMA_MODEL = "qwen2.5-coder:0.5b"
_TOOLING_STATUS_CACHE_TTL_SECONDS = 10.0
_OLLAMA_SUGGESTED_MODELS: tuple[str, ...] = (
    "qwen2.5-coder:0.5b",
    "qwen2.5-coder:7b",
    "qwen3:8b",
    "deepseek-r1:8b",
    "llama3.2:3b",
    "gemma3:4b",
    "mistral-small:24b",
)
_TOOLING_STATUS_CACHE = LruTtlCache[str, dict[str, dict[str, Any]]](
    max_entries=8,
    ttl_seconds=_TOOLING_STATUS_CACHE_TTL_SECONDS,
)


@dataclass(frozen=True, slots=True)
class ToolingStatus:
    tool: str
    display_name: str
    command: str
    resolved_command: str
    installed: bool
    version: str = ""
    running: bool | None = None
    models: list[str] = field(default_factory=list)
    recommended_models: list[str] = field(default_factory=list)
    model_store_path: str = ""
    reason: str = ""
    install_hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "display_name": self.display_name,
            "command": self.command,
            "resolved_command": self.resolved_command,
            "installed": self.installed,
            "version": self.version,
            "running": self.running,
            "models": list(self.models),
            "recommended_models": list(self.recommended_models),
            "model_store_path": self.model_store_path,
            "reason": self.reason,
            "install_hint": self.install_hint,
        }


def get_tooling_statuses(
    *,
    force_refresh: bool = False,
    startup_safe: bool = False,
    include_ollama_details: bool = True,
) -> dict[str, dict[str, Any]]:
    cache_key = (
        f"{'startup' if startup_safe else 'full'}:"
        f"{'ollama-details' if include_ollama_details else 'ollama-summary'}"
    )
    if not force_refresh:
        cached = _TOOLING_STATUS_CACHE.get(cache_key)
        if cached is not None:
            return deepcopy(cached)
    statuses = _collect_tooling_statuses(
        startup_safe=startup_safe,
        include_ollama_details=include_ollama_details,
    )
    _TOOLING_STATUS_CACHE.set(cache_key, deepcopy(statuses))
    return statuses


def _collect_tooling_statuses(
    *,
    startup_safe: bool = False,
    include_ollama_details: bool = True,
) -> dict[str, dict[str, Any]]:
    npm_status = _npm_status(startup_safe=startup_safe)
    codex_status = _cli_status("codex", startup_safe=startup_safe)
    gemini_status = _cli_status("gemini", startup_safe=startup_safe)
    claude_status = _cli_status("claude", startup_safe=startup_safe)
    ollama_status = _ollama_status(
        startup_safe=startup_safe,
        include_details=include_ollama_details,
    )
    return {
        "npm": npm_status.to_dict(),
        "codex": codex_status.to_dict(),
        "gemini": gemini_status.to_dict(),
        "claude": claude_status.to_dict(),
        "ollama": ollama_status.to_dict(),
    }


def _invalidate_tooling_status_cache() -> None:
    _TOOLING_STATUS_CACHE.clear()


def run_tooling_action(
    workspace_root: Path,
    *,
    action: str,
    tool: str,
    model: str = "",
) -> dict[str, Any]:
    normalized_action = str(action or "").strip().lower()
    normalized_tool = str(tool or "").strip().lower()
    normalized_model = str(model or "").strip().lower()
    if normalized_tool not in {"codex", "gemini", "claude", "ollama"}:
        raise ValueError(f"Unsupported tooling target: {tool}")
    if normalized_action not in {"install", "connect"}:
        raise ValueError(f"Unsupported tooling action: {action}")
    if normalized_action == "connect" and normalized_tool != "ollama":
        raise ValueError("Only Ollama supports the connect action.")

    _invalidate_tooling_status_cache()
    _append_tooling_event(
        workspace_root,
        {
            "tool": normalized_tool,
            "action": normalized_action,
            "phase": "started",
            "model": normalized_model,
        },
    )
    try:
        if normalized_action == "install":
            if normalized_tool == "ollama":
                result = _install_ollama()
            else:
                result = _install_cli_package(normalized_tool)
        else:
            result = _connect_ollama(normalized_model)
        _append_tooling_event(
            workspace_root,
            {
                "tool": normalized_tool,
                "action": normalized_action,
                "phase": "completed",
                "model": normalized_model,
                "result": result,
            },
        )
        return result
    except Exception as exc:
        _append_tooling_event(
            workspace_root,
            {
                "tool": normalized_tool,
                "action": normalized_action,
                "phase": "failed",
                "model": normalized_model,
                "error": str(exc).strip(),
            },
        )
        raise
    finally:
        _invalidate_tooling_status_cache()


def _append_tooling_event(workspace_root: Path, payload: dict[str, Any]) -> None:
    append_jsonl(
        Path(workspace_root) / _TOOLING_EVENT_LOG,
        {
            "timestamp": now_utc_iso(),
            **payload,
        },
    )


def _npm_status(*, startup_safe: bool = False) -> ToolingStatus:
    command = "npm.cmd" if os.name == "nt" else "npm"
    resolved_command = _resolve_command(command)
    installed = bool(resolved_command)
    version = _command_version(resolved_command) if installed and not startup_safe else ""
    reason = (
        "npm is available for installing terminal agents."
        if installed
        else "Node.js/npm is required to install Codex, Gemini, and Claude Code."
    )
    return ToolingStatus(
        tool="npm",
        display_name=_DISPLAY_NAMES["npm"],
        command=command,
        resolved_command=resolved_command,
        installed=installed,
        version=version,
        reason=reason,
        install_hint="Install Node.js first if npm is missing.",
    )


def _cli_status(tool: str, *, startup_safe: bool = False) -> ToolingStatus:
    command = default_codex_path("openai" if tool == "codex" else tool)
    resolved_command = _resolve_command(command)
    installed = bool(resolved_command)
    version = _command_version(resolved_command) if installed and not startup_safe else ""
    reason = (
        f"{_DISPLAY_NAMES[tool]} is installed."
        if installed
        else f"{_DISPLAY_NAMES[tool]} is not installed."
    )
    return ToolingStatus(
        tool=tool,
        display_name=_DISPLAY_NAMES[tool],
        command=command,
        resolved_command=resolved_command,
        installed=installed,
        version=version,
        reason=reason,
        install_hint=(
            f"Install with npm package {_NPM_PACKAGES[tool]}."
            if tool in _NPM_PACKAGES
            else ""
        ),
    )


def _ollama_status(*, startup_safe: bool = False, include_details: bool = True) -> ToolingStatus:
    model_store_root = _ollama_model_store_root()
    _migrate_legacy_ollama_model_store(model_store_root)
    resolved_command = _resolve_command("ollama")
    installed = bool(resolved_command)
    version = _command_version(resolved_command) if installed and not startup_safe else ""
    details_requested = include_details and not startup_safe
    if not details_requested:
        running = None
        models: list[str] = []
    else:
        running, runtime_models = _ollama_runtime_status() if installed else (False, [])
        managed_models = _managed_ollama_models(model_store_root)
        models = _merge_model_names(runtime_models, managed_models)
    if not installed:
        reason = "Ollama is not installed."
    elif startup_safe:
        reason = "Ollama is installed. Detailed runtime status loads after startup."
    elif not include_details:
        reason = "Ollama is installed. Open the model manager to load runtime details."
    elif running and models:
        reason = f"Ollama is connected with {len(models)} installed model(s)."
    elif models:
        reason = f"Ollama found {len(models)} model(s) in the managed model store."
    elif running:
        reason = "Ollama is running but no models are installed yet."
    else:
        reason = "Ollama is installed but the local server is not running."
    return ToolingStatus(
        tool="ollama",
        display_name=_DISPLAY_NAMES["ollama"],
        command="ollama",
        resolved_command=resolved_command,
        installed=installed,
        version=version,
        running=running,
        models=models,
        recommended_models=list(_OLLAMA_SUGGESTED_MODELS),
        model_store_path=str(model_store_root),
        reason=reason,
        install_hint="Install Ollama, then connect and pull a model.",
    )


def _install_cli_package(tool: str) -> dict[str, Any]:
    status = _cli_status(tool)
    if status.installed:
        return {
            "tool": tool,
            "action": "install",
            "changed": False,
            "message": f"{status.display_name} is already installed.",
        }
    npm_status = _npm_status()
    if not npm_status.installed:
        raise RuntimeError(npm_status.reason)
    package_name = _NPM_PACKAGES[tool]
    completed = run_subprocess(
        [npm_status.resolved_command or npm_status.command, "install", "-g", package_name],
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout_seconds=_INSTALL_TIMEOUT_SECONDS,
    )
    if completed.returncode != 0:
        raise RuntimeError(_subprocess_error_message(completed, f"Failed to install {package_name}."))
    installed_status = _cli_status(tool)
    if not installed_status.installed:
        raise RuntimeError(f"{installed_status.display_name} did not appear on PATH after installation.")
    return {
        "tool": tool,
        "action": "install",
        "changed": True,
        "message": f"Installed {installed_status.display_name}.",
        "version": installed_status.version,
    }


def _install_ollama() -> dict[str, Any]:
    status = _ollama_status()
    if status.installed:
        return {
            "tool": "ollama",
            "action": "install",
            "changed": False,
            "message": "Ollama is already installed.",
        }
    if os.name == "nt":
        _download_and_run_ollama_windows_installer()
    else:
        raise RuntimeError("Automatic Ollama installation is only wired for Windows right now.")
    installed_status = _ollama_status()
    if not installed_status.installed:
        raise RuntimeError("Ollama installation finished but the command was not detected.")
    return {
        "tool": "ollama",
        "action": "install",
        "changed": True,
        "message": "Installed Ollama.",
        "version": installed_status.version,
    }


def _connect_ollama(model: str) -> dict[str, Any]:
    status = _ollama_status()
    if not status.installed:
        raise RuntimeError("Install Ollama before trying to connect.")
    model_store_root = _configure_ollama_model_store()
    _ensure_ollama_running()
    selected_model = str(model or "").strip().lower() or _default_ollama_model_name()
    running, current_models = _ollama_runtime_status()
    if not running:
        raise RuntimeError("Ollama is installed but the local API did not come online.")
    if selected_model and selected_model not in {item.lower() for item in current_models}:
        completed = run_subprocess(
            [_resolve_command("ollama") or "ollama", "pull", selected_model],
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout_seconds=_INSTALL_TIMEOUT_SECONDS,
            env=_ollama_runtime_env(model_store_root),
        )
        if completed.returncode != 0:
            raise RuntimeError(_subprocess_error_message(completed, f"Failed to pull {selected_model} from Ollama."))
    running, runtime_models = _ollama_runtime_status()
    models = _merge_model_names(runtime_models, _managed_ollama_models(model_store_root))
    return {
        "tool": "ollama",
        "action": "connect",
        "changed": selected_model.lower() not in {item.lower() for item in current_models},
        "message": (
            f"Connected Ollama and pulled {selected_model}."
            if selected_model
            else "Connected Ollama."
        ),
        "model": selected_model,
        "models": models,
        "running": running,
        "model_store_path": str(model_store_root),
    }


def _download_and_run_ollama_windows_installer() -> None:
    with tempfile.TemporaryDirectory(prefix="jakal-flow-ollama-") as temp_dir:
        installer_path = Path(temp_dir) / "OllamaSetup.exe"
        try:
            with urllib_request.urlopen(_OLLAMA_INSTALLER_URL, timeout=60.0) as response:
                installer_path.write_bytes(response.read())
        except OSError as exc:
            raise RuntimeError(f"Failed to download the Ollama installer: {exc}") from exc
        completed = run_subprocess(
            [str(installer_path)],
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout_seconds=_INSTALL_TIMEOUT_SECONDS,
        )
        if completed.returncode not in {0, 1641, 3010}:
            raise RuntimeError(_subprocess_error_message(completed, "The Ollama installer did not complete successfully."))
        _wait_for_condition(lambda: _ollama_status().installed, timeout_seconds=30.0)


def _ensure_ollama_running() -> None:
    running, _models = _ollama_runtime_status()
    if running:
        return
    resolved_command = _resolve_command("ollama")
    if not resolved_command:
        raise RuntimeError("Ollama is not installed.")
    popen_kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
    else:
        popen_kwargs["start_new_session"] = True
    try:
        subprocess.Popen([resolved_command, "serve"], env=_ollama_runtime_env(_configure_ollama_model_store()), **popen_kwargs)
    except OSError as exc:
        raise RuntimeError(f"Failed to start Ollama: {exc}") from exc
    if not _wait_for_condition(lambda: _ollama_runtime_status()[0], timeout_seconds=_OLLAMA_CONNECT_TIMEOUT_SECONDS):
        raise RuntimeError("Timed out waiting for the Ollama server to start.")


def _ollama_runtime_status() -> tuple[bool, list[str]]:
    try:
        payload = _ollama_api_request("/api/tags", timeout_seconds=4.0)
    except RuntimeError:
        return False, []
    raw_models = payload.get("models", [])
    if not isinstance(raw_models, list):
        return True, []
    models = []
    for item in raw_models:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if name:
            models.append(name)
    return True, models


def _ollama_api_request(
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout_seconds: float,
) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    method = "GET"
    if payload is not None:
        method = "POST"
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    request = urllib_request.Request(f"{_OLLAMA_API_ROOT}{path}", data=data, headers=headers, method=method)
    try:
        with urllib_request.urlopen(request, timeout=timeout_seconds) as response:
            raw_body = response.read().decode("utf-8", errors="replace").strip()
    except (urllib_error.URLError, urllib_error.HTTPError, OSError) as exc:
        raise RuntimeError(f"Ollama API request failed: {exc}") from exc
    if not raw_body:
        return {}
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Ollama returned malformed JSON.") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Ollama returned an unexpected response payload.")
    error_message = str(payload.get("error", "")).strip()
    if error_message:
        raise RuntimeError(error_message)
    return payload


def _default_ollama_model_name() -> str:
    detected = default_local_model("ollama", "ollama")
    return str(detected or _DEFAULT_OLLAMA_MODEL).strip().lower()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _legacy_repo_ollama_model_store_root() -> Path:
    return _repo_root() / "third_party" / "ollama" / "models"


def _ollama_model_store_root() -> Path:
    return configured_ollama_model_store_root(legacy_root=_legacy_repo_ollama_model_store_root())


def _migrate_legacy_ollama_model_store(model_store_root: Path) -> bool:
    legacy_root = _legacy_repo_ollama_model_store_root()
    try:
        if legacy_root.resolve() == model_store_root.resolve():
            return False
    except OSError:
        if str(legacy_root) == str(model_store_root):
            return False
    if not legacy_root.exists():
        return False
    if model_store_root.exists():
        try:
            next(model_store_root.iterdir())
            return False
        except StopIteration:
            try:
                model_store_root.rmdir()
            except OSError:
                return False
        except OSError:
            return False
    try:
        model_store_root.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy_root), str(model_store_root))
        return True
    except OSError:
        return False


def _ollama_model_store_is_app_managed() -> bool:
    explicit_override = str(os.environ.get(OLLAMA_MODELS_ENV_VAR, "") or "").strip()
    if explicit_override:
        return False
    existing_store = str(os.environ.get("OLLAMA_MODELS", "") or "").strip()
    if existing_store:
        candidate = Path(existing_store).expanduser().resolve()
        try:
            if candidate != _legacy_repo_ollama_model_store_root().resolve():
                return False
        except OSError:
            if str(candidate) != str(_legacy_repo_ollama_model_store_root()):
                return False
    return _ollama_model_store_root() == default_ollama_model_store_root()


def _configure_ollama_model_store() -> Path:
    root = _ollama_model_store_root()
    _migrate_legacy_ollama_model_store(root)
    root.mkdir(parents=True, exist_ok=True)
    os.environ["OLLAMA_MODELS"] = str(root)
    if os.name == "nt" and _ollama_model_store_is_app_managed():
        _persist_windows_ollama_models_env(root)
    return root


def _persist_windows_ollama_models_env(model_store_root: Path) -> None:
    target = str(model_store_root)
    try:
        run_subprocess(
            ["setx", "OLLAMA_MODELS", target],
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout_seconds=30.0,
        )
    except Exception:
        return


def _ollama_runtime_env(model_store_root: Path | None = None) -> dict[str, str]:
    root = model_store_root or _ollama_model_store_root()
    root.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["OLLAMA_MODELS"] = str(root)
    return env


def _merge_model_names(*model_groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in model_groups:
        for item in group or []:
            name = str(item or "").strip()
            key = name.lower()
            if not name or key in seen:
                continue
            seen.add(key)
            merged.append(name)
    return merged


def _managed_ollama_models(model_store_root: Path | None = None) -> list[str]:
    manifest_root = (model_store_root or _ollama_model_store_root()) / "manifests" / "registry.ollama.ai" / "library"
    if not manifest_root.exists():
        return []
    models: list[str] = []
    for family_dir in sorted(path for path in manifest_root.iterdir() if path.is_dir()):
        for tag_path in sorted(path for path in family_dir.iterdir() if path.is_file()):
            model_name = f"{family_dir.name}:{tag_path.name}"
            if model_name not in models:
                models.append(model_name)
    return models


def _command_version(command: str) -> str:
    resolved_command = str(command or "").strip()
    if not resolved_command:
        return ""
    try:
        completed = run_subprocess(
            [resolved_command, "--version"],
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout_seconds=_CLI_VERSION_TIMEOUT_SECONDS,
        )
    except OSError:
        return ""
    output = str(completed.stdout or completed.stderr or "").strip()
    if not output:
        return ""
    return output.splitlines()[0].strip()


def _resolve_command(command: str) -> str:
    candidate = str(command or "").strip()
    if not candidate:
        return ""
    if candidate in {
        default_codex_path("openai"),
        default_codex_path("claude"),
        default_codex_path("gemini"),
        default_codex_path("qwen_code"),
    }:
        resolved = str(resolve_codex_path(candidate)).strip()
        if _command_exists(resolved):
            return resolved
        return ""
    resolved = shutil.which(candidate)
    return str(resolved or "").strip()


def _command_exists(command: str) -> bool:
    candidate = str(command or "").strip()
    if not candidate:
        return False
    if "\\" in candidate or "/" in candidate:
        return Path(candidate).expanduser().exists()
    return shutil.which(candidate) is not None


def _subprocess_error_message(completed: subprocess.CompletedProcess[Any], fallback: str) -> str:
    stderr = str(completed.stderr or "").strip()
    stdout = str(completed.stdout or "").strip()
    detail = stderr or stdout
    if not detail:
        return fallback
    line = detail.splitlines()[0].strip()
    return f"{fallback} {line}".strip()


def _wait_for_condition(callback, *, timeout_seconds: float, interval_seconds: float = 0.5) -> bool:
    deadline = time.monotonic() + max(0.1, float(timeout_seconds))
    while time.monotonic() < deadline:
        try:
            if callback():
                return True
        except Exception:
            pass
        time.sleep(interval_seconds)
    return False
