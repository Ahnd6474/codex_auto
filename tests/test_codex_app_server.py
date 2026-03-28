from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jakal_flow.codex_app_server import fetch_codex_backend_snapshot, resolve_codex_path


class _FakeSession:
    def __init__(self, codex_path: str) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def request(self, method: str, params: dict[str, object] | None = None) -> dict[str, object]:
        payload = params or {}
        self.calls.append((method, payload))
        if method == "account/read":
            return {
                "account": {
                    "type": "chatgpt",
                    "email": "demo@example.com",
                    "planType": "pro",
                },
                "requiresOpenaiAuth": True,
            }
        if method == "account/rateLimits/read":
            return {
                "rateLimits": {
                    "limitId": "codex",
                    "planType": "pro",
                    "primary": {
                        "usedPercent": 25,
                        "windowDurationMins": 300,
                        "resetsAt": 1774494924,
                    },
                }
            }
        if method == "model/list":
            return {
                "data": [
                    {
                        "id": "gpt-5.3-codex-spark",
                        "model": "gpt-5.3-codex-spark",
                        "displayName": "GPT-5.3-Codex-Spark",
                        "description": "Ultra-fast coding model.",
                        "hidden": False,
                        "isDefault": False,
                        "defaultReasoningEffort": "high",
                        "supportedReasoningEfforts": [
                            {"reasoningEffort": "low"},
                            {"reasoningEffort": "high"},
                        ],
                        "inputModalities": ["text"],
                        "supportsPersonality": True,
                    }
                ],
                "nextCursor": None,
            }
        raise AssertionError(f"Unexpected request: {method}")


class CodexAppServerTests(unittest.TestCase):
    def test_resolve_codex_path_uses_platform_default_when_blank(self) -> None:
        with mock.patch("jakal_flow.codex_app_server.default_codex_path", return_value="codex"):
            self.assertEqual(resolve_codex_path(""), "codex")
            self.assertEqual(resolve_codex_path("   "), "codex")

    def test_fetch_codex_backend_snapshot_formats_models_and_rate_limits(self) -> None:
        with mock.patch("jakal_flow.codex_app_server._CodexAppServerSession", _FakeSession), mock.patch(
            "jakal_flow.codex_app_server.discover_local_model_catalog",
            return_value=[],
        ):
            snapshot = fetch_codex_backend_snapshot("codex.cmd")

        self.assertTrue(snapshot.available)
        self.assertEqual(snapshot.account["email"], "demo@example.com")
        self.assertEqual(snapshot.account["plan_type"], "pro")
        self.assertEqual(snapshot.rate_limits["items"][0]["primary"]["remaining_percent"], 75)
        self.assertEqual(snapshot.model_catalog[0]["model"], "auto")
        self.assertEqual(snapshot.model_catalog[1]["model"], "gpt-5.3-codex-spark")
        self.assertEqual(snapshot.model_catalog[1]["supported_reasoning_efforts"], ["low", "high"])
        self.assertIn("gemini-2.5-pro", [item["model"] for item in snapshot.model_catalog if item.get("provider") == "gemini"])

    def test_fetch_codex_backend_snapshot_returns_fallback_when_app_server_fails(self) -> None:
        with mock.patch("jakal_flow.codex_app_server._CodexAppServerSession", side_effect=RuntimeError("boom")), mock.patch(
            "jakal_flow.codex_app_server.discover_local_model_catalog",
            return_value=[],
        ):
            snapshot = fetch_codex_backend_snapshot("codex.cmd")

        self.assertFalse(snapshot.available)
        self.assertEqual(snapshot.model_catalog[0]["model"], "auto")
        self.assertIn("boom", snapshot.error)

    def test_fetch_codex_backend_snapshot_appends_local_models(self) -> None:
        local_entry = {
            "id": "ollama:qwen2.5-coder:0.5b",
            "model": "qwen2.5-coder:0.5b",
            "display_name": "qwen2.5-coder:0.5b (Ollama)",
            "description": "Local Ollama model",
            "hidden": False,
            "is_default": False,
            "default_reasoning_effort": "medium",
            "supported_reasoning_efforts": ["low", "medium", "high", "xhigh"],
            "provider": "oss",
            "local_provider": "ollama",
        }
        with mock.patch("jakal_flow.codex_app_server._CodexAppServerSession", _FakeSession), mock.patch(
            "jakal_flow.codex_app_server.discover_local_model_catalog",
            return_value=[local_entry],
        ):
            snapshot = fetch_codex_backend_snapshot("codex.cmd")

        self.assertTrue(snapshot.available)
        self.assertEqual(snapshot.model_catalog[-1]["model"], "qwen2.5-coder:0.5b")
        self.assertEqual(snapshot.model_catalog[-1]["provider"], "oss")

    def test_fetch_codex_backend_snapshot_stays_available_with_local_models_when_codex_fails(self) -> None:
        local_entry = {
            "id": "ollama:qwen2.5-coder:0.5b",
            "model": "qwen2.5-coder:0.5b",
            "display_name": "qwen2.5-coder:0.5b (Ollama)",
            "description": "Local Ollama model",
            "hidden": False,
            "is_default": False,
            "default_reasoning_effort": "medium",
            "supported_reasoning_efforts": ["low", "medium", "high", "xhigh"],
            "provider": "oss",
            "local_provider": "ollama",
        }
        with mock.patch("jakal_flow.codex_app_server._CodexAppServerSession", side_effect=RuntimeError("boom")), mock.patch(
            "jakal_flow.codex_app_server.discover_local_model_catalog",
            return_value=[local_entry],
        ):
            snapshot = fetch_codex_backend_snapshot("codex.cmd")

        self.assertTrue(snapshot.available)
        self.assertIn("qwen2.5-coder:0.5b", [item["model"] for item in snapshot.model_catalog if item.get("provider") == "oss"])
        self.assertIn("boom", snapshot.error)

    def test_fetch_codex_backend_snapshot_supports_gemini_cli(self) -> None:
        with mock.patch(
            "jakal_flow.codex_app_server.subprocess.run",
            return_value=subprocess.CompletedProcess(["gemini", "--version"], 0, stdout="0.1.0\n", stderr=""),
        ):
            snapshot = fetch_codex_backend_snapshot("gemini")

        self.assertTrue(snapshot.available)
        self.assertEqual(snapshot.account["type"], "gemini-cli")
        self.assertEqual(snapshot.account["version"], "0.1.0")
        self.assertIn("gemini-3-flash-preview", [item["model"] for item in snapshot.model_catalog if item.get("provider") == "gemini"])
        self.assertEqual(snapshot.error, "")

    def test_fetch_codex_backend_snapshot_supports_claude_code(self) -> None:
        def fake_run(command, **_kwargs):
            if command[-1] == "--version":
                return subprocess.CompletedProcess(command, 0, stdout="1.2.3\n", stderr="")
            if command[-2:] == ["auth", "status"]:
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout='{"authenticated": true, "email": "demo@example.com", "planType": "pro"}',
                    stderr="",
                )
            raise AssertionError(f"Unexpected command: {command}")

        with mock.patch("jakal_flow.codex_app_server.subprocess.run", side_effect=fake_run):
            snapshot = fetch_codex_backend_snapshot("claude")

        self.assertTrue(snapshot.available)
        self.assertEqual(snapshot.account["authenticated"], True)
        self.assertEqual(snapshot.account["email"], "demo@example.com")
        self.assertEqual(snapshot.account["plan_type"], "pro")
        self.assertEqual(snapshot.account["type"], "claude-code")
        self.assertEqual(snapshot.account["version"], "1.2.3")
        self.assertIn("claude-sonnet-4-6", [item["model"] for item in snapshot.model_catalog if item.get("provider") == "claude"])
        self.assertEqual(snapshot.error, "")

    def test_fetch_codex_backend_snapshot_supports_qwen_code(self) -> None:
        with mock.patch(
            "jakal_flow.codex_app_server.subprocess.run",
            return_value=subprocess.CompletedProcess(["qwen", "--version"], 0, stdout="0.13.1\n", stderr=""),
        ):
            snapshot = fetch_codex_backend_snapshot("qwen")

        self.assertTrue(snapshot.available)
        self.assertEqual(snapshot.account["type"], "qwen-code")
        self.assertEqual(snapshot.account["version"], "0.13.1")
        self.assertIn("qwen3-coder-plus", [item["model"] for item in snapshot.model_catalog if item.get("provider") == "qwen_code"])
        self.assertEqual(snapshot.error, "")


if __name__ == "__main__":
    unittest.main()
