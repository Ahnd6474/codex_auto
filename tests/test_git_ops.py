from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jakal_flow.git_ops import GitOps
from jakal_flow.models import CommandResult


class GitOpsTests(unittest.TestCase):
    def test_ensure_repository_skips_checkout_when_target_branch_is_already_current(self) -> None:
        repo_dir = Path(__file__).resolve().parents[1] / ".tmp_git_ops_branch_test"
        git = GitOps()
        calls: list[list[str]] = []

        def fake_run(args: list[str], cwd: Path, check: bool = True) -> CommandResult:
            calls.append(args)
            if args == ["init"]:
                return CommandResult(command=["git", *args], returncode=0, stdout="", stderr="")
            if args == ["branch", "--show-current"]:
                return CommandResult(command=["git", *args], returncode=0, stdout="main\n", stderr="")
            raise AssertionError(f"Unexpected git command: {args}")

        with mock.patch.object(git, "is_git_repository", return_value=False), mock.patch.object(
            git,
            "run",
            side_effect=fake_run,
        ):
            created = git.ensure_repository(repo_dir, "main")

        self.assertTrue(created)
        self.assertEqual(calls, [["init"], ["branch", "--show-current"]])


if __name__ == "__main__":
    unittest.main()
