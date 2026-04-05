from __future__ import annotations

import configparser
import os
import subprocess
from io import StringIO
from pathlib import Path

from .errors import SubprocessTimeoutError
from .lit_ops import LitCommandError, LitOps
from .models import CommandResult
from .subprocess_utils import run_subprocess
from .utils import decode_process_output, read_text, remove_tree, write_text


class GitCommandError(RuntimeError):
    pass


UNTRACKED_OVERWRITE_MARKER = "The following untracked working tree files would be overwritten by merge:"
MISSING_REGISTERED_WORKTREE_MARKER = "is a missing but already registered worktree"
GIT_QUERY_TIMEOUT_SECONDS = 10.0
GIT_REMOTE_QUERY_TIMEOUT_SECONDS = 60.0
GIT_STATUS_TIMEOUT_SECONDS = 60.0
GIT_LOCAL_MUTATION_TIMEOUT_SECONDS = 90.0
GIT_COMMIT_TIMEOUT_SECONDS = 300.0
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
        self.lit = LitOps()

    def is_lit_repository(self, repo_dir: Path) -> bool:
        return self.lit.is_lit_repository(repo_dir)

    def repository_backend(self, repo_dir: Path, preferred: str = "auto") -> str:
        normalized = str(preferred or "auto").strip().lower() or "auto"
        if normalized in {"git", "lit"}:
            return normalized
        if self.is_git_repository(repo_dir):
            return "git"
        if self.is_lit_repository(repo_dir):
            return "lit"
        return "git"

    def _uses_lit_backend(self, repo_dir: Path) -> bool:
        return self.repository_backend(repo_dir) == "lit"

    def _safe_directory_args(self, cwd: Path) -> list[str]:
        resolved = cwd.resolve()
        return ["-c", f"safe.directory={resolved.as_posix()}"]

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
        try:
            completed = run_subprocess(
                command,
                cwd=cwd,
                capture_output=True,
                check=False,
                env=process_env,
                timeout_seconds=self._timeout_seconds_for_args(args, timeout_seconds),
            )
        except OSError as exc:
            raise GitCommandError(
                f"git executable could not be started: {exc}"
            ) from exc
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
        if primary == "remote":
            return GIT_REMOTE_QUERY_TIMEOUT_SECONDS
        if prefix in self._FAST_QUERY_COMMANDS or (primary,) in self._FAST_QUERY_COMMANDS:
            return GIT_QUERY_TIMEOUT_SECONDS
        if primary == "clone":
            return GIT_CLONE_TIMEOUT_SECONDS
        if primary == "commit":
            return GIT_COMMIT_TIMEOUT_SECONDS
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
        if self._uses_lit_backend(repo_dir):
            raise GitCommandError("lit repositories do not support remote clone/update through jakal-flow.")
        if (repo_dir / ".git").exists():
            self.run(["fetch", "origin", branch], cwd=repo_dir)
            self.run(["checkout", branch], cwd=repo_dir)
            self.run(["pull", "--ff-only", "origin", branch], cwd=repo_dir)
            return
        repo_dir.parent.mkdir(parents=True, exist_ok=True)
        self.run(["clone", "--branch", branch, "--single-branch", repo_url, str(repo_dir)], cwd=repo_dir.parent)

    def is_git_repository(self, repo_dir: Path) -> bool:
        return (repo_dir / ".git").exists()

    def ensure_repository(self, repo_dir: Path, branch: str, backend: str = "git") -> bool:
        if self.repository_backend(repo_dir, preferred=backend) == "lit":
            try:
                created = self.lit.ensure_repository(repo_dir, branch)
            except LitCommandError as exc:
                raise GitCommandError(str(exc)) from exc
            self._invalidate_repo_caches(repo_dir)
            return created
        repo_dir.mkdir(parents=True, exist_ok=True)
        created = False
        if not self.is_git_repository(repo_dir):
            self.run(["init"], cwd=repo_dir)
            created = True
        if branch:
            current_branch = self.current_branch(repo_dir)
            if current_branch == branch:
                return created
            if self.branch_exists(repo_dir, branch):
                self.run(["checkout", branch], cwd=repo_dir)
            else:
                self.run(["checkout", "-b", branch], cwd=repo_dir)
        return created

    def configure_local_identity(self, repo_dir: Path, name: str, email: str) -> None:
        if self._uses_lit_backend(repo_dir):
            return
        repo_key = str(repo_dir.resolve())
        normalized = (str(name).strip(), str(email).strip())
        if self._configured_identity_cache.get(repo_key) == normalized:
            return
        configured_name = self._read_git_config_value(repo_dir, "user", "name")
        configured_email = self._read_git_config_value(repo_dir, "user", "email")
        if configured_name == normalized[0] and configured_email == normalized[1]:
            self._configured_identity_cache[repo_key] = normalized
            return
        if configured_name != normalized[0]:
            self._run_config_command(repo_dir, ["config", "user.name", normalized[0]])
        if configured_email != normalized[1]:
            self._run_config_command(repo_dir, ["config", "user.email", normalized[1]])
        self._configured_identity_cache[repo_key] = normalized

    def _config_lock_file(self, repo_dir: Path) -> Path | None:
        config_path = self._git_config_path_for_repo(repo_dir)
        if config_path is None:
            return None
        return config_path.with_name("config.lock")

    def _run_config_command(self, repo_dir: Path, args: list[str]) -> None:
        try:
            self.run(args, cwd=repo_dir)
            return
        except GitCommandError as exc:
            message = str(exc)
            if "could not lock config file" not in message or "File exists" not in message:
                raise
        lock_file = self._config_lock_file(repo_dir)
        if lock_file is None or not lock_file.exists():
            raise
        try:
            lock_file.unlink()
        except OSError:
            raise
        self.run(args, cwd=repo_dir)

    def current_revision(self, repo_dir: Path) -> str:
        repo_key = str(repo_dir.resolve())
        cached = self._current_revision_cache.get(repo_key)
        if cached:
            return cached
        if self._uses_lit_backend(repo_dir):
            revision = self.lit.current_revision(repo_dir)
            if revision:
                self._current_revision_cache[repo_key] = revision
            return revision
        revision = self._current_revision_from_head(repo_dir)
        if not revision:
            try:
                revision = self.run(["rev-parse", "HEAD"], cwd=repo_dir).stdout.strip()
            except SubprocessTimeoutError:
                revision = ""
        if revision:
            self._current_revision_cache[repo_key] = revision
        return revision

    def has_commits(self, repo_dir: Path) -> bool:
        if self._uses_lit_backend(repo_dir):
            return self.lit.has_commits(repo_dir)
        if self._current_revision_from_head(repo_dir):
            return True
        try:
            result = self.run(["rev-parse", "--verify", "HEAD"], cwd=repo_dir, check=False)
        except SubprocessTimeoutError:
            return False
        return result.returncode == 0

    def _git_dir_for_repo(self, repo_dir: Path) -> Path | None:
        dot_git = repo_dir / ".git"
        if dot_git.is_dir():
            return dot_git
        if not dot_git.is_file():
            return None
        try:
            header = read_text(dot_git).strip()
        except OSError:
            return None
        prefix = "gitdir:"
        if not header.lower().startswith(prefix):
            return None
        git_dir_text = header[len(prefix) :].strip()
        if not git_dir_text:
            return None
        git_dir = Path(git_dir_text)
        if not git_dir.is_absolute():
            git_dir = (repo_dir / git_dir).resolve(strict=False)
        return git_dir

    def _worktree_git_file(self, worktree_dir: Path) -> Path:
        return worktree_dir / ".git"

    def _read_worktree_gitdir(self, worktree_dir: Path) -> Path | None:
        git_file = self._worktree_git_file(worktree_dir)
        if not git_file.is_file():
            return None
        try:
            contents = read_text(git_file).strip()
        except OSError:
            return None
        prefix = "gitdir:"
        if not contents.lower().startswith(prefix):
            return None
        gitdir_text = contents[len(prefix) :].strip()
        if not gitdir_text:
            return None
        gitdir = Path(gitdir_text)
        if not gitdir.is_absolute():
            gitdir = (worktree_dir / gitdir).resolve(strict=False)
        return gitdir

    def _expected_worktree_gitdir(self, repo_dir: Path, worktree_dir: Path) -> Path:
        git_dir = self._git_dir_for_repo(repo_dir)
        if git_dir is None:
            return repo_dir.resolve(strict=False) / ".git" / "worktrees" / worktree_dir.name
        return git_dir / "worktrees" / worktree_dir.name

    def _repair_worktree_gitdir_alias(self, repo_dir: Path, worktree_dir: Path, current_gitdir: Path) -> bool:
        git_file = self._worktree_git_file(worktree_dir)
        expected_gitdir = self._expected_worktree_gitdir(repo_dir, worktree_dir)
        if current_gitdir == expected_gitdir:
            return False
        if current_gitdir.parent.resolve(strict=False) != expected_gitdir.parent.resolve(strict=False):
            return False
        try:
            write_text(git_file, f"gitdir: {expected_gitdir.as_posix()}\n")
        except OSError:
            return False
        return True

    def _has_live_worktree_registration(self, repo_dir: Path, worktree_dir: Path) -> bool:
        current_gitdir = self._read_worktree_gitdir(worktree_dir)
        if current_gitdir is None:
            return False
        if self._repair_worktree_gitdir_alias(repo_dir, worktree_dir, current_gitdir):
            return True
        if current_gitdir.exists():
            return True
        self._clear_stale_worktree_registration(repo_dir, worktree_dir)
        return False

    def _clear_stale_worktree_registration(self, repo_dir: Path, worktree_dir: Path) -> None:
        try:
            self.remove_worktree(repo_dir, worktree_dir, force=True)
        except OSError:
            remove_tree(worktree_dir, ignore_errors=True)
        try:
            self.prune_worktrees(repo_dir)
        except OSError:
            pass

    def _current_branch_from_head(self, repo_dir: Path) -> str:
        git_dir = self._git_dir_for_repo(repo_dir)
        if git_dir is None:
            return ""
        head_path = git_dir / "HEAD"
        try:
            head_contents = read_text(head_path).strip()
        except OSError:
            return ""
        prefix = "ref:"
        if not head_contents.lower().startswith(prefix):
            return ""
        ref_name = head_contents[len(prefix) :].strip()
        branch_prefix = "refs/heads/"
        if not ref_name.startswith(branch_prefix):
            return ""
        return ref_name[len(branch_prefix) :].strip()

    def _current_revision_from_head(self, repo_dir: Path) -> str:
        git_dir = self._git_dir_for_repo(repo_dir)
        if git_dir is None:
            return ""
        head_contents = self._read_git_head(git_dir)
        if not head_contents:
            return ""
        if head_contents.lower().startswith("ref:"):
            ref_name = head_contents[4:].strip()
            return self._read_git_ref_revision(git_dir, ref_name)
        return head_contents if self._looks_like_git_revision(head_contents) else ""

    def _read_git_head(self, git_dir: Path) -> str:
        try:
            return read_text(git_dir / "HEAD").strip()
        except OSError:
            return ""

    def _read_git_ref_revision(self, git_dir: Path, ref_name: str) -> str:
        normalized_ref = str(ref_name or "").strip()
        if not normalized_ref:
            return ""
        ref_path = git_dir / Path(normalized_ref)
        try:
            revision = read_text(ref_path).strip()
        except OSError:
            revision = ""
        if self._looks_like_git_revision(revision):
            return revision
        packed_refs_path = git_dir / "packed-refs"
        try:
            packed_refs = read_text(packed_refs_path).splitlines()
        except OSError:
            return ""
        for line in packed_refs:
            raw = line.strip()
            if not raw or raw.startswith("#") or raw.startswith("^"):
                continue
            revision_text, _, packed_ref = raw.partition(" ")
            if packed_ref.strip() != normalized_ref:
                continue
            revision_text = revision_text.strip()
            return revision_text if self._looks_like_git_revision(revision_text) else ""
        return ""

    def _git_config_path_for_repo(self, repo_dir: Path) -> Path | None:
        git_dir = self._git_dir_for_repo(repo_dir)
        if git_dir is None:
            return None
        return git_dir / "config"

    def _read_git_config(self, repo_dir: Path) -> configparser.ConfigParser | None:
        config_path = self._git_config_path_for_repo(repo_dir)
        if config_path is None:
            return None
        parser = configparser.ConfigParser(interpolation=None)
        try:
            with StringIO(read_text(config_path)) as handle:
                parser.read_file(handle)
        except (OSError, UnicodeError, configparser.Error):
            return None
        return parser

    def _read_git_config_value(self, repo_dir: Path, section: str, option: str) -> str | None:
        parser = self._read_git_config(repo_dir)
        if parser is None:
            return None
        if not parser.has_section(section):
            return None
        value = parser.get(section, option, fallback="").strip()
        return value or None

    def _git_config_has_section(self, repo_dir: Path, section: str) -> bool:
        parser = self._read_git_config(repo_dir)
        return bool(parser is not None and parser.has_section(section))

    def _git_state_revision(self, repo_dir: Path, state_name: str) -> str:
        normalized = str(state_name or "").strip()
        if not normalized:
            return ""
        git_dir = self._git_dir_for_repo(repo_dir)
        if git_dir is None:
            return ""
        try:
            revision = read_text(git_dir / normalized).strip()
        except OSError:
            return ""
        return revision if self._looks_like_git_revision(revision) else ""

    def _looks_like_git_revision(self, value: str) -> bool:
        normalized = str(value or "").strip()
        if len(normalized) < 7:
            return False
        return all(character in "0123456789abcdefABCDEF" for character in normalized)

    def current_branch(self, repo_dir: Path) -> str:
        if self._uses_lit_backend(repo_dir):
            return self.lit.current_branch(repo_dir)
        head_branch = self._current_branch_from_head(repo_dir)
        if head_branch:
            return head_branch
        try:
            result = self.run(["branch", "--show-current"], cwd=repo_dir, check=False)
        except SubprocessTimeoutError:
            result = CommandResult(command=["git", "branch", "--show-current"], returncode=1, stdout="", stderr="")
        branch = result.stdout.strip()
        if branch:
            return branch
        try:
            fallback = self.run(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir, check=False).stdout.strip()
        except SubprocessTimeoutError:
            return ""
        return "" if fallback == "HEAD" else fallback

    def remote_url(self, repo_dir: Path, remote_name: str = "origin") -> str | None:
        if self._uses_lit_backend(repo_dir):
            return None
        section = f'remote "{str(remote_name or "").strip()}"'
        configured_url = self._read_git_config_value(repo_dir, section, "url")
        if configured_url:
            return configured_url
        try:
            result = self.run(["remote", "get-url", remote_name], cwd=repo_dir, check=False)
        except SubprocessTimeoutError:
            return configured_url
        url = result.stdout.strip()
        return url or configured_url

    def set_remote_url(self, repo_dir: Path, remote_name: str, remote_url: str) -> None:
        if self._uses_lit_backend(repo_dir):
            raise GitCommandError("lit repositories do not support Git remotes.")
        normalized_remote_name = str(remote_name or "").strip()
        normalized_remote_url = str(remote_url or "").strip()
        section = f'remote "{normalized_remote_name}"'
        configured_remote_url = self._read_git_config_value(repo_dir, section, "url")
        if configured_remote_url == normalized_remote_url:
            return
        existing_remote_url = configured_remote_url or self.remote_url(repo_dir, normalized_remote_name)
        if existing_remote_url == normalized_remote_url:
            return
        if existing_remote_url is not None or self._git_config_has_section(repo_dir, section):
            self.run(["remote", "set-url", normalized_remote_name, normalized_remote_url], cwd=repo_dir)
            return
        self.run(["remote", "add", normalized_remote_name, normalized_remote_url], cwd=repo_dir)

    def has_changes(self, repo_dir: Path) -> bool:
        if self._uses_lit_backend(repo_dir):
            return self.lit.has_changes(repo_dir)
        output = self.run(["status", "--porcelain"], cwd=repo_dir).stdout.splitlines()
        return any(self._parse_status_path(line) is not None for line in output)

    def changed_files(self, repo_dir: Path) -> list[str]:
        if self._uses_lit_backend(repo_dir):
            return self.lit.changed_files(repo_dir)
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
        if self._uses_lit_backend(repo_dir):
            try:
                revision = self.lit.commit_all(repo_dir, message)
            except LitCommandError as exc:
                raise GitCommandError(str(exc)) from exc
            self._current_revision_cache[str(repo_dir.resolve())] = revision
            return revision
        self.run(["add", "-A"], cwd=repo_dir)
        self.run(["commit", "-m", message], cwd=repo_dir, env=self._commit_env(author_name))
        return self.current_revision(repo_dir)

    def add_paths(self, repo_dir: Path, paths: list[str], force: bool = False) -> None:
        if self._uses_lit_backend(repo_dir):
            try:
                self.lit.add_paths(repo_dir, paths)
            except LitCommandError as exc:
                raise GitCommandError(str(exc)) from exc
            self._invalidate_repo_caches(repo_dir)
            return
        normalized_paths = [str(path).strip() for path in paths if str(path).strip()]
        if not normalized_paths:
            return
        args = ["add"]
        if force:
            args.append("-f")
        args.extend(["--", *normalized_paths])
        self.run(args, cwd=repo_dir)

    def add_all(self, repo_dir: Path) -> None:
        if self._uses_lit_backend(repo_dir):
            try:
                self.lit.add_all(repo_dir)
            except LitCommandError as exc:
                raise GitCommandError(str(exc)) from exc
            self._invalidate_repo_caches(repo_dir)
            return
        self.run(["add", "-A"], cwd=repo_dir)

    def create_initial_commit(self, repo_dir: Path, message: str, author_name: str | None = None, force: bool = False) -> str:
        if self._uses_lit_backend(repo_dir):
            try:
                revision = self.lit.create_initial_commit(repo_dir, message)
            except LitCommandError as exc:
                raise GitCommandError(str(exc)) from exc
            self._current_revision_cache[str(repo_dir.resolve())] = revision
            return revision
        add_args = ["add", "-A"]
        if force:
            add_args.append("-f")
        self.run(add_args, cwd=repo_dir)
        self.run(["commit", "--allow-empty", "-m", message], cwd=repo_dir, env=self._commit_env(author_name))
        return self.current_revision(repo_dir)

    def commit_paths(self, repo_dir: Path, paths: list[str], message: str, author_name: str | None = None, force: bool = False) -> str:
        if self._uses_lit_backend(repo_dir):
            try:
                revision = self.lit.commit_paths(repo_dir, paths, message)
            except LitCommandError as exc:
                raise GitCommandError(str(exc)) from exc
            self._current_revision_cache[str(repo_dir.resolve())] = revision
            return revision
        normalized_paths = [str(path).strip() for path in paths if str(path).strip()]
        if not normalized_paths:
            raise ValueError("paths must not be empty.")
        self.add_paths(repo_dir, normalized_paths, force=force)
        self.run(["commit", "-m", message, "--", *normalized_paths], cwd=repo_dir, env=self._commit_env(author_name))
        return self.current_revision(repo_dir)

    def commit_staged(self, repo_dir: Path, message: str, author_name: str | None = None) -> str:
        if self._uses_lit_backend(repo_dir):
            try:
                revision = self.lit.commit_staged(repo_dir, message)
            except LitCommandError as exc:
                raise GitCommandError(str(exc)) from exc
            self._current_revision_cache[str(repo_dir.resolve())] = revision
            return revision
        self.run(["commit", "-m", message], cwd=repo_dir, env=self._commit_env(author_name))
        return self.current_revision(repo_dir)

    def push(self, repo_dir: Path, branch: str) -> None:
        if self._uses_lit_backend(repo_dir):
            raise GitCommandError("lit repositories do not support push through jakal-flow.")
        self.run(["push", "origin", branch], cwd=repo_dir)

    def push_refspec(self, repo_dir: Path, local_ref: str, remote_branch: str, force: bool = False) -> None:
        refspec = f"{local_ref.strip()}:refs/heads/{remote_branch.strip()}"
        args = ["push", "origin"]
        if force:
            args.append("--force-with-lease")
        args.append(refspec)
        self.run(args, cwd=repo_dir)

    def fetch(self, repo_dir: Path, remote_name: str, branch: str = "") -> None:
        if self._uses_lit_backend(repo_dir):
            raise GitCommandError("lit repositories do not support fetch through jakal-flow.")
        args = ["fetch", remote_name]
        if branch.strip():
            args.append(branch.strip())
        self.run(args, cwd=repo_dir)

    def pull_ff_only(self, repo_dir: Path, remote_name: str, branch: str) -> None:
        if self._uses_lit_backend(repo_dir):
            raise GitCommandError("lit repositories do not support pull through jakal-flow.")
        self.run(["pull", "--ff-only", remote_name, branch], cwd=repo_dir)

    def delete_remote_branch(self, repo_dir: Path, remote_name: str, branch_name: str) -> None:
        self.run(["push", remote_name, "--delete", branch_name], cwd=repo_dir)

    def branch_exists(self, repo_dir: Path, branch_name: str) -> bool:
        if self._uses_lit_backend(repo_dir):
            return self.lit.branch_exists(repo_dir, branch_name)
        return bool(self.local_branch_revision(repo_dir, branch_name))

    def local_branch_revision(self, repo_dir: Path, branch_name: str) -> str:
        if self._uses_lit_backend(repo_dir):
            return self.lit.local_branch_revision(repo_dir, branch_name)
        normalized = str(branch_name or "").strip()
        if not normalized:
            return ""
        git_dir = self._git_dir_for_repo(repo_dir)
        revision = self._read_git_ref_revision(git_dir, f"refs/heads/{normalized}") if git_dir is not None else ""
        if revision:
            return revision
        result = self.run(["rev-parse", "--verify", f"refs/heads/{normalized}"], cwd=repo_dir, check=False)
        return result.stdout.strip() if result.returncode == 0 else ""

    def remote_branch_revision(self, repo_dir: Path, remote_name: str, branch: str) -> str | None:
        if self._uses_lit_backend(repo_dir):
            return None
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
        if older == newer:
            return True
        result = self.run(["merge-base", "--is-ancestor", older, newer], cwd=repo_dir, check=False)
        return result.returncode == 0

    def _is_missing_registered_worktree_error(self, error_text: str) -> bool:
        return MISSING_REGISTERED_WORKTREE_MARKER in error_text

    def prune_worktrees(self, repo_dir: Path) -> None:
        if self._uses_lit_backend(repo_dir):
            return
        self.run(["worktree", "prune"], cwd=repo_dir, check=False)

    def add_worktree(self, repo_dir: Path, worktree_dir: Path, branch_name: str, start_point: str) -> None:
        if self._uses_lit_backend(repo_dir):
            raise GitCommandError("lit repositories do not support Git worktrees in jakal-flow yet.")
        worktree_dir.parent.mkdir(parents=True, exist_ok=True)
        if self._has_live_worktree_registration(repo_dir, worktree_dir):
            return
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
        if self._uses_lit_backend(repo_dir):
            raise GitCommandError("lit repositories do not support Git worktrees in jakal-flow yet.")
        worktree_dir.parent.mkdir(parents=True, exist_ok=True)
        if self._has_live_worktree_registration(repo_dir, worktree_dir):
            return
        add_args = ["worktree", "add", str(worktree_dir), branch_name]
        try:
            self.run(add_args, cwd=repo_dir)
        except GitCommandError as exc:
            if not self._is_missing_registered_worktree_error(str(exc)):
                raise
            self._clear_stale_worktree_registration(repo_dir, worktree_dir)
            self.run(add_args, cwd=repo_dir)

    def remove_worktree(self, repo_dir: Path, worktree_dir: Path, force: bool = True) -> None:
        if self._uses_lit_backend(repo_dir):
            raise GitCommandError("lit repositories do not support Git worktrees in jakal-flow yet.")
        args = ["worktree", "remove"]
        if force:
            args.append("--force")
        args.append(str(worktree_dir))
        self.run(args, cwd=repo_dir, check=False)
        remove_tree(worktree_dir, ignore_errors=True)

    def delete_branch(self, repo_dir: Path, branch_name: str, force: bool = True) -> None:
        if self._uses_lit_backend(repo_dir):
            raise GitCommandError("lit repositories do not support branch deletion through jakal-flow yet.")
        args = ["branch", "-D" if force else "-d", branch_name]
        self.run(args, cwd=repo_dir, check=False)

    def cherry_pick(self, repo_dir: Path, revision: str) -> None:
        if self._uses_lit_backend(repo_dir):
            raise GitCommandError("lit repositories do not support cherry-pick through jakal-flow yet.")
        self.run(["cherry-pick", revision], cwd=repo_dir)

    def try_cherry_pick(self, repo_dir: Path, revision: str) -> CommandResult:
        if self._uses_lit_backend(repo_dir):
            raise GitCommandError("lit repositories do not support cherry-pick through jakal-flow yet.")
        return self.run(["cherry-pick", revision], cwd=repo_dir, check=False)

    def abort_cherry_pick(self, repo_dir: Path) -> None:
        if self._uses_lit_backend(repo_dir):
            return
        self.run(["cherry-pick", "--abort"], cwd=repo_dir, check=False)

    def skip_cherry_pick(self, repo_dir: Path) -> None:
        if self._uses_lit_backend(repo_dir):
            return
        self.run(["cherry-pick", "--skip"], cwd=repo_dir, check=False)

    def continue_cherry_pick(self, repo_dir: Path) -> None:
        if self._uses_lit_backend(repo_dir):
            raise GitCommandError("lit repositories do not support cherry-pick through jakal-flow yet.")
        self.run(["cherry-pick", "--continue"], cwd=repo_dir)

    def cherry_pick_in_progress(self, repo_dir: Path) -> bool:
        if self._uses_lit_backend(repo_dir):
            return False
        return bool(self._git_state_revision(repo_dir, "CHERRY_PICK_HEAD"))

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
        if self._uses_lit_backend(repo_dir):
            raise GitCommandError("lit repositories do not support fast-forward merge through jakal-flow yet.")
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
        if self._uses_lit_backend(repo_dir):
            return self.lit.conflicted_files(repo_dir)
        result = self.run(["diff", "--name-only", "--diff-filter=U"], cwd=repo_dir, check=False)
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    def checkout_conflict_side(self, repo_dir: Path, side: str, paths: list[str]) -> None:
        if self._uses_lit_backend(repo_dir):
            raise GitCommandError("lit repositories do not support conflict-side checkout through jakal-flow yet.")
        if side not in {"ours", "theirs"}:
            raise ValueError(f"Unsupported conflict side: {side}")
        if not paths:
            return
        self.run(["checkout", f"--{side}", "--", *paths], cwd=repo_dir)
        self.run(["add", "--", *paths], cwd=repo_dir)

    def hard_reset(self, repo_dir: Path, revision: str) -> None:
        if self._uses_lit_backend(repo_dir):
            try:
                self.lit.hard_reset(repo_dir, revision)
            except LitCommandError as exc:
                raise GitCommandError(str(exc)) from exc
            normalized_revision = str(revision).strip()
            if normalized_revision:
                self._current_revision_cache[str(repo_dir.resolve())] = normalized_revision
            return
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
