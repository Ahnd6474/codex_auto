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
    def setUp(self) -> None:
        tooling_manager._invalidate_tooling_status_cache()

    def tearDown(self) -> None:
        tooling_manager._invalidate_tooling_status_cache()

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
            recommended_models=["qwen2.5-coder:0.5b", "qwen2.5-coder:7b"],
            model_store_path="C:/repo/third_party/ollama/models",
            reason="Ollama is connected with 1 installed model(s).",
        )):
            statuses = tooling_manager.get_tooling_statuses()

        self.assertTrue(statuses["npm"]["installed"])
        self.assertTrue(statuses["codex"]["installed"])
        self.assertFalse(statuses["gemini"]["installed"])
        self.assertEqual(statuses["claude"]["version"], "1.2.3")
        self.assertEqual(statuses["ollama"]["models"], ["qwen2.5-coder:0.5b"])
        self.assertEqual(statuses["ollama"]["recommended_models"], ["qwen2.5-coder:0.5b", "qwen2.5-coder:7b"])
        self.assertEqual(statuses["ollama"]["model_store_path"], "C:/repo/third_party/ollama/models")

    def test_get_tooling_statuses_reuses_cached_snapshot_until_force_refresh(self) -> None:
        with mock.patch.object(
            tooling_manager,
            "_collect_tooling_statuses",
            side_effect=[
                {"codex": {"installed": False}},
                {"codex": {"installed": True}},
            ],
        ) as collect_statuses:
            first = tooling_manager.get_tooling_statuses()
            first["codex"]["installed"] = "mutated"
            second = tooling_manager.get_tooling_statuses()
            refreshed = tooling_manager.get_tooling_statuses(force_refresh=True)

        self.assertEqual(collect_statuses.call_count, 2)
        self.assertEqual(second["codex"]["installed"], False)
        self.assertEqual(refreshed["codex"]["installed"], True)

    def test_get_tooling_statuses_keeps_startup_safe_cache_separate(self) -> None:
        with mock.patch.object(
            tooling_manager,
            "_collect_tooling_statuses",
            side_effect=[
                {"codex": {"installed": False, "version": ""}},
                {"codex": {"installed": True, "version": "0.1.0"}},
            ],
        ) as collect_statuses:
            startup = tooling_manager.get_tooling_statuses(startup_safe=True)
            full = tooling_manager.get_tooling_statuses()

        self.assertEqual(collect_statuses.call_count, 2)
        self.assertEqual(
            collect_statuses.call_args_list[0].kwargs,
            {"startup_safe": True, "include_ollama_details": True},
        )
        self.assertEqual(
            collect_statuses.call_args_list[1].kwargs,
            {"startup_safe": False, "include_ollama_details": True},
        )
        self.assertEqual(startup["codex"]["version"], "")
        self.assertEqual(full["codex"]["version"], "0.1.0")

    def test_get_tooling_statuses_keeps_ollama_detail_cache_separate(self) -> None:
        with mock.patch.object(
            tooling_manager,
            "_collect_tooling_statuses",
            side_effect=[
                {"ollama": {"running": None, "models": []}},
                {"ollama": {"running": False, "models": ["qwen2.5-coder:0.5b"]}},
            ],
        ) as collect_statuses:
            summary = tooling_manager.get_tooling_statuses(include_ollama_details=False)
            detailed = tooling_manager.get_tooling_statuses(include_ollama_details=True)

        self.assertEqual(collect_statuses.call_count, 2)
        self.assertEqual(
            collect_statuses.call_args_list[0].kwargs,
            {"startup_safe": False, "include_ollama_details": False},
        )
        self.assertEqual(
            collect_statuses.call_args_list[1].kwargs,
            {"startup_safe": False, "include_ollama_details": True},
        )
        self.assertIsNone(summary["ollama"]["running"])
        self.assertFalse(detailed["ollama"]["running"])

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
        ), mock.patch.object(
            tooling_manager,
            "_configure_ollama_model_store",
            return_value=Path("C:/repo/third_party/ollama/models"),
        ), mock.patch.object(tooling_manager, "_ensure_ollama_running") as ensure_running, mock.patch.object(
            tooling_manager,
            "_ollama_runtime_status",
            side_effect=[(True, []), (True, ["qwen2.5-coder:0.5b"])],
        ), mock.patch.object(tooling_manager, "_vendored_ollama_models", return_value=[]), mock.patch.object(
            tooling_manager,
            "run_subprocess",
            return_value=mock.Mock(returncode=0, stdout="", stderr=""),
        ) as run_subprocess_mock:
            result = tooling_manager.run_tooling_action(
                temp_dir,
                action="connect",
                tool="ollama",
                model="qwen2.5-coder:0.5b",
            )

        ensure_running.assert_called_once()
        run_subprocess_mock.assert_called_once()
        self.assertEqual(run_subprocess_mock.call_args.args[0][1:], ["pull", "qwen2.5-coder:0.5b"])
        self.assertTrue(str(run_subprocess_mock.call_args.args[0][0]).lower().endswith("ollama.exe"))
        self.assertEqual(
            run_subprocess_mock.call_args.kwargs["env"]["OLLAMA_MODELS"],
            str(Path("C:/repo/third_party/ollama/models")),
        )
        self.assertTrue(result["changed"])
        self.assertEqual(result["model"], "qwen2.5-coder:0.5b")
        self.assertIn("pulled", result["message"].lower())
        self.assertEqual(result["model_store_path"], str(Path("C:/repo/third_party/ollama/models")))

    def test_persist_windows_ollama_models_env_still_calls_setx_when_process_env_matches(self) -> None:
        with mock.patch.dict(tooling_manager.os.environ, {"OLLAMA_MODELS": "C:/repo/third_party/ollama/models"}, clear=False), mock.patch.object(
            tooling_manager,
            "run_subprocess",
            return_value=mock.Mock(returncode=0, stdout="", stderr=""),
        ) as run_subprocess_mock:
            tooling_manager._persist_windows_ollama_models_env(Path("C:/repo/third_party/ollama/models"))

        run_subprocess_mock.assert_called_once_with(
            ["setx", "OLLAMA_MODELS", str(Path("C:/repo/third_party/ollama/models"))],
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout_seconds=30.0,
        )


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

    def test_get_tooling_status_command_skips_ollama_details_by_default(self) -> None:
        fake_service = mock.Mock(get_snapshot=mock.Mock(return_value=fake_codex_snapshot()))
        with TemporaryTestDir() as temp_dir, mock.patch(
            "jakal_flow.ui_bridge._codex_snapshot_service",
            new=fake_service,
        ), mock.patch(
            "jakal_flow.ui_bridge_commands.tooling.tooling_snapshot_payload",
            return_value={
                "codex_status": fake_codex_snapshot_payload(),
                "model_catalog": [{"model": "auto", "provider": "openai"}],
                "tooling_statuses": {"ollama": {"installed": True}},
            },
        ) as tooling_snapshot_payload_mock:
            ui_bridge.run_command("get-tooling-status", temp_dir, {})

        self.assertFalse(tooling_snapshot_payload_mock.call_args.kwargs["include_ollama_details"])

    def test_get_tooling_status_command_can_skip_codex_refresh(self) -> None:
        fake_service = mock.Mock(get_snapshot=mock.Mock(return_value=fake_codex_snapshot()))
        with TemporaryTestDir() as temp_dir, mock.patch(
            "jakal_flow.ui_bridge._codex_snapshot_service",
            new=fake_service,
        ), mock.patch(
            "jakal_flow.ui_bridge_commands.tooling.tooling_snapshot_payload",
            return_value={
                "codex_status": fake_codex_snapshot_payload(),
                "model_catalog": [{"model": "auto", "provider": "openai"}],
                "tooling_statuses": {"ollama": {"installed": True}},
            },
        ) as tooling_snapshot_payload_mock:
            ui_bridge.run_command(
                "get-tooling-status",
                temp_dir,
                {"force_refresh": True, "refresh_codex_status": False},
            )

        self.assertFalse(tooling_snapshot_payload_mock.call_args.kwargs["refresh_codex_status"])

    def test_manage_tooling_connect_includes_ollama_details(self) -> None:
        fake_service = mock.Mock(get_snapshot=mock.Mock(return_value=fake_codex_snapshot()))
        with TemporaryTestDir() as temp_dir, mock.patch(
            "jakal_flow.ui_bridge._codex_snapshot_service",
            new=fake_service,
        ), mock.patch(
            "jakal_flow.ui_bridge_commands.tooling.run_tooling_action",
            return_value={
                "tool": "ollama",
                "action": "connect",
                "changed": True,
                "message": "Connected Ollama.",
            },
        ), mock.patch(
            "jakal_flow.ui_bridge_commands.tooling.tooling_snapshot_payload",
            return_value={
                "codex_status": fake_codex_snapshot_payload(),
                "model_catalog": [{"model": "auto", "provider": "openai"}],
                "tooling_statuses": {"ollama": {"installed": True}},
            },
        ) as tooling_snapshot_payload_mock:
            ui_bridge.run_command(
                "manage-tooling",
                temp_dir,
                {"tool": "ollama", "action": "connect", "model": "qwen2.5-coder:0.5b"},
            )

        self.assertTrue(tooling_snapshot_payload_mock.call_args.kwargs["include_ollama_details"])

    def test_tooling_snapshot_payload_prefers_startup_safe_tooling_statuses_when_cached(self) -> None:
        fake_service = mock.Mock(
            peek_snapshot=mock.Mock(return_value=fake_codex_snapshot()),
        )
        with mock.patch(
            "jakal_flow.ui_bridge_commands.tooling.provider_statuses_payload",
            return_value={"openai": {"available": True}},
        ), mock.patch(
            "jakal_flow.ui_bridge_commands.tooling.get_tooling_statuses",
            return_value={"codex": {"installed": True, "version": ""}},
        ) as get_tooling_statuses_mock:
            snapshot = ui_bridge.tooling_snapshot_payload(
                codex_snapshot_service=fake_service,
                force_refresh=False,
                prefer_cached=True,
            )

        get_tooling_statuses_mock.assert_called_once_with(force_refresh=False, startup_safe=True)
        self.assertTrue(snapshot["tooling_statuses"]["codex"]["installed"])

    def test_tooling_snapshot_payload_refreshes_tooling_without_refreshing_codex(self) -> None:
        fake_service = mock.Mock(
            peek_snapshot=mock.Mock(return_value=fake_codex_snapshot()),
            get_snapshot=mock.Mock(side_effect=AssertionError("codex refresh should be skipped")),
        )
        with mock.patch(
            "jakal_flow.ui_bridge_commands.tooling.provider_statuses_payload",
            return_value={"openai": {"available": True}},
        ), mock.patch(
            "jakal_flow.ui_bridge_commands.tooling.get_tooling_statuses",
            return_value={"ollama": {"installed": True, "version": "0.6.0"}},
        ) as get_tooling_statuses_mock:
            snapshot = ui_bridge.tooling_snapshot_payload(
                codex_snapshot_service=fake_service,
                force_refresh=True,
                refresh_codex_status=False,
            )

        fake_service.get_snapshot.assert_not_called()
        get_tooling_statuses_mock.assert_called_once_with(
            force_refresh=True,
            include_ollama_details=False,
        )
        self.assertTrue(snapshot["codex_status"]["available"])
        self.assertTrue(snapshot["tooling_statuses"]["ollama"]["installed"])


if __name__ == "__main__":
    unittest.main()
