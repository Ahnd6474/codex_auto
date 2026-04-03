from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


def _make_has_test_target(makefile: Path) -> bool:
    try:
        for line in makefile.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if stripped.startswith("test:") or stripped.startswith("test "):
                return True
    except OSError:
        return False
    return False


def infer_test_command(repo_dir: Path) -> str:
    if _make_has_test_target(repo_dir / "Makefile"):
        return "make test"
    if (repo_dir / "pytest.ini").exists() or (repo_dir / "conftest.py").exists():
        return "pytest -q"
    if (repo_dir / "pyproject.toml").exists() or (repo_dir / "requirements.txt").exists():
        if (repo_dir / "tests").exists():
            return "pytest -q"
    if (repo_dir / "Cargo.toml").exists():
        return "cargo test"
    if (repo_dir / "go.mod").exists():
        return "go test ./..."
    package_json = repo_dir / "package.json"
    if package_json.exists():
        try:
            package_data = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            package_data = {}
        scripts = package_data.get("scripts", {}) if isinstance(package_data, dict) else {}
        if isinstance(scripts, dict) and "test" in scripts:
            if (repo_dir / "pnpm-lock.yaml").exists() and shutil.which("pnpm"):
                return "pnpm test"
            if (repo_dir / "yarn.lock").exists() and shutil.which("yarn"):
                return "yarn test"
            return "npm test"
    return "python -m pytest"


def main(argv: list[str] | None = None) -> int:
    _ = argv
    repo_dir = Path.cwd()
    command = infer_test_command(repo_dir)
    completed = subprocess.run(command, cwd=repo_dir, shell=True)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
