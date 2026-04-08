from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys

from .models import CommandResult
from .subprocess_utils import run_subprocess
from .utils import decode_process_output


class LitCommandError(RuntimeError):
    pass


LIT_QUERY_TIMEOUT_SECONDS = 10.0
LIT_STATUS_TIMEOUT_SECONDS = 60.0
LIT_LOCAL_MUTATION_TIMEOUT_SECONDS = 90.0
LIT_COMMIT_TIMEOUT_SECONDS = 300.0
LIT_MERGE_TIMEOUT_SECONDS = 180.0


class LitOps:
    def __init__(self, command: str = "lit") -> None:
        self.command = str(command or "lit").strip() or "lit"

    def _candidate_commands(self) -> list[list[str]]:
        candidates: list[list[str]] = [[self.command]]
        module_command = self._module_command()
        if module_command and module_command not in candidates:
            candidates.append(module_command)
        return candidates

    def _module_command(self) -> list[str] | None:
        if self.command != "lit":
            return None
        python_executable = str(sys.executable or "").strip()
        if not python_executable:
            return None
        if importlib.util.find_spec("lit") is None:
            return None
        return [python_executable, "-m", "lit"]

    def run(
        self,
        args: list[str],
        cwd: Path,
        check: bool = True,
        env: dict[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> CommandResult:
        process_env = None
        if env:
            process_env = os.environ.copy()
            process_env.update(env)
        launch_errors: list[OSError] = []
        for prefix in self._candidate_commands():
            command = [*prefix, *args]
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
                launch_errors.append(exc)
                continue
            stdout = completed.stdout if isinstance(completed.stdout, str) else decode_process_output(completed.stdout)
            stderr = completed.stderr if isinstance(completed.stderr, str) else decode_process_output(completed.stderr)
            result = CommandResult(
                command=command,
                returncode=completed.returncode,
                stdout=stdout,
                stderr=stderr,
            )
            if check and completed.returncode != 0:
                detail = stderr.strip() or stdout.strip()
                raise LitCommandError(
                    f"lit {' '.join(args)} failed with code {completed.returncode}: {detail}"
                )
            return result
        detail = str(launch_errors[-1]).strip() if launch_errors else "unknown error"
        raise LitCommandError(
            f"{self.command} executable could not be started. Install the published package with "
            f"'python -m pip install jakal-lit' or ensure 'lit' is on PATH: {detail}"
        ) from (launch_errors[-1] if launch_errors else None)

    def _timeout_seconds_for_args(self, args: list[str], override: float | None = None) -> float:
        if override is not None:
            return float(override)
        if not args:
            return LIT_QUERY_TIMEOUT_SECONDS
        primary = str(args[0]).strip().lower()
        if primary in {"status", "verify"}:
            return LIT_STATUS_TIMEOUT_SECONDS
        if primary == "commit":
            return LIT_COMMIT_TIMEOUT_SECONDS
        if primary in {"merge", "rebase", "rollback"}:
            return LIT_MERGE_TIMEOUT_SECONDS
        if primary in {"add", "branch", "checkout", "lineage", "restore"}:
            return LIT_LOCAL_MUTATION_TIMEOUT_SECONDS
        return LIT_QUERY_TIMEOUT_SECONDS

    def is_lit_repository(self, repo_dir: Path) -> bool:
        return (repo_dir / ".lit").exists()

    def ensure_repository(self, repo_dir: Path, branch: str) -> bool:
        repo_dir.mkdir(parents=True, exist_ok=True)
        created = False
        if not self.is_lit_repository(repo_dir):
            self.run(["init", ".", "--branch", branch or "main"], cwd=repo_dir)
            created = True
        normalized_branch = str(branch or "").strip()
        if not normalized_branch:
            return created
        current_branch = self.current_branch(repo_dir)
        if current_branch == normalized_branch:
            return created
        if self.branch_exists(repo_dir, normalized_branch):
            self.run(["checkout", normalized_branch], cwd=repo_dir)
            return created
        if self.has_commits(repo_dir):
            self.run(["branch", normalized_branch, "--start-point", "HEAD"], cwd=repo_dir)
            self.run(["checkout", normalized_branch], cwd=repo_dir)
            return created
        self._write_head_branch(repo_dir, normalized_branch)
        return created

    def current_branch(self, repo_dir: Path) -> str:
        head_value = self._read_head(repo_dir)
        if not head_value.startswith("refs/heads/"):
            return ""
        return head_value[len("refs/heads/") :].strip()

    def current_revision(self, repo_dir: Path) -> str:
        branch_name = self.current_branch(repo_dir)
        if branch_name:
            return self.local_branch_revision(repo_dir, branch_name)
        head_value = self._read_head(repo_dir)
        if head_value.startswith("refs/heads/"):
            return ""
        return head_value

    def has_commits(self, repo_dir: Path) -> bool:
        return bool(self.current_revision(repo_dir))

    def branch_exists(self, repo_dir: Path, branch_name: str) -> bool:
        return self._branch_path(repo_dir, branch_name).exists()

    def local_branch_revision(self, repo_dir: Path, branch_name: str) -> str:
        path = self._branch_path(repo_dir, branch_name)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8").strip()

    def has_changes(self, repo_dir: Path) -> bool:
        return bool(self.changed_files(repo_dir))

    def changed_files(self, repo_dir: Path) -> list[str]:
        result = self.run(["status"], cwd=repo_dir, check=False)
        output = result.stdout.strip()
        if not output or "nothing to commit, working tree clean" in output:
            return []
        paths: list[str] = []
        seen: set[str] = set()
        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.endswith(":"):
                continue
            if line == "nothing to commit, working tree clean":
                continue
            if ": " in line:
                _, candidate = line.split(": ", 1)
            else:
                candidate = line
            normalized = candidate.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            paths.append(normalized)
        return paths

    def add_paths(self, repo_dir: Path, paths: list[str]) -> None:
        normalized_paths = [str(path).strip() for path in paths if str(path).strip()]
        if not normalized_paths:
            return
        self.run(["add", *normalized_paths], cwd=repo_dir)

    def add_all(self, repo_dir: Path) -> None:
        self.add_paths(repo_dir, self.changed_files(repo_dir))

    def commit_staged(self, repo_dir: Path, message: str) -> str:
        self.run(["commit", "-m", message], cwd=repo_dir)
        return self.current_revision(repo_dir)

    def commit_all(self, repo_dir: Path, message: str) -> str:
        self.add_all(repo_dir)
        return self.commit_staged(repo_dir, message)

    def create_initial_commit(self, repo_dir: Path, message: str) -> str:
        self.add_all(repo_dir)
        return self.commit_staged(repo_dir, message)

    def commit_paths(self, repo_dir: Path, paths: list[str], message: str) -> str:
        self.add_paths(repo_dir, paths)
        return self.commit_staged(repo_dir, message)

    def conflicted_files(self, repo_dir: Path) -> list[str]:
        merge_state = self._read_json(repo_dir / ".lit" / "state" / "merge.json")
        rebase_state = self._read_json(repo_dir / ".lit" / "state" / "rebase.json")
        conflicts: list[str] = []
        for payload in (merge_state, rebase_state):
            items = payload.get("conflicts", []) if isinstance(payload, dict) else []
            for item in items:
                path = str(item).strip()
                if path and path not in conflicts:
                    conflicts.append(path)
        return conflicts

    def hard_reset(self, repo_dir: Path, revision: str) -> None:
        normalized_revision = str(revision or "").strip()
        if not normalized_revision:
            raise LitCommandError("lit hard reset requires a revision.")
        current_branch = self.current_branch(repo_dir)
        self.run(["restore", "--source", normalized_revision], cwd=repo_dir)
        if current_branch:
            branch_path = self._branch_path(repo_dir, current_branch)
            branch_path.parent.mkdir(parents=True, exist_ok=True)
            branch_path.write_text(f"{normalized_revision}\n", encoding="utf-8")
        else:
            head_path = repo_dir / ".lit" / "HEAD"
            head_path.write_text(f"{normalized_revision}\n", encoding="utf-8")

    def merge_revision(self, repo_dir: Path, revision: str) -> None:
        result = self.run(["merge", revision], cwd=repo_dir, check=False)
        if result.returncode != 0 or self.conflicted_files(repo_dir):
            detail = result.stderr.strip() or result.stdout.strip() or f"Merge failed for {revision}"
            raise LitCommandError(detail)

    def rollback_to_revision(self, repo_dir: Path, revision: str) -> None:
        normalized_revision = str(revision or "").strip()
        if not normalized_revision:
            raise LitCommandError("lit rollback requires a revision.")
        self.hard_reset(repo_dir, normalized_revision)

    def _read_head(self, repo_dir: Path) -> str:
        head_path = repo_dir / ".lit" / "HEAD"
        if not head_path.exists():
            return ""
        value = head_path.read_text(encoding="utf-8").strip()
        if value.startswith("ref: "):
            return value[len("ref: ") :].strip()
        return value

    def _write_head_branch(self, repo_dir: Path, branch_name: str) -> None:
        head_path = repo_dir / ".lit" / "HEAD"
        head_path.parent.mkdir(parents=True, exist_ok=True)
        head_path.write_text(f"ref: refs/heads/{branch_name}\n", encoding="utf-8")
        branch_path = self._branch_path(repo_dir, branch_name)
        branch_path.parent.mkdir(parents=True, exist_ok=True)
        if not branch_path.exists():
            branch_path.write_text("", encoding="utf-8")

    def _branch_path(self, repo_dir: Path, branch_name: str) -> Path:
        parts = [part for part in str(branch_name).strip().split("/") if part]
        return repo_dir / ".lit" / "refs" / "heads" / Path(*parts)

    def _read_json(self, path: Path) -> dict[str, object] | None:
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None


__all__ = ["LitCommandError", "LitOps"]
