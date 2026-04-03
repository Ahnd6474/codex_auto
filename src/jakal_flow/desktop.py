from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess


_ACTION_TO_SCRIPT = {
    "dev": "tauri:dev",
    "build": "tauri:build",
    "build-full": "tauri:build:full",
    "build-python": "tauri:build:python",
    "build-lean": "tauri:build:lean",
    "build-all": "tauri:build:all",
    "test": "test",
    "web-dev": "dev",
    "web-build": "build",
}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def desktop_root() -> Path:
    return repo_root() / "desktop"


def npm_executable() -> str:
    override = str(os.environ.get("JAKAL_FLOW_NPM", "") or "").strip()
    if override:
        return override
    candidates = ["npm.cmd", "npm"] if os.name == "nt" else ["npm"]
    for candidate in candidates:
        if shutil.which(candidate):
            return candidate
    return candidates[0]


def command_for_action(action: str, extra_args: list[str]) -> list[str]:
    normalized_action = str(action or "").strip().lower()
    if normalized_action not in _ACTION_TO_SCRIPT:
        raise ValueError(f"Unsupported desktop action: {action}")
    normalized_extra = list(extra_args or [])
    if normalized_extra[:1] == ["--"]:
        normalized_extra = normalized_extra[1:]
    return [npm_executable(), "run", _ACTION_TO_SCRIPT[normalized_action], *normalized_extra]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the jakal-flow desktop app from the repository root")
    parser.add_argument(
        "action",
        choices=sorted(_ACTION_TO_SCRIPT),
        help="Desktop workflow to run",
    )
    parser.add_argument(
        "extra_args",
        nargs=argparse.REMAINDER,
        help="Extra arguments forwarded after '--' to the underlying npm script",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    desktop_dir = desktop_root()
    if not desktop_dir.is_dir():
        raise SystemExit(f"Desktop app directory is missing: {desktop_dir}")
    command = command_for_action(args.action, args.extra_args)
    completed = subprocess.run(command, cwd=desktop_dir, check=False)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
