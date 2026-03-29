from __future__ import annotations

import hashlib
import platform
import sys
from pathlib import Path
from time import monotonic

from .execution_control import execution_scope_id, run_subprocess_capture
from .models import ProjectContext, TestRunResult
from .errors import SubprocessTimeoutError
from .subprocess_utils import run_subprocess
from .utils import compact_text, decode_process_output, ensure_dir, now_utc_iso, read_json, read_text, sanitized_subprocess_env, write_json, write_text

RELEVANT_ENV_FILES = (
    "pyproject.toml",
    "poetry.lock",
    "requirements.txt",
    "requirements-dev.txt",
    "requirements-test.txt",
    "Pipfile.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "bun.lockb",
    "Cargo.lock",
    "go.sum",
    "Gemfile.lock",
    "composer.lock",
)
GIT_FINGERPRINT_TIMEOUT_SECONDS = 20.0
IGNORED_RUNTIME_PATH_PARTS = frozenset(
    {
        ".git",
        ".lineages",
        ".parallel_runs",
        ".pytest_cache",
        "__pycache__",
        "jakal-flow-logs",
    }
)
SHORT_CACHE_KEY_LENGTH = 16


class VerificationRunner:
    def _failure_reason(self, stdout: str, stderr: str, max_chars: int = 280) -> str:
        source = stderr if str(stderr).strip() else stdout
        lines = [line.strip() for line in str(source).splitlines() if line.strip()]
        if not lines:
            return ""
        excerpt = " | ".join(lines[-4:])
        return compact_text(excerpt, max_chars=max_chars)

    def _summary(self, command: str, returncode: int, *, stdout: str, stderr: str, cached: bool = False) -> tuple[str, str]:
        failure_reason = self._failure_reason(stdout, stderr) if returncode != 0 else ""
        summary = f"{command} exited with {returncode}"
        if cached:
            summary = f"{summary} (cached)"
        if failure_reason:
            summary = f"{summary}: {failure_reason}"
        return summary, failure_reason

    def run(
        self,
        context: ProjectContext,
        block_index: int,
        label: str,
        command: str | None = None,
    ) -> TestRunResult:
        verify_command = str(command or context.runtime.test_cmd).strip() or context.runtime.test_cmd
        block_dir = context.paths.logs_dir / f"block_{block_index:04d}"
        stdout_file = block_dir / f"{label}.test.stdout.log"
        stderr_file = block_dir / f"{label}.test.stderr.log"
        state_fingerprint = self._compute_state_fingerprint(context.paths.repo_dir)
        environment_fingerprint = self._environment_fingerprint(context.paths.repo_dir)
        cache_key = self._cache_key(verify_command, state_fingerprint, environment_fingerprint)
        cache_root = ensure_dir(context.paths.state_dir / "verification_cache")
        cache_entry_file = self._cache_entry_file(cache_root, cache_key)
        cached = read_json(cache_entry_file, default=None)
        if not isinstance(cached, dict):
            cached = read_json(cache_root / f"{cache_key}.json", default=None)
        if isinstance(cached, dict):
            cached_result = self._replay_cached_result(
                cached,
                stdout_file=stdout_file,
                stderr_file=stderr_file,
                verify_command=verify_command,
                state_fingerprint=state_fingerprint,
                cache_key=cache_key,
            )
            if cached_result is not None:
                return cached_result

        start = monotonic()
        completed = run_subprocess_capture(
            verify_command,
            scope_id=execution_scope_id(context),
            label=f"verification {label}",
            cwd=context.paths.repo_dir,
            env=sanitized_subprocess_env(),
            shell=True,
        )
        duration_seconds = round(max(0.0, monotonic() - start), 3)
        stdout = decode_process_output(completed.stdout)
        stderr = decode_process_output(completed.stderr)
        write_text(stdout_file, stdout)
        write_text(stderr_file, stderr)
        summary, failure_reason = self._summary(verify_command, completed.returncode, stdout=stdout, stderr=stderr)

        cache_stdout_file = self._cache_artifact_file(cache_root, cache_key, "stdout")
        cache_stderr_file = self._cache_artifact_file(cache_root, cache_key, "stderr")
        write_text(cache_stdout_file, stdout)
        write_text(cache_stderr_file, stderr)
        write_json(
            cache_entry_file,
            {
                "cache_key": cache_key,
                "created_at": now_utc_iso(),
                "command": verify_command,
                "returncode": completed.returncode,
                "summary": summary,
                "failure_reason": failure_reason,
                "state_fingerprint": state_fingerprint,
                "environment_fingerprint": environment_fingerprint,
                "duration_seconds": duration_seconds,
                "stdout_cache_file": str(cache_stdout_file),
                "stderr_cache_file": str(cache_stderr_file),
            },
        )
        return TestRunResult(
            command=verify_command,
            returncode=completed.returncode,
            stdout_file=stdout_file,
            stderr_file=stderr_file,
            summary=summary,
            failure_reason=failure_reason,
            duration_seconds=duration_seconds,
            source_duration_seconds=duration_seconds,
            cache_hit=False,
            state_fingerprint=state_fingerprint,
            cache_key=cache_key,
        )

    def _replay_cached_result(
        self,
        cached: dict[str, object],
        *,
        stdout_file: Path,
        stderr_file: Path,
        verify_command: str,
        state_fingerprint: str,
        cache_key: str,
    ) -> TestRunResult | None:
        stdout_cache = Path(str(cached.get("stdout_cache_file", "")).strip())
        stderr_cache = Path(str(cached.get("stderr_cache_file", "")).strip())
        if not stdout_cache.exists() or not stderr_cache.exists():
            return None
        stdout = read_text(stdout_cache)
        stderr = read_text(stderr_cache)
        write_text(stdout_file, stdout)
        write_text(stderr_file, stderr)
        returncode = int(cached.get("returncode", 1))
        cached_failure_reason = str(cached.get("failure_reason", "")).strip()
        cached_summary, computed_failure_reason = self._summary(
            verify_command,
            returncode,
            stdout=stdout,
            stderr=stderr,
            cached=True,
        )
        if not cached_failure_reason:
            cached_failure_reason = computed_failure_reason
        source_duration_seconds = round(float(cached.get("duration_seconds", 0.0) or 0.0), 3)
        return TestRunResult(
            command=verify_command,
            returncode=returncode,
            stdout_file=stdout_file,
            stderr_file=stderr_file,
            summary=cached_summary,
            failure_reason=cached_failure_reason,
            duration_seconds=0.0,
            source_duration_seconds=source_duration_seconds,
            cache_hit=True,
            state_fingerprint=state_fingerprint,
            cache_key=cache_key,
        )

    def _cache_key(self, command: str, state_fingerprint: str, environment_fingerprint: str) -> str:
        digest = hashlib.sha1()
        digest.update(command.encode("utf-8"))
        digest.update(b"\n")
        digest.update(state_fingerprint.encode("utf-8"))
        digest.update(b"\n")
        digest.update(environment_fingerprint.encode("utf-8"))
        return digest.hexdigest()

    def _compute_state_fingerprint(self, repo_dir: Path) -> str:
        try:
            head_result = run_subprocess(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_dir,
                capture_output=True,
                check=False,
                timeout_seconds=GIT_FINGERPRINT_TIMEOUT_SECONDS,
            )
        except (OSError, SubprocessTimeoutError):
            return self._fallback_tree_fingerprint(repo_dir)
        head_revision = decode_process_output(head_result.stdout).strip() if head_result.returncode == 0 else ""
        if not head_revision:
            return self._fallback_tree_fingerprint(repo_dir)

        try:
            status_result = run_subprocess(
                ["git", "status", "--porcelain=v1", "--untracked-files=all"],
                cwd=repo_dir,
                capture_output=True,
                check=False,
                timeout_seconds=GIT_FINGERPRINT_TIMEOUT_SECONDS,
            )
        except (OSError, SubprocessTimeoutError):
            return self._fallback_tree_fingerprint(repo_dir)
        if status_result.returncode != 0:
            return self._fallback_tree_fingerprint(repo_dir)

        digest = hashlib.sha1()
        digest.update(f"head:{head_revision}\n".encode("utf-8"))
        for entry in self._parse_status_entries(decode_process_output(status_result.stdout)):
            digest.update(f"status:{entry['status']}|path:{entry['path']}|orig:{entry['orig_path']}\n".encode("utf-8"))
            if entry["orig_path"]:
                self._update_path_hash(digest, repo_dir / str(entry["orig_path"]))
            self._update_path_hash(digest, repo_dir / str(entry["path"]))
        return digest.hexdigest()

    def _environment_fingerprint(self, repo_dir: Path) -> str:
        digest = hashlib.sha1()
        digest.update(sys.executable.encode("utf-8"))
        digest.update(b"\n")
        digest.update(platform.platform().encode("utf-8"))
        for name in RELEVANT_ENV_FILES:
            path = repo_dir / name
            if not path.exists() or not path.is_file():
                continue
            digest.update(f"\n{name}\n".encode("utf-8"))
            digest.update(hashlib.sha1(path.read_bytes()).hexdigest().encode("utf-8"))
        return digest.hexdigest()

    def _fallback_tree_fingerprint(self, repo_dir: Path) -> str:
        digest = hashlib.sha1()
        for path in sorted(repo_dir.rglob("*")):
            if self._should_ignore_path(path, repo_dir):
                continue
            try:
                if path.is_dir():
                    continue
                digest.update(str(path.relative_to(repo_dir)).replace("\\", "/").encode("utf-8"))
                digest.update(b"\n")
                digest.update(hashlib.sha1(path.read_bytes()).hexdigest().encode("utf-8"))
                digest.update(b"\n")
            except OSError:
                continue
        return digest.hexdigest()

    def _parse_status_entries(self, output: str) -> list[dict[str, str]]:
        entries: list[dict[str, str]] = []
        for raw_line in output.splitlines():
            line = raw_line.rstrip()
            if len(line) < 4:
                continue
            status = line[:2]
            payload = line[3:].strip()
            orig_path = ""
            path = payload
            if " -> " in payload and any(flag in status for flag in ("R", "C")):
                orig_path, path = payload.split(" -> ", 1)
            entries.append(
                {
                    "status": status,
                    "path": path.strip(),
                    "orig_path": orig_path.strip(),
                }
            )
        entries.sort(key=lambda item: (item["path"], item["orig_path"], item["status"]))
        return entries

    def _update_path_hash(self, digest, path: Path) -> None:
        normalized = str(path).replace("\\", "/")
        digest.update(normalized.encode("utf-8"))
        digest.update(b"\n")
        try:
            if not path.exists():
                digest.update(b"<missing>\n")
                return
            if path.is_dir():
                digest.update(b"<dir>\n")
                return
            if path.is_symlink():
                digest.update(b"<symlink>\n")
                digest.update(str(path.readlink()).encode("utf-8"))
                digest.update(b"\n")
                return
            digest.update(hashlib.sha1(path.read_bytes()).hexdigest().encode("utf-8"))
            digest.update(b"\n")
        except OSError as exc:
            digest.update(f"<unreadable:{exc.__class__.__name__}>\n".encode("utf-8"))

    def _cache_entry_file(self, cache_root: Path, cache_key: str) -> Path:
        return cache_root / f"{self._cache_file_stem(cache_key)}.json"

    def _cache_artifact_file(self, cache_root: Path, cache_key: str, kind: str) -> Path:
        suffix = "out.log" if kind == "stdout" else "err.log"
        return cache_root / f"{self._cache_file_stem(cache_key)}.{suffix}"

    def _cache_file_stem(self, cache_key: str) -> str:
        normalized = str(cache_key).strip().lower()
        return normalized[:SHORT_CACHE_KEY_LENGTH] or "cache"

    def _should_ignore_path(self, path: Path, repo_dir: Path) -> bool:
        try:
            relative_parts = path.relative_to(repo_dir).parts
        except ValueError:
            relative_parts = path.parts
        return any(part in IGNORED_RUNTIME_PATH_PARTS for part in relative_parts)
