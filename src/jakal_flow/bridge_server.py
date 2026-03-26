from __future__ import annotations

import argparse
import json
from pathlib import Path
from threading import Lock, Thread
import sys
import time
from typing import Any

from .bridge_contract import BRIDGE_PROTOCOL_VERSION, BridgeEnvelope, BridgeEvent, BridgeJobSnapshot
from .bridge_events import BridgeEventSink, bridge_event_context
from .ui_bridge import configure_stdio, default_workspace_root, run_command
from .utils import now_utc_iso, parse_json_text


def now_ms() -> int:
    return int(time.time() * 1000)


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
    def __init__(self, send_message) -> None:
        self._jobs: dict[str, BridgeJobSnapshot] = {}
        self._lock = Lock()
        self._send_message = send_message

    def _publish(self, snapshot: BridgeJobSnapshot) -> None:
        self._send_message(
            BridgeEnvelope(
                kind="event",
                event="job.updated",
                payload={"job": snapshot.to_dict()},
            )
        )

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            jobs = sorted(
                self._jobs.values(),
                key=lambda item: (item.updated_at_ms, item.id),
                reverse=True,
            )
            return [job.to_dict() for job in jobs]

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            snapshot = self._jobs.get(job_id)
            return None if snapshot is None else snapshot.to_dict()

    def any_running(self) -> bool:
        with self._lock:
            return any(job.status == "running" for job in self._jobs.values())

    def create(self, command: str, payload: dict[str, Any] | None = None) -> BridgeJobSnapshot:
        if self.any_running():
            raise RuntimeError("Another background task is already running.")
        job_id = f"job-{command}-{now_ms()}"
        repo_id = ""
        project_dir = ""
        if isinstance(payload, dict):
            repo_id = str(payload.get("repo_id", "")).strip()
            project_dir = str(payload.get("project_dir", "")).strip()
        snapshot = BridgeJobSnapshot(
            id=job_id,
            command=command,
            status="running",
            updated_at_ms=now_ms(),
            repo_id=repo_id,
            project_dir=project_dir,
        )
        with self._lock:
            self._jobs[job_id] = snapshot
        self._publish(snapshot)
        return snapshot

    def update(self, job_id: str, **changes: Any) -> BridgeJobSnapshot | None:
        with self._lock:
            snapshot = self._jobs.get(job_id)
            if snapshot is None:
                return None
            for key, value in changes.items():
                setattr(snapshot, key, value)
            snapshot.updated_at_ms = now_ms()
        self._publish(snapshot)
        return snapshot


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

    def _error_response(self, request_id: str, error: str) -> None:
        self._send_envelope(
            BridgeEnvelope(
                kind="response",
                id=request_id,
                ok=False,
                error=error,
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

    def _run_job(self, job_id: str, command: str, workspace_root: Path, payload: dict[str, Any] | None) -> None:
        try:
            with bridge_event_context(self._event_sink):
                result = run_command(command, workspace_root, payload)
            self._jobs.update(job_id, status="completed", error=None, result=result if isinstance(result, dict) else {})
            self._send_envelope(
                BridgeEnvelope(
                    kind="event",
                    event="project.changed",
                    payload=self._infer_project_event_payload(command, workspace_root, payload, result),
                )
            )
        except Exception as exc:
            self._jobs.update(job_id, status="failed", error=str(exc).strip() or str(exc), result=None)

    def _handle_request(self, request_id: str, method: str, params: dict[str, Any]) -> None:
        workspace_root = Path(str(params.get("workspace_root", default_workspace_root())).strip() or default_workspace_root())
        payload = params.get("payload", {})
        payload = payload if isinstance(payload, dict) else {}
        command = str(params.get("command", "")).strip()

        if method == "bridge_request":
            with bridge_event_context(self._event_sink):
                result = run_command(command, workspace_root, payload)
            self._send_envelope(BridgeEnvelope(kind="response", id=request_id, ok=True, result=result if isinstance(result, dict) else {}))
            if command not in {"bootstrap", "list-projects", "load-project"}:
                self._send_envelope(
                    BridgeEnvelope(
                        kind="event",
                        event="project.changed",
                        payload=self._infer_project_event_payload(command, workspace_root, payload, result),
                    )
                )
            return

        if method == "start_job":
            snapshot = self._jobs.create(command, payload)
            thread = Thread(
                target=self._run_job,
                args=(snapshot.id, command, workspace_root, payload),
                daemon=True,
            )
            thread.start()
            self._send_envelope(BridgeEnvelope(kind="response", id=request_id, ok=True, result=snapshot.to_dict()))
            return

        if method == "get_job":
            result = self._jobs.get_job(str(params.get("job_id", "")).strip())
            self._send_envelope(BridgeEnvelope(kind="response", id=request_id, ok=True, result=result))
            return

        if method == "list_jobs":
            self._send_envelope(BridgeEnvelope(kind="response", id=request_id, ok=True, result=self._jobs.list_jobs()))
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

    def serve_forever(self) -> int:
        for raw_line in sys.stdin:
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = parse_json_text(line)
                if not isinstance(payload, dict):
                    raise ValueError("Bridge request must be a JSON object.")
                request_id = str(payload.get("id", "")).strip()
                method = str(payload.get("method", "")).strip()
                params = payload.get("params", {})
                if not request_id:
                    raise ValueError("Bridge request id is required.")
                if not isinstance(params, dict):
                    raise ValueError("Bridge params must be a JSON object.")
                self._handle_request(request_id, method, params)
            except Exception as exc:
                request_id = ""
                try:
                    parsed = parse_json_text(line)
                    if isinstance(parsed, dict):
                        request_id = str(parsed.get("id", "")).strip()
                except Exception:
                    request_id = ""
                self._error_response(request_id, str(exc).strip() or str(exc))
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
