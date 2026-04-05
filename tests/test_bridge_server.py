from __future__ import annotations

from pathlib import Path
import shutil
import io
import json
import sys
import unittest
from unittest import mock
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jakal_flow.bridge_server import BridgeServer


def local_temp_root() -> Path:
    root = Path(__file__).resolve().parents[1] / ".tub"
    root.mkdir(parents=True, exist_ok=True)
    return root


class TemporaryTestDir:
    def __enter__(self) -> Path:
        self.path = local_temp_root() / f"bridge-{uuid.uuid4().hex[:8]}"
        self.path.mkdir(parents=True, exist_ok=True)
        return self.path

    def __exit__(self, exc_type, exc, tb) -> None:
        shutil.rmtree(self.path, ignore_errors=True)


class CaptureBridgeServer(BridgeServer):
    def __init__(self) -> None:
        self.envelopes: list[dict] = []
        super().__init__()

    def _send_envelope(self, envelope) -> None:
        self.envelopes.append(envelope.to_dict())


class BridgeServerTests(unittest.TestCase):
    def test_chat_conversation_job_can_run_alongside_execution_job_for_same_project(self) -> None:
        with TemporaryTestDir() as workspace_root:
            workspace_root.mkdir(parents=True, exist_ok=True)
            repo_dir = workspace_root / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            server = CaptureBridgeServer()

            run_snapshot = server._jobs.create(
                "run-plan",
                workspace_root,
                {"project_dir": str(repo_dir)},
            )
            chat_snapshot = server._jobs.create(
                "send-chat-message",
                workspace_root,
                {"project_dir": str(repo_dir), "chat_mode": "conversation"},
            )

            self.assertEqual(run_snapshot.job_lane, "execution")
            self.assertEqual(chat_snapshot.job_lane, "chat")
            self.assertEqual(chat_snapshot.chat_mode, "conversation")

    def test_chat_conversation_job_still_rejects_duplicate_chat_lane_for_same_project(self) -> None:
        with TemporaryTestDir() as workspace_root:
            workspace_root.mkdir(parents=True, exist_ok=True)
            repo_dir = workspace_root / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            server = CaptureBridgeServer()

            server._jobs.create(
                "send-chat-message",
                workspace_root,
                {"project_dir": str(repo_dir), "chat_mode": "review"},
            )

            with self.assertRaisesRegex(RuntimeError, "already active for this project"):
                server._jobs.create(
                    "send-chat-message",
                    workspace_root,
                    {"project_dir": str(repo_dir), "chat_mode": "conversation"},
                )

    def test_chat_debugger_job_stays_in_execution_lane_and_conflicts_with_execution_job(self) -> None:
        with TemporaryTestDir() as workspace_root:
            workspace_root.mkdir(parents=True, exist_ok=True)
            repo_dir = workspace_root / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            server = CaptureBridgeServer()

            server._jobs.create(
                "run-plan",
                workspace_root,
                {"project_dir": str(repo_dir)},
            )

            with self.assertRaisesRegex(RuntimeError, "already active for this project"):
                server._jobs.create(
                    "send-chat-message",
                    workspace_root,
                    {"project_dir": str(repo_dir), "chat_mode": "debugger"},
                )

    def test_bridge_request_skips_project_changed_event_when_result_disables_it(self) -> None:
        with TemporaryTestDir() as workspace_root:
            server = CaptureBridgeServer()

            with mock.patch(
                "jakal_flow.bridge_server.run_command",
                return_value={"chat": {"messages": []}, "emit_project_changed": False},
            ):
                server._handle_request(
                    "req-1",
                    "bridge_request",
                    {
                        "command": "load-project-chat",
                        "workspace_root": str(workspace_root),
                        "payload": {},
                    },
                )

            response_events = [item for item in server.envelopes if item.get("kind") == "response"]
            project_events = [item for item in server.envelopes if item.get("event") == "project.changed"]
            self.assertEqual(len(response_events), 1)
            self.assertEqual(project_events, [])

    def test_background_job_skips_project_changed_event_when_result_disables_it(self) -> None:
        with TemporaryTestDir() as workspace_root:
            workspace_root.mkdir(parents=True, exist_ok=True)
            repo_dir = workspace_root / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            server = CaptureBridgeServer()

            snapshot = server._jobs.create(
                "send-chat-message",
                workspace_root,
                {"project_dir": str(repo_dir)},
            )
            server.envelopes.clear()

            with mock.patch(
                "jakal_flow.bridge_server.run_command",
                return_value={"chat": {"messages": []}, "emit_project_changed": False},
            ):
                server._run_job(
                    snapshot.id,
                    "send-chat-message",
                    workspace_root,
                    {"project_dir": str(repo_dir)},
                )

            project_events = [item for item in server.envelopes if item.get("event") == "project.changed"]
            job_updates = [item for item in server.envelopes if item.get("event") == "job.updated"]
            self.assertEqual(project_events, [])
            self.assertTrue(job_updates)
            self.assertEqual(job_updates[-1]["payload"]["job"]["status"], "completed")

    def test_handle_request_returns_structured_error_payload_for_invalid_request(self) -> None:
        with TemporaryTestDir() as workspace_root:
            workspace_root.mkdir(parents=True, exist_ok=True)
            server = CaptureBridgeServer()
            with mock.patch(
                "jakal_flow.bridge_server.run_command",
                side_effect=ValueError("Invalid payload"),
            ):
                server._handle_request(
                    "req-1",
                    "bridge_request",
                    {
                        "command": "load-project",
                        "workspace_root": str(workspace_root),
                        "payload": {},
                    },
                )

            responses = [item for item in server.envelopes if item.get("kind") == "response"]
            self.assertTrue(responses)
            last_response = responses[-1]
            self.assertFalse(bool(last_response.get("ok")))
            self.assertIsInstance(last_response.get("error"), dict)
            self.assertEqual(last_response["error"].get("reason_code"), "invalid_request")
            self.assertEqual(last_response["error"].get("command"), "load-project")
            self.assertEqual(last_response["error"].get("method"), "bridge_request")
            self.assertEqual(last_response["error"].get("request_id"), "req-1")

    def test_handle_request_returns_structured_error_for_unsupported_method(self) -> None:
        with TemporaryTestDir() as workspace_root:
            workspace_root.mkdir(parents=True, exist_ok=True)
            server = CaptureBridgeServer()
            server._handle_request(
                "req-2",
                "unsupported_bridge_method",
                {"command": "load-project", "workspace_root": str(workspace_root), "payload": {}},
            )

            responses = [item for item in server.envelopes if item.get("kind") == "response"]
            self.assertTrue(responses)
            last_error = responses[-1]["error"]
            self.assertEqual(last_error.get("reason_code"), "unsupported_method")
            self.assertEqual(last_error.get("message"), "Unsupported bridge method: unsupported_bridge_method")

    def test_serve_forever_treats_invalid_json_as_structured_error(self) -> None:
        server = CaptureBridgeServer()
        with mock.patch("sys.stdin", io.StringIO("not-json\n")):
            with mock.patch.object(server, "_error_response") as error_response:
                server.serve_forever()

        error_response.assert_called_once()
        args, _ = error_response.call_args
        self.assertEqual(args[0], "")
        self.assertIsInstance(args[1], ValueError)
        self.assertTrue(str(args[1]).strip())

    def test_serve_forever_rejects_request_without_id(self) -> None:
        with TemporaryTestDir() as workspace_root:
            workspace_root.mkdir(parents=True, exist_ok=True)
            server = CaptureBridgeServer()
            payload = json.dumps(
                {
                "method": "bridge_request",
                "params": {
                    "command": "bootstrap",
                    "workspace_root": str(workspace_root),
                    "payload": {},
                },
                },
            )
            with mock.patch("sys.stdin", io.StringIO(f"{payload}\n")):
                with mock.patch.object(server, "_error_response") as error_response:
                    server.serve_forever()

            error_response.assert_called_once()
            args, kwargs = error_response.call_args
            self.assertEqual(args[0], "")
            self.assertIsInstance(args[1], ValueError)
            self.assertEqual(str(args[1]), "Bridge request id is required.")
            self.assertEqual(kwargs["method"], "bridge_request")
            self.assertEqual(kwargs["command"], "bootstrap")

    def test_serve_forever_rejects_request_with_non_dict_params(self) -> None:
        server = CaptureBridgeServer()
        payload = json.dumps(
            {
                "id": "req-bridge-params-invalid",
                "method": "bridge_request",
                "params": [],
            }
        )
        with mock.patch("sys.stdin", io.StringIO(f"{payload}\n")):
            with mock.patch.object(server, "_error_response") as error_response:
                server.serve_forever()

            error_response.assert_called_once()
            args, kwargs = error_response.call_args
            self.assertEqual(args[0], "req-bridge-params-invalid")
            self.assertIsInstance(args[1], ValueError)
            self.assertEqual(str(args[1]), "Bridge params must be a JSON object.")
            self.assertEqual(kwargs["method"], "bridge_request")

    def test_scheduler_limit_is_scoped_per_workspace(self) -> None:
        with TemporaryTestDir() as workspace_one, TemporaryTestDir() as workspace_two:
            repo_one_a = workspace_one / "repo-one-a"
            repo_one_b = workspace_one / "repo-one-b"
            repo_two = workspace_two / "repo-two"
            repo_one_a.mkdir(parents=True, exist_ok=True)
            repo_one_b.mkdir(parents=True, exist_ok=True)
            repo_two.mkdir(parents=True, exist_ok=True)
            server = CaptureBridgeServer()

            snapshot, _promoted = server._jobs.set_max_running_jobs(workspace_one, 1)

            self.assertEqual(snapshot["max_concurrent_jobs"], 1)
            self.assertEqual(server._jobs.scheduler_snapshot(workspace_two)["max_concurrent_jobs"], 2)

            server._jobs.create(
                "run-plan",
                workspace_one,
                {"project_dir": str(repo_one_a), "runtime": {"allow_background_queue": False}},
            )
            with self.assertRaisesRegex(RuntimeError, "wait for a free slot"):
                server._jobs.create(
                    "run-plan",
                    workspace_one,
                    {"project_dir": str(repo_one_b), "runtime": {"allow_background_queue": False}},
                )

            other_workspace_job = server._jobs.create(
                "run-plan",
                workspace_two,
                {"project_dir": str(repo_two), "runtime": {"allow_background_queue": False}},
            )
            self.assertEqual(other_workspace_job.status, "running")

    def test_start_job_returns_duplicate_job_reason_code(self) -> None:
        with TemporaryTestDir() as workspace_root:
            workspace_root.mkdir(parents=True, exist_ok=True)
            repo_dir = workspace_root / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            server = CaptureBridgeServer()

            server._jobs.create(
                "run-plan",
                workspace_root,
                {"project_dir": str(repo_dir)},
            )
            server._handle_request(
                "req-dup",
                "start_job",
                {
                    "command": "run-plan",
                    "workspace_root": str(workspace_root),
                    "payload": {"project_dir": str(repo_dir)},
                },
            )

            responses = [item for item in server.envelopes if item.get("kind") == "response"]
            self.assertTrue(responses)
            last_response = responses[-1]
            self.assertFalse(bool(last_response.get("ok")))
            self.assertEqual(last_response["error"].get("reason_code"), "duplicate_job")

    def test_bridge_request_overlays_active_execution_job_into_listing_payload(self) -> None:
        with TemporaryTestDir() as workspace_root:
            workspace_root.mkdir(parents=True, exist_ok=True)
            repo_dir = workspace_root / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            server = CaptureBridgeServer()
            server._jobs.create(
                "run-plan",
                workspace_root,
                {"repo_id": "repo-1", "project_dir": str(repo_dir)},
            )

            with mock.patch(
                "jakal_flow.bridge_server.run_command",
                return_value={
                    "projects": [
                        {
                            "repo_id": "repo-1",
                            "repo_path": str(repo_dir),
                            "status": "plan_ready",
                        }
                    ],
                    "history": [],
                    "workspace": {
                        "project_count": 1,
                        "ready_like": 1,
                        "running": 0,
                        "failed": 0,
                    },
                },
            ):
                server._handle_request(
                    "req-listing",
                    "bridge_request",
                    {
                        "command": "list-projects",
                        "workspace_root": str(workspace_root),
                        "payload": {},
                    },
                )

            responses = [item for item in server.envelopes if item.get("kind") == "response"]
            self.assertTrue(responses)
            result = responses[-1]["result"]
            self.assertEqual(result["projects"][0]["status"], "running:run-plan")
            self.assertEqual(result["workspace"]["running"], 1)

    def test_bridge_request_overlays_active_execution_job_into_detail_execution_state(self) -> None:
        with TemporaryTestDir() as workspace_root:
            workspace_root.mkdir(parents=True, exist_ok=True)
            repo_dir = workspace_root / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            server = CaptureBridgeServer()
            server._jobs.create(
                "run-plan",
                workspace_root,
                {"repo_id": "repo-1", "project_dir": str(repo_dir)},
            )

            with mock.patch(
                "jakal_flow.bridge_server.run_command",
                return_value={
                    "project": {
                        "repo_id": "repo-1",
                        "repo_path": str(repo_dir),
                        "current_status": "plan_ready",
                    },
                    "loop_state": {
                        "pending_checkpoint_approval": False,
                    },
                    "checkpoints": {
                        "items": [],
                        "pending": None,
                    },
                    "execution_processes": [],
                    "execution_state": {
                        "display_family": "idle",
                        "display_status": "plan_ready",
                        "project_status": "plan_ready",
                        "consistent": True,
                        "active_families": [],
                        "checkpoint_family": "idle",
                        "flow_family": "idle",
                        "process_family": "idle",
                        "toolbar_family": "idle",
                        "mismatch_summary": "",
                        "report_lines": [],
                    },
                    "snapshot": {
                        "project": {
                            "current_status": "plan_ready",
                        },
                    },
                    "bottom_panels": {
                        "git_status": {
                            "current_status": "plan_ready",
                        },
                    },
                },
            ):
                server._handle_request(
                    "req-detail",
                    "bridge_request",
                    {
                        "command": "load-project",
                        "workspace_root": str(workspace_root),
                        "payload": {
                            "repo_id": "repo-1",
                        },
                    },
                )

            responses = [item for item in server.envelopes if item.get("kind") == "response"]
            self.assertTrue(responses)
            result = responses[-1]["result"]
            self.assertEqual(result["project"]["current_status"], "running:run-plan")
            self.assertEqual(result["snapshot"]["project"]["current_status"], "running:run-plan")
            self.assertEqual(result["bottom_panels"]["git_status"]["current_status"], "running:run-plan")
            self.assertEqual(result["execution_state"]["project_status"], "running:run-plan")
            self.assertEqual(result["execution_state"]["display_status"], "running:run-plan")

    def test_bridge_request_emits_project_changed_with_repo_hint_for_disconnected_project(self) -> None:
        with TemporaryTestDir() as workspace_root:
            workspace_root.mkdir(parents=True, exist_ok=True)
            server = CaptureBridgeServer()

            with mock.patch(
                "jakal_flow.bridge_server.run_command",
                return_value={
                    "project": {
                        "repo_id": "repo-1",
                        "repo_path": "",
                        "repo_path_hint": "C:/stale-repo",
                        "repo_available": False,
                        "repo_binding": "missing",
                        "project_root_relative": "projects/repo-1",
                        "current_status": "plan_ready",
                    },
                },
            ):
                server._handle_request(
                    "req-save-plan",
                    "bridge_request",
                    {
                        "command": "save-plan",
                        "workspace_root": str(workspace_root),
                        "payload": {
                            "repo_id": "repo-1",
                            "project_dir": "C:/stale-repo",
                        },
                    },
                )

            project_events = [item for item in server.envelopes if item.get("event") == "project.changed"]
            self.assertEqual(len(project_events), 1)
            project = project_events[0]["payload"]["project"]
            self.assertEqual(project["repo_id"], "repo-1")
            self.assertEqual(project["project_dir"], "")
            self.assertEqual(project["project_dir_hint"], "C:/stale-repo")
            self.assertFalse(project["repo_available"])
            self.assertEqual(project["repo_binding"], "missing")
            self.assertEqual(project["project_root_relative"], "projects/repo-1")

    def test_bridge_request_uses_request_path_as_hint_only_when_result_has_no_project_payload(self) -> None:
        with TemporaryTestDir() as workspace_root:
            workspace_root.mkdir(parents=True, exist_ok=True)
            server = CaptureBridgeServer()

            with mock.patch(
                "jakal_flow.bridge_server.run_command",
                return_value={"run_control": {"stop_after_current_step": True}},
            ):
                server._handle_request(
                    "req-stop",
                    "bridge_request",
                    {
                        "command": "request-stop",
                        "workspace_root": str(workspace_root),
                        "payload": {
                            "repo_id": "repo-1",
                            "project_dir": "C:/repo",
                        },
                    },
                )

            project_events = [item for item in server.envelopes if item.get("event") == "project.changed"]
            self.assertEqual(len(project_events), 1)
            project = project_events[0]["payload"]["project"]
            self.assertEqual(project["repo_id"], "repo-1")
            self.assertNotIn("project_dir", project)
            self.assertEqual(project["project_dir_hint"], "C:/repo")
