from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import unittest
from unittest import mock
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jakal_flow.models import ExecutionPlanState, ExecutionStep
from jakal_flow.ui_bridge import progress_caption, run_command, runtime_from_payload


def local_temp_root() -> Path:
    root = Path(__file__).resolve().parents[1] / ".tmp_ui_bridge_tests"
    root.mkdir(parents=True, exist_ok=True)
    return root


class TemporaryTestDir:
    def __enter__(self) -> Path:
        self.path = local_temp_root() / f"case_{uuid.uuid4().hex}"
        self.path.mkdir(parents=True, exist_ok=True)
        return self.path

    def __exit__(self, exc_type, exc, tb) -> None:
        shutil.rmtree(self.path, ignore_errors=True)


def fake_codex_snapshot() -> mock.Mock:
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
            },
            {
                "id": "gpt-5.3-codex-spark",
                "model": "gpt-5.3-codex-spark",
                "display_name": "GPT-5.3-Codex-Spark",
                "description": "Ultra-fast coding model.",
                "hidden": False,
                "is_default": False,
                "default_reasoning_effort": "high",
                "supported_reasoning_efforts": ["low", "medium", "high", "xhigh"],
            },
        ],
        "account": {
            "authenticated": True,
            "requires_openai_auth": True,
            "type": "chatgpt",
            "email": "demo@example.com",
            "plan_type": "pro",
        },
        "rate_limits": {
            "default_limit_id": "codex",
            "items": [
                {
                    "limit_id": "codex",
                    "limit_name": None,
                    "plan_type": "pro",
                    "primary": {
                        "used_percent": 11,
                        "remaining_percent": 89,
                        "window_duration_mins": 300,
                        "resets_at": "2026-03-26T12:00:00+00:00",
                    },
                    "secondary": None,
                    "credits": None,
                }
            ],
        },
        "error": "",
    }
    return mock.Mock(model_catalog=payload["model_catalog"], to_dict=mock.Mock(return_value=payload))


class UIBridgeTests(unittest.TestCase):
    def test_progress_caption_reports_ready_nodes_for_parallel_dag(self) -> None:
        caption = progress_caption(
            ExecutionPlanState(
                execution_mode="parallel",
                steps=[
                    ExecutionStep(step_id="ST1", title="Root", status="completed"),
                    ExecutionStep(step_id="ST2", title="Frontend", depends_on=["ST1"], owned_paths=["desktop/src"]),
                    ExecutionStep(step_id="ST3", title="Backend", depends_on=["ST1"], owned_paths=["src/jakal_flow"]),
                    ExecutionStep(step_id="ST4", title="Closeout", depends_on=["ST2", "ST3"], owned_paths=["docs"]),
                ],
            )
        )

        self.assertEqual(caption, "Completed 1/4 steps, ready: ST2, ST3")

    def test_runtime_from_payload_coerces_invalid_scalar_values(self) -> None:
        runtime = runtime_from_payload(
            {
                "model": "gpt-5.4-mini",
                "model_preset": "missing",
                "max_blocks": "not-a-number",
                "allow_push": "false",
                "require_checkpoint_approval": "true",
                "execution_mode": "PARALLEL",
                "parallel_workers": "bogus",
                "no_progress_limit": "-3",
                "regression_limit": "bogus",
                "empty_cycle_limit": 0,
                "checkpoint_interval_blocks": "0",
            }
        )

        self.assertEqual(runtime.model, "gpt-5.4-mini")
        self.assertEqual(runtime.model_preset, "")
        self.assertEqual(runtime.max_blocks, 5)
        self.assertFalse(runtime.allow_push)
        self.assertTrue(runtime.require_checkpoint_approval)
        self.assertEqual(runtime.execution_mode, "parallel")
        self.assertEqual(runtime.parallel_workers, 2)
        self.assertEqual(runtime.no_progress_limit, 1)
        self.assertEqual(runtime.regression_limit, 3)
        self.assertEqual(runtime.empty_cycle_limit, 1)
        self.assertEqual(runtime.checkpoint_interval_blocks, 1)

    def test_runtime_from_payload_normalizes_legacy_auto_model_presets(self) -> None:
        runtime = runtime_from_payload(
            {
                "model": "auto",
                "model_preset": "auto-high",
                "effort": "medium",
            }
        )

        self.assertEqual(runtime.model, "auto")
        self.assertEqual(runtime.model_preset, "high")
        self.assertEqual(runtime.effort, "high")

    def test_runtime_from_payload_coerces_fast_mode_flag(self) -> None:
        runtime = runtime_from_payload(
            {
                "model": "gpt-5.4",
                "use_fast_mode": "true",
            }
        )

        self.assertEqual(runtime.model, "gpt-5.4")
        self.assertTrue(runtime.use_fast_mode)

    def test_runtime_from_payload_coerces_word_report_flag(self) -> None:
        runtime = runtime_from_payload(
            {
                "model": "gpt-5.4",
                "generate_word_report": "true",
            }
        )

        self.assertEqual(runtime.model, "gpt-5.4")
        self.assertTrue(runtime.generate_word_report)

    def test_bootstrap_exposes_workspace_and_model_presets(self) -> None:
        with TemporaryTestDir() as temp_dir:
            with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: fake_codex_snapshot()):
                payload = run_command("bootstrap", temp_dir)

        self.assertEqual(payload["workspace_root"], str(temp_dir.resolve()))
        self.assertTrue(payload["model_presets"])
        self.assertTrue(payload["model_catalog"])
        self.assertEqual(payload["codex_status"]["account"]["plan_type"], "pro")
        self.assertEqual(payload["default_runtime"]["model"], "auto")
        self.assertEqual(payload["default_runtime"]["model_preset"], "auto")
        self.assertEqual(payload["default_runtime"]["sandbox_mode"], "danger-full-access")

    def test_project_setup_and_load_round_trip(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Demo Project",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            self.assertEqual(detail["project"]["display_name"], "Demo Project")
            self.assertEqual(detail["runtime"]["test_cmd"], "python -m unittest")
            self.assertEqual(detail["run_control"]["stop_after_current_step"], False)
            self.assertIn("workspace_tree", detail)
            self.assertIn("reports", detail)
            self.assertIn("history", detail)
            self.assertIn("checkpoints", detail)
            self.assertIn("bottom_panels", detail)
            self.assertIn("github", detail)
            self.assertEqual(detail["codex_status"]["account"]["email"], "demo@example.com")

            listing = run_command("list-projects", workspace_root)
            self.assertEqual(len(listing["projects"]), 1)
            self.assertEqual(listing["projects"][0]["display_name"], "Demo Project")

            with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: fake_codex_snapshot()):
                loaded = run_command(
                    "load-project",
                    workspace_root,
                    {
                        "repo_id": detail["project"]["repo_id"],
                    },
                )
            self.assertIn("Demo Project", loaded["summary"])
            self.assertEqual(loaded["stats"]["total_steps"], 0)

    def test_delete_project_removes_managed_workspace_but_keeps_local_repo(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            (repo_dir / "README.md").write_text("demo", encoding="utf-8")

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Delete Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            managed_root = Path(detail["project"]["project_root"])
            self.assertTrue(managed_root.exists())

            deleted = run_command(
                "delete-project",
                workspace_root,
                {
                    "repo_id": detail["project"]["repo_id"],
                },
            )

            self.assertEqual(deleted["deleted"]["display_name"], "Delete Demo")
            self.assertEqual(deleted["projects"], [])
            self.assertFalse(managed_root.exists())
            self.assertTrue(repo_dir.exists())
            self.assertTrue((repo_dir / "README.md").exists())

    def test_delete_all_projects_clears_registry_but_keeps_local_repos(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_a = temp_dir / "repo-a"
            repo_b = temp_dir / "repo-b"
            repo_a.mkdir(parents=True, exist_ok=True)
            repo_b.mkdir(parents=True, exist_ok=True)
            (repo_a / "README.md").write_text("a", encoding="utf-8")
            (repo_b / "README.md").write_text("b", encoding="utf-8")

            for repo_dir, name in ((repo_a, "A"), (repo_b, "B")):
                payload = {
                    "project_dir": str(repo_dir),
                    "display_name": f"Project {name}",
                    "branch": "main",
                    "origin_url": "",
                    "runtime": {
                        "model": "gpt-5.4",
                        "effort": "high",
                        "test_cmd": "python -m unittest",
                        "max_blocks": 5,
                    },
                }
                with mock.patch("codex_auto.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                    "codex_auto.ui_bridge.fetch_codex_backend_snapshot",
                    side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
                ):
                    run_command("save-project-setup", workspace_root, payload)

            deleted = run_command("delete-all-projects", workspace_root, {})
            self.assertTrue(deleted["deleted_all"])
            self.assertEqual(deleted["projects"], [])
            self.assertTrue(repo_a.exists())
            self.assertTrue(repo_b.exists())
            self.assertTrue((repo_a / "README.md").exists())
            self.assertTrue((repo_b / "README.md").exists())

    def test_save_plan_and_request_stop_persist_bridge_state(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            setup_payload = {
                "project_dir": str(repo_dir),
                "display_name": "Plan Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m pytest",
                    "execution_mode": "parallel",
                    "parallel_workers": 3,
                    "max_blocks": 4,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, setup_payload)

            save_plan_payload = {
                "project_dir": str(repo_dir),
                "branch": "main",
                "origin_url": "",
                "runtime": detail["runtime"],
                "plan": {
                    "plan_title": "Desktop rollout",
                    "project_prompt": "Build the React and Tauri desktop app.",
                    "summary": "Deliver the desktop shell in small verified steps.",
                    "execution_mode": "parallel",
                    "default_test_command": "python -m pytest",
                    "steps": [
                        {
                            "step_id": "custom-1",
                            "title": "Add the bridge",
                            "display_description": "Expose JSON commands for the desktop shell.",
                            "codex_description": "Create a JSON bridge for the UI.",
                            "test_command": "python -m pytest",
                            "success_criteria": "The desktop bridge can load and save projects.",
                            "reasoning_effort": "medium",
                            "depends_on": [],
                            "owned_paths": ["src/jakal_flow/ui_bridge.py", "tests/test_ui_bridge.py"],
                        },
                        {
                            "step_id": "custom-2",
                            "title": "Add the React shell",
                            "display_description": "Build the setup and flow screens.",
                            "codex_description": "Create the desktop shell with the required views.",
                            "test_command": "python -m pytest",
                            "success_criteria": "The desktop app can render the plan flow.",
                            "reasoning_effort": "xhigh",
                            "depends_on": [],
                            "owned_paths": ["desktop/src", "desktop/package.json"],
                        },
                    ],
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                saved = run_command("save-plan", workspace_root, save_plan_payload)

            self.assertEqual(saved["plan"]["steps"][0]["step_id"], "ST1")
            self.assertEqual(saved["plan"]["steps"][1]["step_id"], "ST2")
            self.assertEqual(saved["plan"]["steps"][0]["reasoning_effort"], "medium")
            self.assertEqual(saved["plan"]["steps"][1]["reasoning_effort"], "xhigh")
            self.assertEqual(saved["plan"]["execution_mode"], "parallel")
            self.assertEqual(saved["plan"]["steps"][0]["depends_on"], [])
            self.assertEqual(saved["plan"]["steps"][0]["owned_paths"], ["src/jakal_flow/ui_bridge.py", "tests/test_ui_bridge.py"])
            self.assertEqual(saved["runtime"]["execution_mode"], "parallel")
            self.assertEqual(saved["runtime"]["parallel_workers"], 3)
            self.assertEqual(saved["stats"]["total_steps"], 2)

            stop_payload = run_command(
                "request-stop",
                workspace_root,
                {
                    "project_dir": str(repo_dir),
                    "source": "unit-test",
                },
            )
            self.assertEqual(stop_payload["run_control"]["stop_after_current_step"], True)

            with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: fake_codex_snapshot()):
                loaded = run_command(
                    "load-project",
                    workspace_root,
                    {
                        "project_dir": str(repo_dir),
                    },
                )
            self.assertEqual(loaded["run_control"]["stop_after_current_step"], True)

            control_path = Path(loaded["files"]["ui_control_file"])
            self.assertTrue(control_path.exists())
            control_payload = json.loads(control_path.read_text(encoding="utf-8"))
            self.assertEqual(control_payload["request_source"], "unit-test")

    def test_load_project_tolerates_malformed_ui_state_files(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "State Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            control_path = Path(detail["files"]["ui_control_file"])
            control_path.write_text(
                json.dumps(
                    {
                        "stop_after_current_step": "yes",
                        "requested_at": 123,
                        "request_source": ["desktop"],
                    }
                ),
                encoding="utf-8",
            )
            checkpoint_path = Path(detail["project"]["project_root"]) / "state" / "CHECKPOINTS.json"
            checkpoint_path.write_text(
                json.dumps(
                    {
                        "checkpoints": [
                            {"checkpoint_id": "CP1", "status": "awaiting_review"},
                            "bad-entry",
                            99,
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: fake_codex_snapshot()):
                loaded = run_command(
                    "load-project",
                    workspace_root,
                    {
                        "project_dir": str(repo_dir),
                    },
                )

            self.assertTrue(loaded["run_control"]["stop_after_current_step"])
            self.assertEqual(loaded["run_control"]["requested_at"], "123")
            self.assertIsNone(loaded["run_control"]["request_source"])
            self.assertEqual(len(loaded["checkpoints"]["items"]), 1)
            self.assertEqual(loaded["checkpoints"]["pending"]["checkpoint_id"], "CP1")

    def test_load_project_can_skip_codex_status_refresh(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Fast Load Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                run_command("save-project-setup", workspace_root, payload)

            with mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=AssertionError("Codex status refresh should be skipped."),
            ):
                loaded = run_command(
                    "load-project",
                    workspace_root,
                    {
                        "project_dir": str(repo_dir),
                        "refresh_codex_status": False,
                        "detail_level": "core",
                    },
                )

            self.assertEqual(loaded["project"]["display_name"], "Fast Load Demo")
            self.assertEqual(loaded["detail_level"], "core")
            self.assertEqual(loaded["codex_status"], {})
            self.assertEqual(loaded["bottom_panels"]["codex_status"], {})
            self.assertEqual(loaded["history"]["blocks"], [])
            self.assertEqual(loaded["workspace_tree"], [])
            self.assertEqual(loaded["checkpoints"]["items"], [])

    def test_share_bridge_commands_create_and_revoke_read_only_session(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Share Bridge Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m pytest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                run_command("save-project-setup", workspace_root, payload)

            try:
                server_status = run_command("start_share_server", workspace_root, {})
                self.assertTrue(server_status["running"])
                self.assertTrue(str(server_status["base_url"]).startswith("http://127.0.0.1:"))

                with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: fake_codex_snapshot()):
                    created = run_command(
                        "create_share_session",
                        workspace_root,
                        {
                            "project_dir": str(repo_dir),
                            "created_by": "unit-test",
                            "bind_host": "0.0.0.0",
                            "public_base_url": "https://share.example.com/base",
                        },
                    )
                self.assertIn("share", created)
                self.assertIn("created_share_session", created)
                self.assertTrue(created["created_share_session"]["share_url"].startswith("https://share.example.com/base/share/view?"))
                self.assertTrue(created["created_share_session"]["local_url"].startswith("http://"))
                self.assertEqual(created["share"]["active_session"]["created_by"], "unit-test")
                self.assertEqual(created["share"]["server"]["config"]["bind_host"], "0.0.0.0")
                self.assertEqual(created["share"]["server"]["config"]["public_base_url"], "https://share.example.com/base")

                with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: fake_codex_snapshot()):
                    revoked = run_command(
                        "revoke_share_session",
                        workspace_root,
                        {
                            "project_dir": str(repo_dir),
                            "session_id": created["share"]["active_session"]["session_id"],
                        },
                    )
                self.assertIsNone(revoked["share"]["active_session"])
                self.assertIn("revoked_share_session", revoked)
            finally:
                run_command("stop_share_server", workspace_root, {})

    def test_share_bridge_can_auto_start_quick_tunnel_for_public_phone_link(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Quick Tunnel Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m pytest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                run_command("save-project-setup", workspace_root, payload)

            try:
                with mock.patch(
                    "jakal_flow.ui_bridge.start_cloudflare_quick_tunnel",
                    return_value={
                        "running": True,
                        "provider": "cloudflare-quick-tunnel",
                        "public_url": "https://demo.trycloudflare.com",
                        "target_url": "http://0.0.0.0:43123",
                        "pid": 4242,
                        "started_at": "2026-03-26T00:00:00+00:00",
                        "available": True,
                    },
                ) as start_tunnel, mock.patch(
                    "jakal_flow.public_tunnel.public_tunnel_status_payload",
                    return_value={
                        "running": True,
                        "provider": "cloudflare-quick-tunnel",
                        "public_url": "https://demo.trycloudflare.com",
                        "target_url": "http://0.0.0.0:43123",
                        "pid": 4242,
                        "started_at": "2026-03-26T00:00:00+00:00",
                        "available": True,
                    },
                ), mock.patch(
                    "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                    side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
                ):
                    created = run_command(
                        "create_share_session",
                        workspace_root,
                        {
                            "project_dir": str(repo_dir),
                            "created_by": "unit-test",
                            "bind_host": "0.0.0.0",
                            "public_base_url": "",
                        },
                    )

                start_tunnel.assert_called_once()
                self.assertEqual(created["share"]["server"]["share_base_url"], "https://demo.trycloudflare.com")
                self.assertEqual(created["share"]["server"]["share_base_url_source"], "quick_tunnel")
                self.assertTrue(created["created_share_session"]["share_url"].startswith("https://demo.trycloudflare.com/share/view?"))
            finally:
                run_command("stop_share_server", workspace_root, {})

    def test_share_bridge_falls_back_to_local_share_session_when_quick_tunnel_fails(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Tunnel Fallback Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m pytest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                run_command("save-project-setup", workspace_root, payload)

            try:
                with mock.patch(
                    "jakal_flow.ui_bridge.start_cloudflare_quick_tunnel",
                    side_effect=RuntimeError("quick tunnel startup failed"),
                ), mock.patch(
                    "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                    side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
                ):
                    created = run_command(
                        "create_share_session",
                        workspace_root,
                        {
                            "project_dir": str(repo_dir),
                            "created_by": "unit-test",
                            "bind_host": "0.0.0.0",
                            "public_base_url": "",
                        },
                    )

                self.assertIn("created_share_session", created)
                self.assertIn("share_tunnel_warning", created)
                self.assertIn("quick tunnel startup failed", created["share_tunnel_warning"])
                self.assertTrue(created["created_share_session"]["local_url"].startswith("http://127.0.0.1:"))
            finally:
                run_command("stop_share_server", workspace_root, {})


if __name__ == "__main__":
    unittest.main()
