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
from .model_providers import discover_local_model_catalog, provider_preset
from .models import ExecutionStep, RuntimeOptions
from .platform_defaults import default_codex_path

CLAUDE_DEFAULT_MODEL = "claude-sonnet-4-6"
GEMINI_DEFAULT_MODEL = "gemini-3-flash-preview"
QWEN_CODE_DEFAULT_MODEL = "qwen3-coder-plus"
DEEPSEEK_DEFAULT_MODEL = "deepseek-chat"
KIMI_DEFAULT_MODEL = "kimi-k2.5"
MINIMAX_DEFAULT_MODEL = "MiniMax-M2.5"
GLM_DEFAULT_MODEL = "glm-4.7"
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
    fetch = fetch_snapshot
    snapshots = {
        "openai": _snapshot_to_dict(fetch(default_codex_path("openai"))) if callable(fetch) else {},
        "claude": _snapshot_to_dict(fetch(default_codex_path("claude"))) if callable(fetch) else {},
        "gemini": _snapshot_to_dict(fetch(default_codex_path("gemini"))) if callable(fetch) else {},
        "qwen_code": _snapshot_to_dict(fetch(default_codex_path("qwen_code"))) if callable(fetch) else {},
    }
    local_models = discover_local_model_catalog()
    openai_status = _provider_status_from_snapshot("openai", snapshots["openai"])
    claude_status = _provider_status_from_snapshot("claude", snapshots["claude"])
    gemini_status = _provider_status_from_snapshot("gemini", snapshots["gemini"])
    statuses = {
        "openai": openai_status,
        "openrouter": _provider_status_from_snapshot("openrouter", snapshots["openai"]),
        "opencdk": _provider_status_from_snapshot("opencdk", snapshots["openai"]),
        "local_openai": _provider_status_from_snapshot("local_openai", snapshots["openai"]),
        "claude": claude_status,
        "deepseek": _provider_status_from_snapshot("deepseek", snapshots["claude"]),
        "gemini": gemini_status,
        "qwen_code": _provider_status_from_snapshot("qwen_code", snapshots["qwen_code"]),
        "kimi": _provider_status_from_snapshot("kimi", snapshots["openai"]),
        "minimax": _provider_status_from_snapshot("minimax", snapshots["claude"]),
        "glm": _provider_status_from_snapshot("glm", snapshots["claude"]),
        "oss": _local_oss_provider_status(local_models, snapshots["openai"]),
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
    ensemble_openai_model = normalize_step_model(getattr(runtime, "ensemble_openai_model", ""))
    ensemble_gemini_model = normalize_step_model(getattr(runtime, "ensemble_gemini_model", ""))
    ensemble_claude_model = normalize_step_model(getattr(runtime, "ensemble_claude_model", ""))
    if normalized_provider == "gemini":
        if runtime_provider == "ensemble" and ensemble_gemini_model:
            return ensemble_gemini_model
        if runtime_provider == "gemini" and runtime_model:
            return runtime_model
        return GEMINI_DEFAULT_MODEL
    if normalized_provider == "claude":
        if runtime_provider == "ensemble" and ensemble_claude_model:
            return ensemble_claude_model
        if runtime_provider == "claude" and runtime_model:
            return runtime_model
        return CLAUDE_DEFAULT_MODEL
    if normalized_provider == "qwen_code":
        if runtime_provider == "qwen_code" and runtime_model:
            return runtime_model
        return QWEN_CODE_DEFAULT_MODEL
    if normalized_provider == "deepseek":
        if runtime_provider == "deepseek" and runtime_model:
            return runtime_model
        return DEEPSEEK_DEFAULT_MODEL
    if normalized_provider == "kimi":
        if runtime_provider == "kimi" and runtime_model:
            return runtime_model
        return KIMI_DEFAULT_MODEL
    if normalized_provider == "minimax":
        if runtime_provider == "minimax" and runtime_model:
            return runtime_model
        return MINIMAX_DEFAULT_MODEL
    if normalized_provider == "glm":
        if runtime_provider == "glm" and runtime_model:
            return runtime_model
        return GLM_DEFAULT_MODEL
    if normalized_provider in {"ensemble", "openai"}:
        if runtime_provider == "ensemble" and ensemble_openai_model:
            return ensemble_openai_model
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
    available = _command_available(default_codex_path(provider))
    default_model = _provider_default_model(provider)

    if provider == "openai":
        configured = _openai_auth_env_configured() or bool(account.get("authenticated"))
        usable = available and configured
        if usable:
            reason = "Codex CLI is available for planning and general execution."
        elif available:
            reason = "Codex CLI is installed but OpenAI authentication is not configured."
        else:
            reason = snapshot.get("error", "") or "Codex CLI is not installed."
    elif provider == "claude":
        configured = _claude_auth_env_configured() or bool(account.get("authenticated"))
        usable = available and configured
        if usable:
            reason = "Claude Code is ready for frontend or UI-oriented steps."
        elif available:
            reason = "Claude Code is installed but Anthropic authentication is not configured."
        else:
            reason = snapshot.get("error", "") or "Claude Code is not installed."
    elif provider == "gemini":
        configured = _gemini_auth_env_configured() or _gemini_settings_file_configured()
        usable = available and configured
        if usable:
            reason = "Gemini CLI can be used as an ensemble fallback."
        elif available:
            reason = "Gemini CLI is installed but Gemini authentication is not configured."
        else:
            reason = snapshot.get("error", "") or "Gemini CLI is not installed."
    elif provider == "qwen_code":
        configured = _provider_api_env_configured(provider)
        usable = available and configured
        if usable:
            reason = "Qwen Code is installed and DashScope authentication is configured."
        elif available:
            reason = "Qwen Code is installed but DashScope authentication is not configured."
        else:
            reason = snapshot.get("error", "") or "Qwen Code is not installed."
    elif provider in {"deepseek", "minimax", "glm"}:
        configured = _provider_api_env_configured(provider) or _claude_auth_env_configured() or bool(account.get("authenticated"))
        usable = available and configured
        if usable:
            reason = f"{preset.display_name} is ready through the Claude Code backend."
        elif available:
            reason = f"{preset.display_name} shares the Claude Code backend but its API credentials are not configured."
        else:
            reason = snapshot.get("error", "") or "Claude Code is not installed."
    elif provider in {"kimi", "openrouter", "opencdk"}:
        configured = _provider_api_env_configured(provider)
        usable = available and configured
        if usable:
            reason = f"{preset.display_name} is ready through the Codex/OpenAI-compatible backend."
        elif available:
            reason = f"{preset.display_name} is installed but its API credentials are not configured."
        else:
            reason = snapshot.get("error", "") or "Codex CLI is not installed."
    elif provider == "local_openai":
        configured = available
        usable = available
        if usable:
            reason = "Codex CLI is installed; point it at a running local OpenAI-compatible endpoint to use this backend."
        else:
            reason = snapshot.get("error", "") or "Codex CLI is not installed."
    else:
        configured = available
        usable = available
        reason = snapshot.get("error", "") or (f"{preset.display_name} is available." if available else f"{preset.display_name} is not installed.")

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


def _local_oss_provider_status(local_models: list[dict[str, Any]], openai_snapshot: dict[str, Any]) -> dict[str, Any]:
    preset = provider_preset("oss")
    codex_available = _command_available(default_codex_path("openai"))
    available_models = [item for item in local_models if isinstance(item, dict) and str(item.get("model", "")).strip()]
    available = codex_available and bool(available_models)
    configured = bool(available_models)
    usable = available
    default_model = str(available_models[0].get("model", "")).strip().lower() if available_models else ""
    if usable:
        reason = f"Local OSS mode is ready with {len(available_models)} detected local model(s)."
    elif codex_available:
        reason = "Local OSS mode requires at least one detected local model from Ollama or the bundled catalog."
    else:
        reason = str(openai_snapshot.get("error", "") or "Codex CLI is not installed.").strip()
    return {
        "provider": "oss",
        "display_name": preset.display_name,
        "available": available,
        "configured": configured,
        "usable": usable,
        "default_model": default_model,
        "codex_path": default_codex_path("openai"),
        "reason": reason,
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
    required_providers = ("openai", "claude", "gemini")
    missing_installs = [provider for provider in required_providers if not bool(statuses.get(provider, {}).get("available"))]
    missing_config = [provider for provider in required_providers if bool(statuses.get(provider, {}).get("available")) and not bool(statuses.get(provider, {}).get("configured"))]
    available = not missing_installs
    configured = not missing_installs and not missing_config
    usable = all(bool(statuses.get(provider, {}).get("usable")) for provider in required_providers)
    if usable:
        reason = "Uses Codex for planning/general work, Claude for UI/front-end steps, and Gemini as the fallback."
    elif missing_installs:
        reason = f"The ensemble requires all three installed backends: missing {', '.join(missing_installs)}."
    elif missing_config:
        reason = f"The ensemble has all three CLIs installed, but these backends still need credentials: {', '.join(missing_config)}."
    else:
        reason = "The ensemble requires Codex, Claude Code, and Gemini CLI to be usable together."
    return {
        "provider": "ensemble",
        "display_name": provider_preset("ensemble").display_name,
        "available": available,
        "configured": configured,
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


def _provider_api_env_configured(provider: str) -> bool:
    env_name = str(provider_preset(provider).default_api_key_env or "").strip()
    return bool(env_name and str(os.environ.get(env_name, "")).strip())


def _provider_default_model(provider: str) -> str:
    if provider == "claude":
        return CLAUDE_DEFAULT_MODEL
    if provider == "gemini":
        return GEMINI_DEFAULT_MODEL
    if provider == "qwen_code":
        return QWEN_CODE_DEFAULT_MODEL
    if provider == "deepseek":
        return DEEPSEEK_DEFAULT_MODEL
    if provider == "kimi":
        return KIMI_DEFAULT_MODEL
    if provider == "minimax":
        return MINIMAX_DEFAULT_MODEL
    if provider == "glm":
        return GLM_DEFAULT_MODEL
    if provider in {"openai", "ensemble"}:
        return "auto"
    return ""
