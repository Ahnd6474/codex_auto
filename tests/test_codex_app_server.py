from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codex_auto.codex_app_server import fetch_codex_backend_snapshot


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
    def test_fetch_codex_backend_snapshot_formats_models_and_rate_limits(self) -> None:
        with mock.patch("codex_auto.codex_app_server._CodexAppServerSession", _FakeSession):
            snapshot = fetch_codex_backend_snapshot("codex.cmd")

        self.assertTrue(snapshot.available)
        self.assertEqual(snapshot.account["email"], "demo@example.com")
        self.assertEqual(snapshot.account["plan_type"], "pro")
        self.assertEqual(snapshot.rate_limits["items"][0]["primary"]["remaining_percent"], 75)
        self.assertEqual(snapshot.model_catalog[0]["model"], "auto")
        self.assertEqual(snapshot.model_catalog[1]["model"], "gpt-5.3-codex-spark")
        self.assertEqual(snapshot.model_catalog[1]["supported_reasoning_efforts"], ["low", "high"])

    def test_fetch_codex_backend_snapshot_returns_fallback_when_app_server_fails(self) -> None:
        with mock.patch("codex_auto.codex_app_server._CodexAppServerSession", side_effect=RuntimeError("boom")):
            snapshot = fetch_codex_backend_snapshot("codex.cmd")

        self.assertFalse(snapshot.available)
        self.assertEqual(snapshot.model_catalog[0]["model"], "auto")
        self.assertIn("boom", snapshot.error)


if __name__ == "__main__":
    unittest.main()
