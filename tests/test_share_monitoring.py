from __future__ import annotations

import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import shutil
import sys
import threading
import unittest
from unittest import mock
import urllib.error
import urllib.request
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jakal_flow.orchestrator import Orchestrator
from jakal_flow.share import (
    ShareSession,
    create_share_session,
    load_share_sessions,
    process_is_running,
    public_monitor_status,
    revoke_share_session,
    save_share_sessions,
    validate_share_session,
)
from jakal_flow.share_server import ShareHTTPServer, ShareRequestHandler
from jakal_flow.ui_bridge import run_command
from jakal_flow.utils import append_jsonl


def local_temp_root() -> Path:
    root = Path(__file__).resolve().parents[1] / ".tmp_share_tests"
    root.mkdir(parents=True, exist_ok=True)
    return root


class TemporaryTestDir:
    def __enter__(self) -> Path:
        self.path = local_temp_root() / f"case_{uuid.uuid4().hex}"
        self.path.mkdir(parents=True, exist_ok=True)
        return self.path

    def __exit__(self, exc_type, exc, tb) -> None:
        shutil.rmtree(self.path, ignore_errors=True)


def create_project(workspace_root: Path, repo_dir: Path) -> tuple[Orchestrator, object]:
    payload = {
        "project_dir": str(repo_dir),
        "display_name": "Share Demo",
        "branch": "main",
        "origin_url": "",
        "runtime": {
            "model": "gpt-5.4",
            "model_preset": "high",
            "effort": "high",
            "test_cmd": "python -m pytest",
            "max_blocks": 4,
        },
    }
    with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
        "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
        side_effect=lambda *args, **kwargs: _fake_codex_snapshot(),
    ):
        run_command("save-project-setup", workspace_root, payload)
    orchestrator = Orchestrator(workspace_root)
    project = orchestrator.local_project(repo_dir)
    assert project is not None
    return orchestrator, project


def _fake_codex_snapshot() -> mock.Mock:
    payload = {
        "checked_at": "2026-03-26T00:00:00+00:00",
        "available": True,
        "model_catalog": [
            {
                "id": "auto",
                "model": "auto",
                "display_name": "Auto",
                "description": "Use Codex default model routing from the installed CLI.",
                "hidden": False,
                "is_default": True,
                "default_reasoning_effort": "medium",
                "supported_reasoning_efforts": ["low", "medium", "high", "xhigh"],
            }
        ],
        "account": {
            "authenticated": True,
            "requires_openai_auth": True,
            "type": "chatgpt",
            "email": "demo@example.com",
            "plan_type": "pro",
        },
        "rate_limits": {"default_limit_id": "codex", "items": []},
        "error": "",
    }
    return mock.Mock(model_catalog=payload["model_catalog"], to_dict=mock.Mock(return_value=payload))


class ShareMonitoringTests(unittest.TestCase):
    @mock.patch("jakal_flow.share.os.name", "nt")
    @mock.patch("jakal_flow.share.subprocess.run")
    def test_process_is_running_handles_non_utf8_tasklist_output(self, run_mock: mock.Mock) -> None:
        run_mock.return_value = mock.Mock(stdout=b"\xc0\xfd\xbc\xd3 python.exe                 4321")

        self.assertTrue(process_is_running(4321))

    def test_session_creation_revokes_previous_active_session(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            _orchestrator, project = create_project(workspace_root, repo_dir)

            first = create_share_session(project, expires_in_minutes=60, created_by="test")
            second = create_share_session(project, expires_in_minutes=60, created_by="test")
            sessions = load_share_sessions(project)

            self.assertEqual(len(sessions), 2)
            self.assertTrue(first.session_id != second.session_id)
            self.assertIsNotNone(next(item for item in sessions if item.session_id == first.session_id).revoked_at)
            self.assertTrue(next(item for item in sessions if item.session_id == second.session_id).is_active())

    def test_session_expiry_and_token_validation_and_revoke_behavior(self) -> None:
        session = ShareSession(
            session_id="demo-session",
            viewer_token="secret-token",
            created_at="2026-03-26T00:00:00+00:00",
            expires_at="2026-03-25T00:00:00+00:00",
        )
        with self.assertRaises(PermissionError):
            validate_share_session(session, "secret-token")
        with self.assertRaises(PermissionError):
            validate_share_session(
                ShareSession(
                    session_id="demo-session",
                    viewer_token="secret-token",
                    created_at="2026-03-26T00:00:00+00:00",
                    expires_at="2099-03-25T00:00:00+00:00",
                ),
                "wrong-token",
            )

        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            _orchestrator, project = create_project(workspace_root, repo_dir)
            created = create_share_session(project, expires_in_minutes=60, created_by="test")
            revoke_share_session(project, created.session_id)
            revoked = next(item for item in load_share_sessions(project) if item.session_id == created.session_id)
            with self.assertRaises(PermissionError):
                validate_share_session(revoked, created.viewer_token)

    def test_public_monitor_status_masks_sensitive_log_content(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            orchestrator, project = create_project(workspace_root, repo_dir)

            append_jsonl(
                project.paths.ui_event_log_file,
                {
                    "timestamp": "2026-03-26T10:00:00+00:00",
                    "event_type": "step-started",
                    "message": "Using token=ghp_abcdefghijklmnopqrstuvwxyz123456 and C:\\secret\\repo\\.env",
                    "details": {"step_id": "ST1"},
                },
            )
            append_jsonl(
                project.paths.logs_dir / "test_runs.jsonl",
                {
                    "label": "block-search-pass",
                    "block_index": 1,
                    "returncode": 1,
                    "summary": "failed with sk-testsecretvalue123456 at /Users/alice/project/.env",
                    "stdout_file": str(project.paths.logs_dir / "stdout.log"),
                    "stderr_file": str(project.paths.logs_dir / "stderr.log"),
                },
            )

            status = public_monitor_status(project, orchestrator.load_execution_plan_state(project), log_limit=5)

            self.assertEqual(status["project"]["display_name"], "Share Demo")
            self.assertIn("overall_run_status", status)
            self.assertIn("current_task", status)
            self.assertIn("latest_test_result", status)
            self.assertIn("recent_logs", status)
            self.assertNotIn("ghp_", json.dumps(status))
            self.assertNotIn("sk-testsecretvalue123456", json.dumps(status))
            self.assertNotIn("C:\\secret\\repo", json.dumps(status))
            self.assertNotIn("/Users/alice/project", json.dumps(status))
            self.assertNotIn("stdout_file", json.dumps(status))
            self.assertTrue(any("[masked]" in line or "[path]" in line for line in status["recent_logs"]))

    def test_share_status_api_enforces_token_and_returns_read_only_shape(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            orchestrator, project = create_project(workspace_root, repo_dir)
            append_jsonl(
                project.paths.ui_event_log_file,
                {
                    "timestamp": "2026-03-26T10:00:00+00:00",
                    "event_type": "run-started",
                    "message": "Started the run loop.",
                    "details": {},
                },
            )
            append_jsonl(
                project.paths.logs_dir / "test_runs.jsonl",
                {
                    "label": "block-search-pass",
                    "block_index": 1,
                    "returncode": 0,
                    "summary": "python -m pytest exited with 0",
                },
            )
            session = create_share_session(project, expires_in_minutes=60, created_by="test")
            save_share_sessions(project, load_share_sessions(project))

            server = ShareHTTPServer(("127.0.0.1", 0), ShareRequestHandler, workspace_root=workspace_root)
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
            thread.start()
            try:
                base_url = f"http://127.0.0.1:{server.server_address[1]}"
                response = urllib.request.urlopen(
                    f"{base_url}/share/api/status?session={session.session_id}&token={session.viewer_token}"
                )
                payload = json.loads(response.read().decode("utf-8"))
                self.assertEqual(payload["project"]["display_name"], "Share Demo")
                self.assertIn("overall_run_status", payload)
                self.assertIn("recent_logs", payload)
                self.assertIn("latest_test_result", payload)
                self.assertNotIn("repo_path", json.dumps(payload))
                self.assertNotIn("project_root", json.dumps(payload))

                with self.assertRaises(urllib.error.HTTPError) as bad_token:
                    urllib.request.urlopen(f"{base_url}/share/api/status?session={session.session_id}&token=bad-token")
                self.assertEqual(bad_token.exception.code, 403)

                revoke_share_session(project, session.session_id)
                with self.assertRaises(urllib.error.HTTPError) as revoked:
                    urllib.request.urlopen(
                        f"{base_url}/share/api/status?session={session.session_id}&token={session.viewer_token}"
                    )
                self.assertEqual(revoked.exception.code, 403)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_share_events_api_streams_live_status_payload(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            _orchestrator, project = create_project(workspace_root, repo_dir)
            append_jsonl(
                project.paths.ui_event_log_file,
                {
                    "timestamp": "2026-03-26T10:00:00+00:00",
                    "event_type": "run-started",
                    "message": "Started the run loop.",
                    "details": {},
                },
            )
            session = create_share_session(project, expires_in_minutes=60, created_by="test")

            server = ShareHTTPServer(("127.0.0.1", 0), ShareRequestHandler, workspace_root=workspace_root)
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
            thread.start()
            try:
                base_url = f"http://127.0.0.1:{server.server_address[1]}"
                response = urllib.request.urlopen(
                    f"{base_url}/share/api/events?session={session.session_id}&token={session.viewer_token}",
                    timeout=3,
                )
                self.assertIn("text/event-stream", response.headers.get("Content-Type", ""))

                event_name = ""
                payload = None
                for _ in range(12):
                    line = response.readline().decode("utf-8").strip()
                    if not line:
                        continue
                    if line.startswith("event: "):
                        event_name = line.split(": ", 1)[1]
                    elif line.startswith("data: ") and event_name == "status":
                        payload = json.loads(line.split(": ", 1)[1])
                        break

                self.assertIsNotNone(payload)
                self.assertEqual(payload["project"]["display_name"], "Share Demo")
                self.assertIn("recent_logs", payload)
                self.assertIn("latest_test_result", payload)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
