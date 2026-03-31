from __future__ import annotations

import os
import sys
from pathlib import Path

from .subprocess_utils import run_subprocess
from .utils import decode_process_output, read_text, write_text


VENV_CREATION_TIMEOUT_SECONDS = 300.0


DEFAULT_GITIGNORE_ENTRIES = [
    "_tmp_*/",
    ".venv/",
    "__pycache__/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    ".coverage",
    "*.pyc",
    "build/",
    "dist/",
    ".parallel_runs/",
    ".lineages/",
    "jakal-flow-logs/",
]


def ensure_virtualenv(project_dir: Path, python_executable: str | None = None) -> Path:
    venv_dir = project_dir / ".venv"
    if venv_dir.exists():
        return venv_dir
    command = [python_executable or sys.executable, "-m", "venv", str(venv_dir)]
    completed = run_subprocess(
        command,
        cwd=project_dir,
        capture_output=True,
        check=False,
        timeout_seconds=VENV_CREATION_TIMEOUT_SECONDS,
    )
    if completed.returncode != 0:
        venv_python = venv_dir / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")
        if venv_python.exists():
            return venv_dir
        stderr = decode_process_output(completed.stderr).strip()
        raise RuntimeError(f"Failed to create .venv in {project_dir}: {stderr or completed.returncode}")
    return venv_dir


def ensure_gitignore(project_dir: Path, entries: list[str] | None = None) -> bool:
    entries = entries or DEFAULT_GITIGNORE_ENTRIES
    gitignore_path = project_dir / ".gitignore"
    existing_lines = []
    if gitignore_path.exists():
        existing_lines = read_text(gitignore_path).splitlines()
    normalized_existing = {line.strip() for line in existing_lines if line.strip()}
    additions = [entry for entry in entries if entry.strip() and entry.strip() not in normalized_existing]
    if not additions:
        return False
    new_lines = existing_lines[:]
    if new_lines and new_lines[-1].strip():
        new_lines.append("")
    if not new_lines:
        new_lines.append("# jakal-flow")
    elif new_lines[-1].strip():
        new_lines.append("")
    new_lines.extend(additions)
    write_text(gitignore_path, "\n".join(new_lines).rstrip() + "\n")
    return True
