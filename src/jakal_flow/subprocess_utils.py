from __future__ import annotations

import os
from pathlib import Path
import subprocess
from typing import Any

from .errors import SubprocessTimeoutError


def _command_text(command: str | list[str]) -> str:
    if isinstance(command, str):
        return command
    return " ".join(str(part) for part in command)


def run_subprocess(
    command: str | list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = False,
    timeout_seconds: float | None = None,
    capture_output: bool = False,
    text: bool = False,
    encoding: str | None = None,
    errors: str | None = None,
    shell: bool = False,
    stdin: Any = None,
    stdout: Any = None,
    stderr: Any = None,
    creationflags: int = 0,
    startupinfo: Any = None,
) -> subprocess.CompletedProcess[Any]:
    run_kwargs: dict[str, Any] = {
        "cwd": cwd,
        "env": env,
        "check": check,
        "timeout": timeout_seconds,
        "text": text,
        "encoding": encoding,
        "errors": errors,
        "shell": shell,
        "stdin": stdin,
        "stdout": stdout,
        "stderr": stderr,
        "creationflags": creationflags,
        "startupinfo": startupinfo,
    }
    if capture_output:
        run_kwargs["capture_output"] = True
    try:
        return subprocess.run(command, **run_kwargs)
    except subprocess.TimeoutExpired as exc:
        raise SubprocessTimeoutError(
            f"Command timed out after {timeout_seconds} seconds: {_command_text(command)}"
        ) from exc


def windows_process_is_running(pid: int) -> bool | None:
    if os.name != "nt":
        return None
    if pid <= 0:
        return False
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return None

    synchronize = 0x00100000
    wait_object_0 = 0x00000000
    wait_timeout = 0x00000102

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(synchronize, False, pid)
    if not handle:
        error = ctypes.get_last_error()
        if error == 5:
            return True
        if error == 87:
            return False
        return None
    try:
        wait_result = kernel32.WaitForSingleObject(handle, 0)
    finally:
        kernel32.CloseHandle(handle)
    if wait_result == wait_timeout:
        return True
    if wait_result == wait_object_0:
        return False
    return None


def terminate_process_handle(
    process: subprocess.Popen[Any] | None,
    *,
    wait_timeout_seconds: float = 1.5,
) -> None:
    if process is None:
        return
    try:
        process.terminate()
        process.wait(timeout=wait_timeout_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=wait_timeout_seconds)
        except subprocess.TimeoutExpired:
            process.wait()
    except OSError:
        return
