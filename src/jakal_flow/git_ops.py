from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .models import CommandResult
from .utils import decode_process_output, remove_tree


class GitCommandError(RuntimeError):
    pass


UNTRACKED_OVERWRITE_MARKER = "The following untracked working tree files would be overwritten by merge:"


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

    def _commit_env(self, author_name: str | None = None) -> dict[str, str] | None:
        normalized = str(author_name or "").strip()
        if not normalized:
            return None
        return {
            "GIT_AUTHOR_NAME": normalized,
            "GIT_COMMITTER_NAME": normalized,
        }

    def run(
        self,
        args: list[str],
        cwd: Path,
        check: bool = True,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        command = ["git", *self._safe_directory_args(cwd), *args]
        process_env = None
        if env:
            process_env = os.environ.copy()
            process_env.update(env)
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            check=False,
            env=process_env,
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

    def commit_all(self, repo_dir: Path, message: str, author_name: str | None = None) -> str:
        self.run(["add", "-A"], cwd=repo_dir)
        self.run(["commit", "-m", message], cwd=repo_dir, env=self._commit_env(author_name))
        return self.current_revision(repo_dir)

    def add_all(self, repo_dir: Path) -> None:
        self.run(["add", "-A"], cwd=repo_dir)

    def create_initial_commit(self, repo_dir: Path, message: str, author_name: str | None = None) -> str:
        self.run(["add", "-A"], cwd=repo_dir)
        self.run(["commit", "--allow-empty", "-m", message], cwd=repo_dir, env=self._commit_env(author_name))
        return self.current_revision(repo_dir)

    def commit_staged(self, repo_dir: Path, message: str, author_name: str | None = None) -> str:
        self.run(["commit", "-m", message], cwd=repo_dir, env=self._commit_env(author_name))
        return self.current_revision(repo_dir)

    def push(self, repo_dir: Path, branch: str) -> None:
        self.run(["push", "origin", branch], cwd=repo_dir)

    def branch_exists(self, repo_dir: Path, branch_name: str) -> bool:
        result = self.run(["rev-parse", "--verify", f"refs/heads/{branch_name}"], cwd=repo_dir, check=False)
        return result.returncode == 0

    def remote_branch_revision(self, repo_dir: Path, remote_name: str, branch: str) -> str | None:
        if not branch.strip():
            return None
        result = self.run(["ls-remote", "--heads", remote_name, branch], cwd=repo_dir, check=False)
        if result.returncode != 0:
            return None
        line = next((item.strip() for item in result.stdout.splitlines() if item.strip()), "")
        if not line:
            return None
        return line.split()[0].strip() or None

    def is_ancestor(self, repo_dir: Path, older_revision: str, newer_revision: str) -> bool:
        older = older_revision.strip()
        newer = newer_revision.strip()
        if not older or not newer:
            return False
        result = self.run(["merge-base", "--is-ancestor", older, newer], cwd=repo_dir, check=False)
        return result.returncode == 0

    def add_worktree(self, repo_dir: Path, worktree_dir: Path, branch_name: str, start_point: str) -> None:
        worktree_dir.parent.mkdir(parents=True, exist_ok=True)
        self.run(["worktree", "add", "-b", branch_name, str(worktree_dir), start_point], cwd=repo_dir)

    def attach_worktree(self, repo_dir: Path, worktree_dir: Path, branch_name: str) -> None:
        worktree_dir.parent.mkdir(parents=True, exist_ok=True)
        self.run(["worktree", "add", str(worktree_dir), branch_name], cwd=repo_dir)

    def remove_worktree(self, repo_dir: Path, worktree_dir: Path, force: bool = True) -> None:
        args = ["worktree", "remove"]
        if force:
            args.append("--force")
        args.append(str(worktree_dir))
        self.run(args, cwd=repo_dir, check=False)
        remove_tree(worktree_dir, ignore_errors=True)

    def delete_branch(self, repo_dir: Path, branch_name: str, force: bool = True) -> None:
        args = ["branch", "-D" if force else "-d", branch_name]
        self.run(args, cwd=repo_dir, check=False)

    def cherry_pick(self, repo_dir: Path, revision: str) -> None:
        self.run(["cherry-pick", revision], cwd=repo_dir)

    def try_cherry_pick(self, repo_dir: Path, revision: str) -> CommandResult:
        return self.run(["cherry-pick", revision], cwd=repo_dir, check=False)

    def abort_cherry_pick(self, repo_dir: Path) -> None:
        self.run(["cherry-pick", "--abort"], cwd=repo_dir, check=False)

    def skip_cherry_pick(self, repo_dir: Path) -> None:
        self.run(["cherry-pick", "--skip"], cwd=repo_dir, check=False)

    def continue_cherry_pick(self, repo_dir: Path) -> None:
        self.run(["cherry-pick", "--continue"], cwd=repo_dir)

    def cherry_pick_in_progress(self, repo_dir: Path) -> bool:
        result = self.run(["rev-parse", "-q", "--verify", "CHERRY_PICK_HEAD"], cwd=repo_dir, check=False)
        return result.returncode == 0

    def _parse_untracked_overwrite_paths(self, stderr: str) -> list[str]:
        lines = stderr.splitlines()
        collecting = False
        paths: list[str] = []
        for raw_line in lines:
            line = raw_line.rstrip()
            if not collecting:
                if UNTRACKED_OVERWRITE_MARKER in line:
                    collecting = True
                continue
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("Please move or remove them before you merge.") or stripped == "Aborting":
                break
            paths.append(stripped)
        return paths

    def _resolve_merge_blocker_path(self, repo_dir: Path, relative_path: str) -> Path | None:
        candidate = Path(relative_path)
        if candidate.is_absolute():
            return None
        resolved_repo_dir = repo_dir.resolve()
        resolved_path = (repo_dir / candidate).resolve(strict=False)
        if resolved_path != resolved_repo_dir and resolved_repo_dir not in resolved_path.parents:
            return None
        return resolved_path

    def _read_revision_file_bytes(self, repo_dir: Path, revision: str, relative_path: str) -> bytes | None:
        command = [
            "git",
            *self._safe_directory_args(repo_dir),
            "show",
            f"{revision}:{relative_path}",
        ]
        completed = subprocess.run(
            command,
            cwd=repo_dir,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            return None
        return completed.stdout

    def _matches_merge_target_contents(self, local_bytes: bytes, expected_bytes: bytes) -> bool:
        if local_bytes == expected_bytes:
            return True
        if b"\0" in local_bytes or b"\0" in expected_bytes:
            return False
        return local_bytes.replace(b"\r\n", b"\n") == expected_bytes.replace(b"\r\n", b"\n")

    def _remove_identical_untracked_merge_blockers(self, repo_dir: Path, revision: str, stderr: str) -> bool:
        removed_any = False
        resolved_repo_dir = repo_dir.resolve()
        for relative_path in self._parse_untracked_overwrite_paths(stderr):
            resolved_path = self._resolve_merge_blocker_path(repo_dir, relative_path)
            if resolved_path is None or not resolved_path.is_file():
                continue
            normalized_relative_path = resolved_path.relative_to(resolved_repo_dir).as_posix()
            untracked_result = self.run(
                ["ls-files", "--others", "--exclude-standard", "--", normalized_relative_path],
                cwd=repo_dir,
                check=False,
            )
            untracked_paths = {line.strip() for line in untracked_result.stdout.splitlines() if line.strip()}
            if normalized_relative_path not in untracked_paths:
                continue
            expected_bytes = self._read_revision_file_bytes(repo_dir, revision, normalized_relative_path)
            if expected_bytes is None:
                continue
            if not self._matches_merge_target_contents(resolved_path.read_bytes(), expected_bytes):
                continue
            resolved_path.unlink()
            removed_any = True
        return removed_any

    def merge_ff_only(self, repo_dir: Path, revision: str) -> None:
        args = ["merge", "--ff-only", revision]
        result = self.run(args, cwd=repo_dir, check=False)
        if result.returncode == 0:
            return
        if self._remove_identical_untracked_merge_blockers(repo_dir, revision, result.stderr):
            retry_result = self.run(args, cwd=repo_dir, check=False)
            if retry_result.returncode == 0:
                return
            result = retry_result
        error_text = result.stderr.strip() or result.stdout.strip()
        raise GitCommandError(
            f"git {' '.join(args)} failed with code {result.returncode}: {error_text}"
        )

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
