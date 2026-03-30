from __future__ import annotations

import unittest

from jakal_flow.reporting import Reporter
from jakal_flow.utils import stable_repo_identity


class FailureSummaryTests(unittest.TestCase):
    def test_summarize_logged_result_recovers_failure_cause_from_diagnostics(self) -> None:
        summary = Reporter.summarize_logged_result(
            block_entry={"status": "failed", "test_summary": "Lineage worker finished."},
            pass_entry={
                "codex_diagnostics": {
                    "attempts": [
                        {
                            "attempt": 1,
                            "stderr_excerpt": (
                                "YOLO mode is enabled. All tool calls will be automatically approved.\n"
                                "Loaded cached credentials.\n"
                                "TerminalQuotaError: You have exhausted your capacity on this model."
                            ),
                        }
                    ]
                }
            },
            completed_summary="Lineage worker finished.",
            failed_summary="Lineage worker failed.",
        )

        self.assertEqual(
            summary,
            "Lineage worker failed. Cause: TerminalQuotaError: You have exhausted your capacity on this model.",
        )

    def test_summarize_logged_result_uses_test_results_summary(self) -> None:
        summary = Reporter.summarize_logged_result(
            block_entry={"status": "failed", "test_summary": ""},
            pass_entry={"test_results": {"summary": "python -m pytest exited with 1"}},
            completed_summary="Parallel worker finished.",
            failed_summary="Parallel worker failed.",
        )

        self.assertEqual(summary, "Parallel worker failed. Cause: python -m pytest exited with 1")

    def test_logged_pass_failure_detail_falls_back_to_structured_failure_fields(self) -> None:
        detail = Reporter.logged_pass_failure_detail(
            {
                "failure_type": "ExecutionPreflightError",
                "failure_reason_code": "preflight_failed",
            }
        )

        self.assertEqual(detail, "ExecutionPreflightError / preflight_failed")


class StableRepoIdentityTests(unittest.TestCase):
    def test_stable_repo_identity_uses_short_ascii_slug_for_windows_local_path(self) -> None:
        _repo_id, slug = stable_repo_identity(r"C:\Users\ahnd6\OneDrive\문서\GitHub\lit", "main")

        self.assertTrue(slug.startswith("lit-main-"))
        self.assertTrue(all(ord(char) < 128 for char in slug))
        self.assertNotIn("users", slug)
        self.assertNotIn("onedrive", slug)


if __name__ == "__main__":
    unittest.main()
