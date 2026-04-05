from __future__ import annotations

import http.client
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import unittest
from unittest import mock
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlsplit
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jakal_flow.orchestrator import Orchestrator
from jakal_flow.models import ExecutionPlanState, ExecutionStep
from jakal_flow.job_scheduler import write_scheduler_state
from jakal_flow.share import (
    ShareSession,
    ShareServerState,
    create_workspace_share_session,
    current_step_summary,
    create_share_session,
    load_workspace_share_sessions,
    load_share_sessions,
    process_is_running,
    project_share_payload,
    public_execution_flow_svg,
    public_monitor_status,
    public_session_summary,
    public_workspace_monitor_status,
    revoke_share_session,
    save_share_sessions,
    share_server_status_payload,
    normalize_share_bind_host,
    validate_share_session,
    workspace_active_share_session,
)
from jakal_flow.public_tunnel import (
    ensure_cloudflared_path,
    install_cloudflared_with_winget,
    normalize_tunnel_target_url,
    process_is_running as tunnel_process_is_running,
)
from jakal_flow.rate_limiter import TokenBucketRule
from jakal_flow.share_server import ShareHTTPServer, ShareRemoteControlManager, ShareRequestHandler
from jakal_flow.ui_bridge import run_command
from jakal_flow.ui_bridge_commands.share import verify_local_share_session_access
from jakal_flow.utils import append_jsonl, read_jsonl_tail


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
    with mock.patch("jakal_flow.orchestrator.Orchestrator._resolve_local_repo_backend", return_value="git"), mock.patch(
        "jakal_flow.orchestrator.ensure_virtualenv",
        return_value=repo_dir / ".venv",
    ), mock.patch(
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
    def test_verify_local_share_session_access_retries_after_remote_disconnect(self) -> None:
        session_payload = {
            "local_url": "http://127.0.0.1:55180/share/view",
            "session_id": "demo-session",
            "viewer_token": "demo-token",
        }
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b"{}"
        response.status = 200

        with mock.patch(
            "jakal_flow.ui_bridge_commands.share.urlopen",
            side_effect=[
                http.client.RemoteDisconnected("Remote end closed connection without response"),
                response,
            ],
        ):
            verify_local_share_session_access(session_payload)

    def test_process_is_running_treats_posix_zombie_as_not_running(self) -> None:
        if not Path("/proc").exists():
            self.skipTest("Requires /proc to verify zombie process state.")
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(3600)"])
        try:
            child.terminate()
            time.sleep(0.1)
            self.assertFalse(process_is_running(child.pid))
            self.assertFalse(tunnel_process_is_running(child.pid))
        finally:
            child.wait(timeout=2)

    def test_current_step_summary_combines_parallel_running_steps(self) -> None:
        summary = current_step_summary(
            ExecutionPlanState(
                execution_mode="parallel",
                steps=[
                    ExecutionStep(step_id="ST1", title="Root", status="completed"),
                    ExecutionStep(step_id="ST2", title="Frontend", depends_on=["ST1"], owned_paths=["desktop/src"], status="running"),
                    ExecutionStep(step_id="ST3", title="Backend", depends_on=["ST1"], owned_paths=["src/jakal_flow"], status="running"),
                ],
            )
        )

        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertEqual(summary["status"], "running")
        self.assertEqual(summary["step_id"], "ST2, ST3")
        self.assertEqual(summary["title"], "Parallel batch: ST2, ST3")
        self.assertEqual(summary["summary"], "Frontend, Backend")

    def test_current_step_summary_includes_integrating_parallel_steps(self) -> None:
        summary = current_step_summary(
            ExecutionPlanState(
                execution_mode="parallel",
                steps=[
                    ExecutionStep(step_id="ST1", title="Root", status="completed"),
                    ExecutionStep(step_id="ST2", title="Frontend", depends_on=["ST1"], owned_paths=["desktop/src"], status="integrating"),
                    ExecutionStep(step_id="ST3", title="Backend", depends_on=["ST1"], owned_paths=["src/jakal_flow"], status="running"),
                ],
            )
        )

        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertEqual(summary["status"], "running")
        self.assertEqual(summary["step_id"], "ST2, ST3")
        self.assertEqual(summary["title"], "Parallel batch: ST2, ST3")
        self.assertEqual(summary["summary"], "Frontend, Backend")

    def test_normalize_tunnel_target_url_rewrites_wildcard_host(self) -> None:
        self.assertEqual(
            normalize_tunnel_target_url("http://0.0.0.0:55180"),
            "http://127.0.0.1:55180",
        )
        self.assertEqual(
            normalize_tunnel_target_url("https://example.com/base"),
            "https://example.com/base",
        )

    def test_normalize_share_bind_host_migrates_legacy_localhost_default(self) -> None:
        self.assertEqual(normalize_share_bind_host("127.0.0.1"), "0.0.0.0")
        self.assertEqual(normalize_share_bind_host(""), "0.0.0.0")
        self.assertEqual(normalize_share_bind_host("0.0.0.0"), "0.0.0.0")

    def test_install_cloudflared_with_winget_uses_user_scope_and_returns_installed_binary(self) -> None:
        workspace_root = Path("C:/tmp/share-install-demo")
        expected_path = "C:/Users/demo/AppData/Local/Microsoft/WinGet/Links/cloudflared.exe"

        with mock.patch("jakal_flow.public_tunnel.os.name", "nt"), mock.patch(
            "jakal_flow.public_tunnel.resolve_winget_path",
            return_value="C:/Users/demo/AppData/Local/Microsoft/WindowsApps/winget.exe",
        ), mock.patch(
            "jakal_flow.public_tunnel.resolve_cloudflared_path",
            side_effect=[None, expected_path],
        ), mock.patch(
            "jakal_flow.public_tunnel.subprocess.run",
            return_value=mock.Mock(returncode=0, stdout="installed", stderr=""),
        ) as run_mock, mock.patch(
            "jakal_flow.public_tunnel.append_jsonl",
        ):
            resolved = install_cloudflared_with_winget(workspace_root)

        self.assertEqual(resolved, expected_path)
        command = run_mock.call_args.args[0]
        self.assertEqual(command[0], "C:/Users/demo/AppData/Local/Microsoft/WindowsApps/winget.exe")
        self.assertIn("--scope", command)
        self.assertIn("user", command)
        self.assertIn("--disable-interactivity", command)
        self.assertIn("Cloudflare.cloudflared", command)

    def test_ensure_cloudflared_path_auto_installs_on_windows_when_missing(self) -> None:
        workspace_root = Path("C:/tmp/share-install-demo")

        with mock.patch("jakal_flow.public_tunnel.resolve_cloudflared_path", return_value=None), mock.patch(
            "jakal_flow.public_tunnel.os.name",
            "nt",
        ), mock.patch(
            "jakal_flow.public_tunnel.install_cloudflared_with_winget",
            return_value="C:/Users/demo/AppData/Local/Microsoft/WinGet/Links/cloudflared.exe",
        ) as install_mock:
            resolved = ensure_cloudflared_path(workspace_root)

        self.assertTrue(resolved.endswith("cloudflared.exe"))
        install_mock.assert_called_once_with(workspace_root)

    @mock.patch("jakal_flow.share.os.name", "nt")
    @mock.patch("jakal_flow.subprocess_utils.subprocess.run")
    def test_process_is_running_handles_non_utf8_tasklist_output(self, run_mock: mock.Mock) -> None:
        run_mock.return_value = mock.Mock(stdout=b"\xc0\xfd\xbc\xd3 python.exe                 4321")

        self.assertTrue(process_is_running(4321))

    @mock.patch("jakal_flow.share.os.name", "nt")
    @mock.patch("jakal_flow.share.windows_process_is_running", return_value=True)
    @mock.patch("jakal_flow.subprocess_utils.subprocess.run")
    def test_process_is_running_falls_back_when_tasklist_access_is_denied(
        self,
        run_mock: mock.Mock,
        fallback_mock: mock.Mock,
    ) -> None:
        run_mock.return_value = mock.Mock(returncode=1, stdout=b"", stderr=b"ERROR: Access denied")

        self.assertTrue(process_is_running(4321))
        fallback_mock.assert_called_once_with(4321)

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

    def test_workspace_share_session_revokes_active_session_across_projects(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_one = temp_dir / "repo-one"
            repo_two = temp_dir / "repo-two"
            repo_one.mkdir(parents=True, exist_ok=True)
            repo_two.mkdir(parents=True, exist_ok=True)
            _orchestrator, project_one = create_project(workspace_root, repo_one)
            _orchestrator, project_two = create_project(workspace_root, repo_two)

            first = create_workspace_share_session(workspace_root, project_one, expires_in_minutes=60, created_by="test")
            second = create_workspace_share_session(workspace_root, project_two, expires_in_minutes=60, created_by="test")

            workspace_sessions = load_workspace_share_sessions(workspace_root)
            active = workspace_active_share_session(workspace_root)

            self.assertEqual(len(workspace_sessions), 2)
            self.assertIsNotNone(next(item for item in workspace_sessions if item.session_id == first.session_id).revoked_at)
            self.assertTrue(next(item for item in workspace_sessions if item.session_id == second.session_id).is_active())
            self.assertIsNotNone(active)
            assert active is not None
            self.assertEqual(active["session_id"], second.session_id)
            self.assertEqual(active["created_by"], "test")

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
            self.assertIn("run_control", status)
            self.assertIn("remote_control", status)
            self.assertNotIn("ghp_", json.dumps(status))
            self.assertNotIn("sk-testsecretvalue123456", json.dumps(status))
            self.assertNotIn("C:\\secret\\repo", json.dumps(status))
            self.assertNotIn("/Users/alice/project", json.dumps(status))
            self.assertNotIn("stdout_file", json.dumps(status))
            self.assertTrue(any("[masked]" in line or "[path]" in line for line in status["recent_logs"]))

    def test_public_workspace_monitor_status_lists_all_in_progress_projects(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_one = temp_dir / "repo-one"
            repo_two = temp_dir / "repo-two"
            repo_one.mkdir(parents=True, exist_ok=True)
            repo_two.mkdir(parents=True, exist_ok=True)
            orchestrator, project_one = create_project(workspace_root, repo_one)
            _orchestrator, project_two = create_project(workspace_root, repo_two)

            project_one.metadata.current_status = "running:st1"
            orchestrator.workspace.save_project(project_one)

            save_plan_payload = {
                "project_dir": str(repo_two),
                "display_name": "Share Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": project_two.runtime.to_dict(),
                "plan": {
                    "execution_mode": "parallel",
                    "workflow_mode": "standard",
                    "steps": [
                        {
                            "step_id": "ST1",
                            "title": "Resume me",
                            "display_description": "Resume the saved run.",
                            "codex_description": "Continue the remaining work for the saved plan.",
                            "test_command": "python -m pytest",
                            "success_criteria": "The saved plan can continue.",
                            "reasoning_effort": "high",
                            "depends_on": [],
                            "owned_paths": ["src/jakal_flow/share.py"],
                            "status": "pending",
                        }
                    ],
                },
            }
            with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: _fake_codex_snapshot()):
                run_command("save-plan", workspace_root, save_plan_payload)

            payload = public_workspace_monitor_status(workspace_root, orchestrator=Orchestrator(workspace_root))

            self.assertEqual(payload["workspace"]["project_count"], 2)
            self.assertEqual(payload["workspace"]["running_count"], 1)
            self.assertEqual(payload["workspace"]["resume_ready_count"], 1)
            self.assertEqual(len(payload["projects"]), 2)
            self.assertEqual(payload["projects"][0]["project"]["repo_id"], project_one.metadata.repo_id)
            self.assertIn(project_two.metadata.repo_id, [item["project"]["repo_id"] for item in payload["projects"]])

    def test_public_execution_flow_svg_masks_sensitive_step_text(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            orchestrator, project = create_project(workspace_root, repo_dir)
            save_plan_payload = {
                "project_dir": str(repo_dir),
                "display_name": "Share Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": project.runtime.to_dict(),
                "plan": {
                    "execution_mode": "parallel",
                    "workflow_mode": "standard",
                    "steps": [
                        {
                            "step_id": "ST1",
                            "title": "Use C:\\secret\\repo and token=ghp_abcdefghijklmnopqrstuvwxyz123456",
                            "display_description": "Touch /Users/alice/project/.env safely",
                            "codex_description": "internal",
                            "test_command": "python -m pytest",
                            "success_criteria": "done",
                            "reasoning_effort": "high",
                            "depends_on": [],
                            "owned_paths": ["src/jakal_flow/share.py"],
                            "status": "pending",
                        }
                    ],
                },
            }
            with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: _fake_codex_snapshot()):
                run_command("save-plan", workspace_root, save_plan_payload)
            project = Orchestrator(workspace_root).local_project(repo_dir)
            assert project is not None
            svg = public_execution_flow_svg(project, orchestrator.load_execution_plan_state(project))

            self.assertIn("<svg", svg)
            self.assertIn("ST1", svg)
            self.assertNotIn("ghp_", svg)
            self.assertNotIn("C:\\secret\\repo", svg)
            self.assertNotIn("/Users/alice/project", svg)
            self.assertTrue("[masked]" in svg or "[path]" in svg)

    def test_project_share_payload_reuses_server_status_for_multiple_sessions(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            _orchestrator, project = create_project(workspace_root, repo_dir)
            create_workspace_share_session(workspace_root, project, expires_in_minutes=60, created_by="test")
            create_workspace_share_session(workspace_root, project, expires_in_minutes=60, created_by="test")

            server_payload = {
                "viewer_path": "/share/view",
                "base_url": "http://127.0.0.1:8080",
                "host": "127.0.0.1",
                "share_base_url": "https://share.example.com/base",
            }

            with mock.patch("jakal_flow.share.share_server_status_payload", return_value=server_payload) as server_mock, mock.patch(
                "jakal_flow.share.load_share_server_state",
                return_value=None,
            ) as state_mock:
                payload = project_share_payload(workspace_root, project)

            self.assertEqual(server_mock.call_count, 1)
            self.assertEqual(state_mock.call_count, 1)
            self.assertEqual(len(payload["sessions"]), 2)
            self.assertEqual(payload["server"]["share_base_url"], "https://share.example.com/base")

    def test_project_share_payload_exposes_workspace_active_session_from_other_project(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_one = temp_dir / "repo-one"
            repo_two = temp_dir / "repo-two"
            repo_one.mkdir(parents=True, exist_ok=True)
            repo_two.mkdir(parents=True, exist_ok=True)
            _orchestrator, project_one = create_project(workspace_root, repo_one)
            _orchestrator, project_two = create_project(workspace_root, repo_two)

            create_workspace_share_session(workspace_root, project_two, expires_in_minutes=60, created_by="test")

            payload = project_share_payload(workspace_root, project_one)

            self.assertEqual(len(payload["sessions"]), 1)
            self.assertIsNone(payload["project_active_session"])
            self.assertIsNotNone(payload["active_session"])
            assert payload["active_session"] is not None
            self.assertEqual(payload["active_session"]["session_id"], payload["sessions"][0]["session_id"])

    def test_share_server_status_ignores_stale_tunnel_target(self) -> None:
        workspace_root = Path("C:/tmp/share-status-demo")
        state = ShareServerState(
            host="0.0.0.0",
            port=43123,
            pid=1234,
            started_at="2026-03-26T00:00:00+00:00",
        )
        tunnel_payload = {
            "running": True,
            "provider": "cloudflare-quick-tunnel",
            "public_url": "https://stale.trycloudflare.com",
            "target_url": "http://127.0.0.1:99999",
            "pid": 4242,
            "started_at": "2026-03-26T00:00:00+00:00",
            "available": True,
        }

        with mock.patch("jakal_flow.share.load_share_server_config", return_value=mock.Mock(public_base_url="", to_dict=lambda: {})), mock.patch(
            "jakal_flow.share.load_share_server_state",
            return_value=state,
        ), mock.patch("jakal_flow.share.process_is_running", return_value=True), mock.patch(
            "jakal_flow.public_tunnel.public_tunnel_status_payload",
            return_value=tunnel_payload,
        ):
            payload = share_server_status_payload(workspace_root)

        self.assertEqual(payload["share_base_url"], "http://0.0.0.0:43123")
        self.assertEqual(payload["share_base_url_source"], "local")

    def test_public_session_summary_ignores_stale_local_state_when_server_is_down(self) -> None:
        workspace_root = Path("C:/tmp/share-status-demo")
        session = ShareSession(
            session_id="demo-session",
            viewer_token="secret-token",
            created_at="2026-03-26T00:00:00+00:00",
            expires_at="2026-03-26T01:00:00+00:00",
            created_by="test",
        )
        stale_state = ShareServerState(
            host="0.0.0.0",
            port=43123,
            pid=4242,
            started_at="2026-03-26T00:00:00+00:00",
            viewer_path="/share/view",
        )

        payload = public_session_summary(
            workspace_root,
            None,
            session,
            include_token=True,
            server={
                "running": False,
                "host": "0.0.0.0",
                "port": None,
                "pid": None,
                "started_at": None,
                "base_url": None,
                "viewer_path": "/share/view",
                "share_base_url": None,
            },
            state=stale_state,
        )

        self.assertIsNone(payload["local_url"])
        self.assertIsNone(payload["share_url"])

    def test_public_session_summary_keeps_stable_access_link_across_session_regeneration(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            _orchestrator, project = create_project(workspace_root, repo_dir)

            first = create_workspace_share_session(workspace_root, project, expires_in_minutes=60, created_by="test")
            first_payload = public_session_summary(
                workspace_root,
                project,
                first,
                include_token=True,
                server={
                    "running": True,
                    "host": "0.0.0.0",
                    "port": 43123,
                    "pid": 4242,
                    "started_at": "2026-03-26T00:00:00+00:00",
                    "base_url": "http://0.0.0.0:43123",
                    "viewer_path": "/share/view",
                    "share_base_url": "https://share.example.com/base",
                },
                state=ShareServerState(
                    host="0.0.0.0",
                    port=43123,
                    pid=4242,
                    started_at="2026-03-26T00:00:00+00:00",
                    viewer_path="/share/view",
                ),
            )

            second = create_workspace_share_session(workspace_root, project, expires_in_minutes=60, created_by="test")
            second_payload = public_session_summary(
                workspace_root,
                project,
                second,
                include_token=True,
                server={
                    "running": True,
                    "host": "0.0.0.0",
                    "port": 43123,
                    "pid": 4242,
                    "started_at": "2026-03-26T00:00:00+00:00",
                    "base_url": "http://0.0.0.0:43123",
                    "viewer_path": "/share/view",
                    "share_base_url": "https://share.example.com/base",
                },
                state=ShareServerState(
                    host="0.0.0.0",
                    port=43123,
                    pid=4242,
                    started_at="2026-03-26T00:00:00+00:00",
                    viewer_path="/share/view",
                ),
            )

            self.assertNotEqual(first_payload["session_id"], second_payload["session_id"])
            self.assertEqual(first_payload["share_url"], second_payload["share_url"])
            self.assertEqual(first_payload["local_url"], second_payload["local_url"])
            self.assertIn("?access=", str(first_payload["share_url"]))
            self.assertEqual(first_payload["access_token"], second_payload["access_token"])

    def test_share_logs_api_builds_monitor_status_once(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            _orchestrator, project = create_project(workspace_root, repo_dir)
            session = create_share_session(project, expires_in_minutes=60, created_by="test")

            server = ShareHTTPServer(("127.0.0.1", 0), ShareRequestHandler, workspace_root=workspace_root)
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
            thread.start()
            try:
                monitor_payload = {
                    "project": {"display_name": "Share Demo", "slug": project.metadata.slug},
                    "overall_run_status": "setup_ready",
                    "current_phase": "setup_ready",
                    "current_block_index": 0,
                    "current_task": {"title": "", "step": None},
                    "latest_test_result": None,
                    "recent_logs": ["line-1", "line-2"],
                    "last_updated_at": "2026-03-26T10:00:00+00:00",
                }
                with mock.patch("jakal_flow.share_server.public_monitor_status", return_value=monitor_payload) as monitor_mock:
                    base_url = f"http://127.0.0.1:{server.server_address[1]}"
                    response = urllib.request.urlopen(
                        f"{base_url}/share/api/logs?session={session.session_id}&token={session.viewer_token}"
                    )
                    payload = json.loads(response.read().decode("utf-8"))

                self.assertEqual(monitor_mock.call_count, 1)
                self.assertEqual(payload["items"], ["line-1", "line-2"])
                self.assertEqual(payload["last_updated_at"], "2026-03-26T10:00:00+00:00")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_share_status_api_enforces_token_and_returns_read_only_shape(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            orchestrator, project = create_project(workspace_root, repo_dir)
            project.metadata.current_status = "running:st1"
            orchestrator.workspace.save_project(project)
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
                self.assertIn("workspace", payload)
                self.assertIn("projects", payload)
                self.assertEqual(payload["workspace"]["project_count"], 1)
                self.assertEqual(payload["projects"][0]["project"]["display_name"], "Share Demo")
                self.assertIn("overall_run_status", payload["projects"][0])
                self.assertIn("recent_logs", payload["projects"][0])
                self.assertIn("latest_test_result", payload["projects"][0])
                self.assertIn("run_control", payload["projects"][0])
                self.assertIn("remote_control", payload["projects"][0])
                self.assertNotIn("repo_path", json.dumps(payload))
                self.assertNotIn("project_root", json.dumps(payload))

                access_payload = public_session_summary(
                    workspace_root,
                    project,
                    session,
                    include_token=True,
                    server={
                        "running": True,
                        "host": "127.0.0.1",
                        "port": server.server_address[1],
                        "pid": 4242,
                        "started_at": "2026-03-26T00:00:00+00:00",
                        "base_url": base_url,
                        "viewer_path": "/share/view",
                        "share_base_url": base_url,
                    },
                    state=ShareServerState(
                        host="127.0.0.1",
                        port=server.server_address[1],
                        pid=4242,
                        started_at="2026-03-26T00:00:00+00:00",
                        viewer_path="/share/view",
                    ),
                )
                access_url = str(access_payload["share_url"])
                access_token = parse_qs(urlsplit(access_url).query).get("access", [""])[0]
                access_response = urllib.request.urlopen(f"{base_url}/share/api/status?access={access_token}")
                access_status_payload = json.loads(access_response.read().decode("utf-8"))
                self.assertEqual(access_status_payload["share_session"]["session_id"], session.session_id)

                with self.assertRaises(urllib.error.HTTPError) as unknown_session:
                    urllib.request.urlopen(
                        f"{base_url}/share/api/status?session=missing-session&token={session.viewer_token}"
                    )
                self.assertEqual(unknown_session.exception.code, 404)
                self.assertIn("Unknown share session.", unknown_session.exception.read().decode("utf-8"))

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

    def test_share_server_serves_translation_assets(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            server = ShareHTTPServer(("127.0.0.1", 0), ShareRequestHandler, workspace_root=workspace_root)
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
            thread.start()
            try:
                base_url = f"http://127.0.0.1:{server.server_address[1]}"
                generated = urllib.request.urlopen(f"{base_url}/share/generated_share_translations.js")
                generated_text = generated.read().decode("utf-8")
                self.assertIn("JakalFlowGeneratedShareTranslations", generated_text)

                manual = urllib.request.urlopen(f"{base_url}/share/manual_share_translations.js")
                manual_text = manual.read().decode("utf-8")
                self.assertIn("JakalFlowManualShareTranslations", manual_text)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_share_html_uses_view_relative_asset_paths(self) -> None:
        html = (Path(__file__).resolve().parents[1] / "website" / "share.html").read_text(encoding="utf-8")

        self.assertIn('href="share.css"', html)
        self.assertIn('src="generated_share_translations.js"', html)
        self.assertIn('src="manual_share_translations.js"', html)
        self.assertIn('src="share.js"', html)
        self.assertNotIn('href="/share/share.css"', html)
        self.assertNotIn('src="/share/share.js"', html)

    def test_share_script_uses_view_relative_api_paths(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "website" / "share.js").read_text(encoding="utf-8")

        self.assertIn('pathname.endsWith("/share/view")', script)
        self.assertIn('shareEndpoint("api/status")', script)
        self.assertIn('shareEndpoint("api/events")', script)
        self.assertIn('shareEndpoint("api/flow.svg")', script)
        self.assertIn('shareEndpoint("api/control")', script)
        self.assertIn('builtInEnglishShareTranslations', script)
        self.assertIn('language === "en" ? builtInEnglishShareTranslations : {}', script)
        self.assertIn("shareErrorDescriptor", script)
        self.assertIn("share_link_not_found_title", script)
        self.assertIn("share_link_expired_title", script)
        self.assertIn("share_link_revoked_title", script)
        self.assertIn("share_link_invalid_title", script)
        self.assertIn('const access = queryValue("access")', script)
        self.assertIn('applyShareCredentials(url, credentials)', script)
        self.assertIn("await reconcileStatus()", script)
        self.assertNotIn('new URL("/share/api/status", window.location.origin)', script)
        self.assertNotIn('new URL("/share/api/events", window.location.origin)', script)

    def test_share_events_api_streams_live_status_payload(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            orchestrator, project = create_project(workspace_root, repo_dir)
            project.metadata.current_status = "running:st1"
            orchestrator.workspace.save_project(project)
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
                self.assertEqual(payload["workspace"]["project_count"], 1)
                self.assertEqual(payload["projects"][0]["project"]["display_name"], "Share Demo")
                self.assertIn("recent_logs", payload["projects"][0])
                self.assertIn("latest_test_result", payload["projects"][0])
                self.assertIn("remote_control", payload["projects"][0])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_share_flow_svg_api_serves_masked_svg(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            orchestrator, project = create_project(workspace_root, repo_dir)
            save_plan_payload = {
                "project_dir": str(repo_dir),
                "display_name": "Share Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": project.runtime.to_dict(),
                "plan": {
                    "execution_mode": "parallel",
                    "workflow_mode": "standard",
                    "steps": [
                        {
                            "step_id": "ST1",
                            "title": "Flow path C:\\secret\\repo",
                            "display_description": "Inspect /Users/alice/project/.env",
                            "codex_description": "internal",
                            "test_command": "python -m pytest",
                            "success_criteria": "done",
                            "reasoning_effort": "high",
                            "depends_on": [],
                            "owned_paths": ["src/jakal_flow/share_server.py"],
                            "status": "pending",
                        }
                    ],
                },
            }
            with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: _fake_codex_snapshot()):
                run_command("save-plan", workspace_root, save_plan_payload)
            project = Orchestrator(workspace_root).local_project(repo_dir)
            assert project is not None
            session = create_share_session(project, expires_in_minutes=60, created_by="test")

            server = ShareHTTPServer(("127.0.0.1", 0), ShareRequestHandler, workspace_root=workspace_root)
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
            thread.start()
            try:
                base_url = f"http://127.0.0.1:{server.server_address[1]}"
                response = urllib.request.urlopen(
                    f"{base_url}/share/api/flow.svg?session={session.session_id}&token={session.viewer_token}"
                )
                svg = response.read().decode("utf-8")

                self.assertIn("image/svg+xml", response.headers.get("Content-Type", ""))
                self.assertIn("<svg", svg)
                self.assertIn("ST1", svg)
                self.assertNotIn("C:\\secret\\repo", svg)
                self.assertNotIn("/Users/alice/project", svg)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_share_control_api_requests_pause_after_current_step(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            orchestrator, project = create_project(workspace_root, repo_dir)
            project.metadata.current_status = "running:st1"
            orchestrator.workspace.save_project(project)
            session = create_share_session(project, expires_in_minutes=60, created_by="test")

            server = ShareHTTPServer(("127.0.0.1", 0), ShareRequestHandler, workspace_root=workspace_root)
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
            thread.start()
            try:
                base_url = f"http://127.0.0.1:{server.server_address[1]}"
                request = urllib.request.Request(
                    f"{base_url}/share/api/control?session={session.session_id}&token={session.viewer_token}",
                    data=json.dumps({"action": "pause", "repo_id": project.metadata.repo_id}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                response = urllib.request.urlopen(request)
                payload = json.loads(response.read().decode("utf-8"))

                self.assertEqual(payload["control_result"]["action"], "pause")
                self.assertEqual(payload["control_result"]["repo_id"], project.metadata.repo_id)
                monitored = next(item for item in payload["projects"] if item["project"]["repo_id"] == project.metadata.repo_id)
                self.assertTrue(monitored["run_control"]["stop_after_current_step"])
                self.assertTrue(monitored["remote_control"]["pause_requested"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_share_control_api_queues_resume_job(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            _orchestrator, project = create_project(workspace_root, repo_dir)
            save_plan_payload = {
                "project_dir": str(repo_dir),
                "display_name": "Share Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": project.runtime.to_dict(),
                "plan": {
                    "execution_mode": "parallel",
                    "workflow_mode": "standard",
                    "steps": [
                        {
                            "step_id": "ST1",
                            "title": "Resume me",
                            "display_description": "Resume the saved run.",
                            "codex_description": "Continue the remaining work for the saved plan.",
                            "test_command": "python -m pytest",
                            "success_criteria": "The saved plan can continue.",
                            "reasoning_effort": "high",
                            "depends_on": [],
                            "owned_paths": ["src/jakal_flow/share_server.py"],
                            "status": "pending",
                        }
                    ],
                },
            }
            with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: _fake_codex_snapshot()):
                run_command("save-plan", workspace_root, save_plan_payload)
            project = Orchestrator(workspace_root).local_project(repo_dir)
            assert project is not None
            session = create_share_session(project, expires_in_minutes=60, created_by="test")

            server = ShareHTTPServer(("127.0.0.1", 0), ShareRequestHandler, workspace_root=workspace_root)
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
            thread.start()
            called = threading.Event()
            release = threading.Event()
            captured: dict[str, object] = {}

            def fake_run(command: str, actual_workspace_root: Path, payload: dict[str, object]) -> dict[str, object]:
                captured["command"] = command
                captured["workspace_root"] = actual_workspace_root
                captured["payload"] = payload
                called.set()
                release.wait(timeout=2)
                return {}

            try:
                with mock.patch("jakal_flow.share_server.run_command", side_effect=fake_run):
                    base_url = f"http://127.0.0.1:{server.server_address[1]}"
                    request = urllib.request.Request(
                        f"{base_url}/share/api/control?session={session.session_id}&token={session.viewer_token}",
                        data=json.dumps({"action": "resume", "repo_id": project.metadata.repo_id}).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    response = urllib.request.urlopen(request)
                    payload = json.loads(response.read().decode("utf-8"))

                self.assertTrue(called.wait(timeout=2))
                self.assertEqual(captured["command"], "run-plan")
                self.assertEqual(captured["workspace_root"], workspace_root)
                self.assertEqual(captured["payload"]["project_dir"], str(repo_dir))
                self.assertEqual(payload["control_result"]["action"], "resume")
                self.assertTrue(payload["control_result"]["queued"])
                monitored = next(item for item in payload["projects"] if item["project"]["repo_id"] == project.metadata.repo_id)
                self.assertTrue(monitored["remote_control"]["resume_starting"])
            finally:
                release.set()
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_share_control_api_rejects_resume_when_workspace_scheduler_is_busy(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            other_repo_dir = temp_dir / "other-repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            other_repo_dir.mkdir(parents=True, exist_ok=True)
            _orchestrator, project = create_project(workspace_root, repo_dir)
            save_plan_payload = {
                "project_dir": str(repo_dir),
                "display_name": "Share Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": project.runtime.to_dict(),
                "plan": {
                    "execution_mode": "parallel",
                    "workflow_mode": "standard",
                    "steps": [
                        {
                            "step_id": "ST1",
                            "title": "Resume me",
                            "display_description": "Resume the saved run.",
                            "codex_description": "Continue the remaining work for the saved plan.",
                            "test_command": "python -m pytest",
                            "success_criteria": "The saved plan can continue.",
                            "reasoning_effort": "high",
                            "depends_on": [],
                            "owned_paths": ["src/jakal_flow/share_server.py"],
                            "status": "pending",
                        }
                    ],
                },
            }
            with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: _fake_codex_snapshot()):
                run_command("save-plan", workspace_root, save_plan_payload)
            project = Orchestrator(workspace_root).local_project(repo_dir)
            assert project is not None
            session = create_share_session(project, expires_in_minutes=60, created_by="test")
            write_scheduler_state(
                workspace_root,
                max_concurrent_jobs=1,
                jobs=[
                    {
                        "id": "job-other",
                        "command": "run-plan",
                        "status": "running",
                        "repo_id": "repo-other",
                        "project_dir": str(other_repo_dir),
                        "workspace_root": str(workspace_root),
                        "job_lane": "execution",
                    }
                ],
            )

            server = ShareHTTPServer(("127.0.0.1", 0), ShareRequestHandler, workspace_root=workspace_root)
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
            thread.start()
            try:
                base_url = f"http://127.0.0.1:{server.server_address[1]}"
                request = urllib.request.Request(
                    f"{base_url}/share/api/control?session={session.session_id}&token={session.viewer_token}",
                    data=json.dumps({"action": "resume", "repo_id": project.metadata.repo_id}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with mock.patch("jakal_flow.share_server.run_command") as mocked_run:
                    with self.assertRaises(urllib.error.HTTPError) as error_context:
                        urllib.request.urlopen(request)

                self.assertEqual(error_context.exception.code, 409)
                payload = json.loads(error_context.exception.read().decode("utf-8"))
                self.assertIn("wait for a free slot", payload.get("error", ""))
                mocked_run.assert_not_called()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_remote_resume_rejects_disconnected_local_project(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            orchestrator, project = create_project(workspace_root, repo_dir)
            save_plan_payload = {
                "project_dir": str(repo_dir),
                "display_name": "Share Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": project.runtime.to_dict(),
                "plan": {
                    "execution_mode": "parallel",
                    "workflow_mode": "standard",
                    "steps": [
                        {
                            "step_id": "ST1",
                            "title": "Resume me",
                            "display_description": "Resume the saved run.",
                            "codex_description": "Continue the saved run.",
                            "test_command": "python -m pytest",
                            "success_criteria": "The saved plan can continue.",
                            "reasoning_effort": "high",
                            "depends_on": [],
                            "owned_paths": ["src/jakal_flow/share_server.py"],
                            "status": "pending",
                        }
                    ],
                },
            }
            with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: _fake_codex_snapshot()):
                run_command("save-plan", workspace_root, save_plan_payload)

            stale_repo = temp_dir / "missing-repo"
            metadata_path = project.paths.project_root / "metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["repo_path"] = str(stale_repo)
            metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
            registry = json.loads(orchestrator.workspace.registry_file.read_text(encoding="utf-8"))
            registry["projects"][project.metadata.repo_id]["repo_path"] = str(stale_repo)
            orchestrator.workspace.registry_file.write_text(json.dumps(registry, indent=2, sort_keys=True), encoding="utf-8")
            disconnected = Orchestrator(workspace_root).workspace.load_project_by_id(project.metadata.repo_id)

            manager = ShareRemoteControlManager(workspace_root)

            with self.assertRaisesRegex(RuntimeError, "repository is not accessible"):
                manager.queue_resume(disconnected, Orchestrator(workspace_root))

            recent_events = [item for item in read_jsonl_tail(disconnected.paths.ui_event_log_file, 8) if isinstance(item, dict)]
            self.assertTrue(recent_events)
            self.assertEqual(recent_events[-1]["event_type"], "remote-resume-rejected")

    def test_share_status_api_returns_429_when_rate_limited(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            _orchestrator, project = create_project(workspace_root, repo_dir)
            session = create_share_session(project, expires_in_minutes=60, created_by="test")

            server = ShareHTTPServer(("127.0.0.1", 0), ShareRequestHandler, workspace_root=workspace_root)
            server.request_rate_limit_rules["/share/api/status"] = TokenBucketRule(
                capacity=1.0,
                refill_tokens_per_second=0.0,
            )
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
            thread.start()
            try:
                base_url = f"http://127.0.0.1:{server.server_address[1]}"
                status_url = f"{base_url}/share/api/status?session={session.session_id}&token={session.viewer_token}"

                first = urllib.request.urlopen(status_url)
                self.assertEqual(first.status, 200)

                with self.assertRaises(urllib.error.HTTPError) as limited:
                    urllib.request.urlopen(status_url)

                self.assertEqual(limited.exception.code, 429)
                self.assertEqual(limited.exception.headers.get("Retry-After"), "1")
                self.assertIn("Too many requests", limited.exception.read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
