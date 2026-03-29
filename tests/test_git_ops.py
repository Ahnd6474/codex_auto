from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
import shutil
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

    def test_changed_files_ignores_untracked_tmp_scratch_directories(self) -> None:
        repo_dir = Path(__file__).resolve().parents[1] / ".tmp_git_ops_runtime_scratch_filter_test"
        shutil.rmtree(repo_dir, ignore_errors=True)
        git = GitOps()
        git.ensure_repository(repo_dir, "main")
        git.configure_local_identity(repo_dir, "Test User", "test@example.com")
        (repo_dir / "README.md").write_text("seed\n", encoding="utf-8")
        git.create_initial_commit(repo_dir, "Initial commit")
        (repo_dir / "_tmp_remote_experiment_repo").mkdir(parents=True, exist_ok=True)
        (repo_dir / "_tmp_remote_experiment_repo" / "README.md").write_text("scratch\n", encoding="utf-8")
        (repo_dir / "docs").mkdir(parents=True, exist_ok=True)
        (repo_dir / "docs" / "guide.md").write_text("tracked change\n", encoding="utf-8")

        try:
            changed_files = git.changed_files(repo_dir)
            has_changes = git.has_changes(repo_dir)
        finally:
            shutil.rmtree(repo_dir, ignore_errors=True)

        self.assertEqual(len(changed_files), 1)
        self.assertTrue(changed_files[0].endswith("docs/"))
        self.assertNotIn("_tmp_remote_experiment_repo", changed_files[0])
        self.assertTrue(has_changes)

    def test_has_changes_returns_false_for_only_untracked_tmp_scratch_directories(self) -> None:
        repo_dir = Path(__file__).resolve().parents[1] / ".tmp_git_ops_runtime_only_scratch_filter_test"
        shutil.rmtree(repo_dir, ignore_errors=True)
        git = GitOps()
        git.ensure_repository(repo_dir, "main")
        git.configure_local_identity(repo_dir, "Test User", "test@example.com")
        (repo_dir / "README.md").write_text("seed\n", encoding="utf-8")
        git.create_initial_commit(repo_dir, "Initial commit")
        (repo_dir / "_tmp_remote_experiment_repo").mkdir(parents=True, exist_ok=True)
        (repo_dir / "_tmp_remote_experiment_repo" / "README.md").write_text("scratch\n", encoding="utf-8")

        try:
            changed_files = git.changed_files(repo_dir)
            has_changes = git.has_changes(repo_dir)
        finally:
            shutil.rmtree(repo_dir, ignore_errors=True)

        self.assertEqual(changed_files, [])
        self.assertFalse(has_changes)

    def test_run_filters_benign_line_ending_warnings_from_stderr(self) -> None:
        repo_dir = Path(__file__).resolve().parents[1]
        git = GitOps()
        completed = subprocess.CompletedProcess(
            args=["git", "status", "--short"],
            returncode=0,
            stdout=b"",
            stderr=(
                b"warning: in the working copy of 'README.md', LF will be replaced by CRLF the next time Git touches it\n"
                b"fatal: unrelated\n"
            ),
        )

        with mock.patch("jakal_flow.git_ops.run_subprocess", return_value=completed):
            result = git.run(["status", "--short"], cwd=repo_dir, check=False)

        self.assertEqual(result.stderr, "fatal: unrelated\n")

    def test_add_worktree_recovers_missing_registered_path_and_reuses_existing_branch(self) -> None:
        repo_dir = Path(__file__).resolve().parents[1]
        worktree_dir = repo_dir / ".tmp_stale_worktree" / "repo"
        git = GitOps()
        calls: list[list[str]] = []
        state = {"failed_once": False}

        def fake_run(
            args: list[str],
            cwd: Path,
            check: bool = True,
            env: dict[str, str] | None = None,
        ) -> CommandResult:
            calls.append(args)
            if args == ["worktree", "add", "-b", "feature", str(worktree_dir), "main"] and not state["failed_once"]:
                state["failed_once"] = True
                raise GitCommandError(
                    f"git worktree add -b feature {worktree_dir} main failed with code 128: "
                    f"fatal: '{worktree_dir.as_posix()}' is a missing but already registered worktree"
                )
            if args == ["worktree", "remove", "--force", str(worktree_dir)]:
                return CommandResult(command=["git", *args], returncode=0, stdout="", stderr="")
            if args == ["worktree", "prune"]:
                return CommandResult(command=["git", *args], returncode=0, stdout="", stderr="")
            if args == ["rev-parse", "--verify", "refs/heads/feature"]:
                return CommandResult(command=["git", *args], returncode=0, stdout="abc123\n", stderr="")
            if args == ["worktree", "add", str(worktree_dir), "feature"]:
                return CommandResult(command=["git", *args], returncode=0, stdout="", stderr="")
            raise AssertionError(f"Unexpected git command: {args}")

        with mock.patch.object(git, "run", side_effect=fake_run):
            git.add_worktree(repo_dir, worktree_dir, "feature", "main")

        self.assertEqual(
            calls,
            [
                ["worktree", "add", "-b", "feature", str(worktree_dir), "main"],
                ["worktree", "remove", "--force", str(worktree_dir)],
                ["worktree", "prune"],
                ["rev-parse", "--verify", "refs/heads/feature"],
                ["worktree", "add", str(worktree_dir), "feature"],
            ],
        )

    def test_attach_worktree_recovers_missing_registered_path(self) -> None:
        repo_dir = Path(__file__).resolve().parents[1]
        worktree_dir = repo_dir / ".tmp_stale_attach_worktree" / "repo"
        git = GitOps()
        calls: list[list[str]] = []
        state = {"failed_once": False}

        def fake_run(
            args: list[str],
            cwd: Path,
            check: bool = True,
            env: dict[str, str] | None = None,
        ) -> CommandResult:
            calls.append(args)
            if args == ["worktree", "add", str(worktree_dir), "feature"] and not state["failed_once"]:
                state["failed_once"] = True
                raise GitCommandError(
                    f"git worktree add {worktree_dir} feature failed with code 128: "
                    f"fatal: '{worktree_dir.as_posix()}' is a missing but already registered worktree"
                )
            if args == ["worktree", "remove", "--force", str(worktree_dir)]:
                return CommandResult(command=["git", *args], returncode=0, stdout="", stderr="")
            if args == ["worktree", "prune"]:
                return CommandResult(command=["git", *args], returncode=0, stdout="", stderr="")
            if args == ["worktree", "add", str(worktree_dir), "feature"]:
                return CommandResult(command=["git", *args], returncode=0, stdout="", stderr="")
            raise AssertionError(f"Unexpected git command: {args}")

        with mock.patch.object(git, "run", side_effect=fake_run):
            git.attach_worktree(repo_dir, worktree_dir, "feature")

        self.assertEqual(
            calls,
            [
                ["worktree", "add", str(worktree_dir), "feature"],
                ["worktree", "remove", "--force", str(worktree_dir)],
                ["worktree", "prune"],
                ["worktree", "add", str(worktree_dir), "feature"],
            ],
        )


if __name__ == "__main__":
    unittest.main()
