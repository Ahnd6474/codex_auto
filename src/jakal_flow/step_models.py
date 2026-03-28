from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path
import re
import shutil
from typing import Any, Callable

from .codex_app_server import fetch_codex_backend_snapshot
from .model_constants import VALID_MODEL_PROVIDERS
from .model_providers import provider_preset
from .models import ExecutionStep, RuntimeOptions
from .platform_defaults import default_codex_path

CLAUDE_DEFAULT_MODEL = "claude-sonnet-4-6"
GEMINI_DEFAULT_MODEL = "gemini-3-flash-preview"
_OPENAI_AUTH_ENV_VARS = ("OPENAI_API_KEY",)
_CLAUDE_AUTH_ENV_VARS = ("ANTHROPIC_API_KEY",)
_GEMINI_AUTH_ENV_VARS = (
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GOOGLE_GENAI_USE_VERTEXAI",
    "GOOGLE_GENAI_USE_GCA",
)

_UI_PATH_PREFIXES = (
    "desktop/",
    "frontend/",
    "ui/",
    "web/",
    "website/",
)
_UI_SUFFIXES = (".css", ".scss", ".sass", ".less", ".jsx", ".tsx", ".html")
_UI_KEYWORD_PATTERN = re.compile(
    r"\b("
    r"ui|ux|frontend|react|tauri|desktop|screen|layout|style|styling|theme|component|"
    r"button|sidebar|toolbar|panel|modal|dialog|form|page|view"
    r")\b",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class StepModelChoice:
    provider: str
    model: str
    source: str
    reason: str


def normalize_step_model_provider(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in VALID_MODEL_PROVIDERS:
        return normalized
    return ""


def normalize_step_model(value: str) -> str:
    return str(value or "").strip().lower()


def resolve_step_model_choice(step: ExecutionStep, runtime: RuntimeOptions) -> StepModelChoice:
    explicit_provider = normalize_step_model_provider(getattr(step, "model_provider", ""))
    explicit_model = normalize_step_model(getattr(step, "model", ""))
    if explicit_provider:
        return StepModelChoice(
            provider=explicit_provider,
            model=explicit_model or _default_model_for_provider(explicit_provider, runtime),
            source="manual",
            reason="step override",
        )

    if _looks_like_ui_step(step):
        provider, reason = _ui_provider_choice(runtime)
        return StepModelChoice(
            provider=provider,
            model=explicit_model or _default_model_for_provider(provider, runtime),
            source="auto",
            reason=reason,
        )

    provider, reason = _general_provider_choice(runtime)
    return StepModelChoice(
        provider=provider,
        model=explicit_model or _default_model_for_provider(provider, runtime),
        source="auto",
        reason=reason,
    )


def provider_statuses_payload(
    fetch_snapshot: Callable[[str], Any] | None = None,
) -> dict[str, dict[str, Any]]:
    fetch = fetch_snapshot or fetch_codex_backend_snapshot
    openai_status = _provider_status_from_snapshot("openai", _snapshot_to_dict(fetch(default_codex_path("openai"))))
    claude_status = _provider_status_from_snapshot("claude", _snapshot_to_dict(fetch(default_codex_path("claude"))))
    gemini_status = _provider_status_from_snapshot("gemini", _snapshot_to_dict(fetch(default_codex_path("gemini"))))
    statuses = {
        "openai": openai_status,
        "claude": claude_status,
        "gemini": gemini_status,
    }
    statuses["ensemble"] = _ensemble_provider_status(statuses)
    return statuses


def planning_model_selection_guidance(
    runtime: RuntimeOptions,
    fetch_snapshot: Callable[[str], Any] | None = None,
) -> str:
    if _routing_mode(runtime) != "ensemble":
        return "\n".join(
            [
                "Default routing for this run:",
                "- General implementation steps should stay on `openai` with the current Codex model selection.",
                "- UI, frontend, desktop, web, and visual polish steps may use `gemini` when Gemini CLI is configured; otherwise keep them on `openai`.",
                "- If you do not need to pin a provider for a non-ensemble run, leaving `model_provider` and `model` blank is acceptable.",
            ]
        )

    statuses = provider_statuses_payload(fetch_snapshot=fetch_snapshot)
    planning_provider, planning_reason = _general_provider_choice(runtime)
    planning_model = _default_model_for_provider(planning_provider, runtime) or "provider default"
    ui_provider, ui_reason = _ui_provider_choice(runtime)
    ui_model = _default_model_for_provider(ui_provider, runtime) or "provider default"

    lines = [
        "Available execution backends on this machine:",
    ]
    for provider_name in ("openai", "claude", "gemini", "ensemble"):
        status = statuses[provider_name]
        state = "usable" if status["usable"] else ("available but not configured" if status["available"] else "unavailable")
        details = status.get("reason", "")
        default_model = status.get("default_model", "")
        model_suffix = f"; default model `{default_model}`" if default_model else ""
        detail_suffix = f"; {details}" if details else ""
        lines.append(f"- `{provider_name}`: {state}{model_suffix}{detail_suffix}")

    lines.extend(
        [
            "",
            "Routing policy for this run:",
            (
                f"- Planning and general implementation steps should use `{planning_provider}`"
                f" with model `{planning_model}`. Reason: {planning_reason}."
            ),
            (
                f"- UI, frontend, desktop, web, and visual polish steps should use `{ui_provider}`"
                f" with model `{ui_model}`. Reason: {ui_reason}."
            ),
            "- Only assign providers marked usable above unless the target repository explicitly pins a different backend.",
            "- In ensemble mode, set `model_provider` and `model` explicitly for every planned task.",
        ]
    )
    return "\n".join(lines)


def claude_available_for_auto_selection() -> bool:
    if not _command_available(default_codex_path("claude")):
        return False
    return _claude_auth_env_configured() or _claude_cli_authenticated()


def gemini_available_for_auto_selection() -> bool:
    return _command_available(default_codex_path("gemini")) and (
        _gemini_auth_env_configured() or _gemini_settings_file_configured()
    )


def _general_provider_choice(runtime: RuntimeOptions) -> tuple[str, str]:
    if _routing_mode(runtime) == "ensemble":
        return "openai", "Ensemble primary coding preference"
    return "openai", "AGENTS.md Codex preference"


def _ui_provider_choice(runtime: RuntimeOptions) -> tuple[str, str]:
    if _routing_mode(runtime) == "ensemble":
        if claude_available_for_auto_selection():
            return "claude", "Ensemble UI preference"
        if gemini_available_for_auto_selection():
            return "gemini", "Ensemble UI fallback because Claude Code is not configured"
        return "openai", "Ensemble UI fallback because Claude Code and Gemini CLI are not configured"

    if gemini_available_for_auto_selection():
        return "gemini", "AGENTS.md UI preference"
    return "openai", "AGENTS.md UI preference skipped because Gemini auth is not configured"


def _routing_mode(runtime: RuntimeOptions) -> str:
    runtime_provider = normalize_step_model_provider(getattr(runtime, "model_provider", ""))
    return "ensemble" if runtime_provider == "ensemble" else "agents"


def _default_model_for_provider(provider: str, runtime: RuntimeOptions) -> str:
    normalized_provider = normalize_step_model_provider(provider) or "openai"
    runtime_provider = str(getattr(runtime, "model_provider", "") or "").strip().lower()
    runtime_model = normalize_step_model(getattr(runtime, "model", "") or getattr(runtime, "model_slug_input", ""))
    if normalized_provider == "gemini":
        if runtime_provider == "gemini" and runtime_model:
            return runtime_model
        return GEMINI_DEFAULT_MODEL
    if normalized_provider == "claude":
        if runtime_provider == "claude" and runtime_model:
            return runtime_model
        return CLAUDE_DEFAULT_MODEL
    if normalized_provider in {"ensemble", "openai"}:
        if runtime_provider in {"ensemble", "openai"} and runtime_model:
            return runtime_model
        return runtime_model or "auto"
    if runtime_provider == normalized_provider and runtime_model:
        return runtime_model
    return ""


def _looks_like_ui_step(step: ExecutionStep) -> bool:
    for raw_path in getattr(step, "owned_paths", []) or []:
        normalized_path = str(raw_path or "").strip().replace("\\", "/").lower()
        if not normalized_path:
            continue
        if normalized_path.startswith(_UI_PATH_PREFIXES):
            return True
        if normalized_path.startswith("desktop/") or normalized_path.endswith(_UI_SUFFIXES):
            return True
    text = " ".join(
        [
            str(getattr(step, "title", "") or ""),
            str(getattr(step, "display_description", "") or ""),
            str(getattr(step, "codex_description", "") or ""),
        ]
    )
    return bool(_UI_KEYWORD_PATTERN.search(text))


def _provider_status_from_snapshot(provider: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    preset = provider_preset(provider)
    account = snapshot.get("account", {}) if isinstance(snapshot.get("account", {}), dict) else {}
    available = bool(snapshot.get("available", False))
    default_model = ""
    if provider == "claude":
        default_model = CLAUDE_DEFAULT_MODEL
    elif provider == "gemini":
        default_model = GEMINI_DEFAULT_MODEL
    elif provider == "openai":
        default_model = "auto"

    if provider == "openai":
        configured = _openai_auth_env_configured() or bool(account.get("authenticated"))
        usable = available and configured
        if usable:
            reason = "Codex CLI is available for planning and general execution."
        elif available:
            reason = "Codex CLI is available but OpenAI authentication is not configured."
        else:
            reason = snapshot.get("error", "") or "Codex CLI is not available."
    elif provider == "claude":
        configured = _claude_auth_env_configured() or bool(account.get("authenticated"))
        usable = available and configured
        if usable:
            reason = "Claude Code is ready for frontend or UI-oriented steps."
        elif available:
            reason = "Claude Code is installed but Anthropic authentication is not configured."
        else:
            reason = snapshot.get("error", "") or "Claude Code is not available."
    else:
        configured = _gemini_auth_env_configured() or _gemini_settings_file_configured()
        usable = available and configured
        if usable:
            reason = "Gemini CLI can be used as an ensemble fallback."
        elif available:
            reason = "Gemini CLI is installed but Gemini authentication is not configured."
        else:
            reason = snapshot.get("error", "") or "Gemini CLI is not available."

    return {
        "provider": provider,
        "display_name": preset.display_name,
        "available": available,
        "configured": configured,
        "usable": usable,
        "default_model": default_model,
        "codex_path": default_codex_path(provider),
        "reason": str(reason or "").strip(),
    }


def _ensemble_provider_status(statuses: dict[str, dict[str, Any]]) -> dict[str, Any]:
    openai_status = statuses.get("openai", {})
    claude_status = statuses.get("claude", {})
    gemini_status = statuses.get("gemini", {})
    ui_provider = "claude" if claude_status.get("usable") else ("gemini" if gemini_status.get("usable") else "openai")
    ui_model = (
        CLAUDE_DEFAULT_MODEL
        if ui_provider == "claude"
        else (GEMINI_DEFAULT_MODEL if ui_provider == "gemini" else "auto")
    )
    usable = bool(openai_status.get("usable"))
    if usable:
        reason = f"Uses Codex for planning/general work and `{ui_provider}` for UI/front-end steps."
    else:
        reason = "The ensemble requires a usable Codex backend for planning and general execution."
    return {
        "provider": "ensemble",
        "display_name": provider_preset("ensemble").display_name,
        "available": bool(openai_status.get("available")),
        "configured": bool(openai_status.get("configured")),
        "usable": usable,
        "default_model": _default_model_for_provider("openai", RuntimeOptions()),
        "planning_provider": "openai",
        "ui_provider": ui_provider,
        "ui_model": ui_model,
        "codex_path": default_codex_path("openai"),
        "reason": reason,
    }


def _snapshot_to_dict(snapshot: Any) -> dict[str, Any]:
    if isinstance(snapshot, dict):
        return snapshot
    to_dict = getattr(snapshot, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, dict):
            return payload
    return {
        "available": bool(getattr(snapshot, "available", False)),
        "account": getattr(snapshot, "account", {}) or {},
        "error": str(getattr(snapshot, "error", "") or "").strip(),
    }


def _command_available(command: str) -> bool:
    candidate = str(command or "").strip()
    if not candidate:
        return False
    if "\\" in candidate or "/" in candidate:
        return Path(candidate).expanduser().exists()
    return shutil.which(candidate) is not None


def _openai_auth_env_configured() -> bool:
    return any(str(os.environ.get(name, "")).strip() for name in _OPENAI_AUTH_ENV_VARS)


def _claude_auth_env_configured() -> bool:
    return any(str(os.environ.get(name, "")).strip() for name in _CLAUDE_AUTH_ENV_VARS)


@lru_cache(maxsize=1)
def _claude_cli_authenticated() -> bool:
    snapshot = _snapshot_to_dict(fetch_codex_backend_snapshot(default_codex_path("claude")))
    account = snapshot.get("account", {}) if isinstance(snapshot.get("account", {}), dict) else {}
    return bool(account.get("authenticated"))


def _gemini_auth_env_configured() -> bool:
    return any(str(os.environ.get(name, "")).strip() for name in _GEMINI_AUTH_ENV_VARS)


def _gemini_settings_file_configured(settings_path: Path | None = None) -> bool:
    candidate = settings_path or (Path.home() / ".gemini" / "settings.json")
    try:
        if not candidate.is_file():
            return False
        return bool(candidate.read_text(encoding="utf-8", errors="replace").strip())
    except OSError:
        return False
