from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
import subprocess
from threading import RLock
from typing import Any, Iterator

from .models import ProjectContext
from .process_supervisor import terminate_process


PROCESS_POLL_TIMEOUT_SECONDS = 0.2
PROCESS_TERMINATION_TIMEOUT_SECONDS = 1.0


class ImmediateStopRequested(RuntimeError):
    """Raised when the user asks to stop the active step immediately."""


@dataclass(slots=True)
class ManagedProcess:
    scope_id: str
    label: str
    process: subprocess.Popen[bytes]

    @property
    def pid(self) -> int:
        return int(self.process.pid or 0)


class ExecutionStopRegistry:
    def __init__(self) -> None:
        self._lock = RLock()
        self._requested_scopes: set[str] = set()
        self._active_processes: dict[str, dict[int, ManagedProcess]] = {}

    def request_stop(self, scope_id: str) -> None:
        normalized_scope = self._normalize_scope(scope_id)
        processes: list[ManagedProcess] = []
        with self._lock:
            self._requested_scopes.add(normalized_scope)
            processes = list(self._active_processes.get(normalized_scope, {}).values())
        for entry in processes:
            terminate_process(entry.pid)

    def clear(self, scope_id: str) -> None:
        normalized_scope = self._normalize_scope(scope_id)
        with self._lock:
            self._requested_scopes.discard(normalized_scope)

    def stop_requested(self, scope_id: str) -> bool:
        normalized_scope = self._normalize_scope(scope_id)
        with self._lock:
            return normalized_scope in self._requested_scopes

    @contextmanager
    def manage_process(
        self,
        scope_id: str,
        process: subprocess.Popen[bytes],
        *,
        label: str,
    ) -> Iterator[None]:
        normalized_scope = self._normalize_scope(scope_id)
        entry = ManagedProcess(scope_id=normalized_scope, label=label, process=process)
        with self._lock:
            self._active_processes.setdefault(normalized_scope, {})[entry.pid] = entry
        try:
            yield
        finally:
            with self._lock:
                scoped = self._active_processes.get(normalized_scope, {})
                scoped.pop(entry.pid, None)
                if not scoped:
                    self._active_processes.pop(normalized_scope, None)

    def _normalize_scope(self, scope_id: str) -> str:
        normalized = str(scope_id or "").strip()
        if not normalized:
            raise ValueError("Execution stop scope id is required.")
        return normalized


EXECUTION_STOP_REGISTRY = ExecutionStopRegistry()


def execution_scope_id(context: ProjectContext) -> str:
    return str(context.metadata.source_repo_id or context.metadata.repo_id).strip() or str(context.metadata.repo_path)


def run_subprocess_capture(
    command: str | list[str],
    *,
    scope_id: str,
    label: str,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    shell: bool = False,
    input_bytes: bytes | None = None,
    timeout_seconds: float | None = None,
) -> subprocess.CompletedProcess[bytes]:
    if EXECUTION_STOP_REGISTRY.stop_requested(scope_id):
        raise ImmediateStopRequested(f"Immediate stop requested before starting {label}.")

    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        shell=shell,
        stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    start_time = monotonic()
    deadline = None if timeout_seconds is None else start_time + float(timeout_seconds)
    normalized_timeout = timeout_seconds
    if normalized_timeout is not None and normalized_timeout <= 0:
        normalized_timeout = None
    pending_input = input_bytes
    with EXECUTION_STOP_REGISTRY.manage_process(scope_id, process, label=label):
        while True:
            communicate_timeout = PROCESS_POLL_TIMEOUT_SECONDS
            if deadline is not None:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    break
                communicate_timeout = min(communicate_timeout, remaining)
            try:
                stdout, stderr = process.communicate(input=pending_input, timeout=communicate_timeout)
                return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
            except subprocess.TimeoutExpired:
                pending_input = None
                if deadline is not None and monotonic() >= deadline:
                    break
                if not EXECUTION_STOP_REGISTRY.stop_requested(scope_id):
                    continue
                terminate_process(int(process.pid or 0))
                try:
                    stdout, stderr = process.communicate(timeout=PROCESS_TERMINATION_TIMEOUT_SECONDS)
                except subprocess.TimeoutExpired:
                    process.kill()
                    stdout, stderr = process.communicate()
                raise ImmediateStopRequested(f"Immediate stop requested while running {label}.") from None
    terminate_process(int(process.pid or 0))
    try:
        stdout, stderr = process.communicate(timeout=PROCESS_TERMINATION_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
    timeout_seconds_value = float(normalized_timeout or 0.0)
    raise RuntimeError(f"{label} subprocess timed out after {timeout_seconds_value:.1f}s.") from subprocess.TimeoutExpired(command, timeout_seconds_value)
