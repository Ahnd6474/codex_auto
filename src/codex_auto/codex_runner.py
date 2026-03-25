from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

from .models import CodexRunResult, ProjectContext
from .utils import compact_text, decode_process_output, ensure_dir, parse_json_text, read_text, write_json, write_text


class CodexRunner:
    _TRANSIENT_RETRY_LIMIT = 2
    _UNEXPECTED_TOKEN_PATTERN = re.compile(r"unexpected token", re.IGNORECASE)

    def __init__(self, codex_path: str) -> None:
        self.codex_path = self._resolve_codex_path(codex_path)

    def _resolve_codex_path(self, codex_path: str) -> str:
        if codex_path.lower() == "codex.cmd":
            appdata = os.environ.get("APPDATA")
            if appdata:
                candidate = Path(appdata) / "npm" / "codex.cmd"
                if candidate.exists():
                    return str(candidate)
        return codex_path

    def run_pass(
        self,
        context: ProjectContext,
        prompt: str,
        pass_type: str,
        block_index: int,
        search_enabled: bool = False,
    ) -> CodexRunResult:
        pass_slug = pass_type.replace(" ", "_").replace("/", "_")
        block_dir = ensure_dir(context.paths.logs_dir / f"block_{block_index:04d}")
        prompt_file = block_dir / f"{pass_slug}.prompt.md"
        output_file = block_dir / f"{pass_slug}.last_message.txt"
        event_file = block_dir / f"{pass_slug}.events.jsonl"
        diagnostics_file = block_dir / f"{pass_slug}.diagnostics.json"
        write_text(prompt_file, prompt)

        command = [self.codex_path, "-a", context.runtime.approval_mode]
        if search_enabled:
            command.append("--search")
        command.extend(
            [
                "exec",
                "-c",
                f'reasoning.effort="{context.runtime.effort}"',
                "-s",
                context.runtime.sandbox_mode,
                "-m",
                context.runtime.model,
                "--json",
                "-o",
                str(output_file),
                "-C",
                str(context.paths.repo_dir),
                "--add-dir",
                str(context.paths.docs_dir),
                "--add-dir",
                str(context.paths.memory_dir),
                "--add-dir",
                str(context.paths.state_dir),
                "-",
            ]
        )
        stdout = ""
        stderr = ""
        completed: subprocess.CompletedProcess[bytes] | None = None
        attempt_records: list[dict[str, object]] = []
        for attempt_index in range(1, self._TRANSIENT_RETRY_LIMIT + 2):
            try:
                output_file.unlink(missing_ok=True)
            except OSError:
                pass
            completed = subprocess.run(
                command,
                input=prompt.encode("utf-8"),
                capture_output=True,
                check=False,
            )
            stdout = decode_process_output(completed.stdout)
            stderr = decode_process_output(completed.stderr)
            attempt_last_message = read_text(output_file).strip()
            unexpected_token_detected = self._is_unexpected_token_failure(
                completed.returncode,
                stdout,
                stderr,
                attempt_last_message,
            )
            self._write_attempt_artifacts(
                block_dir=block_dir,
                pass_slug=pass_slug,
                attempt_index=attempt_index,
                stdout=stdout,
                stderr=stderr,
                last_message=attempt_last_message,
            )
            attempt_records.append(
                {
                    "attempt": attempt_index,
                    "returncode": completed.returncode,
                    "unexpected_token_detected": unexpected_token_detected,
                    "stdout_excerpt": compact_text(stdout, 500),
                    "stderr_excerpt": compact_text(stderr, 500),
                    "last_message_excerpt": compact_text(attempt_last_message, 500),
                }
            )
            if unexpected_token_detected and completed.returncode != 0 and attempt_index <= self._TRANSIENT_RETRY_LIMIT:
                time.sleep(float(attempt_index))
                continue
            break

        if completed is None:
            raise RuntimeError("Codex process did not start.")

        write_text(event_file, stdout)
        if stderr:
            write_text(block_dir / f"{pass_slug}.stderr.log", stderr)
        diagnostics = {
            "attempt_count": len(attempt_records),
            "unexpected_token_detected": any(
                bool(item.get("unexpected_token_detected")) for item in attempt_records
            ),
            "recovered_after_retry": completed.returncode == 0 and len(attempt_records) > 1,
            "attempts": attempt_records,
        }
        write_json(diagnostics_file, diagnostics)
        usage = self._extract_usage(stdout)
        return CodexRunResult(
            pass_type=pass_type,
            prompt_file=prompt_file,
            output_file=output_file,
            event_file=event_file,
            returncode=completed.returncode,
            search_enabled=search_enabled,
            changed_files=[],
            usage=usage,
            last_message=read_text(output_file).strip() or None,
            attempt_count=len(attempt_records),
            diagnostics=diagnostics,
        )

    def _extract_usage(self, stdout: str) -> dict[str, int]:
        usage = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = parse_json_text(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            if payload.get("type") != "turn.completed":
                continue
            turn_usage = payload.get("usage", {})
            for key in usage:
                value = turn_usage.get(key)
                if isinstance(value, int):
                    usage[key] += value
        return usage

    def _is_unexpected_token_failure(
        self,
        returncode: int,
        stdout: str,
        stderr: str,
        last_message: str,
    ) -> bool:
        if returncode == 0:
            return False
        combined = "\n".join(part for part in [stdout, stderr, last_message] if part.strip())
        return bool(self._UNEXPECTED_TOKEN_PATTERN.search(combined))

    def _write_attempt_artifacts(
        self,
        block_dir: Path,
        pass_slug: str,
        attempt_index: int,
        stdout: str,
        stderr: str,
        last_message: str,
    ) -> None:
        attempt_prefix = block_dir / f"{pass_slug}.attempt_{attempt_index}"
        write_text(attempt_prefix.with_suffix(".events.jsonl"), stdout)
        if stderr:
            write_text(attempt_prefix.with_suffix(".stderr.log"), stderr)
        if last_message:
            write_text(attempt_prefix.with_suffix(".last_message.txt"), last_message)
