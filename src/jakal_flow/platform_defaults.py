from __future__ import annotations

import os


def default_codex_path(provider: str = "") -> str:
    normalized_provider = str(provider or "").strip().lower()
    if normalized_provider == "claude":
        return "claude.cmd" if os.name == "nt" else "claude"
    if normalized_provider == "gemini":
        return "gemini.cmd" if os.name == "nt" else "gemini"
    return "codex.cmd" if os.name == "nt" else "codex"
