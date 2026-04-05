from __future__ import annotations

import os
from pathlib import Path
import sys


APP_DATA_DIRNAME = "jakal-flow"
OLLAMA_MODELS_ENV_VAR = "JAKAL_FLOW_OLLAMA_MODELS"


def default_codex_path(provider: str = "") -> str:
    normalized_provider = str(provider or "").strip().lower()
    if normalized_provider in {"claude", "deepseek", "minimax", "glm"}:
        return "claude.cmd" if os.name == "nt" else "claude"
    if normalized_provider == "gemini":
        return "gemini.cmd" if os.name == "nt" else "gemini"
    if normalized_provider == "qwen_code":
        return "qwen.cmd" if os.name == "nt" else "qwen"
    return "codex.cmd" if os.name == "nt" else "codex"


def default_app_data_home() -> Path:
    if os.name == "nt":
        root = str(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or "").strip()
        if root:
            return Path(root).expanduser().resolve()
        return (Path.home() / "AppData" / "Local").resolve()
    if sys.platform == "darwin":
        return (Path.home() / "Library" / "Application Support").resolve()
    xdg_data_home = str(os.environ.get("XDG_DATA_HOME", "") or "").strip()
    if xdg_data_home:
        return Path(xdg_data_home).expanduser().resolve()
    return (Path.home() / ".local" / "share").resolve()


def default_app_data_root(app_name: str = APP_DATA_DIRNAME) -> Path:
    return (default_app_data_home() / app_name).resolve()


def configured_ollama_model_store_root(*, legacy_root: Path | None = None) -> Path:
    explicit_override = str(os.environ.get(OLLAMA_MODELS_ENV_VAR, "") or "").strip()
    if explicit_override:
        return Path(explicit_override).expanduser().resolve()

    existing_store = str(os.environ.get("OLLAMA_MODELS", "") or "").strip()
    if existing_store:
        candidate = Path(existing_store).expanduser().resolve()
        if legacy_root is not None:
            try:
                legacy_candidate = legacy_root.expanduser().resolve()
            except OSError:
                legacy_candidate = legacy_root.expanduser()
            if candidate == legacy_candidate:
                return default_ollama_model_store_root()
        return candidate

    return default_ollama_model_store_root()


def default_ollama_model_store_root() -> Path:
    return (default_app_data_root() / "ollama" / "models").resolve()
