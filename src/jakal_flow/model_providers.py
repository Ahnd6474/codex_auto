from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .model_constants import (
    BILLING_MODE_INCLUDED,
    BILLING_MODE_PER_PASS,
    BILLING_MODE_TOKEN,
    DEFAULT_LOCAL_MODEL_PROVIDER,
    DEFAULT_MODEL_PROVIDER,
    VALID_LOCAL_MODEL_PROVIDERS,
    VALID_BILLING_MODES,
    VALID_MODEL_PROVIDERS,
)


@dataclass(frozen=True, slots=True)
class ProviderPreset:
    provider: str
    display_name: str
    description: str
    default_base_url: str = ""
    default_api_key_env: str = ""
    default_billing_mode: str = BILLING_MODE_INCLUDED
    supports_auto_model: bool = False
    supports_catalog: bool = False
    is_local: bool = False


PROVIDER_PRESETS: dict[str, ProviderPreset] = {
    "openai": ProviderPreset(
        provider="openai",
        display_name="OpenAI / Codex Cloud",
        description="Use the installed Codex CLI with OpenAI-hosted models and the native model catalog.",
        default_api_key_env="OPENAI_API_KEY",
        default_billing_mode=BILLING_MODE_INCLUDED,
        supports_auto_model=True,
        supports_catalog=True,
    ),
    "gemini": ProviderPreset(
        provider="gemini",
        display_name="Gemini CLI",
        description="Use the installed Gemini CLI in headless mode with Gemini authentication.",
        default_api_key_env="GEMINI_API_KEY",
        default_billing_mode=BILLING_MODE_INCLUDED,
        supports_auto_model=False,
        supports_catalog=False,
    ),
    "openrouter": ProviderPreset(
        provider="openrouter",
        display_name="OpenRouter",
        description="Use an OpenAI-compatible OpenRouter endpoint through Codex CLI base URL overrides.",
        default_base_url="https://openrouter.ai/api/v1",
        default_api_key_env="OPENROUTER_API_KEY",
        default_billing_mode=BILLING_MODE_TOKEN,
        supports_auto_model=False,
        supports_catalog=False,
    ),
    "opencdk": ProviderPreset(
        provider="opencdk",
        display_name="OpenCDK",
        description="Use an OpenAI-compatible OpenCDK endpoint through Codex CLI base URL overrides.",
        default_api_key_env="OPENCDK_API_KEY",
        default_billing_mode=BILLING_MODE_TOKEN,
        supports_auto_model=False,
        supports_catalog=False,
    ),
    "local_openai": ProviderPreset(
        provider="local_openai",
        display_name="Local OpenAI-Compatible",
        description="Use any local server that exposes an OpenAI-compatible API, such as vLLM, llama.cpp, or LocalAI.",
        default_base_url="http://127.0.0.1:1234/v1",
        default_billing_mode=BILLING_MODE_INCLUDED,
        supports_auto_model=False,
        supports_catalog=False,
        is_local=True,
    ),
    "oss": ProviderPreset(
        provider="oss",
        display_name="Local OSS",
        description="Use Codex CLI OSS mode through a local provider such as Ollama or LM Studio.",
        default_billing_mode=BILLING_MODE_PER_PASS,
        supports_auto_model=False,
        supports_catalog=False,
        is_local=True,
    ),
}


def normalize_model_provider(value: str, fallback: str = DEFAULT_MODEL_PROVIDER) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in VALID_MODEL_PROVIDERS:
        return normalized
    return fallback


def normalize_local_model_provider(value: str, fallback: str = "") -> str:
    normalized = str(value or "").strip().lower()
    if normalized in VALID_LOCAL_MODEL_PROVIDERS:
        return normalized
    return fallback


def provider_preset(value: str, fallback: str = DEFAULT_MODEL_PROVIDER) -> ProviderPreset:
    normalized = normalize_model_provider(value, fallback=fallback)
    return PROVIDER_PRESETS.get(normalized, PROVIDER_PRESETS[DEFAULT_MODEL_PROVIDER])


def provider_supports_auto_model(value: str) -> bool:
    return provider_preset(value).supports_auto_model


def provider_supports_catalog(value: str) -> bool:
    return provider_preset(value).supports_catalog


def provider_uses_openai_compatible_api(value: str) -> bool:
    return normalize_model_provider(value) in {"openai", "openrouter", "opencdk", "local_openai"}


def normalize_billing_mode(value: str, provider: str, fallback: str | None = None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in VALID_BILLING_MODES:
        return normalized
    if fallback and fallback in VALID_BILLING_MODES:
        return fallback
    return provider_preset(provider).default_billing_mode


def discover_local_model_catalog(third_party_root: Path | None = None) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()
    for provider, model_name, source, installed in _iter_local_models(third_party_root=third_party_root):
        key = (provider, model_name.lower())
        if key in seen_keys:
            continue
        seen_keys.add(key)
        entries.append(
            {
                "id": f"{provider}:{model_name}",
                "model": model_name,
                "display_name": f"{model_name} ({_local_provider_label(provider)})",
                "description": _local_model_description(provider, source, installed),
                "hidden": False,
                "is_default": False,
                "default_reasoning_effort": "medium",
                "supported_reasoning_efforts": ["low", "medium", "high", "xhigh"],
                "input_modalities": ["text"],
                "supports_personality": False,
                "upgrade": None,
                "availability_nux": None,
                "provider": "oss",
                "local_provider": provider,
                "source": source,
                "installed": installed,
            }
        )
    return sorted(entries, key=lambda item: (item["local_provider"], item["model"].lower()))


def _iter_local_models(third_party_root: Path | None = None) -> list[tuple[str, str, str, bool]]:
    discovered: list[tuple[str, str, str, bool]] = []
    seen: set[tuple[str, str]] = set()

    for model_name in _ollama_cli_models():
        key = (DEFAULT_LOCAL_MODEL_PROVIDER, model_name.lower())
        if key in seen:
            continue
        seen.add(key)
        discovered.append((DEFAULT_LOCAL_MODEL_PROVIDER, model_name, "ollama-cli", True))

    for model_name in _vendored_ollama_models(third_party_root=third_party_root):
        key = (DEFAULT_LOCAL_MODEL_PROVIDER, model_name.lower())
        if key in seen:
            continue
        seen.add(key)
        discovered.append((DEFAULT_LOCAL_MODEL_PROVIDER, model_name, "vendored-third-party", False))

    return discovered


def _ollama_cli_models() -> list[str]:
    try:
        completed = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=4,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return []
    if completed.returncode != 0:
        return []
    models: list[str] = []
    for index, line in enumerate(completed.stdout.splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        if index == 0 and stripped.lower().startswith("name"):
            continue
        model_name = stripped.split()[0].strip()
        if model_name:
            models.append(model_name)
    return models


def _vendored_ollama_models(third_party_root: Path | None = None) -> list[str]:
    root = (third_party_root or _default_third_party_root()) / "ollama"
    if not root.exists():
        return []
    models: list[str] = []
    for provider_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        manifest_root = provider_dir / "manifests" / "registry.ollama.ai" / "library"
        if manifest_root.exists():
            for family_dir in sorted(path for path in manifest_root.iterdir() if path.is_dir()):
                for tag_path in sorted(path for path in family_dir.iterdir() if path.is_file()):
                    model_name = f"{family_dir.name}:{tag_path.name}"
                    if model_name not in models:
                        models.append(model_name)
            continue
        fallback_name = provider_dir.name.replace("--", ":")
        if fallback_name not in models:
            models.append(fallback_name)
    return models


def _default_third_party_root() -> Path:
    return Path(__file__).resolve().parents[2] / "third_party"


def _local_provider_label(value: str) -> str:
    normalized = normalize_local_model_provider(value, fallback=value)
    if normalized == "lmstudio":
        return "LM Studio"
    if normalized == "ollama":
        return "Ollama"
    return normalized or "Local"


def _local_model_description(provider: str, source: str, installed: bool) -> str:
    provider_label = _local_provider_label(provider)
    status_text = "detected on this machine" if installed else "available from the repository bundle"
    if source == "ollama-cli":
        return f"Run this local {provider_label} model through Codex CLI OSS mode; the model is {status_text}."
    return f"Run this local {provider_label} model through Codex CLI OSS mode; the model is {status_text}."
