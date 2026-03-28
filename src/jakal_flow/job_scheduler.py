from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any

from .utils import append_jsonl, ensure_dir, now_utc_iso, write_json


DEFAULT_MAX_CONCURRENT_JOBS = 2


def _normalize(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return {key: _normalize(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


def normalize_max_concurrent_jobs(value: Any, default: int = DEFAULT_MAX_CONCURRENT_JOBS) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        parsed = default
    return max(1, parsed)


def scheduler_state_file(workspace_root: Path) -> Path:
    return workspace_root / "job_scheduler.json"


def scheduler_event_log_file(workspace_root: Path) -> Path:
    return workspace_root / "job_scheduler_events.jsonl"


@dataclass(slots=True)
class WorkspaceSchedulerState:
    workspace_root: Path
    max_concurrent_jobs: int = DEFAULT_MAX_CONCURRENT_JOBS
    updated_at: str | None = None
    jobs: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)


def write_scheduler_state(
    workspace_root: Path,
    *,
    max_concurrent_jobs: int,
    jobs: list[dict[str, Any]],
) -> None:
    ensure_dir(workspace_root)
    write_json(
        scheduler_state_file(workspace_root),
        WorkspaceSchedulerState(
            workspace_root=workspace_root,
            max_concurrent_jobs=normalize_max_concurrent_jobs(max_concurrent_jobs),
            updated_at=now_utc_iso(),
            jobs=jobs,
        ).to_dict(),
    )


def append_scheduler_event(
    workspace_root: Path,
    event_type: str,
    *,
    job: dict[str, Any],
    details: dict[str, Any] | None = None,
) -> None:
    append_jsonl(
        scheduler_event_log_file(workspace_root),
        {
            "timestamp": now_utc_iso(),
            "event_type": str(event_type).strip() or "scheduler-event",
            "job": job,
            "details": details or {},
        },
    )
