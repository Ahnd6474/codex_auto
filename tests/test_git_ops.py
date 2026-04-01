from __future__ import annotations

import subprocess
import sys
import os
import tempfile
import unittest
import shutil
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jakal_flow.errors import SubprocessTimeoutError
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

    def test_current_branch_reads_head_without_git_subprocess(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        repo_dir = Path(temp_dir.name)
        git = GitOps()
        (repo_dir / ".git").mkdir(parents=True, exist_ok=True)
        (repo_dir / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

        try:
            with mock.patch.object(git, "run", side_effect=AssertionError("git subprocess should not run")):
                branch = git.current_branch(repo_dir)
        finally:
            temp_dir.cleanup()

        self.assertEqual(branch, "main")

    def test_current_revision_reads_head_without_git_subprocess(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        repo_dir = Path(temp_dir.name)
        git = GitOps()
        revision = "0123456789abcdef0123456789abcdef01234567"
        (repo_dir / ".git" / "refs" / "heads").mkdir(parents=True, exist_ok=True)
        (repo_dir / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        (repo_dir / ".git" / "refs" / "heads" / "main").write_text(f"{revision}\n", encoding="utf-8")

        try:
            with mock.patch.object(git, "run", side_effect=AssertionError("git subprocess should not run")):
                head_revision = git.current_revision(repo_dir)
        finally:
            temp_dir.cleanup()

        self.assertEqual(head_revision, revision)

    def test_has_commits_reads_head_without_git_subprocess(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        repo_dir = Path(temp_dir.name)
        git = GitOps()
        revision = "0123456789abcdef0123456789abcdef01234567"
        (repo_dir / ".git" / "refs" / "heads").mkdir(parents=True, exist_ok=True)
        (repo_dir / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        (repo_dir / ".git" / "refs" / "heads" / "main").write_text(f"{revision}\n", encoding="utf-8")

        try:
            with mock.patch.object(git, "run", side_effect=AssertionError("git subprocess should not run")):
                has_commits = git.has_commits(repo_dir)
        finally:
            temp_dir.cleanup()

        self.assertTrue(has_commits)

    def test_current_branch_returns_empty_when_git_queries_time_out(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        repo_dir = Path(temp_dir.name)
        git = GitOps()

        try:
            with mock.patch.object(
                git,
                "run",
                side_effect=SubprocessTimeoutError("Command timed out after 10.0 seconds: git branch --show-current"),
            ):
                branch = git.current_branch(repo_dir)
        finally:
            temp_dir.cleanup()

        self.assertEqual(branch, "")

    def test_remote_url_falls_back_to_git_config_when_query_times_out(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        repo_dir = Path(temp_dir.name)
        git = GitOps()
        (repo_dir / ".git").mkdir(parents=True, exist_ok=True)
        (repo_dir / ".git" / "config").write_text(
            '[remote "origin"]\n\turl = https://github.com/example/project.git\n',
            encoding="utf-8",
        )

        try:
            with mock.patch.object(
                git,
                "run",
                side_effect=SubprocessTimeoutError("Command timed out after 60.0 seconds: git remote get-url origin"),
            ):
                remote_url = git.remote_url(repo_dir)
        finally:
            temp_dir.cleanup()

        self.assertEqual(remote_url, "https://github.com/example/project.git")

    def test_remote_url_returns_none_when_query_times_out_without_configured_remote(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        repo_dir = Path(temp_dir.name)
        git = GitOps()
        (repo_dir / ".git").mkdir(parents=True, exist_ok=True)
        (repo_dir / ".git" / "config").write_text("", encoding="utf-8")

        try:
            with mock.patch.object(
                git,
                "run",
                side_effect=SubprocessTimeoutError("Command timed out after 60.0 seconds: git remote get-url origin"),
            ):
                remote_url = git.remote_url(repo_dir)
        finally:
            temp_dir.cleanup()

        self.assertIsNone(remote_url)

    def test_configure_local_identity_skips_matching_git_config_without_subprocess(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        repo_dir = Path(temp_dir.name)
        git = GitOps()
        (repo_dir / ".git").mkdir(parents=True, exist_ok=True)
        (repo_dir / ".git" / "config").write_text(
            "[user]\n\tname = Test User\n\temail = test@example.com\n",
            encoding="utf-8",
        )

        try:
            with mock.patch.object(git, "run", side_effect=AssertionError("git subprocess should not run")):
                git.configure_local_identity(repo_dir, "Test User", "test@example.com")
        finally:
            temp_dir.cleanup()

        self.assertEqual(
            git._configured_identity_cache[str(repo_dir.resolve())],
            ("Test User", "test@example.com"),
        )

    def test_configure_local_identity_updates_only_changed_field(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        repo_dir = Path(temp_dir.name)
        git = GitOps()
        (repo_dir / ".git").mkdir(parents=True, exist_ok=True)
        (repo_dir / ".git" / "config").write_text(
            "[user]\n\tname = Test User\n\temail = stale@example.com\n",
            encoding="utf-8",
        )
        calls: list[list[str]] = []

        def fake_run(
            args: list[str],
            cwd: Path,
            check: bool = True,
            env: dict[str, str] | None = None,
        ) -> CommandResult:
            calls.append(args)
            return CommandResult(command=["git", *args], returncode=0, stdout="", stderr="")

        try:
            with mock.patch.object(git, "run", side_effect=fake_run):
                git.configure_local_identity(repo_dir, "Test User", "test@example.com")
        finally:
            temp_dir.cleanup()

        self.assertEqual(calls, [["config", "user.email", "test@example.com"]])

    def test_set_remote_url_skips_matching_git_config_without_subprocess(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        repo_dir = Path(temp_dir.name)
        git = GitOps()
        (repo_dir / ".git").mkdir(parents=True, exist_ok=True)
        (repo_dir / ".git" / "config").write_text(
            '[remote "origin"]\n\turl = https://github.com/example/project.git\n',
            encoding="utf-8",
        )

        try:
            with mock.patch.object(git, "run", side_effect=AssertionError("git subprocess should not run")):
                git.set_remote_url(repo_dir, "origin", "https://github.com/example/project.git")
        finally:
            temp_dir.cleanup()

    def test_set_remote_url_updates_when_git_config_differs(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        repo_dir = Path(temp_dir.name)
        git = GitOps()
        (repo_dir / ".git").mkdir(parents=True, exist_ok=True)
        (repo_dir / ".git" / "config").write_text(
            '[remote "origin"]\n\turl = https://github.com/example/old.git\n',
            encoding="utf-8",
        )
        calls: list[list[str]] = []

        def fake_run(
            args: list[str],
            cwd: Path,
            check: bool = True,
            env: dict[str, str] | None = None,
        ) -> CommandResult:
            calls.append(args)
            return CommandResult(command=["git", *args], returncode=0, stdout="", stderr="")

        try:
            with mock.patch.object(git, "run", side_effect=fake_run):
                git.set_remote_url(repo_dir, "origin", "https://github.com/example/project.git")
        finally:
            temp_dir.cleanup()

        self.assertEqual(
            calls,
            [["remote", "set-url", "origin", "https://github.com/example/project.git"]],
        )

    def test_current_revision_returns_empty_when_git_query_times_out(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        repo_dir = Path(temp_dir.name)
        git = GitOps()

        try:
            with mock.patch.object(
                git,
                "run",
                side_effect=SubprocessTimeoutError("Command timed out after 10.0 seconds: git rev-parse HEAD"),
            ):
                revision = git.current_revision(repo_dir)
        finally:
            temp_dir.cleanup()

        self.assertEqual(revision, "")

    def test_has_commits_returns_false_when_git_query_times_out(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        repo_dir = Path(temp_dir.name)
        git = GitOps()

        try:
            with mock.patch.object(
                git,
                "run",
                side_effect=SubprocessTimeoutError("Command timed out after 10.0 seconds: git rev-parse --verify HEAD"),
            ):
                has_commits = git.has_commits(repo_dir)
        finally:
            temp_dir.cleanup()

        self.assertFalse(has_commits)

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

        with mock.patch.object(git, "_current_revision_from_head", return_value=""), mock.patch.object(
            git,
            "run",
            side_effect=fake_run,
        ):
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

        with mock.patch.object(git, "_current_revision_from_head", return_value=""), mock.patch.object(
            git,
            "run",
            side_effect=fake_run,
        ):
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

    def test_commit_paths_uses_custom_author_name(self) -> None:
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
                return CommandResult(command=["git", *args], returncode=0, stdout="setup123\n", stderr="")
            return CommandResult(command=["git", *args], returncode=0, stdout="", stderr="")

        with mock.patch.object(git, "_current_revision_from_head", return_value=""), mock.patch.object(
            git,
            "run",
            side_effect=fake_run,
        ):
            revision = git.commit_paths(
                repo_dir,
                [".gitignore"],
                "Demo environment setup",
                author_name="Jakal-Flow-setup",
            )

        self.assertEqual(revision, "setup123")
        self.assertEqual(calls[0], (["add", "--", ".gitignore"], None))
        self.assertEqual(
            calls[1],
            (
                ["commit", "-m", "Demo environment setup", "--", ".gitignore"],
                {
                    "GIT_AUTHOR_NAME": "Jakal-Flow-setup",
                    "GIT_COMMITTER_NAME": "Jakal-Flow-setup",
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
        temp_dir = tempfile.TemporaryDirectory()
        repo_dir = Path(temp_dir.name)
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
            temp_dir.cleanup()

        self.assertEqual(len(changed_files), 1)
        self.assertEqual(changed_files[0].replace("\\", "/").rstrip("/"), "docs")
        self.assertNotIn("_tmp_remote_experiment_repo", changed_files[0])
        self.assertTrue(has_changes)

    def test_has_changes_returns_false_for_only_untracked_tmp_scratch_directories(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        repo_dir = Path(temp_dir.name)
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
            temp_dir.cleanup()

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

    def test_safe_directory_args_are_limited_to_repo_path(self) -> None:
        repo_dir = Path(__file__).resolve().parents[1]
        git = GitOps()

        args = git._safe_directory_args(repo_dir)

        self.assertEqual(args, ["-c", f"safe.directory={repo_dir.resolve().as_posix()}"])

    def test_run_does_not_add_parent_safe_directories_for_remote_queries(self) -> None:
        repo_dir = Path(__file__).resolve().parents[1]
        git = GitOps()
        observed_command: list[str] | None = None

        def fake_run_subprocess(command, cwd, capture_output, check, env, timeout_seconds):
            nonlocal observed_command
            observed_command = list(command)
            return subprocess.CompletedProcess(args=command, returncode=0, stdout=b"origin\n", stderr=b"")

        with mock.patch("jakal_flow.git_ops.run_subprocess", side_effect=fake_run_subprocess):
            result = git.run(["remote"], cwd=repo_dir, check=False)

        self.assertEqual(result.stdout, "origin\n")
        self.assertIsNotNone(observed_command)
        assert observed_command is not None
        safe_directory_values = [
            observed_command[index + 1]
            for index, part in enumerate(observed_command[:-1])
            if part == "-c" and str(observed_command[index + 1]).startswith("safe.directory=")
        ]
        self.assertEqual(safe_directory_values, [f"safe.directory={repo_dir.resolve().as_posix()}"])

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

    def test_add_worktree_repairs_stale_registered_worktree_path(self) -> None:
        fd, git_file_path = tempfile.mkstemp()
        os.close(fd)
        git_file = Path(git_file_path)
        repo_dir = Path("C:/Users/ahnd6/OneDrive/문서/GitHub/lit")
        worktree_dir = Path("C:/Users/ahnd6/OneDrive/문서/GitHub/lit/worktree")
        git = GitOps()
        expected_gitdir = repo_dir.resolve() / ".git" / "worktrees" / worktree_dir.name
        stale_gitdir = Path("C:/Users/ahnd6/OneDrive/문서/GitHub/lit/.git/worktrees/repo")
        git_file.write_text(f"gitdir: {stale_gitdir.as_posix()}\n", encoding="utf-8")

        try:
            with mock.patch.object(git, "_worktree_git_file", return_value=git_file), mock.patch.object(
                Path,
                "mkdir",
                return_value=None,
            ), mock.patch.object(git, "run", side_effect=AssertionError("git subprocess should not run")):
                git.add_worktree(repo_dir, worktree_dir, "feature", "main")

            self.assertEqual(
                git_file.read_text(encoding="utf-8"),
                f"gitdir: {expected_gitdir.as_posix()}\n",
            )
        finally:
            git_file.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
