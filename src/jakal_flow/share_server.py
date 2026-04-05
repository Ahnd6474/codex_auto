from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
from threading import Lock, Thread
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from ._version import __version__
from .errors import HANDLED_OPERATION_EXCEPTIONS
from .job_scheduler import active_scheduler_jobs, load_scheduler_state, matching_active_scheduler_job, running_scheduler_job_count
from .orchestrator import Orchestrator
from .project_snapshot import context_execution_snapshot
from .rate_limiter import TokenBucketRateLimiter, TokenBucketRule
from .run_control import request_stop_after_current_step
from .share import (
    DEFAULT_SHARE_HOST,
    DEFAULT_SHARE_PORT,
    DEFAULT_VIEWER_PATH,
    ShareServerState,
    can_resume_from_remote,
    load_share_server_state,
    mask_public_text,
    public_execution_flow_svg,
    public_monitor_status,
    public_workspace_monitor_status,
    resolve_shared_access,
    resolve_shared_session,
    share_server_log_file,
    share_server_status_file,
    validate_share_session,
)
from .ui_bridge import run_command
from .utils import append_jsonl, now_utc_iso, parse_json_text, write_json


WEBSITE_ROOT = Path(__file__).resolve().parents[2] / "website"
_DEFAULT_SHARE_API_RATE_LIMIT_RULE = TokenBucketRule(capacity=24.0, refill_tokens_per_second=12.0)
_SHARE_API_RATE_LIMIT_RULES: dict[str, TokenBucketRule] = {
    "/share/api/status": TokenBucketRule(capacity=12.0, refill_tokens_per_second=6.0),
    "/share/api/logs": TokenBucketRule(capacity=10.0, refill_tokens_per_second=4.0),
    "/share/api/flow.svg": TokenBucketRule(capacity=6.0, refill_tokens_per_second=2.0),
    "/share/api/events": TokenBucketRule(capacity=2.0, refill_tokens_per_second=0.25),
    "/share/api/control": TokenBucketRule(capacity=4.0, refill_tokens_per_second=1.0),
}


def _path_is_accessible_dir(path: Path | None) -> bool:
    if path is None:
        return False
    try:
        return path.exists() and path.is_dir()
    except OSError:
        return False


class ShareRemoteControlManager:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self._lock = Lock()
        self._resume_starting_repo_ids: set[str] = set()

    def is_resume_starting(self, repo_id: str) -> bool:
        with self._lock:
            return repo_id in self._resume_starting_repo_ids

    def resume_starting_repo_ids(self) -> set[str]:
        with self._lock:
            return set(self._resume_starting_repo_ids)

    def _set_resume_starting(self, repo_id: str, active: bool) -> None:
        with self._lock:
            if active:
                self._resume_starting_repo_ids.add(repo_id)
            else:
                self._resume_starting_repo_ids.discard(repo_id)

    def _starting_resume_count(self, *, exclude_repo_id: str = "") -> int:
        normalized_exclude = str(exclude_repo_id or "").strip()
        with self._lock:
            return sum(1 for item in self._resume_starting_repo_ids if item != normalized_exclude)

    def _ensure_resume_slot_available(
        self,
        *,
        repo_id: str,
        project_dir: Path,
        exclude_starting_repo_id: str = "",
    ) -> None:
        scheduler_state = load_scheduler_state(self.workspace_root)
        if matching_active_scheduler_job(
            scheduler_state,
            repo_id=repo_id,
            project_dir=project_dir,
            job_lane="execution",
        ) is not None:
            raise RuntimeError("Another background task is already active for this project.")
        active_jobs = active_scheduler_jobs(scheduler_state)
        queued_jobs = [job for job in active_jobs if str(job.get("status", "")).strip().lower() == "queued"]
        if queued_jobs:
            raise RuntimeError("Reservations are disabled for this project, so this run must wait for a free slot.")
        running_jobs = running_scheduler_job_count(scheduler_state)
        pending_resumes = self._starting_resume_count(exclude_repo_id=exclude_starting_repo_id)
        if (running_jobs + pending_resumes) >= int(scheduler_state.max_concurrent_jobs or 1):
            raise RuntimeError("Reservations are disabled for this project, so this run must wait for a free slot.")

    def _append_project_event(
        self,
        project,
        event_type: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        append_jsonl(
            project.paths.ui_event_log_file,
            {
                "timestamp": now_utc_iso(),
                "event_type": event_type,
                "message": message,
                "details": details or {},
            },
        )

    def request_pause(self, project) -> dict[str, Any]:
        control = request_stop_after_current_step(project, request_source="share-remote-monitor")
        self._append_project_event(
            project,
            "remote-pause-requested",
            "Pause requested after the current step from the remote monitor.",
            control,
        )
        return control

    def queue_resume(self, project, orchestrator: Orchestrator) -> dict[str, Any]:
        plan_state = orchestrator.load_execution_plan_state(project)
        execution_snapshot = context_execution_snapshot(project, plan_state)
        if execution_snapshot.is_running:
            raise RuntimeError("The run is already active.")
        if not can_resume_from_remote(project, plan_state):
            raise RuntimeError("No remaining paused or pending work is available to resume.")
        repo_id = project.metadata.repo_id
        project_dir = Path(str(project.paths.repo_dir or project.metadata.repo_path or "")).expanduser()
        if not _path_is_accessible_dir(project_dir):
            self._append_project_event(
                project,
                "remote-resume-rejected",
                "Remote resume is blocked until the repository path is rebound or repaired.",
                {
                    "repo_path_hint": str(project.metadata.repo_path or ""),
                    "project_dir": str(project_dir),
                },
            )
            raise RuntimeError("The project repository is not accessible. Rebind or repair it before resuming.")
        if self.is_resume_starting(repo_id):
            raise RuntimeError("A remote resume request is already starting.")
        self._ensure_resume_slot_available(repo_id=repo_id, project_dir=project_dir)

        requested_at = now_utc_iso()
        payload = {
            "repo_id": repo_id,
            "project_dir": str(project.metadata.repo_path),
            "display_name": project.metadata.display_name,
            "branch": project.metadata.branch,
            "origin_url": project.metadata.origin_url,
            "runtime": project.runtime.to_dict(),
            "plan": plan_state.to_dict(),
        }
        self._set_resume_starting(repo_id, True)
        self._append_project_event(
            project,
            "remote-resume-requested",
            "Resume requested from the remote monitor.",
            {"requested_at": requested_at},
        )
        Thread(
            target=self._run_resume_job,
            args=(repo_id, payload),
            daemon=True,
        ).start()
        return {
            "queued": True,
            "requested_at": requested_at,
            "repo_id": repo_id,
        }

    def _run_resume_job(self, repo_id: str, payload: dict[str, Any]) -> None:
        project_dir = Path(str(payload.get("project_dir", "")).strip()).expanduser()
        try:
            self._ensure_resume_slot_available(
                repo_id=repo_id,
                project_dir=project_dir,
                exclude_starting_repo_id=repo_id,
            )
            run_command("run-plan", self.workspace_root, payload)
        except HANDLED_OPERATION_EXCEPTIONS as exc:
            orchestrator = Orchestrator(self.workspace_root)
            project = None
            try:
                project = orchestrator.workspace.load_project_by_id(repo_id)
            except (LookupError, ValueError, OSError):
                project = orchestrator.local_project(project_dir) if str(project_dir) else None
            if project is not None:
                self._append_project_event(
                    project,
                    "remote-resume-failed",
                    "Remote resume failed before the run loop could finish.",
                    {"error": str(exc).strip() or str(exc)},
                )
        finally:
            self._set_resume_starting(repo_id, False)


class ShareRequestHandler(BaseHTTPRequestHandler):
    server_version = f"jakal-flow-share/{__version__}"
    stream_poll_interval_secs = 1.0
    stream_heartbeat_interval_secs = 15.0

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in {"/", ""}:
            self._redirect(DEFAULT_VIEWER_PATH)
            return
        if parsed.path == DEFAULT_VIEWER_PATH:
            self._serve_static(WEBSITE_ROOT / "share.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/share/generated_share_translations.js":
            self._serve_static(WEBSITE_ROOT / "generated_share_translations.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/share/manual_share_translations.js":
            self._serve_static(WEBSITE_ROOT / "manual_share_translations.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/share/share.js":
            self._serve_static(WEBSITE_ROOT / "share.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/share/share.css":
            self._serve_static(WEBSITE_ROOT / "share.css", "text/css; charset=utf-8")
            return
        if parsed.path == "/share/api/status":
            self._serve_status(parsed.query)
            return
        if parsed.path == "/share/api/events":
            self._serve_events(parsed.query)
            return
        if parsed.path == "/share/api/logs":
            self._serve_logs(parsed.query)
            return
        if parsed.path == "/share/api/flow.svg":
            self._serve_flow_svg(parsed.query)
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/share/api/control":
            self._serve_control(parsed.query)
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})

    def log_message(self, format: str, *args: Any) -> None:
        line = mask_public_text(format % args, max_chars=180)
        if not line:
            return
        log_path = share_server_log_file(self.server.workspace_root)  # type: ignore[attr-defined]
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{now_utc_iso()} {line}\n")

    def _redirect(self, path: str) -> None:
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", path)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _serve_static(self, path: Path, content_type: str | None = None) -> None:
        if not path.exists():
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
            return
        raw = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _query_arg(self, query: str, key: str) -> str:
        values = parse_qs(query).get(key, [])
        if not values:
            return ""
        return str(values[0]).strip()

    def _rate_limit_identity(self, query: str) -> str:
        access_token = self._query_arg(query, "access")
        if access_token:
            return f"access:{access_token}"
        session_id = self._query_arg(query, "session")
        if session_id:
            return f"session:{session_id}"
        return "anonymous"

    def _enforce_api_rate_limit(self, path: str, query: str) -> bool:
        client_host = self.client_address[0] if self.client_address else ""
        decision = self.server.consume_api_request(  # type: ignore[attr-defined]
            path=path,
            client_host=client_host,
            identity=self._rate_limit_identity(query),
        )
        if decision.allowed:
            return True
        self._write_json(
            HTTPStatus.TOO_MANY_REQUESTS,
            {"error": "Too many requests. Retry later."},
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )
        return False

    def _validated_session(self, query: str):
        access_token = self._query_arg(query, "access")
        if access_token:
            return resolve_shared_access(self.server.workspace_root, access_token)  # type: ignore[attr-defined]
        session_id = self._query_arg(query, "session")
        token = self._query_arg(query, "token")
        if not session_id or not token:
            raise ValueError("access or session/token is required.")
        project, session = resolve_shared_session(self.server.workspace_root, session_id)  # type: ignore[attr-defined]
        validate_share_session(session, token)
        return project, session

    def _workspace_project(self, repo_id: str):
        target = str(repo_id or "").strip()
        if not target:
            raise ValueError("repo_id is required.")
        orchestrator = Orchestrator(self.server.workspace_root)  # type: ignore[attr-defined]
        return orchestrator.workspace.load_project_by_id(target)

    def _read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0") or "0")
        if content_length <= 0:
            return {}
        raw = self.rfile.read(content_length)
        if not raw.strip():
            return {}
        payload = parse_json_text(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")
        return payload

    def _serve_status(self, query: str) -> None:
        if not self._enforce_api_rate_limit("/share/api/status", query):
            return
        try:
            _owner_project, session = self._validated_session(query)
            orchestrator = Orchestrator(self.server.workspace_root)  # type: ignore[attr-defined]
            self._write_json(HTTPStatus.OK, self._workspace_status_payload(session, orchestrator=orchestrator))
        except ValueError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except KeyError:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "Unknown share session."})
        except PermissionError as exc:
            self._write_json(HTTPStatus.FORBIDDEN, {"error": str(exc)})

    def _serve_logs(self, query: str) -> None:
        if not self._enforce_api_rate_limit("/share/api/logs", query):
            return
        try:
            owner_project, _session = self._validated_session(query)
            limit = min(50, max(1, int(self._query_arg(query, "limit") or "20")))
            offset = max(0, int(self._query_arg(query, "offset") or "0"))
            repo_id = self._query_arg(query, "repo_id")
            project = self._workspace_project(repo_id) if repo_id else owner_project
            if project is None:
                raise ValueError("repo_id is required for workspace share sessions.")
            orchestrator = Orchestrator(self.server.workspace_root)  # type: ignore[attr-defined]
            plan_state = orchestrator.load_execution_plan_state(project)
            status_payload = public_monitor_status(project, plan_state, log_limit=50)
            lines = status_payload.get("recent_logs", [])
            items = lines[offset : offset + limit]
            self._write_json(
                HTTPStatus.OK,
                {
                    "items": items,
                    "offset": offset,
                    "limit": limit,
                    "total": len(lines),
                    "last_updated_at": status_payload.get("last_updated_at"),
                },
            )
        except ValueError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except KeyError:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "Unknown share session."})
        except PermissionError as exc:
            self._write_json(HTTPStatus.FORBIDDEN, {"error": str(exc)})

    def _serve_events(self, query: str) -> None:
        if not self._enforce_api_rate_limit("/share/api/events", query):
            return
        try:
            _owner_project, session = self._validated_session(query)
        except ValueError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except KeyError:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "Unknown share session."})
            return
        except PermissionError as exc:
            self._write_json(HTTPStatus.FORBIDDEN, {"error": str(exc)})
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        last_payload = ""
        last_heartbeat = time.monotonic()
        orchestrator = Orchestrator(self.server.workspace_root)  # type: ignore[attr-defined]
        try:
            self._write_sse_comment("connected")
            self._write_sse_event("ready", {"ok": True})
            while True:
                _owner_project, session = self._validated_session(query)
                payload = self._workspace_status_payload(session, orchestrator=orchestrator)
                serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
                if serialized != last_payload:
                    self._write_sse_event("status", payload)
                    last_payload = serialized
                    last_heartbeat = time.monotonic()
                elif (time.monotonic() - last_heartbeat) >= self.stream_heartbeat_interval_secs:
                    self._write_sse_comment("keepalive")
                    last_heartbeat = time.monotonic()
                time.sleep(self.stream_poll_interval_secs)
        except (BrokenPipeError, ConnectionResetError):
            return
        except KeyError:
            self._write_sse_event("error", {"error": "Unknown share session."})
        except PermissionError as exc:
            self._write_sse_event("error", {"error": str(exc)})

    def _serve_control(self, query: str) -> None:
        if not self._enforce_api_rate_limit("/share/api/control", query):
            return
        try:
            owner_project, session = self._validated_session(query)
            body = self._read_json_body()
            action = str(body.get("action", "")).strip().lower()
            if not action:
                raise ValueError("action is required.")
            repo_id = str(body.get("repo_id", "")).strip()
            project = self._workspace_project(repo_id) if repo_id else owner_project
            if project is None:
                raise ValueError("repo_id is required for workspace share sessions.")
            orchestrator = Orchestrator(self.server.workspace_root)  # type: ignore[attr-defined]
            if action == "pause":
                control = self.server.remote_control_manager.request_pause(project)  # type: ignore[attr-defined]
                payload = self._workspace_status_payload(session, orchestrator=orchestrator)
                payload["control_result"] = {
                    "action": action,
                    "accepted": True,
                    "repo_id": project.metadata.repo_id,
                    "run_control": control,
                }
                self._write_json(HTTPStatus.OK, payload)
                return
            if action == "resume":
                result = self.server.remote_control_manager.queue_resume(project, orchestrator)  # type: ignore[attr-defined]
                payload = self._workspace_status_payload(session, orchestrator=orchestrator)
                payload["control_result"] = {
                    "action": action,
                    "accepted": True,
                    "repo_id": project.metadata.repo_id,
                    **result,
                }
                self._write_json(HTTPStatus.ACCEPTED, payload)
                return
            raise ValueError(f"Unsupported control action: {action}")
        except ValueError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except RuntimeError as exc:
            self._write_json(HTTPStatus.CONFLICT, {"error": str(exc)})
        except KeyError:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "Unknown share session."})
        except PermissionError as exc:
            self._write_json(HTTPStatus.FORBIDDEN, {"error": str(exc)})

    def _serve_flow_svg(self, query: str) -> None:
        if not self._enforce_api_rate_limit("/share/api/flow.svg", query):
            return
        try:
            owner_project, _session = self._validated_session(query)
            repo_id = self._query_arg(query, "repo_id")
            project = self._workspace_project(repo_id) if repo_id else owner_project
            if project is None:
                raise ValueError("repo_id is required for workspace share sessions.")
            orchestrator = Orchestrator(self.server.workspace_root)  # type: ignore[attr-defined]
            plan_state = orchestrator.load_execution_plan_state(project)
            raw = public_execution_flow_svg(project, plan_state).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        except ValueError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except KeyError:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "Unknown share session."})
        except PermissionError as exc:
            self._write_json(HTTPStatus.FORBIDDEN, {"error": str(exc)})

    def _workspace_status_payload(self, session, *, orchestrator: Orchestrator | None = None) -> dict[str, Any]:
        orchestrator = orchestrator or Orchestrator(self.server.workspace_root)  # type: ignore[attr-defined]
        include_repo_ids = self.server.remote_control_manager.resume_starting_repo_ids()  # type: ignore[attr-defined]
        payload = public_workspace_monitor_status(
            self.server.workspace_root,  # type: ignore[attr-defined]
            orchestrator=orchestrator,
            log_limit=8,
            include_repo_ids=include_repo_ids,
        )
        for item in payload.get("projects", []):
            if not isinstance(item, dict):
                continue
            project = item.get("project", {})
            if not isinstance(project, dict):
                continue
            repo_id = str(project.get("repo_id", "")).strip()
            remote_control = item.get("remote_control")
            if not isinstance(remote_control, dict) or not repo_id:
                continue
            resume_starting = self.server.remote_control_manager.is_resume_starting(repo_id)  # type: ignore[attr-defined]
            remote_control["resume_starting"] = resume_starting
            if resume_starting:
                remote_control["can_resume"] = False
        payload["share_session"] = {
            "session_id": session.session_id,
            "expires_at": session.expires_at,
        }
        return payload

    def _write_sse_comment(self, message: str) -> None:
        self.wfile.write(f": {message}\n\n".encode("utf-8"))
        self.wfile.flush()

    def _write_sse_event(self, event_name: str, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False)
        self.wfile.write(b"retry: 3000\n")
        self.wfile.write(f"event: {event_name}\n".encode("utf-8"))
        for line in raw.splitlines() or ["{}"]:
            self.wfile.write(f"data: {line}\n".encode("utf-8"))
        self.wfile.write(b"\n")
        self.wfile.flush()

    def _write_json(
        self,
        status: HTTPStatus,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class ShareHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address, handler_cls, workspace_root: Path):
        super().__init__(server_address, handler_cls)
        self.workspace_root = workspace_root
        self.remote_control_manager = ShareRemoteControlManager(workspace_root)
        self.request_rate_limiter = TokenBucketRateLimiter(max_buckets=512, bucket_ttl_seconds=300.0)
        self.request_rate_limit_rules = dict(_SHARE_API_RATE_LIMIT_RULES)

    def consume_api_request(self, *, path: str, client_host: str, identity: str):
        rule = self.request_rate_limit_rules.get(path, _DEFAULT_SHARE_API_RATE_LIMIT_RULE)
        bucket_id = "|".join((path, client_host or "unknown", identity or "anonymous"))
        return self.request_rate_limiter.consume(bucket_id, rule=rule)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Share server for jakal-flow project monitoring and remote pause/resume control")
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--host", default=DEFAULT_SHARE_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_SHARE_PORT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    workspace_root = Path(args.workspace_root).expanduser().resolve()
    server = ShareHTTPServer((args.host, args.port), ShareRequestHandler, workspace_root=workspace_root)
    state = ShareServerState(
        host=args.host,
        port=int(server.server_address[1]),
        pid=int(getattr(os, "getpid")()),
        started_at=now_utc_iso(),
        viewer_path=DEFAULT_VIEWER_PATH,
    )
    write_json(share_server_status_file(workspace_root), state.to_dict())
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        current = load_share_server_state(workspace_root)
        if current and current.pid == state.pid:
            try:
                share_server_status_file(workspace_root).unlink(missing_ok=True)
            except OSError:
                pass
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
