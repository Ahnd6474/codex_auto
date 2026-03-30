from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .models import CommandResult
from .subprocess_utils import run_subprocess
from .utils import decode_process_output, remove_tree


class GitCommandError(RuntimeError):
    pass


UNTRACKED_OVERWRITE_MARKER = "The following untracked working tree files would be overwritten by merge:"
MISSING_REGISTERED_WORKTREE_MARKER = "is a missing but already registered worktree"
GIT_QUERY_TIMEOUT_SECONDS = 10.0
GIT_STATUS_TIMEOUT_SECONDS = 30.0
GIT_LOCAL_MUTATION_TIMEOUT_SECONDS = 90.0
GIT_MERGE_TIMEOUT_SECONDS = 180.0
GIT_NETWORK_TIMEOUT_SECONDS = 180.0
GIT_CLONE_TIMEOUT_SECONDS = 300.0
GIT_WORKTREE_TIMEOUT_SECONDS = 180.0


class GitOps:
    _UNTRACKED_SCRATCH_PREFIXES = ("_tmp_",)
    _BENIGN_STDERR_MARKERS = (
        "LF will be replaced by CRLF the next time Git touches it",
        "CRLF will be replaced by LF the next time Git touches it",
    )
    _REVISION_MUTATING_COMMANDS = {
        "add",
        "checkout",
        "cherry-pick",
        "clean",
        "clone",
        "commit",
        "config",
        "fetch",
        "init",
        "merge",
        "pull",
        "push",
        "reset",
        "revert",
        "switch",
        "worktree",
    }
    _FAST_QUERY_COMMANDS = {
        ("branch", "--show-current"),
        ("rev-parse", "HEAD"),
        ("rev-parse", "--abbrev-ref"),
        ("rev-parse", "--verify"),
        ("rev-parse", "-q"),
        ("remote",),
        ("diff", "--name-only"),
        ("diff", "--name-status"),
        ("show",),
        ("merge-base", "--is-ancestor"),
        ("ls-files", "--others"),
    }
    _STATUS_COMMANDS = {
        ("status", "--porcelain"),
        ("status", "--porcelain=v1"),
    }
    _NETWORK_COMMANDS = {
        "fetch",
        "pull",
        "push",
        "ls-remote",
    }
    _WORKTREE_COMMANDS = {
        "worktree",
    }
    _MERGE_COMMANDS = {
        "merge",
        "cherry-pick",
    }

    def __init__(self) -> None:
        self._current_revision_cache: dict[str, str] = {}
        self._configured_identity_cache: dict[str, tuple[str, str]] = {}

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
        timeout_seconds: float | None = None,
    ) -> CommandResult:
        command = ["git", *self._safe_directory_args(cwd), *args]
        process_env = None
        if env:
            process_env = os.environ.copy()
            process_env.update(env)
        completed = run_subprocess(
            command,
            cwd=cwd,
            capture_output=True,
            check=False,
            env=process_env,
            timeout_seconds=self._timeout_seconds_for_args(args, timeout_seconds),
        )
        stdout = decode_process_output(completed.stdout)
        stderr = self._filter_benign_stderr(decode_process_output(completed.stderr))
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
        if args and args[0] in self._REVISION_MUTATING_COMMANDS:
            self._invalidate_repo_caches(cwd)
        return result

    def _timeout_seconds_for_args(self, args: list[str], override: float | None = None) -> float:
        if override is not None:
            return float(override)
        if not args:
            return GIT_QUERY_TIMEOUT_SECONDS
        primary = str(args[0]).strip().lower()
        secondary = str(args[1]).strip().lower() if len(args) > 1 else ""
        prefix = (primary, secondary) if secondary else (primary,)
        if prefix in self._STATUS_COMMANDS:
            return GIT_STATUS_TIMEOUT_SECONDS
        if prefix in self._FAST_QUERY_COMMANDS or (primary,) in self._FAST_QUERY_COMMANDS:
            return GIT_QUERY_TIMEOUT_SECONDS
        if primary == "clone":
            return GIT_CLONE_TIMEOUT_SECONDS
        if primary in self._NETWORK_COMMANDS:
            return GIT_NETWORK_TIMEOUT_SECONDS
        if primary in self._WORKTREE_COMMANDS:
            return GIT_WORKTREE_TIMEOUT_SECONDS
        if primary in self._MERGE_COMMANDS:
            return GIT_MERGE_TIMEOUT_SECONDS
        return GIT_LOCAL_MUTATION_TIMEOUT_SECONDS

    def _filter_benign_stderr(self, stderr: str) -> str:
        filtered_lines = [
            line
            for line in str(stderr).splitlines()
            if not any(marker in line for marker in self._BENIGN_STDERR_MARKERS)
        ]
        if not filtered_lines:
            return ""
        return "\n".join(filtered_lines).rstrip() + "\n"

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
        repo_key = str(repo_dir.resolve())
        normalized = (str(name).strip(), str(email).strip())
        if self._configured_identity_cache.get(repo_key) == normalized:
            return
        self.run(["config", "user.name", name], cwd=repo_dir)
        self.run(["config", "user.email", email], cwd=repo_dir)
        self._configured_identity_cache[repo_key] = normalized

    def current_revision(self, repo_dir: Path) -> str:
        repo_key = str(repo_dir.resolve())
        cached = self._current_revision_cache.get(repo_key)
        if cached:
            return cached
        revision = self.run(["rev-parse", "HEAD"], cwd=repo_dir).stdout.strip()
        if revision:
            self._current_revision_cache[repo_key] = revision
        return revision

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
        output = self.run(["status", "--porcelain"], cwd=repo_dir).stdout.splitlines()
        return any(self._parse_status_path(line) is not None for line in output)

    def changed_files(self, repo_dir: Path) -> list[str]:
        output = self.run(["status", "--porcelain"], cwd=repo_dir).stdout.splitlines()
        changed: list[str] = []
        for line in output:
            parsed_path = self._parse_status_path(line)
            if parsed_path is not None:
                changed.append(parsed_path)
        return changed

    def diff_name_status(self, repo_dir: Path, base_revision: str, head_revision: str) -> list[tuple[str, str]]:
        base = str(base_revision or "").strip()
        head = str(head_revision or "").strip()
        if not base or not head:
            return []
        result = self.run(["diff", "--name-status", base, head], cwd=repo_dir, check=False)
        if result.returncode != 0:
            return []
        entries: list[tuple[str, str]] = []
        for line in result.stdout.splitlines():
            raw = line.strip()
            if not raw:
                continue
            parts = raw.split("\t")
            if len(parts) < 2:
                continue
            status = parts[0].strip().upper()
            path = parts[-1].strip()
            if not path:
                continue
            entries.append((status, path))
        return entries

    def read_file_at_revision(self, repo_dir: Path, revision: str, relative_path: str) -> str | None:
        normalized_revision = str(revision or "").strip()
        normalized_path = str(relative_path or "").strip().replace("\\", "/")
        if not normalized_revision or not normalized_path:
            return None
        result = self.run(
            ["show", f"{normalized_revision}:{normalized_path}"],
            cwd=repo_dir,
            check=False,
        )
        if result.returncode != 0:
            return None
        return result.stdout

    def _parse_status_path(self, line: str) -> str | None:
        if len(line) < 4:
            return None
        status = line[:2]
        path = line[3:].strip()
        if not path:
            return None
        if status == "??" and self._is_untracked_scratch_path(path):
            return None
        return path

    def _is_untracked_scratch_path(self, path: str) -> bool:
        normalized = path.strip().replace("\\", "/").rstrip("/")
        if not normalized:
            return False
        leaf_name = normalized.rsplit("/", 1)[-1]
        return any(leaf_name.startswith(prefix) for prefix in self._UNTRACKED_SCRATCH_PREFIXES)

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

    def push_refspec(self, repo_dir: Path, local_ref: str, remote_branch: str, force: bool = False) -> None:
        refspec = f"{local_ref.strip()}:refs/heads/{remote_branch.strip()}"
        args = ["push", "origin"]
        if force:
            args.append("--force-with-lease")
        args.append(refspec)
        self.run(args, cwd=repo_dir)

    def fetch(self, repo_dir: Path, remote_name: str, branch: str = "") -> None:
        args = ["fetch", remote_name]
        if branch.strip():
            args.append(branch.strip())
        self.run(args, cwd=repo_dir)

    def pull_ff_only(self, repo_dir: Path, remote_name: str, branch: str) -> None:
        self.run(["pull", "--ff-only", remote_name, branch], cwd=repo_dir)

    def delete_remote_branch(self, repo_dir: Path, remote_name: str, branch_name: str) -> None:
        self.run(["push", remote_name, "--delete", branch_name], cwd=repo_dir)

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

    def _is_missing_registered_worktree_error(self, error_text: str) -> bool:
        return MISSING_REGISTERED_WORKTREE_MARKER in error_text

    def prune_worktrees(self, repo_dir: Path) -> None:
        self.run(["worktree", "prune"], cwd=repo_dir, check=False)

    def _clear_stale_worktree_registration(self, repo_dir: Path, worktree_dir: Path) -> None:
        self.remove_worktree(repo_dir, worktree_dir, force=True)
        self.prune_worktrees(repo_dir)

    def add_worktree(self, repo_dir: Path, worktree_dir: Path, branch_name: str, start_point: str) -> None:
        worktree_dir.parent.mkdir(parents=True, exist_ok=True)
        add_args = ["worktree", "add", "-b", branch_name, str(worktree_dir), start_point]
        try:
            self.run(add_args, cwd=repo_dir)
        except GitCommandError as exc:
            if not self._is_missing_registered_worktree_error(str(exc)):
                raise
            self._clear_stale_worktree_registration(repo_dir, worktree_dir)
            if self.branch_exists(repo_dir, branch_name):
                self.run(["worktree", "add", str(worktree_dir), branch_name], cwd=repo_dir)
            else:
                self.run(add_args, cwd=repo_dir)

    def attach_worktree(self, repo_dir: Path, worktree_dir: Path, branch_name: str) -> None:
        worktree_dir.parent.mkdir(parents=True, exist_ok=True)
        add_args = ["worktree", "add", str(worktree_dir), branch_name]
        try:
            self.run(add_args, cwd=repo_dir)
        except GitCommandError as exc:
            if not self._is_missing_registered_worktree_error(str(exc)):
                raise
            self._clear_stale_worktree_registration(repo_dir, worktree_dir)
            self.run(add_args, cwd=repo_dir)

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
        normalized_revision = str(revision).strip()
        if normalized_revision:
            self._current_revision_cache[str(repo_dir.resolve())] = normalized_revision

    def _invalidate_repo_caches(self, repo_dir: Path) -> None:
        repo_key = str(repo_dir.resolve())
        self._current_revision_cache.pop(repo_key, None)
        if not (repo_dir / ".git").exists():
            self._configured_identity_cache.pop(repo_key, None)
