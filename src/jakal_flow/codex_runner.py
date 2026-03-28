from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .codex_app_server import cli_backend_kind, is_auto_model, resolve_codex_path
from .execution_control import execution_scope_id, run_subprocess_capture
from .model_selection import normalize_reasoning_effort
from .model_providers import (
    normalize_local_model_provider,
    normalize_model_provider,
    provider_preset,
    provider_uses_openai_compatible_api,
)
from .models import CodexRunResult, ProjectContext
from .utils import compact_text, decode_process_output, ensure_dir, get_env_or_dotenv, parse_json_text, read_text, sanitized_subprocess_env, write_json, write_text


class CodexRunner:
    _TRANSIENT_RETRY_LIMIT = 2
    _UNEXPECTED_TOKEN_PATTERN = re.compile(r"unexpected token", re.IGNORECASE)

    def __init__(self, codex_path: str) -> None:
        self.codex_path = resolve_codex_path(codex_path)

    def run_pass(
        self,
        context: ProjectContext,
        prompt: str,
        pass_type: str,
        block_index: int,
        search_enabled: bool = False,
        reasoning_effort: str | None = None,
    ) -> CodexRunResult:
        pass_slug = pass_type.replace(" ", "_").replace("/", "_")
        block_dir = ensure_dir(context.paths.logs_dir / f"block_{block_index:04d}")
        prompt_file = block_dir / f"{pass_slug}.prompt.md"
        output_file = block_dir / f"{pass_slug}.last_message.txt"
        event_file = block_dir / f"{pass_slug}.events.jsonl"
        diagnostics_file = block_dir / f"{pass_slug}.diagnostics.json"
        formatted_prompt = self._format_prompt(context, prompt)
        write_text(prompt_file, formatted_prompt)

        provider = normalize_model_provider(getattr(context.runtime, "model_provider", ""))
        backend = self._backend_kind(provider)
        child_env = sanitized_subprocess_env(self._provider_environment(context, backend=backend))
        command = self._build_command(
            context,
            backend=backend,
            output_file=output_file,
            search_enabled=search_enabled,
            reasoning_effort=reasoning_effort,
        )
        stdout = ""
        stderr = ""
        completed = None
        attempt_records: list[dict[str, object]] = []
        started_monotonic = time.monotonic()
        scope_id = execution_scope_id(context)
        for attempt_index in range(1, self._TRANSIENT_RETRY_LIMIT + 2):
            try:
                output_file.unlink(missing_ok=True)
            except OSError:
                pass
            attempt_started_monotonic = time.monotonic()
            completed = run_subprocess_capture(
                command,
                scope_id=scope_id,
                label=f"{backend.title()} {pass_type}",
                cwd=context.paths.repo_dir,
                input_bytes=formatted_prompt.encode("utf-8"),
                env=child_env,
            )
            stdout = decode_process_output(completed.stdout)
            stderr = decode_process_output(completed.stderr)
            if backend == "gemini":
                self._write_gemini_output_file(output_file, stdout)
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
                    "duration_seconds": round(max(0.0, time.monotonic() - attempt_started_monotonic), 3),
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
            duration_seconds=round(max(0.0, time.monotonic() - started_monotonic), 3),
            diagnostics=diagnostics,
        )

    def _format_prompt(self, context: ProjectContext, prompt: str) -> str:
        if not getattr(context.runtime, "use_fast_mode", False):
            return prompt
        stripped = prompt.lstrip()
        if stripped.startswith("/fast"):
            return prompt
        return f"/fast\n\n{prompt}"

    def _extract_usage(self, stdout: str) -> dict[str, int]:
        usage = {
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_output_tokens": 0,
            "total_tokens": 0,
        }
        gemini_usage_detected = False
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
                if isinstance(payload, dict):
                    self._accumulate_gemini_usage(payload, usage)
                    gemini_usage_detected = True
                continue
            turn_usage = payload.get("usage", {})
            for key in usage:
                value = turn_usage.get(key)
                if isinstance(value, int):
                    usage[key] += value
        if stdout.strip() and not gemini_usage_detected:
            try:
                payload = parse_json_text(stdout)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                self._accumulate_gemini_usage(payload, usage)
        if usage["total_tokens"] <= 0:
            usage["total_tokens"] = (
                usage["input_tokens"] + usage["output_tokens"] + usage["reasoning_output_tokens"]
            )
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
        attempt_basename = f"{pass_slug}.attempt_{attempt_index}"
        write_text(block_dir / f"{attempt_basename}.events.jsonl", stdout)
        if stderr:
            write_text(block_dir / f"{attempt_basename}.stderr.log", stderr)
        if last_message:
            write_text(block_dir / f"{attempt_basename}.last_message.txt", last_message)

    def _provider_config_overrides(self, context: ProjectContext, *, provider: str | None = None) -> list[str]:
        provider = normalize_model_provider(provider or getattr(context.runtime, "model_provider", ""))
        if not provider_uses_openai_compatible_api(provider) or provider == "openai":
            return []
        overrides: list[str] = []
        preset = provider_preset(provider)
        base_url = str(getattr(context.runtime, "provider_base_url", "") or "").strip() or preset.default_base_url
        if base_url:
            overrides.extend(["-c", f"openai_base_url={self._toml_string(base_url)}"])
        return overrides

    def _provider_environment(self, context: ProjectContext, *, backend: str) -> dict[str, str]:
        provider = normalize_model_provider(getattr(context.runtime, "model_provider", ""))
        if backend == "gemini" or provider == "gemini":
            api_key_env_name = str(getattr(context.runtime, "provider_api_key_env", "") or "").strip() or "GEMINI_API_KEY"
            if not api_key_env_name:
                return {}
            dotenv_path = context.paths.repo_dir / ".env"
            api_key = get_env_or_dotenv(api_key_env_name, dotenv_path).strip()
            if not api_key:
                return {}
            return {"GEMINI_API_KEY": api_key}
        if not provider_uses_openai_compatible_api(provider):
            return {}
        preset = provider_preset(provider)
        provider_base_url = str(getattr(context.runtime, "provider_base_url", "") or "").strip() or preset.default_base_url
        api_key_env_name = str(getattr(context.runtime, "provider_api_key_env", "") or "").strip() or preset.default_api_key_env
        dotenv_path = context.paths.repo_dir / ".env"
        env_updates: dict[str, str] = {}
        if provider_base_url:
            env_updates["OPENAI_BASE_URL"] = provider_base_url
        if api_key_env_name:
            api_key = get_env_or_dotenv(api_key_env_name, dotenv_path).strip()
            if api_key:
                env_updates["OPENAI_API_KEY"] = api_key
        return env_updates

    def _toml_string(self, value: str) -> str:
        escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    def _backend_kind(self, provider: str) -> str:
        if provider == "gemini" or cli_backend_kind(self.codex_path) == "gemini":
            return "gemini"
        return "codex"

    def _build_command(
        self,
        context: ProjectContext,
        *,
        backend: str,
        output_file: Path,
        search_enabled: bool,
        reasoning_effort: str | None,
    ) -> list[str]:
        provider = normalize_model_provider(getattr(context.runtime, "model_provider", ""))
        if backend == "gemini":
            return self._build_gemini_command(context)
        command = [self.codex_path]
        if provider == "oss":
            command.append("--oss")
            local_provider = normalize_local_model_provider(getattr(context.runtime, "local_model_provider", ""))
            if local_provider:
                command.extend(["--local-provider", local_provider])
        else:
            command.extend(self._provider_config_overrides(context, provider=provider))
        command.extend(["-a", context.runtime.approval_mode])
        if search_enabled:
            command.append("--search")
        command.extend(
            [
                "exec",
                "-c",
                f'reasoning.effort="{normalize_reasoning_effort(str(reasoning_effort or getattr(context.runtime, "effort", "")), fallback="medium")}"',
                "-s",
                context.runtime.sandbox_mode,
            ]
        )
        if not is_auto_model(context.runtime.model):
            command.extend(["-m", context.runtime.model])
        command.extend(
            [
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
        return command

    def _build_gemini_command(
        self,
        context: ProjectContext,
    ) -> list[str]:
        command = [
            self.codex_path,
            "--output-format",
            "json",
            "--approval-mode",
            "yolo",
            "--include-directories",
            ",".join(
                [
                    str(context.paths.docs_dir),
                    str(context.paths.memory_dir),
                    str(context.paths.state_dir),
                ]
            ),
        ]
        if context.runtime.sandbox_mode != "danger-full-access":
            command.append("--sandbox")
        if not is_auto_model(context.runtime.model):
            command.extend(["-m", context.runtime.model])
        return command

    def _write_gemini_output_file(self, output_file: Path, stdout: str) -> None:
        response_text = stdout.strip()
        if response_text:
            try:
                payload = parse_json_text(response_text)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                response_value = payload.get("response")
                if isinstance(response_value, str) and response_value.strip():
                    response_text = response_value.strip()
        if response_text:
            write_text(output_file, response_text)

    def _accumulate_gemini_usage(self, payload: dict[str, object], usage: dict[str, int]) -> None:
        stats = payload.get("stats")
        if not isinstance(stats, dict):
            return
        models = stats.get("models")
        if not isinstance(models, dict):
            return
        for details in models.values():
            if not isinstance(details, dict):
                continue
            tokens = details.get("tokens")
            if not isinstance(tokens, dict):
                continue
            prompt_tokens = tokens.get("prompt")
            cached_tokens = tokens.get("cached")
            candidate_tokens = tokens.get("candidates")
            thought_tokens = tokens.get("thoughts")
            total_tokens = tokens.get("total")
            if isinstance(prompt_tokens, int):
                usage["input_tokens"] += prompt_tokens
            if isinstance(cached_tokens, int):
                usage["cached_input_tokens"] += cached_tokens
            if isinstance(candidate_tokens, int):
                usage["output_tokens"] += candidate_tokens
            if isinstance(thought_tokens, int):
                usage["reasoning_output_tokens"] += thought_tokens
            if isinstance(total_tokens, int):
                usage["total_tokens"] += total_tokens
