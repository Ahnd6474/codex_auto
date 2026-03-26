from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path
import signal
import subprocess
import time
from typing import Any


def background_creationflags() -> int:
    if os.name != "nt":
        return 0
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return 0
    return (
        getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )


def hidden_window_creationflags() -> int:
    if os.name != "nt":
        return 0
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return 0
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def hidden_window_startupinfo() -> subprocess.STARTUPINFO | None:
    if os.name != "nt" or not hasattr(subprocess, "STARTUPINFO"):
        return None
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
    startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
    return startupinfo


def spawn_background_process(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    stdout: Any = subprocess.DEVNULL,
    stderr: Any = subprocess.DEVNULL,
    creationflags: int | None = None,
) -> subprocess.Popen[Any]:
    popen_kwargs = {
        "cwd": cwd,
        "env": env,
        "stdin": subprocess.DEVNULL,
        "stdout": stdout,
        "stderr": stderr,
        "creationflags": background_creationflags() if creationflags is None else creationflags,
        "startupinfo": hidden_window_startupinfo(),
        "close_fds": True,
    }
    try:
        return subprocess.Popen(command, **popen_kwargs)
    except (OSError, ValueError):
        if os.name != "nt" or popen_kwargs["startupinfo"] is None:
            raise
        popen_kwargs["startupinfo"] = None
        return subprocess.Popen(command, **popen_kwargs)


def terminate_process(pid: int) -> None:
    if pid <= 0:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            os.kill(pid, signal.SIGTERM)
    except OSError:
        pass


def wait_for_condition(predicate: Callable[[], bool], *, timeout_seconds: float, interval_seconds: float = 0.1) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval_seconds)
    return predicate()
