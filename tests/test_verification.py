from __future__ import annotations

import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jakal_flow.models import RuntimeOptions
from jakal_flow.verification import VerificationRunner
from jakal_flow.workspace import WorkspaceManager


class VerificationRunnerTests(unittest.TestCase):
    def _build_context(self, temp_root: Path):
        workspace = WorkspaceManager(temp_root / "workspace")
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        return workspace.initialize_local_project(
            project_dir=repo_dir,
            branch="main",
            runtime=RuntimeOptions(test_cmd="python -m pytest"),
        )

    def test_verification_runner_reuses_cached_result_for_identical_state(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_verification_cache_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        try:
            context = self._build_context(temp_root)
            runner = VerificationRunner()
            completed = subprocess.CompletedProcess(
                args=["python", "-m", "pytest"],
                returncode=0,
                stdout=b"green\n",
                stderr=b"",
            )

            with mock.patch.object(runner, "_compute_state_fingerprint", return_value="state-a"), mock.patch.object(
                runner,
                "_environment_fingerprint",
                return_value="env-a",
            ), mock.patch("jakal_flow.verification.subprocess.run", return_value=completed) as mocked_run:
                first = runner.run(context=context, block_index=1, label="block-search-pass", command="python -m pytest")
                second = runner.run(context=context, block_index=2, label="block-search-pass", command="python -m pytest")

            self.assertEqual(mocked_run.call_count, 1)
            self.assertFalse(first.cache_hit)
            self.assertTrue(second.cache_hit)
            self.assertEqual(first.cache_key, second.cache_key)
            self.assertIn("(cached)", second.summary)
            self.assertEqual(second.stdout_file.read_text(encoding="utf-8"), "green\n")
            self.assertTrue((context.paths.state_dir / "verification_cache" / f"{first.cache_key}.json").exists())
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

    def test_verification_runner_invalidates_cache_when_state_changes(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_verification_invalidate_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        try:
            context = self._build_context(temp_root)
            runner = VerificationRunner()
            completed = subprocess.CompletedProcess(
                args=["python", "-m", "pytest"],
                returncode=0,
                stdout=b"green\n",
                stderr=b"",
            )

            with mock.patch.object(runner, "_compute_state_fingerprint", side_effect=["state-a", "state-b"]), mock.patch.object(
                runner,
                "_environment_fingerprint",
                return_value="env-a",
            ), mock.patch("jakal_flow.verification.subprocess.run", return_value=completed) as mocked_run:
                first = runner.run(context=context, block_index=1, label="block-search-pass", command="python -m pytest")
                second = runner.run(context=context, block_index=2, label="block-search-pass", command="python -m pytest")

            self.assertEqual(mocked_run.call_count, 2)
            self.assertFalse(first.cache_hit)
            self.assertFalse(second.cache_hit)
            self.assertNotEqual(first.cache_key, second.cache_key)
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
