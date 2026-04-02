from __future__ import annotations

from pathlib import Path
import shutil
import sys
import unittest
from unittest import mock
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import jakal_flow.tooling_manager as tooling_manager
import jakal_flow.ui_bridge as ui_bridge


def local_temp_root() -> Path:
    root = Path(__file__).resolve().parents[1] / ".tub"
    root.mkdir(parents=True, exist_ok=True)
    return root


class TemporaryTestDir:
    def __enter__(self) -> Path:
        self.path = local_temp_root() / f"tooling-{uuid.uuid4().hex[:8]}"
        self.path.mkdir(parents=True, exist_ok=True)
        return self.path

    def __exit__(self, exc_type, exc, tb) -> None:
        shutil.rmtree(self.path, ignore_errors=True)


def fake_codex_snapshot_payload() -> dict:
    return {
        "checked_at": "2026-04-02T00:00:00+00:00",
        "available": True,
        "model_catalog": [{"model": "auto", "provider": "openai"}],
        "account": {"authenticated": True},
        "rate_limits": {"default_limit_id": "", "items": []},
        "error": "",
    }


def fake_codex_snapshot() -> mock.Mock:
    payload = fake_codex_snapshot_payload()
    return mock.Mock(model_catalog=payload["model_catalog"], to_dict=mock.Mock(return_value=payload))


class ToolingManagerTests(unittest.TestCase):
    def test_get_tooling_statuses_reports_detected_tools(self) -> None:
        with mock.patch.object(tooling_manager, "_npm_status", return_value=tooling_manager.ToolingStatus(
            tool="npm",
            display_name="Node.js / npm",
            command="npm.cmd",
            resolved_command="C:/npm.cmd",
            installed=True,
            version="10.9.0",
            reason="npm is available for installing terminal agents.",
        )), mock.patch.object(tooling_manager, "_cli_status", side_effect=[
            tooling_manager.ToolingStatus("codex", "Codex CLI", "codex.cmd", "C:/codex.cmd", True, version="0.1.0"),
            tooling_manager.ToolingStatus("gemini", "Gemini CLI", "gemini.cmd", "", False),
            tooling_manager.ToolingStatus("claude", "Claude Code", "claude.cmd", "C:/claude.cmd", True, version="1.2.3"),
        ]), mock.patch.object(tooling_manager, "_ollama_status", return_value=tooling_manager.ToolingStatus(
            tool="ollama",
            display_name="Ollama",
            command="ollama",
            resolved_command="C:/ollama.exe",
            installed=True,
            version="0.6.0",
            running=True,
            models=["qwen2.5-coder:0.5b"],
            reason="Ollama is connected with 1 installed model(s).",
        )):
            statuses = tooling_manager.get_tooling_statuses()

        self.assertTrue(statuses["npm"]["installed"])
        self.assertTrue(statuses["codex"]["installed"])
        self.assertFalse(statuses["gemini"]["installed"])
        self.assertEqual(statuses["claude"]["version"], "1.2.3")
        self.assertEqual(statuses["ollama"]["models"], ["qwen2.5-coder:0.5b"])

    def test_run_tooling_action_logs_existing_install_without_changes(self) -> None:
        with TemporaryTestDir() as temp_dir, mock.patch.object(
            tooling_manager,
            "_cli_status",
            return_value=tooling_manager.ToolingStatus(
                tool="codex",
                display_name="Codex CLI",
                command="codex.cmd",
                resolved_command="C:/codex.cmd",
                installed=True,
                version="0.1.0",
                reason="Codex CLI is installed.",
            ),
        ):
            result = tooling_manager.run_tooling_action(temp_dir, action="install", tool="codex")

            log_path = temp_dir / "tooling_events.jsonl"
            log_text = log_path.read_text(encoding="utf-8")

        self.assertFalse(result["changed"])
        self.assertIn("already installed", result["message"].lower())
        self.assertIn('"phase": "started"', log_text)
        self.assertIn('"phase": "completed"', log_text)

    def test_run_tooling_action_connects_ollama_and_pulls_model(self) -> None:
        with TemporaryTestDir() as temp_dir, mock.patch.object(
            tooling_manager,
            "_ollama_status",
            return_value=tooling_manager.ToolingStatus(
                tool="ollama",
                display_name="Ollama",
                command="ollama",
                resolved_command="C:/ollama.exe",
                installed=True,
                version="0.6.0",
                running=False,
                models=[],
                reason="Ollama is installed but the local server is not running.",
            ),
        ), mock.patch.object(tooling_manager, "_ensure_ollama_running") as ensure_running, mock.patch.object(
            tooling_manager,
            "_ollama_runtime_status",
            side_effect=[(True, []), (True, ["qwen2.5-coder:0.5b"])],
        ), mock.patch.object(tooling_manager, "_ollama_api_request", return_value={"status": "success"}) as api_request:
            result = tooling_manager.run_tooling_action(
                temp_dir,
                action="connect",
                tool="ollama",
                model="qwen2.5-coder:0.5b",
            )

        ensure_running.assert_called_once()
        api_request.assert_called_once()
        self.assertTrue(result["changed"])
        self.assertEqual(result["model"], "qwen2.5-coder:0.5b")
        self.assertIn("pulled", result["message"].lower())


class ToolingBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        ui_bridge._bridge_command_handlers_cache = None
        ui_bridge._bridge_command_handlers_cache_token = None

    def tearDown(self) -> None:
        ui_bridge._bridge_command_handlers_cache = None
        ui_bridge._bridge_command_handlers_cache_token = None

    def test_bootstrap_payload_includes_tooling_statuses(self) -> None:
        with TemporaryTestDir() as temp_dir, mock.patch(
            "jakal_flow.ui_bridge.tooling_snapshot_payload",
            return_value={
                "codex_status": {
                    **fake_codex_snapshot_payload(),
                    "provider_statuses": {"openai": {"available": True}},
                },
                "model_catalog": [{"model": "auto", "provider": "openai"}],
                "tooling_statuses": {"codex": {"installed": True}},
            },
        ):
            payload = ui_bridge.bootstrap_payload(temp_dir / "workspace")

        self.assertIn("tooling_statuses", payload)
        self.assertTrue(payload["tooling_statuses"]["codex"]["installed"])
        self.assertIn("provider_statuses", payload["codex_status"])

    def test_run_command_manage_tooling_returns_snapshot_and_action(self) -> None:
        fake_service = mock.Mock(get_snapshot=mock.Mock(return_value=fake_codex_snapshot()))
        with TemporaryTestDir() as temp_dir, mock.patch(
            "jakal_flow.ui_bridge._codex_snapshot_service",
            new=fake_service,
        ), mock.patch(
            "jakal_flow.ui_bridge_commands.tooling.get_tooling_statuses",
            return_value={"codex": {"installed": True}},
        ), mock.patch(
            "jakal_flow.ui_bridge_commands.tooling.run_tooling_action",
            return_value={
                "tool": "codex",
                "action": "install",
                "changed": True,
                "message": "Installed Codex CLI.",
            },
        ):
            result = ui_bridge.run_command(
                "manage-tooling",
                temp_dir,
                {"tool": "codex", "action": "install"},
            )

        self.assertEqual(result["tooling_action"]["tool"], "codex")
        self.assertTrue(result["tooling_statuses"]["codex"]["installed"])
        self.assertFalse(result["emit_project_changed"])


if __name__ == "__main__":
    unittest.main()
