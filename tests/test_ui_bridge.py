from __future__ import annotations

from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import sys
import unittest
from unittest import mock
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jakal_flow.cli import main as cli_main
import jakal_flow.ui_bridge_payloads as ui_bridge_payloads
from jakal_flow.models import ExecutionPlanState, ExecutionStep
from jakal_flow.status_views import effective_project_status
from jakal_flow.ui_bridge import default_workspace_root, progress_caption, run_command, runtime_from_payload


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
    def test_default_workspace_root_prefers_explicit_jakal_flow_env(self) -> None:
        with TemporaryTestDir() as temp_dir:
            explicit = temp_dir / "custom-workspace"
            with mock.patch.dict(os.environ, {"JAKAL_FLOW_GUI_WORKSPACE": str(explicit)}, clear=True), mock.patch(
                "jakal_flow.ui_bridge.Path.cwd",
                return_value=temp_dir,
            ), mock.patch(
                "jakal_flow.ui_bridge.Path.home",
                return_value=temp_dir / "home",
            ):
                resolved = default_workspace_root()

        self.assertEqual(resolved, explicit.resolve())

    def test_default_workspace_root_ignores_legacy_codex_auto_locations(self) -> None:
        with TemporaryTestDir() as temp_dir:
            legacy = temp_dir / ".codex-auto-workspace"
            legacy.mkdir(parents=True, exist_ok=True)
            home_dir = temp_dir / "home"
            home_dir.mkdir(parents=True, exist_ok=True)
            with mock.patch.dict(os.environ, {"CODEX_AUTO_GUI_WORKSPACE": str(legacy)}, clear=True), mock.patch(
                "jakal_flow.ui_bridge.Path.cwd",
                return_value=temp_dir,
            ), mock.patch(
                "jakal_flow.ui_bridge.Path.home",
                return_value=home_dir,
            ):
                resolved = default_workspace_root()

        self.assertEqual(resolved, (home_dir / ".jakal-flow-workspace").resolve())

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

    def test_progress_caption_reports_running_nodes_for_parallel_dag(self) -> None:
        caption = progress_caption(
            ExecutionPlanState(
                execution_mode="parallel",
                steps=[
                    ExecutionStep(step_id="ST1", title="Root", status="completed"),
                    ExecutionStep(step_id="ST2", title="Frontend", depends_on=["ST1"], owned_paths=["desktop/src"], status="running"),
                    ExecutionStep(step_id="ST3", title="Backend", depends_on=["ST1"], owned_paths=["src/jakal_flow"], status="running"),
                ],
            )
        )

        self.assertEqual(caption, "Completed 1/3 steps, running: ST2, ST3")

    def test_effective_project_status_prefers_parallel_plan_status_when_steps_are_running(self) -> None:
        status = effective_project_status(
            "running:st2",
            ExecutionPlanState(
                execution_mode="parallel",
                steps=[
                    ExecutionStep(step_id="ST1", title="Root", status="completed"),
                    ExecutionStep(step_id="ST2", title="Frontend", depends_on=["ST1"], owned_paths=["desktop/src"], status="running"),
                    ExecutionStep(step_id="ST3", title="Backend", depends_on=["ST1"], owned_paths=["src/jakal_flow"], status="running"),
                ],
            ),
            mock.Mock(pending_checkpoint_approval=False),
        )

        self.assertEqual(status, "running:parallel")

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
                "optimization_mode": "turbo",
                "optimization_large_file_lines": "0",
                "optimization_long_function_lines": "bogus",
                "optimization_duplicate_block_lines": 1,
                "optimization_max_files": "0",
            }
        )

        self.assertEqual(runtime.model, "gpt-5.4-mini")
        self.assertEqual(runtime.model_preset, "")
        self.assertEqual(runtime.max_blocks, 5)
        self.assertFalse(runtime.allow_push)
        self.assertTrue(runtime.require_checkpoint_approval)
        self.assertEqual(runtime.execution_mode, "parallel")
        self.assertEqual(runtime.parallel_worker_mode, "manual")
        self.assertEqual(runtime.parallel_workers, 2)
        self.assertEqual(runtime.no_progress_limit, 1)
        self.assertEqual(runtime.regression_limit, 3)
        self.assertEqual(runtime.empty_cycle_limit, 1)
        self.assertEqual(runtime.checkpoint_interval_blocks, 1)
        self.assertEqual(runtime.optimization_mode, "light")
        self.assertEqual(runtime.optimization_large_file_lines, 50)
        self.assertEqual(runtime.optimization_long_function_lines, 80)
        self.assertEqual(runtime.optimization_duplicate_block_lines, 3)
        self.assertEqual(runtime.optimization_max_files, 1)

    def test_runtime_from_payload_defaults_parallel_workers_to_auto_mode(self) -> None:
        runtime = runtime_from_payload({"execution_mode": "parallel"})

        self.assertEqual(runtime.execution_mode, "parallel")
        self.assertEqual(runtime.parallel_worker_mode, "auto")
        self.assertEqual(runtime.parallel_workers, 0)

    def test_runtime_from_payload_uses_platform_default_codex_path_when_missing(self) -> None:
        with mock.patch("jakal_flow.ui_bridge.default_codex_path", return_value="codex"):
            runtime = runtime_from_payload({"execution_mode": "parallel", "codex_path": ""})

        self.assertEqual(runtime.codex_path, "codex")

    def test_runtime_from_payload_upgrades_legacy_serial_mode_to_parallel(self) -> None:
        runtime = runtime_from_payload({"execution_mode": "serial"})

        self.assertEqual(runtime.execution_mode, "parallel")
        self.assertEqual(runtime.parallel_worker_mode, "auto")

    def test_runtime_from_payload_accepts_manual_parallel_worker_mode(self) -> None:
        runtime = runtime_from_payload(
            {
                "execution_mode": "parallel",
                "parallel_worker_mode": "manual",
                "parallel_workers": "3",
            }
        )

        self.assertEqual(runtime.execution_mode, "parallel")
        self.assertEqual(runtime.parallel_worker_mode, "manual")
        self.assertEqual(runtime.parallel_workers, 3)

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

    def test_runtime_from_payload_normalizes_local_model_provider(self) -> None:
        runtime = runtime_from_payload(
            {
                "model_provider": "oss",
                "local_model_provider": "",
                "model": "qwen2.5-coder:0.5b",
                "model_preset": "high",
            }
        )

        self.assertEqual(runtime.model_provider, "oss")
        self.assertEqual(runtime.local_model_provider, "ollama")
        self.assertEqual(runtime.model, "qwen2.5-coder:0.5b")
        self.assertEqual(runtime.model_preset, "")

    def test_runtime_from_payload_normalizes_ml_workflow_values(self) -> None:
        runtime = runtime_from_payload(
            {
                "workflow_mode": "ML",
                "ml_max_cycles": "0",
                "execution_mode": "parallel",
            }
        )

        self.assertEqual(runtime.workflow_mode, "ml")
        self.assertEqual(runtime.ml_max_cycles, 1)
        self.assertEqual(runtime.execution_mode, "parallel")

    def test_runtime_from_payload_applies_openrouter_defaults(self) -> None:
        runtime = runtime_from_payload(
            {
                "model_provider": "openrouter",
                "model_slug_input": "openai/gpt-4.1-mini",
                "billing_mode": "token",
            }
        )

        self.assertEqual(runtime.model_provider, "openrouter")
        self.assertEqual(runtime.provider_base_url, "https://openrouter.ai/api/v1")
        self.assertEqual(runtime.provider_api_key_env, "OPENROUTER_API_KEY")
        self.assertEqual(runtime.model, "openai/gpt-4.1-mini")
        self.assertEqual(runtime.billing_mode, "token")

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
        self.assertTrue(payload["default_runtime"]["generate_word_report"])
        self.assertEqual(payload["default_runtime"]["sandbox_mode"], "danger-full-access")
        self.assertEqual(payload["default_runtime"]["optimization_mode"], "light")

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
            self.assertIn("runtime_insights", detail)
            self.assertIn("runtime_insights", detail["bottom_panels"])
            self.assertIn("parallel", detail["runtime_insights"])

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

    def test_delete_project_archives_managed_workspace_and_allows_same_repo_restart(self) -> None:
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

            archived = run_command(
                "delete-project",
                workspace_root,
                {
                    "repo_id": detail["project"]["repo_id"],
                },
            )

            self.assertEqual(archived["archived"]["display_name"], "Delete Demo")
            self.assertTrue(archived["archived"]["archive_id"])
            self.assertEqual(archived["projects"], [])
            self.assertEqual(len(archived["history"]), 1)
            self.assertFalse(managed_root.exists())
            self.assertTrue(repo_dir.exists())
            self.assertTrue((repo_dir / "README.md").exists())

            archived_detail = run_command(
                "load-history-entry",
                workspace_root,
                {
                    "archive_id": archived["archived"]["archive_id"],
                    "detail_level": "full",
                },
            )

            self.assertTrue(archived_detail["project"]["archived"])
            self.assertTrue(Path(archived_detail["project"]["project_root"]).exists())
            self.assertIn("<svg", archived_detail["history"]["flow_svg_text"])

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                restarted = run_command(
                    "save-project-setup",
                    workspace_root,
                    {
                        **payload,
                        "display_name": "Delete Demo Restarted",
                    },
                )

            self.assertEqual(restarted["project"]["display_name"], "Delete Demo Restarted")
            listing = run_command("list-projects", workspace_root)
            self.assertEqual(len(listing["projects"]), 1)
            self.assertEqual(len(listing["history"]), 1)

    def test_delete_all_projects_archives_registry_but_keeps_local_repos(self) -> None:
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
                with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                    "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                    side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
                ):
                    run_command("save-project-setup", workspace_root, payload)

            deleted = run_command("delete-all-projects", workspace_root, {})
            self.assertTrue(deleted["archived_all"])
            self.assertEqual(deleted["archived_count"], 2)
            self.assertEqual(deleted["projects"], [])
            self.assertEqual(len(deleted["history"]), 2)
            self.assertTrue(repo_a.exists())
            self.assertTrue(repo_b.exists())
            self.assertTrue((repo_a / "README.md").exists())
            self.assertTrue((repo_b / "README.md").exists())

    def test_load_history_entry_returns_saved_plan_and_flow_chart(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "History Flow Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "effort": "high",
                    "test_cmd": "python -m pytest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            plan_payload = {
                "project_dir": str(repo_dir),
                "branch": "main",
                "origin_url": "",
                "runtime": detail["runtime"],
                "plan": {
                    "plan_title": "History Flow Demo",
                    "project_prompt": "Rebuild this directory from a fresh prompt.",
                    "summary": "Preserve the flow chart for archived runs.",
                    "execution_mode": "parallel",
                    "default_test_command": "python -m pytest",
                    "steps": [
                        {
                            "step_id": "seed",
                            "title": "Capture the archived flow",
                            "display_description": "Keep the old execution graph available from history.",
                            "codex_description": "Preserve the execution graph.",
                            "test_command": "python -m pytest",
                            "success_criteria": "The archived detail still renders the flow chart.",
                            "reasoning_effort": "high",
                            "depends_on": [],
                            "owned_paths": ["src/jakal_flow/ui_bridge.py"],
                        }
                    ],
                },
            }
            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                saved = run_command("save-plan", workspace_root, plan_payload)
            archived = run_command(
                "delete-project",
                workspace_root,
                {
                    "repo_id": saved["project"]["repo_id"],
                },
            )

            loaded = run_command(
                "load-history-entry",
                workspace_root,
                {
                    "archive_id": archived["archived"]["archive_id"],
                    "detail_level": "full",
                },
            )

            self.assertEqual(loaded["plan"]["project_prompt"], "Rebuild this directory from a fresh prompt.")
            self.assertEqual(loaded["plan"]["steps"][0]["title"], "Capture the archived flow")
            self.assertIn("<svg", loaded["history"]["flow_svg_text"])

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
            self.assertIsNone(loaded["checkpoints"]["pending"])
            self.assertEqual(loaded["checkpoints"]["items"][0]["status"], "approved")

    def test_approve_checkpoint_respects_string_push_flag_and_clears_pending_checkpoint(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Approval Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "allow_push": True,
                    "require_checkpoint_approval": True,
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            project_root = Path(detail["project"]["project_root"])
            checkpoint_path = project_root / "state" / "CHECKPOINTS.json"
            checkpoint_path.write_text(
                json.dumps(
                    {
                        "checkpoints": [
                            {
                                "checkpoint_id": "CP1",
                                "title": "Review me",
                                "target_block": 1,
                                "status": "awaiting_review",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            loop_state_path = project_root / "state" / "LOOP_STATE.json"
            loop_state = json.loads(loop_state_path.read_text(encoding="utf-8"))
            loop_state["current_checkpoint_id"] = "CP1"
            loop_state["pending_checkpoint_approval"] = True
            loop_state_path.write_text(json.dumps(loop_state), encoding="utf-8")

            with mock.patch("jakal_flow.orchestrator.GitOps.push") as push_mock, mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                approved = run_command(
                    "approve-checkpoint",
                    workspace_root,
                    {
                        "repo_id": detail["project"]["repo_id"],
                        "push": "false",
                    },
                )

            push_mock.assert_not_called()
            self.assertIsNone(approved["checkpoints"]["pending"])
            self.assertEqual(approved["project"]["current_status"], "setup_ready")
            self.assertEqual(approved["loop_state"]["current_checkpoint_id"], None)
            self.assertFalse(approved["loop_state"]["pending_checkpoint_approval"])
            self.assertEqual(approved["checkpoints"]["items"][0]["status"], "approved")
            self.assertFalse(approved["checkpoints"]["items"][0]["pushed"])
            self.assertEqual(approved["checkpoints"]["items"][0]["push_skipped_reason"], "not_requested")

    def test_load_project_does_not_report_pending_checkpoint_without_pending_flag(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Checkpoint Sync Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "require_checkpoint_approval": False,
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            project_root = Path(detail["project"]["project_root"])
            checkpoint_path = project_root / "state" / "CHECKPOINTS.json"
            checkpoint_path.write_text(
                json.dumps(
                    {
                        "checkpoints": [
                            {
                                "checkpoint_id": "CP1",
                                "title": "Currently running",
                                "target_block": 1,
                                "status": "running",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            loop_state_path = project_root / "state" / "LOOP_STATE.json"
            loop_state = json.loads(loop_state_path.read_text(encoding="utf-8"))
            loop_state["current_checkpoint_id"] = "CP1"
            loop_state["pending_checkpoint_approval"] = False
            loop_state_path.write_text(json.dumps(loop_state), encoding="utf-8")

            with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: fake_codex_snapshot()):
                loaded = run_command(
                    "load-project",
                    workspace_root,
                    {
                        "project_dir": str(repo_dir),
                    },
                )

            self.assertEqual(loaded["checkpoints"]["items"][0]["status"], "running")
            self.assertIsNone(loaded["checkpoints"]["pending"])

    def test_run_plan_automatically_runs_closeout_after_last_completed_step(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Auto Closeout Demo",
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

            completed_plan = {
                "plan_title": "Auto Closeout Demo",
                "project_prompt": "Finish the work",
                "summary": "Everything is ready for closeout.",
                "workflow_mode": "standard",
                "execution_mode": "parallel",
                "default_test_command": "python -m unittest",
                "steps": [
                    {
                        "step_id": "ST1",
                        "title": "Implement",
                        "display_description": "Implementation finished",
                        "codex_description": "Implementation finished",
                        "success_criteria": "Tests pass",
                        "test_command": "python -m unittest",
                        "reasoning_effort": "high",
                        "status": "completed",
                    }
                ],
            }

            def fake_run_execution_closeout(self, project_dir, runtime, branch="main", origin_url=""):
                context = self.local_project(project_dir)
                assert context is not None
                plan_state = self.load_execution_plan_state(context)
                plan_state.closeout_status = "completed"
                plan_state.closeout_started_at = "2026-03-26T00:10:00+00:00"
                plan_state.closeout_completed_at = "2026-03-26T00:12:00+00:00"
                plan_state.closeout_notes = "Closeout finished successfully."
                saved = self.save_execution_plan_state(context, plan_state)
                context.metadata.current_status = self._status_from_plan_state(saved)
                self.workspace.save_project(context)
                return context, saved

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ), mock.patch(
                "jakal_flow.orchestrator.Orchestrator.run_execution_closeout",
                new=fake_run_execution_closeout,
            ):
                result = run_command(
                    "run-plan",
                    workspace_root,
                    {
                        **payload,
                        "plan": completed_plan,
                    },
                )

            self.assertEqual(result["plan"]["closeout_status"], "completed")
            self.assertEqual(result["project"]["current_status"], "closed_out")
            self.assertTrue(any("closeout-started" in line for line in result["activity"]))
            self.assertTrue(any("closeout-finished" in line for line in result["activity"]))

    def test_load_project_normalizes_stale_awaiting_review_without_pending_flag(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Stale Review Badge Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "require_checkpoint_approval": True,
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            project_root = Path(detail["project"]["project_root"])
            checkpoint_path = project_root / "state" / "CHECKPOINTS.json"
            checkpoint_path.write_text(
                json.dumps(
                    {
                        "checkpoints": [
                            {
                                "checkpoint_id": "CP1",
                                "title": "Review me",
                                "target_block": 1,
                                "status": "awaiting_review",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            loop_state_path = project_root / "state" / "LOOP_STATE.json"
            loop_state = json.loads(loop_state_path.read_text(encoding="utf-8"))
            loop_state["current_checkpoint_id"] = None
            loop_state["pending_checkpoint_approval"] = False
            loop_state_path.write_text(json.dumps(loop_state), encoding="utf-8")

            with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: fake_codex_snapshot()):
                loaded = run_command(
                    "load-project",
                    workspace_root,
                    {
                        "project_dir": str(repo_dir),
                    },
                )

            self.assertIsNone(loaded["checkpoints"]["pending"])
            self.assertEqual(loaded["checkpoints"]["items"][0]["status"], "approved")

    def test_load_project_normalizes_stale_awaiting_checkpoint_status_without_pending_flag(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Stale Project Status Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "require_checkpoint_approval": True,
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            project_root = Path(detail["project"]["project_root"])
            metadata_path = project_root / "metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["current_status"] = "awaiting_checkpoint_approval"
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

            loop_state_path = project_root / "state" / "LOOP_STATE.json"
            loop_state = json.loads(loop_state_path.read_text(encoding="utf-8"))
            loop_state["pending_checkpoint_approval"] = False
            loop_state["current_checkpoint_id"] = None
            loop_state_path.write_text(json.dumps(loop_state), encoding="utf-8")

            with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: fake_codex_snapshot()):
                loaded = run_command(
                    "load-project",
                    workspace_root,
                    {
                        "project_dir": str(repo_dir),
                    },
                )

            self.assertEqual(loaded["project"]["current_status"], "setup_ready")
            self.assertEqual(loaded["snapshot"]["project"]["current_status"], "setup_ready")
            self.assertEqual(loaded["bottom_panels"]["git_status"]["current_status"], "setup_ready")

    def test_list_projects_normalizes_stale_awaiting_checkpoint_status_without_pending_flag(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Stale List Status Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "require_checkpoint_approval": True,
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            project_root = Path(detail["project"]["project_root"])
            metadata_path = project_root / "metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["current_status"] = "awaiting_checkpoint_approval"
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

            loop_state_path = project_root / "state" / "LOOP_STATE.json"
            loop_state = json.loads(loop_state_path.read_text(encoding="utf-8"))
            loop_state["pending_checkpoint_approval"] = False
            loop_state["current_checkpoint_id"] = None
            loop_state_path.write_text(json.dumps(loop_state), encoding="utf-8")

            listing = run_command("list-projects", workspace_root)

            self.assertEqual(listing["projects"][0]["status"], "setup_ready")
            self.assertEqual(listing["workspace"]["ready_like"], 1)
            self.assertEqual(listing["workspace"]["running"], 0)

    def test_cli_list_repos_skips_unreadable_execution_plan_state(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_one = temp_dir / "repo-one"
            repo_two = temp_dir / "repo-two"
            repo_one.mkdir(parents=True, exist_ok=True)
            repo_two.mkdir(parents=True, exist_ok=True)

            base_payload = {
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

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", side_effect=[repo_one / ".venv", repo_two / ".venv"]), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail_one = run_command(
                    "save-project-setup",
                    workspace_root,
                    {
                        **base_payload,
                        "project_dir": str(repo_one),
                        "display_name": "Repo One",
                    },
                )
                detail_two = run_command(
                    "save-project-setup",
                    workspace_root,
                    {
                        **base_payload,
                        "project_dir": str(repo_two),
                        "display_name": "Repo Two",
                    },
                )

            broken_plan = Path(detail_one["project"]["project_root"]) / "state" / "EXECUTION_PLAN.json"
            broken_plan.write_text("{not-json", encoding="utf-8")

            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = cli_main(["list-repos", "--workspace-root", str(workspace_root)])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(len(payload), 2)
            self.assertEqual({item["slug"] for item in payload}, {detail_one["project"]["slug"], detail_two["project"]["slug"]})
            repo_one_entry = next(item for item in payload if item["slug"] == detail_one["project"]["slug"])
            self.assertEqual(repo_one_entry["status"], "setup_ready")
            self.assertEqual(stderr.getvalue(), "")

    def test_cli_list_repos_uses_metadata_status_without_loading_plan_when_not_needed(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Lazy Status Demo",
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

            stdout = io.StringIO()
            stderr = io.StringIO()
            with mock.patch(
                "jakal_flow.cli.Orchestrator.load_execution_plan_state",
                side_effect=AssertionError("list-repos should not load plan for stable metadata statuses"),
            ), redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = cli_main(["list-repos", "--workspace-root", str(workspace_root)])

            self.assertEqual(exit_code, 0)
            listed = json.loads(stdout.getvalue())
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["slug"], detail["project"]["slug"])
            self.assertEqual(listed[0]["status"], "setup_ready")
            self.assertEqual(stderr.getvalue(), "")

    def test_save_project_setup_clears_stale_pending_checkpoint_when_approval_is_disabled(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            enabled_payload = {
                "project_dir": str(repo_dir),
                "display_name": "Stale Checkpoint Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "require_checkpoint_approval": True,
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, enabled_payload)

            project_root = Path(detail["project"]["project_root"])
            checkpoint_path = project_root / "state" / "CHECKPOINTS.json"
            checkpoint_path.write_text(
                json.dumps(
                    {
                        "checkpoints": [
                            {
                                "checkpoint_id": "CP1",
                                "title": "Review me",
                                "target_block": 1,
                                "status": "awaiting_review",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            loop_state_path = project_root / "state" / "LOOP_STATE.json"
            loop_state = json.loads(loop_state_path.read_text(encoding="utf-8"))
            loop_state["current_checkpoint_id"] = "CP1"
            loop_state["pending_checkpoint_approval"] = True
            loop_state["stop_reason"] = "checkpoint approval required"
            loop_state_path.write_text(json.dumps(loop_state), encoding="utf-8")

            disabled_payload = {
                **enabled_payload,
                "runtime": {
                    **enabled_payload["runtime"],
                    "require_checkpoint_approval": False,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                updated = run_command("save-project-setup", workspace_root, disabled_payload)

            self.assertIsNone(updated["checkpoints"]["pending"])
            self.assertIsNone(updated["loop_state"]["current_checkpoint_id"])
            self.assertFalse(updated["loop_state"]["pending_checkpoint_approval"])
            self.assertIsNone(updated["loop_state"]["stop_reason"])
            self.assertTrue(all(item.get("status") != "awaiting_review" for item in updated["checkpoints"]["items"]))

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
            self.assertTrue(loaded["activity"])

    def test_load_project_reuses_cached_core_payload_when_state_is_unchanged(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Cached Core Demo",
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

            cache_file = Path(detail["project"]["project_root"]) / "state" / "PROJECT_DETAIL_CACHE_CORE.json"
            if cache_file.exists():
                cache_file.unlink()

            first = run_command(
                "load-project",
                workspace_root,
                {
                    "repo_id": detail["project"]["repo_id"],
                    "refresh_codex_status": False,
                    "detail_level": "core",
                },
            )

            self.assertFalse(first["payload_cache_hit"])
            self.assertTrue(cache_file.exists())

            with mock.patch(
                "jakal_flow.ui_bridge_payloads._build_project_detail_base_payload",
                side_effect=AssertionError("The cached payload should be reused."),
            ):
                second = run_command(
                    "load-project",
                    workspace_root,
                    {
                        "repo_id": detail["project"]["repo_id"],
                        "refresh_codex_status": False,
                        "detail_level": "core",
                    },
                )

            self.assertTrue(second["payload_cache_hit"])
            self.assertEqual(second["detail_level"], "core")
            self.assertEqual(second["content_signature"], first["content_signature"])
            self.assertEqual(second["detail_signature"], first["detail_signature"])
            self.assertIn("content_signature", second)
            self.assertIn("detail_signature", second)

    def test_load_project_full_detail_reads_each_log_tail_once_on_cache_miss(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Full Detail Tail Demo",
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

            project_root = Path(detail["project"]["project_root"])
            full_cache = project_root / "state" / "PROJECT_DETAIL_CACHE_FULL.json"
            if full_cache.exists():
                full_cache.unlink()

            tail_calls: list[str] = []
            last_calls: list[str] = []
            original_tail = ui_bridge_payloads.read_jsonl_tail
            original_last = ui_bridge_payloads.read_last_jsonl

            def counting_tail(path, *args, **kwargs):
                tail_calls.append(Path(path).name)
                return original_tail(path, *args, **kwargs)

            def counting_last(path, *args, **kwargs):
                last_calls.append(Path(path).name)
                return original_last(path, *args, **kwargs)

            with mock.patch("jakal_flow.ui_bridge_payloads.read_jsonl_tail", side_effect=counting_tail), mock.patch(
                "jakal_flow.ui_bridge_payloads.read_last_jsonl",
                side_effect=counting_last,
            ), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                loaded = run_command(
                    "load-project",
                    workspace_root,
                    {
                        "repo_id": detail["project"]["repo_id"],
                        "refresh_codex_status": False,
                        "detail_level": "full",
                    },
                )

            counts = Counter(tail_calls)
            self.assertFalse(loaded["payload_cache_hit"])
            self.assertEqual(counts["ui_events.jsonl"], 1)
            self.assertEqual(counts["blocks.jsonl"], 1)
            self.assertEqual(counts["passes.jsonl"], 1)
            self.assertEqual(counts["test_runs.jsonl"], 1)
            self.assertNotIn("blocks.jsonl", last_calls)
            self.assertNotIn("passes.jsonl", last_calls)

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

            def tunnel_payload(target_url: str) -> dict[str, object]:
                return {
                    "running": True,
                    "provider": "cloudflare-quick-tunnel",
                    "public_url": "https://demo.trycloudflare.com",
                    "target_url": target_url,
                    "pid": 4242,
                    "started_at": "2026-03-26T00:00:00+00:00",
                    "available": True,
                }

            def current_tunnel_status(_workspace_root: Path) -> dict[str, object]:
                share_state_path = workspace_root / "share_server.json"
                if not share_state_path.exists():
                    return {
                        "running": False,
                        "provider": "cloudflare-quick-tunnel",
                        "public_url": "",
                        "target_url": "",
                        "pid": None,
                        "started_at": None,
                        "available": True,
                    }
                state = json.loads(share_state_path.read_text(encoding="utf-8"))
                return tunnel_payload(f"http://{state['host']}:{state['port']}")

            try:
                with mock.patch(
                    "jakal_flow.ui_bridge.start_cloudflare_quick_tunnel",
                    side_effect=lambda actual_workspace_root, target_url: tunnel_payload(target_url),
                ) as start_tunnel, mock.patch(
                    "jakal_flow.public_tunnel.public_tunnel_status_payload",
                    side_effect=current_tunnel_status,
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
