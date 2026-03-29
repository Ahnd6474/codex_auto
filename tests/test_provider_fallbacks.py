from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jakal_flow.models import RuntimeOptions
from jakal_flow.provider_fallbacks import (
    build_provider_fallback_runtimes,
    is_provider_fallbackable_error,
    is_quota_exhaustion_error,
)


class ProviderFallbackTests(unittest.TestCase):
    def test_quota_exhaustion_detection_matches_provider_errors(self) -> None:
        self.assertTrue(is_quota_exhaustion_error("You have exhausted your capacity on this model."))
        self.assertTrue(is_quota_exhaustion_error("Codex quota window is exhausted."))
        self.assertFalse(is_quota_exhaustion_error("syntax error in generated patch"))

    def test_provider_fallbackable_detection_accepts_auth_and_connectivity_failures(self) -> None:
        self.assertTrue(is_provider_fallbackable_error("Please set an Auth method in your Gemini settings."))
        self.assertTrue(is_provider_fallbackable_error("connection refused"))
        self.assertTrue(is_provider_fallbackable_error("Error when talking to Gemini API"))
        self.assertTrue(is_provider_fallbackable_error("ModelNotFoundError: Requested entity was not found."))
        self.assertFalse(is_provider_fallbackable_error("pytest assertions failed"))

    def test_build_provider_fallback_runtimes_prefers_remote_then_local(self) -> None:
        runtime = RuntimeOptions(
            model_provider="gemini",
            model="gemini-2.5-flash",
            effort="medium",
        )

        fallbacks = build_provider_fallback_runtimes(
            runtime,
            current_provider="gemini",
            local_models=[
                {
                    "provider": "oss",
                    "local_provider": "ollama",
                    "model": "qwen2.5-coder:7b",
                    "installed": True,
                }
            ],
        )

        providers = [item.model_provider for item in fallbacks[:4]]
        self.assertEqual(providers[:3], ["openai", "claude", "qwen_code"])
        self.assertEqual(fallbacks[-1].model_provider, "local_openai")
        self.assertEqual(fallbacks[-2].model_provider, "oss")
        self.assertEqual(fallbacks[-2].local_model_provider, "ollama")
        self.assertEqual(fallbacks[-2].model, "qwen2.5-coder:7b")


if __name__ == "__main__":
    unittest.main()
