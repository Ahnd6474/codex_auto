from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .orchestrator import Orchestrator
from .share import (
    DEFAULT_SHARE_HOST,
    DEFAULT_SHARE_PORT,
    DEFAULT_VIEWER_PATH,
    ShareServerState,
    load_share_server_state,
    mask_public_text,
    public_monitor_status,
    resolve_shared_session,
    share_server_log_file,
    share_server_status_file,
    validate_share_session,
)
from .utils import now_utc_iso, write_json


WEBSITE_ROOT = Path(__file__).resolve().parents[2] / "website"


class ShareRequestHandler(BaseHTTPRequestHandler):
    server_version = "jakal-flow-share/0.1"
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
        self._write_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})

    def log_message(self, format: str, *args: Any) -> None:
        line = mask_public_text(format % args, max_chars=180)
        if not line:
            return
        with share_server_log_file(self.server.workspace_root).open("a", encoding="utf-8") as handle:  # type: ignore[attr-defined]
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

    def _validated_project(self, query: str):
        session_id = self._query_arg(query, "session")
        token = self._query_arg(query, "token")
        if not session_id or not token:
            raise ValueError("session and token are required.")
        project, session = resolve_shared_session(self.server.workspace_root, session_id)  # type: ignore[attr-defined]
        validate_share_session(session, token)
        return project, session

    def _serve_status(self, query: str) -> None:
        try:
            project, session = self._validated_project(query)
            orchestrator = Orchestrator(self.server.workspace_root)  # type: ignore[attr-defined]
            self._write_json(HTTPStatus.OK, self._status_payload(project, session, orchestrator=orchestrator))
        except ValueError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except KeyError:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "Unknown share session."})
        except PermissionError as exc:
            self._write_json(HTTPStatus.FORBIDDEN, {"error": str(exc)})

    def _serve_logs(self, query: str) -> None:
        try:
            project, _session = self._validated_project(query)
            limit = min(50, max(1, int(self._query_arg(query, "limit") or "20")))
            offset = max(0, int(self._query_arg(query, "offset") or "0"))
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
        try:
            project, session = self._validated_project(query)
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
                project, session = resolve_shared_session(self.server.workspace_root, session.session_id)  # type: ignore[attr-defined]
                validate_share_session(session, self._query_arg(query, "token"))
                payload = self._status_payload(project, session, orchestrator=orchestrator)
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

    def _status_payload(self, project, session, *, orchestrator: Orchestrator | None = None) -> dict[str, Any]:
        orchestrator = orchestrator or Orchestrator(self.server.workspace_root)  # type: ignore[attr-defined]
        plan_state = orchestrator.load_execution_plan_state(project)
        payload = public_monitor_status(project, plan_state, log_limit=8)
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

    def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class ShareHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address, handler_cls, workspace_root: Path):
        super().__init__(server_address, handler_cls)
        self.workspace_root = workspace_root


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only share server for jakal-flow project monitoring")
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
