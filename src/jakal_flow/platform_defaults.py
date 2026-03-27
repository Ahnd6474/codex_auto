from __future__ import annotations

import os


def default_codex_path() -> str:
    return "codex.cmd" if os.name == "nt" else "codex"
