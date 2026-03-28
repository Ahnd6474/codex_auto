from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .utils import decode_process_output


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
]


def ensure_virtualenv(project_dir: Path, python_executable: str | None = None) -> Path:
    venv_dir = project_dir / ".venv"
    if venv_dir.exists():
        return venv_dir
    command = [python_executable or sys.executable, "-m", "venv", str(venv_dir)]
    completed = subprocess.run(command, cwd=project_dir, capture_output=True, check=False)
    if completed.returncode != 0:
        stderr = decode_process_output(completed.stderr).strip()
        raise RuntimeError(f"Failed to create .venv in {project_dir}: {stderr or completed.returncode}")
    return venv_dir


def ensure_gitignore(project_dir: Path, entries: list[str] | None = None) -> bool:
    entries = entries or DEFAULT_GITIGNORE_ENTRIES
    gitignore_path = project_dir / ".gitignore"
    existing_lines = []
    if gitignore_path.exists():
        existing_lines = gitignore_path.read_text(encoding="utf-8").splitlines()
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
    gitignore_path.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")
    return True
