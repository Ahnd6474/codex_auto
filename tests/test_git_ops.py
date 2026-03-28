from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jakal_flow.git_ops import GitCommandError, GitOps
from jakal_flow.models import CommandResult


class GitOpsTests(unittest.TestCase):
    def _create_repo_with_merge_blocker(
        self,
        tracked_contents: str,
        working_tree_contents: str,
    ) -> tuple[GitOps, tempfile.TemporaryDirectory[str], Path]:
        temp_dir = tempfile.TemporaryDirectory()
        repo_dir = Path(temp_dir.name)
        git = GitOps()
        git.ensure_repository(repo_dir, "main")
        git.configure_local_identity(repo_dir, "Test User", "test@example.com")
        (repo_dir / "README.md").write_text("seed\n", encoding="utf-8")
        git.create_initial_commit(repo_dir, "Initial commit")
        git.run(["checkout", "-b", "feature"], cwd=repo_dir)
        (repo_dir / ".gitignore").write_text(tracked_contents, encoding="utf-8")
        git.commit_all(repo_dir, "Add ignore file")
        git.run(["checkout", "main"], cwd=repo_dir)
        (repo_dir / ".gitignore").write_text(working_tree_contents, encoding="utf-8")
        return git, temp_dir, repo_dir

    def test_ensure_repository_skips_checkout_when_target_branch_is_already_current(self) -> None:
        repo_dir = Path(__file__).resolve().parents[1] / ".tmp_git_ops_branch_test"
        git = GitOps()
        calls: list[list[str]] = []

        def fake_run(
            args: list[str],
            cwd: Path,
            check: bool = True,
            env: dict[str, str] | None = None,
        ) -> CommandResult:
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

    def test_commit_all_uses_custom_author_name(self) -> None:
        repo_dir = Path(__file__).resolve().parents[1]
        git = GitOps()
        calls: list[tuple[list[str], dict[str, str] | None]] = []

        def fake_run(
            args: list[str],
            cwd: Path,
            check: bool = True,
            env: dict[str, str] | None = None,
        ) -> CommandResult:
            calls.append((args, env))
            if args == ["rev-parse", "HEAD"]:
                return CommandResult(command=["git", *args], returncode=0, stdout="abc123\n", stderr="")
            return CommandResult(command=["git", *args], returncode=0, stdout="", stderr="")

        with mock.patch.object(git, "run", side_effect=fake_run):
            revision = git.commit_all(repo_dir, "Desktop slice", author_name="Jakal-Flow-node-a")

        self.assertEqual(revision, "abc123")
        self.assertEqual(calls[0], (["add", "-A"], None))
        self.assertEqual(
            calls[1],
            (
                ["commit", "-m", "Desktop slice"],
                {
                    "GIT_AUTHOR_NAME": "Jakal-Flow-node-a",
                    "GIT_COMMITTER_NAME": "Jakal-Flow-node-a",
                },
            ),
        )

    def test_commit_staged_uses_custom_author_name(self) -> None:
        repo_dir = Path(__file__).resolve().parents[1]
        git = GitOps()
        calls: list[tuple[list[str], dict[str, str] | None]] = []

        def fake_run(
            args: list[str],
            cwd: Path,
            check: bool = True,
            env: dict[str, str] | None = None,
        ) -> CommandResult:
            calls.append((args, env))
            if args == ["rev-parse", "HEAD"]:
                return CommandResult(command=["git", *args], returncode=0, stdout="merge123\n", stderr="")
            return CommandResult(command=["git", *args], returncode=0, stdout="", stderr="")

        with mock.patch.object(git, "run", side_effect=fake_run):
            revision = git.commit_staged(
                repo_dir,
                "Desktop slice, Backend slice conflict resolution",
                author_name="Jakal-Flow-merge-resolver",
            )

        self.assertEqual(revision, "merge123")
        self.assertEqual(
            calls[0],
            (
                ["commit", "-m", "Desktop slice, Backend slice conflict resolution"],
                {
                    "GIT_AUTHOR_NAME": "Jakal-Flow-merge-resolver",
                    "GIT_COMMITTER_NAME": "Jakal-Flow-merge-resolver",
                },
            ),
        )

    def test_merge_ff_only_retries_when_identical_untracked_file_blocks_merge(self) -> None:
        git, temp_dir, repo_dir = self._create_repo_with_merge_blocker(
            tracked_contents="node_modules/\n",
            working_tree_contents="node_modules/\n",
        )
        try:
            git.merge_ff_only(repo_dir, "feature")
            tracked_result = git.run(["ls-files", "--error-unmatch", ".gitignore"], cwd=repo_dir, check=False)
            status_result = git.run(["status", "--porcelain"], cwd=repo_dir, check=False)
        finally:
            temp_dir.cleanup()

        self.assertEqual(tracked_result.returncode, 0)
        self.assertEqual(status_result.stdout.strip(), "")

    def test_merge_ff_only_keeps_different_untracked_file_blocker(self) -> None:
        git, temp_dir, repo_dir = self._create_repo_with_merge_blocker(
            tracked_contents="node_modules/\n",
            working_tree_contents="dist/\n",
        )
        try:
            with self.assertRaises(GitCommandError):
                git.merge_ff_only(repo_dir, "feature")
            blocker_contents = (repo_dir / ".gitignore").read_text(encoding="utf-8")
        finally:
            temp_dir.cleanup()

        self.assertEqual(blocker_contents, "dist/\n")


if __name__ == "__main__":
    unittest.main()
