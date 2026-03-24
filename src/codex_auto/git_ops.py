from __future__ import annotations

import subprocess
from pathlib import Path

from .models import CommandResult


class GitCommandError(RuntimeError):
    pass


class GitOps:
    def run(self, args: list[str], cwd: Path, check: bool = True) -> CommandResult:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
        )
        result = CommandResult(
            command=["git", *args],
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
        if check and completed.returncode != 0:
            raise GitCommandError(
                f"git {' '.join(args)} failed with code {completed.returncode}: {completed.stderr.strip()}"
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

    def configure_local_identity(self, repo_dir: Path, name: str, email: str) -> None:
        self.run(["config", "user.name", name], cwd=repo_dir)
        self.run(["config", "user.email", email], cwd=repo_dir)

    def current_revision(self, repo_dir: Path) -> str:
        return self.run(["rev-parse", "HEAD"], cwd=repo_dir).stdout.strip()

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

    def push(self, repo_dir: Path, branch: str) -> None:
        self.run(["push", "origin", branch], cwd=repo_dir)

    def hard_reset(self, repo_dir: Path, revision: str) -> None:
        self.run(["reset", "--hard", revision], cwd=repo_dir)
        self.run(["clean", "-fd"], cwd=repo_dir)
