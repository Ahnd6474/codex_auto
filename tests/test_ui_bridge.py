from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import unittest
from unittest import mock
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codex_auto.ui_bridge import run_command


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


class UIBridgeTests(unittest.TestCase):
    def test_bootstrap_exposes_workspace_and_model_presets(self) -> None:
        with TemporaryTestDir() as temp_dir:
            payload = run_command("bootstrap", temp_dir)

        self.assertEqual(payload["workspace_root"], str(temp_dir.resolve()))
        self.assertTrue(payload["model_presets"])
        self.assertEqual(payload["model_presets"][0]["preset_id"], "recommended")
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
                    "model": "gpt-5.3-codex",
                    "model_preset": "recommended",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("codex_auto.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"):
                detail = run_command("save-project-setup", workspace_root, payload)

            self.assertEqual(detail["project"]["display_name"], "Demo Project")
            self.assertEqual(detail["runtime"]["test_cmd"], "python -m unittest")
            self.assertEqual(detail["run_control"]["stop_after_current_step"], False)

            listing = run_command("list-projects", workspace_root)
            self.assertEqual(len(listing["projects"]), 1)
            self.assertEqual(listing["projects"][0]["display_name"], "Demo Project")

            loaded = run_command(
                "load-project",
                workspace_root,
                {
                    "repo_id": detail["project"]["repo_id"],
                },
            )
            self.assertIn("Demo Project", loaded["summary"])
            self.assertEqual(loaded["stats"]["total_steps"], 0)

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
                    "model": "gpt-5.3-codex",
                    "model_preset": "recommended",
                    "effort": "high",
                    "test_cmd": "python -m pytest",
                    "max_blocks": 4,
                },
            }

            with mock.patch("codex_auto.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"):
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
                    "default_test_command": "python -m pytest",
                    "steps": [
                        {
                            "step_id": "custom-1",
                            "title": "Add the bridge",
                            "display_description": "Expose JSON commands for the desktop shell.",
                            "codex_description": "Create a JSON bridge for the UI.",
                            "test_command": "python -m pytest",
                            "success_criteria": "The desktop bridge can load and save projects.",
                        },
                        {
                            "step_id": "custom-2",
                            "title": "Add the React shell",
                            "display_description": "Build the setup and flow screens.",
                            "codex_description": "Create the desktop shell with the required views.",
                            "test_command": "python -m pytest",
                            "success_criteria": "The desktop app can render the plan flow.",
                        },
                    ],
                },
            }

            with mock.patch("codex_auto.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"):
                saved = run_command("save-plan", workspace_root, save_plan_payload)

            self.assertEqual(saved["plan"]["steps"][0]["step_id"], "ST1")
            self.assertEqual(saved["plan"]["steps"][1]["step_id"], "ST2")
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


if __name__ == "__main__":
    unittest.main()
