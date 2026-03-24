from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .models import CodexRunResult, ProjectContext
from .utils import ensure_dir, read_text, write_text


class CodexRunner:
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
        completed = subprocess.run(
            command,
            input=prompt,
            text=True,
            capture_output=True,
            check=False,
        )
        write_text(event_file, completed.stdout)
        if completed.stderr:
            write_text(block_dir / f"{pass_slug}.stderr.log", completed.stderr)
        usage = self._extract_usage(completed.stdout)
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
        )

    def _extract_usage(self, stdout: str) -> dict[str, int]:
        usage = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("type") != "turn.completed":
                continue
            turn_usage = payload.get("usage", {})
            for key in usage:
                value = turn_usage.get(key)
                if isinstance(value, int):
                    usage[key] += value
        return usage
