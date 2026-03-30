from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from .codex_app_server import cli_backend_kind, is_auto_model, resolve_codex_path
from .execution_control import execution_scope_id, run_subprocess_capture
from .model_selection import normalize_reasoning_effort
from .model_providers import (
    effective_local_model_provider,
    provider_backend_kind,
    normalize_local_model_provider,
    normalize_model_provider,
    provider_preset,
    provider_uses_oss_mode,
    provider_uses_openai_compatible_api,
)
from .models import CodexRunResult, ProjectContext
from .step_models import provider_execution_preflight_error
from .utils import compact_text, decode_process_output, ensure_dir, get_env_or_dotenv, parse_json_text, read_text, sanitized_subprocess_env, write_json, write_text


EXECUTION_PATH_ALIAS_LENGTH_THRESHOLD = 140


@dataclass(slots=True)
class _CLIExecutionLayout:
    repo_dir: Path
    docs_dir: Path
    memory_dir: Path
    state_dir: Path
    output_file: Path


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
        preflight_error = provider_execution_preflight_error(
            provider,
            codex_path=self.codex_path,
            repo_dir=context.paths.repo_dir,
            provider_api_key_env=str(getattr(context.runtime, "provider_api_key_env", "") or "").strip(),
            model=str(getattr(context.runtime, "model", "") or getattr(context.runtime, "model_slug_input", "")).strip(),
        )
        if preflight_error:
            raise RuntimeError(preflight_error)
        child_env = sanitized_subprocess_env(self._provider_environment(context, backend=backend))
        stdout = ""
        stderr = ""
        completed = None
        attempt_records: list[dict[str, object]] = []
        started_monotonic = time.monotonic()
        scope_id = execution_scope_id(context)
        with self._execution_layout(context, output_file) as execution_layout:
            runtime_prompt = self._execution_prompt(formatted_prompt, context, execution_layout)
            command = self._build_command(
                context,
                backend=backend,
                output_file=execution_layout.output_file,
                search_enabled=search_enabled,
                reasoning_effort=reasoning_effort,
                prompt_text=runtime_prompt,
                execution_layout=execution_layout,
            )
            for attempt_index in range(1, self._TRANSIENT_RETRY_LIMIT + 2):
                for candidate in {output_file, execution_layout.output_file}:
                    try:
                        candidate.unlink(missing_ok=True)
                    except OSError:
                        pass
                attempt_started_monotonic = time.monotonic()
                completed = run_subprocess_capture(
                    command,
                    scope_id=scope_id,
                    label=f"{backend.title()} {pass_type}",
                    cwd=execution_layout.repo_dir,
                    input_bytes=None if backend in {"claude", "qwen"} else runtime_prompt.encode("utf-8"),
                    env=child_env,
                )
                stdout = decode_process_output(completed.stdout)
                stderr = decode_process_output(completed.stderr)
                if backend == "codex":
                    self._sync_output_file(execution_layout.output_file, output_file)
                elif backend == "gemini":
                    self._write_gemini_output_file(output_file, stdout)
                elif backend == "claude":
                    self._write_claude_output_file(output_file, stdout)
                elif backend == "qwen":
                    self._write_qwen_output_file(output_file, stdout)
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
                if isinstance(payload, dict) and self._accumulate_gemini_usage(payload, usage):
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
                self._accumulate_claude_usage(payload, usage)
                if isinstance(payload.get("message"), dict):
                    self._accumulate_qwen_usage(payload, usage)
            elif isinstance(payload, list):
                for item in payload:
                    if not isinstance(item, dict):
                        continue
                    self._accumulate_qwen_usage(item, usage)
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
        preset = provider_preset(provider)
        if backend == "claude" or provider_backend_kind(provider) == "claude":
            provider_base_url = str(getattr(context.runtime, "provider_base_url", "") or "").strip() or preset.default_base_url
            api_key_env_name = str(getattr(context.runtime, "provider_api_key_env", "") or "").strip() or preset.default_api_key_env
            dotenv_path = context.paths.repo_dir / ".env"
            env_updates: dict[str, str] = {}
            if provider_base_url:
                env_updates["ANTHROPIC_BASE_URL"] = provider_base_url
            if api_key_env_name:
                api_key = get_env_or_dotenv(api_key_env_name, dotenv_path).strip()
                if api_key:
                    env_updates["ANTHROPIC_API_KEY"] = api_key
                    env_updates["ANTHROPIC_AUTH_TOKEN"] = api_key
            selected_model = str(getattr(context.runtime, "model", "") or "").strip()
            if selected_model:
                env_updates["ANTHROPIC_MODEL"] = selected_model
                if provider != "claude":
                    env_updates["ANTHROPIC_DEFAULT_SONNET_MODEL"] = selected_model
                    env_updates["ANTHROPIC_DEFAULT_OPUS_MODEL"] = selected_model
                    env_updates["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = selected_model
                    env_updates["ANTHROPIC_SMALL_FAST_MODEL"] = selected_model
            return env_updates
        if backend == "gemini" or provider == "gemini":
            api_key_env_name = str(getattr(context.runtime, "provider_api_key_env", "") or "").strip() or "GEMINI_API_KEY"
            if not api_key_env_name:
                return {}
            dotenv_path = context.paths.repo_dir / ".env"
            api_key = get_env_or_dotenv(api_key_env_name, dotenv_path).strip()
            if not api_key:
                return {}
            return {"GEMINI_API_KEY": api_key}
        if backend == "qwen" or provider == "qwen_code":
            provider_base_url = str(getattr(context.runtime, "provider_base_url", "") or "").strip() or preset.default_base_url
            api_key_env_name = str(getattr(context.runtime, "provider_api_key_env", "") or "").strip() or preset.default_api_key_env
            dotenv_path = context.paths.repo_dir / ".env"
            env_updates: dict[str, str] = {}
            if api_key_env_name:
                api_key = get_env_or_dotenv(api_key_env_name, dotenv_path).strip()
                if api_key:
                    env_updates["OPENAI_API_KEY"] = api_key
                    if provider_base_url:
                        env_updates["OPENAI_BASE_URL"] = provider_base_url
                    selected_model = str(getattr(context.runtime, "model", "") or "").strip()
                    if selected_model:
                        env_updates["OPENAI_MODEL"] = selected_model
            return env_updates
        if not provider_uses_openai_compatible_api(provider):
            return {}
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
        explicit_backend = provider_backend_kind(provider)
        if explicit_backend in {"claude", "gemini", "qwen"}:
            return explicit_backend
        detected_backend = cli_backend_kind(self.codex_path)
        if detected_backend in {"claude", "gemini", "qwen"}:
            return detected_backend
        return "codex"

    def _build_command(
        self,
        context: ProjectContext,
        *,
        backend: str,
        output_file: Path,
        search_enabled: bool,
        reasoning_effort: str | None,
        prompt_text: str,
        execution_layout: _CLIExecutionLayout | None = None,
    ) -> list[str]:
        execution_layout = execution_layout or _CLIExecutionLayout(
            repo_dir=context.paths.repo_dir,
            docs_dir=context.paths.docs_dir,
            memory_dir=context.paths.memory_dir,
            state_dir=context.paths.state_dir,
            output_file=output_file,
        )
        provider = normalize_model_provider(getattr(context.runtime, "model_provider", ""))
        if backend == "claude":
            return self._build_claude_command(
                context,
                prompt_text=prompt_text,
                reasoning_effort=reasoning_effort,
                execution_layout=execution_layout,
            )
        if backend == "gemini":
            return self._build_gemini_command(context, execution_layout=execution_layout)
        if backend == "qwen":
            return self._build_qwen_command(context, prompt_text=prompt_text, execution_layout=execution_layout)
        command = [self.codex_path]
        if provider_uses_oss_mode(provider):
            command.append("--oss")
            local_provider = effective_local_model_provider(
                provider,
                normalize_local_model_provider(getattr(context.runtime, "local_model_provider", "")),
            )
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
                str(execution_layout.repo_dir),
                "--add-dir",
                str(execution_layout.docs_dir),
                "--add-dir",
                str(execution_layout.memory_dir),
                "--add-dir",
                str(execution_layout.state_dir),
                "-",
            ]
        )
        return command

    def _build_claude_command(
        self,
        context: ProjectContext,
        *,
        prompt_text: str,
        reasoning_effort: str | None,
        execution_layout: _CLIExecutionLayout,
    ) -> list[str]:
        command = [
            self.codex_path,
            "--print",
            "--output-format",
            "json",
            "--bare",
            "--dangerously-skip-permissions",
        ]
        effort = self._claude_reasoning_effort(
            normalize_reasoning_effort(str(reasoning_effort or getattr(context.runtime, "effort", "")), fallback="medium")
        )
        if effort:
            command.extend(["--effort", effort])
        if not is_auto_model(context.runtime.model):
            command.extend(["--model", context.runtime.model])
        for directory in (execution_layout.docs_dir, execution_layout.memory_dir, execution_layout.state_dir):
            command.extend(["--add-dir", str(directory)])
        command.append(prompt_text)
        return command

    def _build_gemini_command(
        self,
        context: ProjectContext,
        *,
        execution_layout: _CLIExecutionLayout,
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
                    str(execution_layout.docs_dir),
                    str(execution_layout.memory_dir),
                    str(execution_layout.state_dir),
                ]
            ),
        ]
        if context.runtime.sandbox_mode != "danger-full-access":
            command.append("--sandbox")
        if not is_auto_model(context.runtime.model):
            command.extend(["-m", context.runtime.model])
        return command

    def _build_qwen_command(
        self,
        context: ProjectContext,
        *,
        prompt_text: str,
        execution_layout: _CLIExecutionLayout,
    ) -> list[str]:
        command = [
            self.codex_path,
            "--output-format",
            "json",
            "--yolo",
            "--include-directories",
            ",".join(
                [
                    str(execution_layout.docs_dir),
                    str(execution_layout.memory_dir),
                    str(execution_layout.state_dir),
                ]
            ),
            "-p",
            prompt_text,
        ]
        if context.runtime.sandbox_mode != "danger-full-access":
            command.append("--sandbox")
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

    def _write_claude_output_file(self, output_file: Path, stdout: str) -> None:
        response_text = stdout.strip()
        if response_text:
            try:
                payload = parse_json_text(response_text)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                candidate = payload.get("result", payload.get("response", ""))
                if isinstance(candidate, str) and candidate.strip():
                    response_text = candidate.strip()
        if response_text:
            write_text(output_file, response_text)

    def _write_qwen_output_file(self, output_file: Path, stdout: str) -> None:
        response_text = stdout.strip()
        if response_text:
            try:
                payload = parse_json_text(response_text)
            except json.JSONDecodeError:
                payload = None
            candidate = self._extract_qwen_response(payload)
            if candidate:
                response_text = candidate
        if response_text:
            write_text(output_file, response_text)

    def _sync_output_file(self, source: Path, destination: Path) -> None:
        if source == destination or not source.exists():
            return
        write_text(destination, read_text(source))

    def _execution_paths_need_alias(self, *paths: Path) -> bool:
        return any(self._path_needs_alias(path) for path in paths)

    def _execution_prompt(
        self,
        prompt_text: str,
        context: ProjectContext,
        execution_layout: _CLIExecutionLayout,
    ) -> str:
        if execution_layout.repo_dir == context.paths.repo_dir:
            return prompt_text
        rewritten = prompt_text
        for source, target in self._prompt_path_replacements(context, execution_layout):
            rewritten = rewritten.replace(source, target)
        return rewritten

    def _prompt_path_replacements(
        self,
        context: ProjectContext,
        execution_layout: _CLIExecutionLayout,
    ) -> list[tuple[str, str]]:
        path_pairs = [
            (context.paths.docs_dir, execution_layout.docs_dir),
            (context.paths.memory_dir, execution_layout.memory_dir),
            (context.paths.state_dir, execution_layout.state_dir),
            (context.paths.repo_dir, execution_layout.repo_dir),
        ]
        replacements: list[tuple[str, str]] = []
        seen: set[str] = set()
        for source_path, target_path in sorted(path_pairs, key=lambda item: len(str(item[0])), reverse=True):
            for source_text, target_text in self._path_text_variants(source_path, target_path):
                if source_text in seen or source_text == target_text:
                    continue
                seen.add(source_text)
                replacements.append((source_text, target_text))
        return replacements

    def _path_text_variants(self, source_path: Path, target_path: Path) -> list[tuple[str, str]]:
        variants: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for source_text, target_text in (
            (str(source_path), str(target_path)),
            (source_path.as_posix(), target_path.as_posix()),
        ):
            pair = (source_text, target_text)
            if not source_text or pair in seen:
                continue
            seen.add(pair)
            variants.append(pair)
        return variants

    def _path_needs_alias(self, path: Path) -> bool:
        raw = str(path)
        return len(raw) >= EXECUTION_PATH_ALIAS_LENGTH_THRESHOLD or any(ord(char) > 127 for char in raw)

    @contextmanager
    def _execution_layout(
        self,
        context: ProjectContext,
        output_file: Path,
    ) -> Iterator[_CLIExecutionLayout]:
        default_layout = _CLIExecutionLayout(
            repo_dir=context.paths.repo_dir,
            docs_dir=context.paths.docs_dir,
            memory_dir=context.paths.memory_dir,
            state_dir=context.paths.state_dir,
            output_file=output_file,
        )
        if not self._execution_paths_need_alias(
            context.paths.repo_dir,
            context.paths.docs_dir,
            context.paths.memory_dir,
            context.paths.state_dir,
            output_file,
        ):
            yield default_layout
            return

        alias_root = Path(tempfile.gettempdir()) / "jakal-flow-cli" / uuid4().hex[:12]
        alias_root.mkdir(parents=True, exist_ok=True)
        alias_layout = _CLIExecutionLayout(
            repo_dir=alias_root / "repo",
            docs_dir=alias_root / "docs",
            memory_dir=alias_root / "memory",
            state_dir=alias_root / "state",
            output_file=alias_root / "out.txt",
        )
        try:
            self._create_directory_alias(alias_layout.repo_dir, context.paths.repo_dir)
            self._create_directory_alias(alias_layout.docs_dir, context.paths.docs_dir)
            self._create_directory_alias(alias_layout.memory_dir, context.paths.memory_dir)
            self._create_directory_alias(alias_layout.state_dir, context.paths.state_dir)
            yield alias_layout
        finally:
            for candidate in (
                alias_layout.output_file,
                alias_layout.state_dir,
                alias_layout.memory_dir,
                alias_layout.docs_dir,
                alias_layout.repo_dir,
            ):
                self._remove_alias_path(candidate)
            self._remove_alias_path(alias_root)

    def _create_directory_alias(self, alias_path: Path, target_path: Path) -> None:
        alias_path.parent.mkdir(parents=True, exist_ok=True)
        self._remove_alias_path(alias_path)
        if os.name == "nt":
            completed = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(alias_path), str(target_path)],
                capture_output=True,
                check=False,
            )
            if completed.returncode != 0:
                stderr = decode_process_output(completed.stderr).strip()
                stdout = decode_process_output(completed.stdout).strip()
                detail = stderr or stdout or "unknown error"
                raise RuntimeError(f"Failed to create execution path alias for {target_path}: {detail}")
            return
        alias_path.symlink_to(target_path, target_is_directory=True)

    def _remove_alias_path(self, path: Path) -> None:
        if not path.exists() and not path.is_symlink():
            return
        try:
            if path.is_symlink() or path.is_file():
                path.unlink(missing_ok=True)
                return
        except OSError:
            pass
        try:
            path.rmdir()
        except OSError:
            pass

    def _accumulate_gemini_usage(self, payload: dict[str, object], usage: dict[str, int]) -> bool:
        stats = payload.get("stats")
        if not isinstance(stats, dict):
            return False
        models = stats.get("models")
        if not isinstance(models, dict):
            return False
        detected = False
        for details in models.values():
            if not isinstance(details, dict):
                continue
            tokens = details.get("tokens")
            if not isinstance(tokens, dict):
                continue
            detected = True
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
        return detected

    def _accumulate_claude_usage(self, payload: dict[str, object], usage: dict[str, int]) -> None:
        if "result" not in payload and str(payload.get("subtype", "")).strip().lower() != "result":
            return
        raw_usage = payload.get("usage")
        if not isinstance(raw_usage, dict):
            return
        input_tokens = raw_usage.get("input_tokens")
        cached_tokens = raw_usage.get("cache_read_input_tokens", raw_usage.get("cached_input_tokens"))
        output_tokens = raw_usage.get("output_tokens")
        reasoning_tokens = raw_usage.get("reasoning_output_tokens", raw_usage.get("thinking_tokens"))
        total_tokens = raw_usage.get("total_tokens")
        if isinstance(input_tokens, int):
            usage["input_tokens"] += input_tokens
        if isinstance(cached_tokens, int):
            usage["cached_input_tokens"] += cached_tokens
        if isinstance(output_tokens, int):
            usage["output_tokens"] += output_tokens
        if isinstance(reasoning_tokens, int):
            usage["reasoning_output_tokens"] += reasoning_tokens
        if isinstance(total_tokens, int):
            usage["total_tokens"] += total_tokens

    def _accumulate_qwen_usage(self, payload: dict[str, object], usage: dict[str, int]) -> None:
        payload_type = str(payload.get("type", "")).strip().lower()
        if payload_type and payload_type != "result":
            return
        raw_usage = payload.get("usage")
        if not isinstance(raw_usage, dict):
            message = payload.get("message")
            if isinstance(message, dict):
                raw_usage = message.get("usage")
        if not isinstance(raw_usage, dict):
            return
        input_tokens = raw_usage.get("input_tokens", raw_usage.get("inputTokens", raw_usage.get("input")))
        cached_tokens = raw_usage.get(
            "cache_read_input_tokens",
            raw_usage.get("cached_input_tokens", raw_usage.get("cachedInputTokens", raw_usage.get("cached"))),
        )
        output_tokens = raw_usage.get("output_tokens", raw_usage.get("outputTokens", raw_usage.get("output")))
        reasoning_tokens = raw_usage.get(
            "reasoning_output_tokens",
            raw_usage.get("thinking_tokens", raw_usage.get("reasoningTokens", raw_usage.get("thoughts"))),
        )
        total_tokens = raw_usage.get("total_tokens", raw_usage.get("totalTokens", raw_usage.get("total")))
        if isinstance(input_tokens, int):
            usage["input_tokens"] += input_tokens
        if isinstance(cached_tokens, int):
            usage["cached_input_tokens"] += cached_tokens
        if isinstance(output_tokens, int):
            usage["output_tokens"] += output_tokens
        if isinstance(reasoning_tokens, int):
            usage["reasoning_output_tokens"] += reasoning_tokens
        if isinstance(total_tokens, int):
            usage["total_tokens"] += total_tokens

    def _extract_qwen_response(self, payload: object) -> str:
        if isinstance(payload, dict):
            response_value = payload.get("response", payload.get("result", ""))
            if isinstance(response_value, str) and response_value.strip():
                return response_value.strip()
        if not isinstance(payload, list):
            return ""
        for item in reversed(payload):
            if not isinstance(item, dict):
                continue
            result_text = item.get("result")
            if isinstance(result_text, str) and result_text.strip():
                return result_text.strip()
            message = item.get("message")
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if not isinstance(content, list):
                continue
            text_chunks = [
                str(block.get("text", "")).strip()
                for block in content
                if isinstance(block, dict) and str(block.get("type", "")).strip() == "text" and str(block.get("text", "")).strip()
            ]
            if text_chunks:
                return "\n".join(text_chunks).strip()
        return ""

    def _claude_reasoning_effort(self, effort: str) -> str:
        normalized = str(effort or "").strip().lower()
        if normalized == "xhigh":
            return "max"
        if normalized in {"low", "medium", "high"}:
            return normalized
        return "medium"
