from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from threading import Lock, Thread
import sys
import time
from typing import Any

from .bridge_contract import BRIDGE_PROTOCOL_VERSION, BridgeEnvelope, BridgeError, BridgeEvent, BridgeJobSnapshot
from .bridge_events import BridgeEventSink, bridge_event_context
from .errors import ExecutionFailure, HANDLED_OPERATION_EXCEPTIONS, JSON_PARSE_EXCEPTIONS, RequestRejectedError
from .job_scheduler import (
    DEFAULT_MAX_CONCURRENT_JOBS,
    append_scheduler_event,
    load_scheduler_state,
    normalize_max_concurrent_jobs,
    scheduler_state_file,
    write_scheduler_state,
)
from .failure_logs import write_runtime_failure_log
from .ui_bridge_payloads import build_execution_state_payload, workspace_snapshot
from .ui_bridge import configure_stdio, default_workspace_root, run_command, runtime_from_payload
from .utils import now_utc_iso, parse_json_text


def now_ms() -> int:
    return int(time.time() * 1000)


def _normalized_project_path(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        resolved = Path(text).expanduser().resolve()
    except OSError:
        resolved = Path(text).expanduser()
    normalized = str(resolved)
    return normalized.lower() if os.name == "nt" else normalized


def _job_queue_sort_key(snapshot: BridgeJobSnapshot) -> tuple[int, int, int, str]:
    return (
        -int(getattr(snapshot, "queue_priority", 0) or 0),
        int(snapshot.updated_at_ms or 0),
        int(snapshot.queue_position or 0),
        snapshot.id,
    )


def _job_queue_settings(payload: dict[str, Any]) -> tuple[bool, int, str]:
    request_payload = payload if isinstance(payload, dict) else {}
    runtime_payload = request_payload.get("runtime", {})
    if not isinstance(runtime_payload, dict):
        runtime_payload = {}
    runtime = runtime_from_payload(runtime_payload)
    display_name = str(request_payload.get("display_name", "")).strip()
    return bool(runtime.allow_background_queue), int(runtime.background_queue_priority), display_name


def _normalized_chat_mode(payload: dict[str, Any] | None) -> str:
    request_payload = payload if isinstance(payload, dict) else {}
    raw_mode = str(request_payload.get("chat_mode", "conversation")).strip().lower()
    return raw_mode if raw_mode in {"conversation", "review", "debugger", "merger"} else "conversation"


def _job_lane(command: str, payload: dict[str, Any] | None = None) -> str:
    normalized_command = str(command or "").strip().lower()
    if normalized_command == "send-chat-message" and _normalized_chat_mode(payload) in {"conversation", "review"}:
        return "chat"
    return "execution"


class _StreamBridgeEventSink(BridgeEventSink):
    def __init__(self, send_message) -> None:
        self._send_message = send_message

    def emit(self, event: str, payload: dict[str, Any] | None = None) -> None:
        self._send_message(
            BridgeEnvelope(
                kind="event",
                event=event,
                payload=payload or {},
                version=BRIDGE_PROTOCOL_VERSION,
            )
        )


class BridgeJobStore:
    def __init__(self, send_message, *, max_running_jobs: int | None = None) -> None:
        self._jobs: dict[str, BridgeJobSnapshot] = {}
        self._requests: dict[str, tuple[str, Path, dict[str, Any]]] = {}
        self._lock = Lock()
        self._send_message = send_message
        self._job_sequence = 0
        raw_limit = max_running_jobs
        if raw_limit is None:
            raw_limit = os.environ.get("JAKAL_FLOW_MAX_CONCURRENT_JOBS", DEFAULT_MAX_CONCURRENT_JOBS)
        self._default_max_running_jobs = normalize_max_concurrent_jobs(raw_limit)
        self._workspace_max_running_jobs: dict[str, int] = {}

    def _next_job_id_unlocked(self, command: str) -> str:
        self._job_sequence += 1
        return f"job-{command}-{now_ms()}-{self._job_sequence}"

    def _publish(self, snapshot: BridgeJobSnapshot) -> None:
        self._send_message(
            BridgeEnvelope(
                kind="event",
                event="job.updated",
                payload={"job": snapshot.to_dict()},
            )
        )

    def _publish_many(self, snapshots: list[BridgeJobSnapshot]) -> None:
        seen: set[str] = set()
        for snapshot in snapshots:
            if snapshot.id in seen:
                continue
            seen.add(snapshot.id)
            self._publish(snapshot)

    def _list_jobs_unlocked(self) -> list[BridgeJobSnapshot]:
        status_rank = {"running": 0, "queued": 1, "failed": 2, "cancelled": 3, "completed": 4}
        return sorted(
            self._jobs.values(),
            key=lambda item: (
                status_rank.get(str(item.status).strip().lower(), 9),
                item.queue_position if str(item.status).strip().lower() == "queued" else 0,
                -int(item.updated_at_ms or 0),
                item.id,
            ),
        )

    def _running_count_unlocked(self, workspace_root: Path) -> int:
        workspace_key = str(workspace_root)
        return sum(
            1
            for job in self._jobs.values()
            if job.workspace_root == workspace_key and str(job.status).strip().lower() == "running"
        )

    def _max_running_jobs_for_workspace_unlocked(self, workspace_root: Path) -> int:
        workspace_key = str(workspace_root)
        cached = self._workspace_max_running_jobs.get(workspace_key)
        if cached is not None:
            return cached
        default_limit = self._default_max_running_jobs
        if scheduler_state_file(workspace_root).exists():
            scheduler_state = load_scheduler_state(
                workspace_root,
                default_max_concurrent_jobs=default_limit,
            )
            default_limit = normalize_max_concurrent_jobs(
                scheduler_state.max_concurrent_jobs,
                default=default_limit,
            )
        self._workspace_max_running_jobs[workspace_key] = default_limit
        return default_limit

    def _refresh_queue_positions_unlocked(self, workspace_root: Path, *, touch_timestamp: bool) -> list[BridgeJobSnapshot]:
        workspace_key = str(workspace_root)
        queued_jobs = sorted(
            [
                job
                for job in self._jobs.values()
                if job.workspace_root == workspace_key and str(job.status).strip().lower() == "queued"
            ],
            key=_job_queue_sort_key,
        )
        changed: list[BridgeJobSnapshot] = []
        for index, job in enumerate(queued_jobs, start=1):
            if job.queue_position == index:
                continue
            job.queue_position = index
            if touch_timestamp:
                job.updated_at_ms = now_ms()
            changed.append(job)
        return changed

    def _persist_workspace_state_unlocked(self, workspace_root: Path) -> None:
        active_jobs = [
            job.to_dict()
            for job in self._list_jobs_unlocked()
            if job.workspace_root == str(workspace_root) and str(job.status).strip().lower() in {"queued", "running"}
        ]
        write_scheduler_state(
            workspace_root,
            max_concurrent_jobs=self._max_running_jobs_for_workspace_unlocked(workspace_root),
            jobs=active_jobs,
        )

    def _scheduler_snapshot_unlocked(self, workspace_root: Path) -> dict[str, Any]:
        workspace_key = str(workspace_root)
        active_jobs = [
            job.to_dict()
            for job in self._list_jobs_unlocked()
            if job.workspace_root == workspace_key and str(job.status).strip().lower() in {"queued", "running"}
        ]
        running_jobs = [job for job in active_jobs if str(job.get("status", "")).strip().lower() == "running"]
        queued_jobs = [job for job in active_jobs if str(job.get("status", "")).strip().lower() == "queued"]
        return {
            "workspace_root": workspace_key,
            "max_concurrent_jobs": self._max_running_jobs_for_workspace_unlocked(workspace_root),
            "running_jobs": running_jobs,
            "queued_jobs": queued_jobs,
            "jobs": active_jobs,
        }

    def _matching_active_job_unlocked(
        self,
        *,
        repo_id: str,
        project_dir: str,
        workspace_root: Path,
        command: str,
        payload: dict[str, Any] | None = None,
    ) -> BridgeJobSnapshot | None:
        normalized_project_dir = _normalized_project_path(project_dir)
        workspace_key = str(workspace_root)
        requested_lane = _job_lane(command, payload)
        for job in self._jobs.values():
            if job.workspace_root != workspace_key:
                continue
            if str(job.status).strip().lower() not in {"queued", "running"}:
                continue
            existing_lane = str(getattr(job, "job_lane", "") or "execution").strip().lower() or "execution"
            if existing_lane != requested_lane:
                continue
            if repo_id and job.repo_id and job.repo_id == repo_id:
                return job
            if normalized_project_dir and _normalized_project_path(job.project_dir) == normalized_project_dir:
                return job
        return None

    def _prune_terminal_jobs_unlocked(self, maximum: int = 40) -> None:
        terminal_jobs = sorted(
            [
                job
                for job in self._jobs.values()
                if str(job.status).strip().lower() in {"completed", "failed", "cancelled"}
            ],
            key=lambda item: (int(item.updated_at_ms or 0), item.id),
            reverse=True,
        )
        for job in terminal_jobs[maximum:]:
            self._jobs.pop(job.id, None)

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            jobs = self._list_jobs_unlocked()
            return [job.to_dict() for job in jobs]

    def scheduler_snapshot(self, workspace_root: Path) -> dict[str, Any]:
        with self._lock:
            return self._scheduler_snapshot_unlocked(workspace_root)

    def active_execution_job_for_project(
        self,
        workspace_root: Path,
        *,
        repo_id: str = "",
        project_dir: str = "",
    ) -> dict[str, Any] | None:
        normalized_project_dir = _normalized_project_path(project_dir)
        workspace_key = str(workspace_root)
        with self._lock:
            for snapshot in self._list_jobs_unlocked():
                if snapshot.workspace_root != workspace_key:
                    continue
                if str(snapshot.status).strip().lower() not in {"queued", "running"}:
                    continue
                if str(getattr(snapshot, "job_lane", "execution") or "execution").strip().lower() != "execution":
                    continue
                if repo_id and snapshot.repo_id and snapshot.repo_id == repo_id:
                    return snapshot.to_dict()
                if normalized_project_dir and _normalized_project_path(snapshot.project_dir) == normalized_project_dir:
                    return snapshot.to_dict()
        return None

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            snapshot = self._jobs.get(job_id)
            return None if snapshot is None else snapshot.to_dict()

    def set_max_running_jobs(self, workspace_root: Path, max_running_jobs: Any) -> tuple[dict[str, Any], list[BridgeJobSnapshot]]:
        publish_updates: list[BridgeJobSnapshot] = []
        with self._lock:
            self._workspace_max_running_jobs[str(workspace_root)] = normalize_max_concurrent_jobs(max_running_jobs)
            publish_updates.extend(self._refresh_queue_positions_unlocked(workspace_root, touch_timestamp=False))
            self._persist_workspace_state_unlocked(workspace_root)
        self._publish_many(publish_updates)
        promoted = self.dequeue_startable_jobs(workspace_root)
        return self.scheduler_snapshot(workspace_root), promoted

    def create(self, command: str, workspace_root: Path, payload: dict[str, Any] | None = None) -> BridgeJobSnapshot:
        repo_id = ""
        project_dir = ""
        request_payload = payload if isinstance(payload, dict) else {}
        repo_id = str(request_payload.get("repo_id", "")).strip()
        project_dir = _normalized_project_path(str(request_payload.get("project_dir", "")).strip())
        allow_background_queue, queue_priority, display_name = _job_queue_settings(request_payload)
        job_lane = _job_lane(command, request_payload)
        chat_mode = _normalized_chat_mode(request_payload) if str(command).strip().lower() == "send-chat-message" else ""
        timestamp_ms = now_ms()
        created_at = now_utc_iso()
        publish_updates: list[BridgeJobSnapshot] = []
        event_type = "job-started"
        event_details: dict[str, Any] = {}
        with self._lock:
            job_id = self._next_job_id_unlocked(command)
            existing = self._matching_active_job_unlocked(
                repo_id=repo_id,
                project_dir=project_dir,
                workspace_root=workspace_root,
                command=command,
                payload=request_payload,
            )
            if existing is not None:
                raise RequestRejectedError(
                    "Another background task is already active for this project.",
                    reason_code="duplicate_job",
                    details={"active_job_id": existing.id},
                )
            workspace_limit = self._max_running_jobs_for_workspace_unlocked(workspace_root)
            running_count = self._running_count_unlocked(workspace_root)
            if running_count >= workspace_limit and not allow_background_queue:
                raise RequestRejectedError(
                    "Reservations are disabled for this project, so this run must wait for a free slot.",
                    reason_code="background_queue_disabled",
                    details={"max_concurrent_jobs": workspace_limit},
                )
            status = "running" if running_count < workspace_limit else "queued"
            snapshot = BridgeJobSnapshot(
                id=job_id,
                command=command,
                status=status,
                job_lane=job_lane,
                chat_mode=chat_mode,
                updated_at_ms=timestamp_ms,
                repo_id=repo_id,
                project_dir=project_dir,
                workspace_root=str(workspace_root),
                display_name=display_name,
                allow_background_queue=allow_background_queue,
                queue_priority=queue_priority,
                created_at=created_at,
                started_at=created_at if status == "running" else None,
                queue_position=0,
            )
            self._jobs[job_id] = snapshot
            self._requests[job_id] = (command, workspace_root, request_payload)
            queue_updates = self._refresh_queue_positions_unlocked(workspace_root, touch_timestamp=False)
            publish_updates = [snapshot, *queue_updates]
            self._persist_workspace_state_unlocked(workspace_root)
            if status == "queued":
                event_type = "job-queued"
                event_details = {"queue_position": snapshot.queue_position}
        self._publish_many(publish_updates)
        append_scheduler_event(
            workspace_root,
            event_type,
            job=snapshot.to_dict(),
            details=event_details,
        )
        return snapshot

    def update(self, job_id: str, **changes: Any) -> BridgeJobSnapshot | None:
        publish_updates: list[BridgeJobSnapshot] = []
        workspace_root = Path()
        event_type = ""
        event_details: dict[str, Any] = {}
        with self._lock:
            snapshot = self._jobs.get(job_id)
            if snapshot is None:
                return None
            previous_status = str(snapshot.status).strip().lower()
            for key, value in changes.items():
                setattr(snapshot, key, value)
            snapshot.updated_at_ms = now_ms()
            current_status = str(snapshot.status).strip().lower()
            if current_status in {"completed", "failed", "cancelled"} and not snapshot.completed_at:
                snapshot.completed_at = now_utc_iso()
                self._requests.pop(job_id, None)
            queue_updates = self._refresh_queue_positions_unlocked(Path(snapshot.workspace_root), touch_timestamp=False)
            self._persist_workspace_state_unlocked(Path(snapshot.workspace_root))
            self._prune_terminal_jobs_unlocked()
            publish_updates = [snapshot, *queue_updates]
            workspace_root = Path(snapshot.workspace_root)
            if previous_status != current_status:
                event_type = f"job-{current_status}"
                if current_status == "queued":
                    event_details = {"queue_position": snapshot.queue_position}
        self._publish_many(publish_updates)
        if event_type:
            append_scheduler_event(
                workspace_root,
                event_type,
                job=snapshot.to_dict(),
                details=event_details,
            )
        return snapshot

    def cancel(self, job_id: str) -> BridgeJobSnapshot | None:
        publish_updates: list[BridgeJobSnapshot] = []
        workspace_root = Path()
        with self._lock:
            snapshot = self._jobs.get(job_id)
            if snapshot is None:
                return None
            current_status = str(snapshot.status).strip().lower()
            if current_status != "queued":
                raise RequestRejectedError(
                    "Only queued jobs can be cancelled.",
                    reason_code="job_not_queued",
                    details={"status": current_status},
                )
            snapshot.status = "cancelled"
            snapshot.error = "Cancelled before execution."
            snapshot.queue_position = 0
            snapshot.result = None
            snapshot.completed_at = now_utc_iso()
            snapshot.updated_at_ms = now_ms()
            self._requests.pop(job_id, None)
            workspace_root = Path(snapshot.workspace_root)
            queue_updates = self._refresh_queue_positions_unlocked(workspace_root, touch_timestamp=False)
            self._persist_workspace_state_unlocked(workspace_root)
            self._prune_terminal_jobs_unlocked()
            publish_updates = [snapshot, *queue_updates]
        self._publish_many(publish_updates)
        append_scheduler_event(
            workspace_root,
            "job-cancelled",
            job=snapshot.to_dict(),
            details={},
        )
        return snapshot

    def request_for(self, job_id: str) -> tuple[str, Path, dict[str, Any]] | None:
        with self._lock:
            request = self._requests.get(job_id)
            if request is None:
                return None
            command, workspace_root, payload = request
            return command, workspace_root, dict(payload)

    def dequeue_startable_jobs(self, workspace_root: Path) -> list[BridgeJobSnapshot]:
        publish_updates: list[BridgeJobSnapshot] = []
        started_jobs: list[BridgeJobSnapshot] = []
        with self._lock:
            workspace_limit = self._max_running_jobs_for_workspace_unlocked(workspace_root)
            while self._running_count_unlocked(workspace_root) < workspace_limit:
                queued_jobs = sorted(
                    [
                        job
                        for job in self._jobs.values()
                        if job.workspace_root == str(workspace_root) and str(job.status).strip().lower() == "queued"
                    ],
                    key=lambda item: (item.queue_position or 9999, *_job_queue_sort_key(item)),
                )
                if not queued_jobs:
                    break
                snapshot = queued_jobs[0]
                snapshot.status = "running"
                snapshot.queue_position = 0
                snapshot.started_at = now_utc_iso()
                snapshot.updated_at_ms = now_ms()
                started_jobs.append(snapshot)
            queue_updates = self._refresh_queue_positions_unlocked(workspace_root, touch_timestamp=False)
            if started_jobs or queue_updates:
                self._persist_workspace_state_unlocked(workspace_root)
            publish_updates = [*started_jobs, *queue_updates]
        self._publish_many(publish_updates)
        for snapshot in started_jobs:
            append_scheduler_event(
                workspace_root,
                "job-started",
                job=snapshot.to_dict(),
                details={},
            )
        return started_jobs


class BridgeServer:
    def __init__(self) -> None:
        self._write_lock = Lock()
        self._event_sink = _StreamBridgeEventSink(self._send_envelope)
        self._jobs = BridgeJobStore(self._send_envelope)

    def _send_envelope(self, envelope: BridgeEnvelope) -> None:
        with self._write_lock:
            sys.stdout.write(json.dumps(envelope.to_dict(), ensure_ascii=False))
            sys.stdout.write("\n")
            sys.stdout.flush()

    def _normalize_error_payload(
        self,
        request_id: str,
        error: BaseException | str,
        *,
        method: str = "",
        command: str = "",
        workspace_root: Path | str = "",
    ) -> BridgeError:
        message = str(error).strip() if str(error).strip() else "Bridge request failed."
        error_type = type(error).__name__
        reason_code = ""
        recoverable = None
        details: dict[str, Any] = {}
        normalized_message = message.lower().strip()
        explicit_reason_code = str(getattr(error, "reason_code", "")).strip().lower()
        explicit_details = getattr(error, "details", None)
        explicit_recoverable = getattr(error, "recoverable", None)
        if isinstance(explicit_details, dict):
            details = dict(explicit_details)
        if explicit_reason_code:
            reason_code = explicit_reason_code
            if isinstance(explicit_recoverable, bool):
                recoverable = explicit_recoverable
            elif isinstance(error, ExecutionFailure):
                recoverable = True
        elif isinstance(error, ValueError):
            if normalized_message.startswith("unsupported bridge method"):
                reason_code = "unsupported_method"
            else:
                reason_code = "invalid_request"
            recoverable = True
        elif isinstance(error, RuntimeError):
            reason_code = "request_rejected"
        elif isinstance(error, LookupError):
            reason_code = "not_found"
            recoverable = True
        else:
            reason_code = "bridge_server_error"
            if normalized_message == "cancelled":
                reason_code = "cancelled"

        return BridgeError(
            message=message,
            type=error_type,
            reason_code=reason_code,
            command=str(command or ""),
            method=str(method or ""),
            request_id=str(request_id or ""),
            workspace_root=str(workspace_root or ""),
            recoverable=bool(recoverable) if isinstance(recoverable, bool) else recoverable,
            details=details,
        )

    def _write_bridge_error_log(self, workspace_root: Path, command: str, error: BaseException | str, request_id: str, method: str) -> None:
        if not isinstance(error, BaseException):
            return
        if not workspace_root:
            return
        try:
            write_runtime_failure_log(
                workspace_root,
                source="bridge-server",
                command=str(command or "bridge"),
                exc=error,
                payload={
                    "method": method,
                    "request_id": request_id,
                },
            )
        except OSError:
            pass

    def _job_project_status(self, job: dict[str, Any] | None) -> str:
        if not isinstance(job, dict):
            return ""
        job_status = str(job.get("status", "")).strip().lower()
        command = str(job.get("command", "")).strip().lower() or "background-job"
        if job_status == "queued":
            return f"queued:{command}"
        if job_status != "running":
            return ""
        if command == "run-manual-debugger":
            return "running:debugging"
        if command == "run-manual-merger":
            return "running:merging"
        if command == "run-closeout":
            return "running:closeout"
        return f"running:{command}"

    def _overlay_project_list_item(
        self,
        workspace_root: Path,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        repo_id = str(payload.get("repo_id", "")).strip()
        project_dir = str(payload.get("repo_path", payload.get("project_dir", ""))).strip()
        active_job = self._jobs.active_execution_job_for_project(
            workspace_root,
            repo_id=repo_id,
            project_dir=project_dir,
        )
        next_status = self._job_project_status(active_job)
        if not next_status:
            return payload
        next_payload = dict(payload)
        next_payload["status"] = next_status
        return next_payload

    def _overlay_listing_payload(
        self,
        workspace_root: Path,
        listing: dict[str, Any],
    ) -> dict[str, Any]:
        projects = listing.get("projects")
        if not isinstance(projects, list):
            return listing
        changed = False
        next_projects: list[dict[str, Any]] = []
        for item in projects:
            if not isinstance(item, dict):
                next_projects.append(item)
                continue
            next_item = self._overlay_project_list_item(workspace_root, item)
            if next_item is not item:
                changed = True
            next_projects.append(next_item)
        if not changed:
            return listing
        next_listing = dict(listing)
        next_listing["projects"] = next_projects
        next_listing["workspace"] = workspace_snapshot([str(item.get("status", "")).strip() for item in next_projects if isinstance(item, dict)])
        return next_listing

    def _overlay_project_detail_payload(
        self,
        workspace_root: Path,
        detail: dict[str, Any],
    ) -> dict[str, Any]:
        project = detail.get("project")
        if not isinstance(project, dict):
            return detail
        active_job = self._jobs.active_execution_job_for_project(
            workspace_root,
            repo_id=str(project.get("repo_id", "")).strip(),
            project_dir=str(project.get("repo_path", "")).strip(),
        )
        next_status = self._job_project_status(active_job)
        if not next_status:
            return detail
        next_detail = dict(detail)
        next_project = dict(project)
        next_project["current_status"] = next_status
        next_detail["project"] = next_project

        snapshot = detail.get("snapshot")
        if isinstance(snapshot, dict):
            next_snapshot = dict(snapshot)
            snapshot_project = snapshot.get("project")
            if isinstance(snapshot_project, dict):
                next_snapshot_project = dict(snapshot_project)
                next_snapshot_project["current_status"] = next_status
                next_snapshot["project"] = next_snapshot_project
            next_detail["snapshot"] = next_snapshot

        bottom_panels = detail.get("bottom_panels")
        if isinstance(bottom_panels, dict):
            next_bottom_panels = dict(bottom_panels)
            git_status = bottom_panels.get("git_status")
            if isinstance(git_status, dict):
                next_git_status = dict(git_status)
                next_git_status["current_status"] = next_status
                next_bottom_panels["git_status"] = next_git_status
            next_detail["bottom_panels"] = next_bottom_panels

        next_detail["execution_state"] = build_execution_state_payload(
            next_status,
            display_status=next_status,
            planning_running=str(next_status).strip().lower() == "running:generate-plan",
            loop_state=detail.get("loop_state") if isinstance(detail.get("loop_state"), dict) else {},
            checkpoints=detail.get("checkpoints") if isinstance(detail.get("checkpoints"), dict) else {},
            execution_processes=detail.get("execution_processes") if isinstance(detail.get("execution_processes"), list) else [],
        )
        return next_detail

    def _overlay_result_with_job_state(
        self,
        command: str,
        workspace_root: Path,
        result: Any,
    ) -> Any:
        if not isinstance(result, dict):
            return result
        normalized_command = str(command or "").strip().lower()
        if normalized_command == "list-projects":
            return self._overlay_listing_payload(workspace_root, result)
        if normalized_command in {"load-project", "load-project-core"}:
            return self._overlay_project_detail_payload(workspace_root, result)
        if normalized_command == "load-visible-project-state":
            next_result = dict(result)
            listing = result.get("listing")
            detail = result.get("detail")
            if isinstance(listing, dict):
                next_result["listing"] = self._overlay_listing_payload(workspace_root, listing)
            if isinstance(detail, dict):
                next_result["detail"] = self._overlay_project_detail_payload(workspace_root, detail)
            return next_result
        return result

    def _error_response(
        self,
        request_id: str,
        error: BaseException | str,
        *,
        method: str = "",
        command: str = "",
        workspace_root: Path | str = "",
    ) -> None:
        payload = self._normalize_error_payload(
            request_id,
            error,
            method=method,
            command=command,
            workspace_root=workspace_root,
        )
        if request_id:
            self._write_bridge_error_log(
                workspace_root=Path(str(workspace_root or Path("."))),
                command=command,
                error=error,
                request_id=request_id,
                method=method,
            )
        self._send_envelope(
            BridgeEnvelope(
                kind="response",
                id=request_id,
                ok=False,
                error=payload.to_dict(),
            )
        )

    def _infer_project_event_payload(
        self,
        command: str,
        workspace_root: Path,
        payload: dict[str, Any] | None,
        result: Any,
    ) -> dict[str, Any]:
        event_payload: dict[str, Any] = {
            "command": command,
            "workspace_root": str(workspace_root),
            "timestamp": now_utc_iso(),
        }
        request_payload = payload if isinstance(payload, dict) else {}
        if isinstance(result, dict):
            project = result.get("project")
            if not isinstance(project, dict):
                detail = result.get("detail")
                project = detail.get("project") if isinstance(detail, dict) else None
            if isinstance(project, dict):
                event_payload["project"] = {
                    "repo_id": str(project.get("repo_id", "")).strip(),
                    "project_dir": str(project.get("repo_path", "")).strip(),
                    "status": str(project.get("current_status", "")).strip(),
                }
            elif isinstance(result.get("deleted"), dict):
                deleted = result["deleted"]
                event_payload["project"] = {
                    "repo_id": str(deleted.get("repo_id", "")).strip(),
                    "project_dir": str(deleted.get("project_dir", "")).strip(),
                    "status": "deleted",
                }
        if "project" not in event_payload:
            event_payload["project"] = {
                "repo_id": str(request_payload.get("repo_id", "")).strip(),
                "project_dir": str(request_payload.get("project_dir", "")).strip(),
                "status": "",
            }
        return event_payload

    def _should_emit_project_changed(self, command: str, result: Any) -> bool:
        if command in {"bootstrap", "list-projects", "load-project", "load-visible-project-state"}:
            return False
        if isinstance(result, dict) and result.get("emit_project_changed") is False:
            return False
        return True

    def _start_job_thread(self, job_id: str) -> None:
        request = self._jobs.request_for(job_id)
        if request is None:
            return
        command, workspace_root, payload = request
        thread = Thread(
            target=self._run_job,
            args=(job_id, command, workspace_root, payload),
            daemon=True,
        )
        thread.start()

    def _run_job(self, job_id: str, command: str, workspace_root: Path, payload: dict[str, Any] | None) -> None:
        try:
            with bridge_event_context(self._event_sink):
                result = run_command(command, workspace_root, payload)
            result = self._overlay_result_with_job_state(command, workspace_root, result)
            self._jobs.update(job_id, status="completed", error=None, result=result if isinstance(result, dict) else {})
            if self._should_emit_project_changed(command, result):
                self._send_envelope(
                    BridgeEnvelope(
                        kind="event",
                        event="project.changed",
                        payload=self._infer_project_event_payload(command, workspace_root, payload, result),
                    )
                )
        except HANDLED_OPERATION_EXCEPTIONS as exc:
            self._write_bridge_error_log(
                workspace_root=workspace_root,
                command=command,
                error=exc,
                request_id=job_id,
                method="run_job",
            )
            error_message = str(exc).strip() or str(exc)
            if isinstance(exc, ExecutionFailure):
                error_message = f"{error_message} (reason_code={exc.reason_code})"
            self._jobs.update(job_id, status="failed", error=error_message, result=None)
        finally:
            for snapshot in self._jobs.dequeue_startable_jobs(workspace_root):
                self._start_job_thread(snapshot.id)

    def _resolve_workspace_root(self, raw_value: Any) -> Path:
        if isinstance(raw_value, Path):
            return raw_value.expanduser().resolve()
        if raw_value is None:
            return default_workspace_root()
        text = str(raw_value).strip()
        if not text or text.lower() == "none":
            return default_workspace_root()
        return Path(text).expanduser().resolve()

    def _handle_request(self, request_id: str, method: str, params: dict[str, Any]) -> None:
        workspace_root = self._resolve_workspace_root(params.get("workspace_root"))
        payload = params.get("payload", {})
        payload = payload if isinstance(payload, dict) else {}
        command = str(params.get("command", "")).strip()
        try:
            if method == "bridge_request":
                with bridge_event_context(self._event_sink):
                    result = run_command(command, workspace_root, payload)
                result = self._overlay_result_with_job_state(command, workspace_root, result)
                self._send_envelope(BridgeEnvelope(kind="response", id=request_id, ok=True, result=result if isinstance(result, dict) else {}))
                if self._should_emit_project_changed(command, result):
                    self._send_envelope(
                        BridgeEnvelope(
                            kind="event",
                            event="project.changed",
                            payload=self._infer_project_event_payload(command, workspace_root, payload, result),
                        )
                    )
                return

            if method == "start_job":
                snapshot = self._jobs.create(command, workspace_root, payload)
                if snapshot.status == "running":
                    self._start_job_thread(snapshot.id)
                self._send_envelope(BridgeEnvelope(kind="response", id=request_id, ok=True, result=snapshot.to_dict()))
                return

            if method == "get_job":
                result = self._jobs.get_job(str(params.get("job_id", "")).strip())
                self._send_envelope(BridgeEnvelope(kind="response", id=request_id, ok=True, result=result))
                return

            if method == "list_jobs":
                self._send_envelope(BridgeEnvelope(kind="response", id=request_id, ok=True, result=self._jobs.list_jobs()))
                return

            if method == "get_scheduler":
                self._send_envelope(
                    BridgeEnvelope(kind="response", id=request_id, ok=True, result=self._jobs.scheduler_snapshot(workspace_root))
                )
                return

            if method == "configure_scheduler":
                result, promoted = self._jobs.set_max_running_jobs(workspace_root, params.get("max_concurrent_jobs"))
                for snapshot in promoted:
                    self._start_job_thread(snapshot.id)
                self._send_envelope(BridgeEnvelope(kind="response", id=request_id, ok=True, result=result))
                return

            if method == "cancel_job":
                result = self._jobs.cancel(str(params.get("job_id", "")).strip())
                if result is None:
                    raise LookupError("The requested background job was not found.")
                self._send_envelope(BridgeEnvelope(kind="response", id=request_id, ok=True, result=result.to_dict()))
                return

            if method == "ping":
                self._send_envelope(
                    BridgeEnvelope(
                        kind="response",
                        id=request_id,
                        ok=True,
                        result={
                            "status": "ok",
                            "protocol_version": BRIDGE_PROTOCOL_VERSION,
                            "timestamp": now_utc_iso(),
                        },
                    )
                )
                return

            raise ValueError(f"Unsupported bridge method: {method}")
        except HANDLED_OPERATION_EXCEPTIONS as exc:
            self._error_response(
                request_id,
                exc,
                method=method,
                command=command,
                workspace_root=workspace_root,
            )

    def serve_forever(self) -> int:
        for raw_line in sys.stdin:
            line = raw_line.strip()
            if not line:
                continue
            parsed_request: dict[str, Any] = {}
            try:
                payload = parse_json_text(line)
                if not isinstance(payload, dict):
                    raise ValueError("Bridge request must be a JSON object.")
                parsed_request = payload
                request_id = str(payload.get("id", "")).strip()
                method = str(payload.get("method", "")).strip()
                params = payload.get("params", {})
                if not request_id:
                    raise ValueError("Bridge request id is required.")
                if not isinstance(params, dict):
                    raise ValueError("Bridge params must be a JSON object.")
                self._handle_request(request_id, method, params)
            except HANDLED_OPERATION_EXCEPTIONS as exc:
                request_id = ""
                request_method = ""
                raw_payload: dict[str, Any] = {}
                if parsed_request:
                    raw_payload = parsed_request
                else:
                    try:
                        fallback = parse_json_text(line)
                        if isinstance(fallback, dict):
                            raw_payload = fallback
                    except JSON_PARSE_EXCEPTIONS:
                        raw_payload = {}
                if raw_payload:
                    request_id = str(raw_payload.get("id", "")).strip()
                    request_method = str(raw_payload.get("method", "")).strip()
                workspace_root = ""
                command = ""
                params = raw_payload.get("params", {})
                if isinstance(params, dict):
                    workspace_root = str(params.get("workspace_root", ""))
                    command = str(params.get("command", ""))
                self._error_response(
                    request_id,
                    exc,
                    method=request_method,
                    command=command,
                    workspace_root=workspace_root,
                )
        return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Persistent stdio bridge server for the jakal-flow desktop app")
    parser.add_argument("--stdio", action="store_true", help="Run the bridge server over newline-delimited stdio JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    _args = parse_args(argv)
    server = BridgeServer()
    return server.serve_forever()


if __name__ == "__main__":
    raise SystemExit(main())
