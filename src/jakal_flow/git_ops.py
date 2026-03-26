from __future__ import annotations

import subprocess
import shutil
from pathlib import Path

from .models import CommandResult
from .utils import decode_process_output


class GitCommandError(RuntimeError):
    pass


class GitOps:
    def _safe_directory_args(self, cwd: Path) -> list[str]:
        resolved = cwd.resolve()
        args: list[str] = []
        seen: set[str] = set()
        for candidate in (resolved, *resolved.parents):
            normalized = candidate.as_posix()
            if normalized in seen:
                continue
            seen.add(normalized)
            args.extend(["-c", f"safe.directory={normalized}"])
        return args

    def run(self, args: list[str], cwd: Path, check: bool = True) -> CommandResult:
        command = ["git", *self._safe_directory_args(cwd), *args]
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            check=False,
        )
        stdout = decode_process_output(completed.stdout)
        stderr = decode_process_output(completed.stderr)
        result = CommandResult(
            command=command,
            returncode=completed.returncode,
            stdout=stdout,
            stderr=stderr,
        )
        if check and completed.returncode != 0:
            raise GitCommandError(
                f"git {' '.join(args)} failed with code {completed.returncode}: {stderr.strip()}"
            )
        return result

    def clone_or_update(self, repo_url: str, branch: str, repo_dir: Path) -> None:
        if (repo_dir / ".git").exists():
            self.run(["fetch", "origin", branch], cwd=repo_dir)
            self.run(["checkout", branch], cwd=repo_dir)
            self.run(["pull", "--ff-only", "origin", branch], cwd=repo_dir)
            return
        repo_dir.parent.mkdir(parents=True, exist_ok=True)
        self.run(["clone", "--branch", branch, "--single-branch", repo_url, str(repo_dir)], cwd=repo_dir.parent)

    def is_git_repository(self, repo_dir: Path) -> bool:
        return (repo_dir / ".git").exists()

    def ensure_repository(self, repo_dir: Path, branch: str) -> bool:
        repo_dir.mkdir(parents=True, exist_ok=True)
        created = False
        if not self.is_git_repository(repo_dir):
            self.run(["init"], cwd=repo_dir)
            created = True
        if branch:
            current_branch = self.current_branch(repo_dir)
            if current_branch == branch:
                return created
            branch_check = self.run(["rev-parse", "--verify", branch], cwd=repo_dir, check=False)
            if branch_check.returncode == 0:
                self.run(["checkout", branch], cwd=repo_dir)
            else:
                self.run(["checkout", "-b", branch], cwd=repo_dir)
        return created

    def configure_local_identity(self, repo_dir: Path, name: str, email: str) -> None:
        self.run(["config", "user.name", name], cwd=repo_dir)
        self.run(["config", "user.email", email], cwd=repo_dir)

    def current_revision(self, repo_dir: Path) -> str:
        return self.run(["rev-parse", "HEAD"], cwd=repo_dir).stdout.strip()

    def has_commits(self, repo_dir: Path) -> bool:
        result = self.run(["rev-parse", "--verify", "HEAD"], cwd=repo_dir, check=False)
        return result.returncode == 0

    def current_branch(self, repo_dir: Path) -> str:
        result = self.run(["branch", "--show-current"], cwd=repo_dir, check=False)
        branch = result.stdout.strip()
        if branch:
            return branch
        fallback = self.run(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir, check=False).stdout.strip()
        return "" if fallback == "HEAD" else fallback

    def remote_url(self, repo_dir: Path, remote_name: str = "origin") -> str | None:
        result = self.run(["remote", "get-url", remote_name], cwd=repo_dir, check=False)
        url = result.stdout.strip()
        return url or None

    def set_remote_url(self, repo_dir: Path, remote_name: str, remote_url: str) -> None:
        existing = self.run(["remote"], cwd=repo_dir, check=False).stdout.splitlines()
        if remote_name in {item.strip() for item in existing}:
            self.run(["remote", "set-url", remote_name, remote_url], cwd=repo_dir)
            return
        self.run(["remote", "add", remote_name, remote_url], cwd=repo_dir)

    def has_changes(self, repo_dir: Path) -> bool:
        return bool(self.run(["status", "--porcelain"], cwd=repo_dir).stdout.strip())

    def changed_files(self, repo_dir: Path) -> list[str]:
        output = self.run(["status", "--porcelain"], cwd=repo_dir).stdout.splitlines()
        changed: list[str] = []
        for line in output:
            if len(line) >= 4:
                changed.append(line[3:].strip())
        return changed

    def commit_all(self, repo_dir: Path, message: str) -> str:
        self.run(["add", "-A"], cwd=repo_dir)
        self.run(["commit", "-m", message], cwd=repo_dir)
        return self.current_revision(repo_dir)

    def add_all(self, repo_dir: Path) -> None:
        self.run(["add", "-A"], cwd=repo_dir)

    def create_initial_commit(self, repo_dir: Path, message: str) -> str:
        self.run(["add", "-A"], cwd=repo_dir)
        self.run(["commit", "--allow-empty", "-m", message], cwd=repo_dir)
        return self.current_revision(repo_dir)

    def push(self, repo_dir: Path, branch: str) -> None:
        self.run(["push", "origin", branch], cwd=repo_dir)

    def add_worktree(self, repo_dir: Path, worktree_dir: Path, branch_name: str, start_point: str) -> None:
        worktree_dir.parent.mkdir(parents=True, exist_ok=True)
        self.run(["worktree", "add", "-b", branch_name, str(worktree_dir), start_point], cwd=repo_dir)

    def remove_worktree(self, repo_dir: Path, worktree_dir: Path, force: bool = True) -> None:
        args = ["worktree", "remove"]
        if force:
            args.append("--force")
        args.append(str(worktree_dir))
        self.run(args, cwd=repo_dir, check=False)
        shutil.rmtree(worktree_dir, ignore_errors=True)

    def delete_branch(self, repo_dir: Path, branch_name: str, force: bool = True) -> None:
        args = ["branch", "-D" if force else "-d", branch_name]
        self.run(args, cwd=repo_dir, check=False)

    def cherry_pick(self, repo_dir: Path, revision: str) -> None:
        self.run(["cherry-pick", revision], cwd=repo_dir)

    def try_cherry_pick(self, repo_dir: Path, revision: str) -> CommandResult:
        return self.run(["cherry-pick", revision], cwd=repo_dir, check=False)

    def abort_cherry_pick(self, repo_dir: Path) -> None:
        self.run(["cherry-pick", "--abort"], cwd=repo_dir, check=False)

    def continue_cherry_pick(self, repo_dir: Path) -> None:
        self.run(["cherry-pick", "--continue"], cwd=repo_dir)

    def cherry_pick_in_progress(self, repo_dir: Path) -> bool:
        result = self.run(["rev-parse", "-q", "--verify", "CHERRY_PICK_HEAD"], cwd=repo_dir, check=False)
        return result.returncode == 0

    def conflicted_files(self, repo_dir: Path) -> list[str]:
        result = self.run(["diff", "--name-only", "--diff-filter=U"], cwd=repo_dir, check=False)
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    def checkout_conflict_side(self, repo_dir: Path, side: str, paths: list[str]) -> None:
        if side not in {"ours", "theirs"}:
            raise ValueError(f"Unsupported conflict side: {side}")
        if not paths:
            return
        self.run(["checkout", f"--{side}", "--", *paths], cwd=repo_dir)
        self.run(["add", "--", *paths], cwd=repo_dir)

    def hard_reset(self, repo_dir: Path, revision: str) -> None:
        self.run(["reset", "--hard", revision], cwd=repo_dir)
        self.run(["clean", "-fd"], cwd=repo_dir)
