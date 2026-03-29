from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jakal_flow.codex_runner import CodexRunner
from jakal_flow.models import RuntimeOptions
from jakal_flow.step_models import (
    CLAUDE_DEFAULT_MODEL,
    DEEPSEEK_DEFAULT_MODEL,
    KIMI_DEFAULT_MODEL,
    QWEN_CODE_DEFAULT_MODEL,
)
from jakal_flow.workspace import WorkspaceManager


def _local_temp_root() -> Path:
    root = Path(__file__).resolve().parents[1] / ".tmp_codex_runner_tests"
    root.mkdir(parents=True, exist_ok=True)
    return root


class _TemporaryTestDir:
    def __enter__(self) -> Path:
        self.path = _local_temp_root() / f"case_{uuid.uuid4().hex}"
        self.path.mkdir(parents=True, exist_ok=True)
        return self.path

    def __exit__(self, exc_type, exc, tb) -> None:
        shutil.rmtree(self.path, ignore_errors=True)


class CodexRunnerTests(unittest.TestCase):
    def _context(self, temp_root: Path):
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        manager = WorkspaceManager(temp_root / "workspace")
        return manager.initialize_local_project(
            project_dir=repo_dir,
            branch="main",
            runtime=RuntimeOptions(model="gpt-5.4", effort="medium"),
        )

    def test_run_pass_retries_unexpected_token_failures(self) -> None:
        with _TemporaryTestDir() as temp_root:
            context = self._context(temp_root)
            runner = CodexRunner("codex.cmd")
            attempts = {"count": 0}

            def fake_run(command, scope_id=None, label="", input_bytes=None, env=None, **_kwargs):
                attempts["count"] += 1
                output_file = Path(command[command.index("-o") + 1])
                if attempts["count"] == 1:
                    return subprocess.CompletedProcess(
                        command,
                        1,
                        stdout=b"",
                        stderr=b"SyntaxError: Unexpected token < in JSON at position 0",
                    )
                output_file.write_text("Recovered response", encoding="utf-8")
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout=b'{"type":"turn.completed","usage":{"input_tokens":7,"output_tokens":3}}\n',
                    stderr=b"",
                )

            with mock.patch("jakal_flow.codex_runner.run_subprocess_capture", side_effect=fake_run), mock.patch(
                "jakal_flow.codex_runner.time.sleep"
            ):
                result = runner.run_pass(
                    context=context,
                    prompt="Apply a safe fix",
                    pass_type="demo pass",
                    block_index=1,
                    search_enabled=False,
                )

            block_dir = context.paths.logs_dir / "block_0001"
            self.assertEqual(attempts["count"], 2)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.attempt_count, 2)
            self.assertEqual(result.last_message, "Recovered response")
            self.assertEqual(result.usage["input_tokens"], 7)
            self.assertEqual(result.usage["output_tokens"], 3)
            self.assertEqual(result.usage["total_tokens"], 10)
            self.assertTrue(result.diagnostics["unexpected_token_detected"])
            self.assertTrue(result.diagnostics["recovered_after_retry"])
            self.assertTrue((block_dir / "demo_pass.attempt_1.stderr.log").exists())
            self.assertTrue((block_dir / "demo_pass.diagnostics.json").exists())

    def test_run_pass_does_not_retry_other_failures(self) -> None:
        with _TemporaryTestDir() as temp_root:
            context = self._context(temp_root)
            runner = CodexRunner("codex.cmd")
            attempts = {"count": 0}

            def fake_run(command, scope_id=None, label="", input_bytes=None, env=None, **_kwargs):
                attempts["count"] += 1
                return subprocess.CompletedProcess(
                    command,
                    1,
                    stdout=b"",
                    stderr=b"authentication failed",
                )

            with mock.patch("jakal_flow.codex_runner.run_subprocess_capture", side_effect=fake_run), mock.patch(
                "jakal_flow.codex_runner.time.sleep"
            ) as mocked_sleep:
                result = runner.run_pass(
                    context=context,
                    prompt="Apply a safe fix",
                    pass_type="demo pass",
                    block_index=1,
                    search_enabled=False,
                )

            self.assertEqual(attempts["count"], 1)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.attempt_count, 1)
            self.assertFalse(result.diagnostics["unexpected_token_detected"])
            mocked_sleep.assert_not_called()

    def test_run_pass_omits_model_flag_for_auto(self) -> None:
        with _TemporaryTestDir() as temp_root:
            repo_dir = temp_root / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            manager = WorkspaceManager(temp_root / "workspace")
            context = manager.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=RuntimeOptions(model="auto", effort="medium"),
            )
            runner = CodexRunner("codex.cmd")
            observed_commands: list[list[str]] = []

            def fake_run(command, scope_id=None, label="", input_bytes=None, env=None, **_kwargs):
                observed_commands.append(command)
                output_file = Path(command[command.index("-o") + 1])
                output_file.write_text("Auto response", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

            with mock.patch("jakal_flow.codex_runner.run_subprocess_capture", side_effect=fake_run):
                runner.run_pass(
                    context=context,
                    prompt="Use the default model routing",
                    pass_type="demo pass",
                    block_index=1,
                    search_enabled=False,
                )

            self.assertEqual(len(observed_commands), 1)
            self.assertNotIn("-m", observed_commands[0])

    def test_run_pass_uses_reasoning_override_when_provided(self) -> None:
        with _TemporaryTestDir() as temp_root:
            context = self._context(temp_root)
            runner = CodexRunner("codex.cmd")
            observed_commands: list[list[str]] = []

            def fake_run(command, scope_id=None, label="", input_bytes=None, env=None, **_kwargs):
                observed_commands.append(command)
                output_file = Path(command[command.index("-o") + 1])
                output_file.write_text("Override response", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

            with mock.patch("jakal_flow.codex_runner.run_subprocess_capture", side_effect=fake_run):
                runner.run_pass(
                    context=context,
                    prompt="Use the planning override",
                    pass_type="demo pass",
                    block_index=1,
                    search_enabled=False,
                    reasoning_effort="xhigh",
                )

            self.assertEqual(len(observed_commands), 1)
            self.assertIn('reasoning.effort="xhigh"', observed_commands[0])

    def test_run_pass_prefixes_fast_command_when_enabled(self) -> None:
        with _TemporaryTestDir() as temp_root:
            repo_dir = temp_root / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            manager = WorkspaceManager(temp_root / "workspace")
            context = manager.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=RuntimeOptions(model="gpt-5.4", effort="medium", use_fast_mode=True),
            )
            runner = CodexRunner("codex.cmd")
            observed_inputs: list[bytes] = []

            def fake_run(command, scope_id=None, label="", input_bytes=None, env=None, **_kwargs):
                observed_inputs.append(input_bytes)
                output_file = Path(command[command.index("-o") + 1])
                output_file.write_text("Fast response", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

            with mock.patch("jakal_flow.codex_runner.run_subprocess_capture", side_effect=fake_run):
                runner.run_pass(
                    context=context,
                    prompt="Apply the requested fix",
                    pass_type="demo pass",
                    block_index=1,
                    search_enabled=False,
                )

            self.assertEqual(len(observed_inputs), 1)
            self.assertEqual(observed_inputs[0].decode("utf-8"), "/fast\n\nApply the requested fix")

    def test_run_pass_uses_ascii_execution_aliases_for_non_ascii_repo_paths(self) -> None:
        with _TemporaryTestDir() as temp_root:
            repo_dir = temp_root / "문서" / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            manager = WorkspaceManager(temp_root / "workspace")
            context = manager.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=RuntimeOptions(model="gpt-5.4", effort="medium"),
            )
            runner = CodexRunner("codex.cmd")
            observed: dict[str, object] = {}

            def fake_run(command, scope_id=None, label="", input_bytes=None, env=None, cwd=None, **_kwargs):
                observed["command"] = list(command)
                observed["cwd"] = cwd
                alias_output = Path(command[command.index("-o") + 1])
                alias_output.write_text("Aliased response", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

            with mock.patch("jakal_flow.codex_runner.run_subprocess_capture", side_effect=fake_run):
                result = runner.run_pass(
                    context=context,
                    prompt="Apply a safe fix",
                    pass_type="demo pass",
                    block_index=1,
                    search_enabled=False,
                )

            self.assertEqual(result.last_message, "Aliased response")
            output_file = context.paths.logs_dir / "block_0001" / "demo_pass.last_message.txt"
            self.assertEqual(output_file.read_text(encoding="utf-8"), "Aliased response")

            observed_command = observed["command"]
            self.assertIsInstance(observed_command, list)
            observed_cwd = Path(observed["cwd"])
            self.assertNotEqual(observed_cwd, context.paths.repo_dir)
            self.assertTrue(all(ord(char) < 128 for char in str(observed_cwd)))

            cli_repo = Path(observed_command[observed_command.index("-C") + 1])
            self.assertEqual(cli_repo, observed_cwd)
            self.assertTrue(all(ord(char) < 128 for char in str(cli_repo)))

            cli_output = Path(observed_command[observed_command.index("-o") + 1])
            self.assertNotEqual(cli_output, output_file)
            self.assertTrue(all(ord(char) < 128 for char in str(cli_output)))

            add_dirs = [Path(observed_command[index + 1]) for index, item in enumerate(observed_command) if item == "--add-dir"]
            self.assertEqual(len(add_dirs), 3)
            for directory in add_dirs:
                self.assertTrue(all(ord(char) < 128 for char in str(directory)))

    def test_run_pass_adds_oss_flags_for_local_models(self) -> None:
        with _TemporaryTestDir() as temp_root:
            repo_dir = temp_root / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            manager = WorkspaceManager(temp_root / "workspace")
            context = manager.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=RuntimeOptions(
                    model_provider="oss",
                    local_model_provider="ollama",
                    model="qwen2.5-coder:0.5b",
                    effort="medium",
                ),
            )
            runner = CodexRunner("codex.cmd")
            observed_commands: list[list[str]] = []

            def fake_run(command, scope_id=None, label="", input_bytes=None, env=None, **_kwargs):
                observed_commands.append(command)
                output_file = Path(command[command.index("-o") + 1])
                output_file.write_text("OSS response", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

            with mock.patch("jakal_flow.codex_runner.run_subprocess_capture", side_effect=fake_run):
                runner.run_pass(
                    context=context,
                    prompt="Use the local model",
                    pass_type="demo pass",
                    block_index=1,
                    search_enabled=False,
                )

            self.assertEqual(len(observed_commands), 1)
            self.assertIn("--oss", observed_commands[0])
            self.assertIn("--local-provider", observed_commands[0])
            self.assertIn("ollama", observed_commands[0])
            self.assertIn("qwen2.5-coder:0.5b", observed_commands[0])

    def test_run_pass_adds_ollama_alias_flags_for_local_models(self) -> None:
        with _TemporaryTestDir() as temp_root:
            repo_dir = temp_root / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            manager = WorkspaceManager(temp_root / "workspace")
            context = manager.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=RuntimeOptions(
                    model_provider="ollama",
                    local_model_provider="lmstudio",
                    model="qwen2.5-coder:0.5b",
                    effort="medium",
                ),
            )
            runner = CodexRunner("codex.cmd")
            observed_commands: list[list[str]] = []

            def fake_run(command, scope_id=None, label="", input_bytes=None, env=None, **_kwargs):
                observed_commands.append(command)
                output_file = Path(command[command.index("-o") + 1])
                output_file.write_text("Ollama response", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

            with mock.patch("jakal_flow.codex_runner.run_subprocess_capture", side_effect=fake_run):
                runner.run_pass(
                    context=context,
                    prompt="Use the Ollama alias provider",
                    pass_type="demo pass",
                    block_index=1,
                    search_enabled=False,
                )

            self.assertEqual(len(observed_commands), 1)
            self.assertIn("--oss", observed_commands[0])
            self.assertIn("--local-provider", observed_commands[0])
            self.assertIn("ollama", observed_commands[0])
            self.assertNotIn("lmstudio", observed_commands[0])

    def test_run_pass_applies_openrouter_base_url_and_api_key_env(self) -> None:
        with _TemporaryTestDir() as temp_root:
            repo_dir = temp_root / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            manager = WorkspaceManager(temp_root / "workspace")
            context = manager.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=RuntimeOptions(
                    model_provider="openrouter",
                    provider_base_url="https://openrouter.ai/api/v1",
                    provider_api_key_env="OPENROUTER_API_KEY",
                    model="openai/gpt-4.1-mini",
                    effort="medium",
                ),
            )
            runner = CodexRunner("codex.cmd")
            observed_commands: list[list[str]] = []
            observed_envs: list[dict[str, str]] = []

            def fake_run(command, scope_id=None, label="", input_bytes=None, env=None, **_kwargs):
                observed_commands.append(command)
                observed_envs.append(dict(env or {}))
                output_file = Path(command[command.index("-o") + 1])
                output_file.write_text("OpenRouter response", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

            with mock.patch.dict("os.environ", {"OPENROUTER_API_KEY": "router-secret"}, clear=False), mock.patch(
                "jakal_flow.codex_runner.run_subprocess_capture",
                side_effect=fake_run,
            ):
                runner.run_pass(
                    context=context,
                    prompt="Use the OpenRouter endpoint",
                    pass_type="demo pass",
                    block_index=1,
                    search_enabled=False,
                )

            self.assertEqual(len(observed_commands), 1)
            self.assertIn("-c", observed_commands[0])
            self.assertIn('openai_base_url="https://openrouter.ai/api/v1"', observed_commands[0])
            self.assertEqual(observed_envs[0]["OPENAI_API_KEY"], "router-secret")
            self.assertEqual(observed_envs[0]["OPENAI_BASE_URL"], "https://openrouter.ai/api/v1")

    def test_run_pass_uses_gemini_headless_mode(self) -> None:
        with _TemporaryTestDir() as temp_root:
            repo_dir = temp_root / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            manager = WorkspaceManager(temp_root / "workspace")
            context = manager.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=RuntimeOptions(
                    model_provider="gemini",
                    provider_api_key_env="GEMINI_API_KEY",
                    model="gemini-2.5-flash",
                    effort="medium",
                    codex_path="gemini.cmd",
                ),
            )
            runner = CodexRunner("gemini.cmd")
            observed_commands: list[list[str]] = []
            observed_envs: list[dict[str, str]] = []

            def fake_run(command, scope_id=None, label="", input_bytes=None, env=None, cwd=None, **_kwargs):
                observed_commands.append(command)
                observed_envs.append(dict(env or {}))
                payload = {
                    "response": "Gemini response",
                    "stats": {
                        "models": {
                            "gemini-2.5-flash": {
                                "tokens": {
                                    "prompt": 11,
                                    "cached": 2,
                                    "candidates": 7,
                                    "thoughts": 3,
                                    "total": 23,
                                }
                            }
                        }
                    },
                }
                return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload).encode("utf-8"), stderr=b"")

            with mock.patch.dict("os.environ", {"GEMINI_API_KEY": "gemini-secret"}, clear=False), mock.patch(
                "jakal_flow.codex_runner.run_subprocess_capture",
                side_effect=fake_run,
            ):
                result = runner.run_pass(
                    context=context,
                    prompt="Apply a safe fix",
                    pass_type="demo pass",
                    block_index=1,
                    search_enabled=False,
                )

            self.assertEqual(len(observed_commands), 1)
            self.assertIn("--output-format", observed_commands[0])
            self.assertIn("json", observed_commands[0])
            self.assertIn("--approval-mode", observed_commands[0])
            self.assertIn("yolo", observed_commands[0])
            self.assertIn("--include-directories", observed_commands[0])
            self.assertIn("gemini-2.5-flash", observed_commands[0])
            self.assertEqual(observed_envs[0]["GEMINI_API_KEY"], "gemini-secret")
            self.assertEqual(result.last_message, "Gemini response")
            self.assertEqual(result.usage["input_tokens"], 11)
            self.assertEqual(result.usage["cached_input_tokens"], 2)
            self.assertEqual(result.usage["output_tokens"], 7)
            self.assertEqual(result.usage["reasoning_output_tokens"], 3)
            self.assertEqual(result.usage["total_tokens"], 23)

    def test_run_pass_fails_fast_when_gemini_auth_is_missing(self) -> None:
        with _TemporaryTestDir() as temp_root:
            repo_dir = temp_root / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            manager = WorkspaceManager(temp_root / "workspace")
            context = manager.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=RuntimeOptions(
                    model_provider="gemini",
                    provider_api_key_env="GEMINI_API_KEY",
                    model="gemini-2.5-flash",
                    effort="medium",
                    codex_path="gemini.cmd",
                ),
            )
            runner = CodexRunner("gemini.cmd")

            with mock.patch("jakal_flow.step_models._command_available", return_value=True), mock.patch(
                "jakal_flow.step_models._gemini_auth_env_configured",
                return_value=False,
            ), mock.patch(
                "jakal_flow.step_models._gemini_settings_file_configured",
                return_value=False,
            ), mock.patch(
                "jakal_flow.codex_runner.run_subprocess_capture",
                side_effect=AssertionError("gemini subprocess should not start without auth"),
            ):
                with self.assertRaisesRegex(RuntimeError, "Please set an Auth method"):
                    runner.run_pass(
                        context=context,
                        prompt="Apply a safe fix",
                        pass_type="demo pass",
                        block_index=1,
                        search_enabled=False,
                    )

    def test_run_pass_accepts_gemini_api_key_from_repo_dotenv(self) -> None:
        with _TemporaryTestDir() as temp_root:
            repo_dir = temp_root / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            (repo_dir / ".env").write_text("GEMINI_API_KEY=dotenv-gemini-secret\n", encoding="utf-8")
            manager = WorkspaceManager(temp_root / "workspace")
            context = manager.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=RuntimeOptions(
                    model_provider="gemini",
                    provider_api_key_env="GEMINI_API_KEY",
                    model="gemini-2.5-flash",
                    effort="medium",
                    codex_path="gemini.cmd",
                ),
            )
            runner = CodexRunner("gemini.cmd")
            observed_envs: list[dict[str, str]] = []

            def fake_run(command, scope_id=None, label="", input_bytes=None, env=None, cwd=None, **_kwargs):
                observed_envs.append(dict(env or {}))
                payload = {"response": "Gemini response"}
                return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload).encode("utf-8"), stderr=b"")

            with mock.patch("jakal_flow.step_models._command_available", return_value=True), mock.patch(
                "jakal_flow.step_models._gemini_auth_env_configured",
                return_value=False,
            ), mock.patch(
                "jakal_flow.step_models._gemini_settings_file_configured",
                return_value=False,
            ), mock.patch(
                "jakal_flow.codex_runner.run_subprocess_capture",
                side_effect=fake_run,
            ):
                result = runner.run_pass(
                    context=context,
                    prompt="Apply a safe fix",
                    pass_type="demo pass",
                    block_index=1,
                    search_enabled=False,
                )

            self.assertEqual(result.returncode, 0)
            self.assertEqual(observed_envs[0]["GEMINI_API_KEY"], "dotenv-gemini-secret")

    def test_run_pass_uses_claude_print_mode(self) -> None:
        with _TemporaryTestDir() as temp_root:
            repo_dir = temp_root / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            manager = WorkspaceManager(temp_root / "workspace")
            context = manager.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=RuntimeOptions(
                    model_provider="claude",
                    provider_api_key_env="ANTHROPIC_API_KEY",
                    provider_base_url="https://anthropic.example.test",
                    model=CLAUDE_DEFAULT_MODEL,
                    effort="medium",
                    codex_path="claude.cmd",
                ),
            )
            runner = CodexRunner("claude.cmd")
            observed_commands: list[list[str]] = []
            observed_envs: list[dict[str, str]] = []
            observed_inputs: list[bytes | None] = []

            def fake_run(command, scope_id=None, label="", input_bytes=None, env=None, cwd=None, **_kwargs):
                observed_commands.append(command)
                observed_envs.append(dict(env or {}))
                observed_inputs.append(input_bytes)
                payload = {
                    "result": "Claude response",
                    "usage": {
                        "input_tokens": 17,
                        "cache_read_input_tokens": 5,
                        "output_tokens": 8,
                        "total_tokens": 25,
                    },
                }
                return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload).encode("utf-8"), stderr=b"")

            with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "claude-secret"}, clear=False), mock.patch(
                "jakal_flow.codex_runner.run_subprocess_capture",
                side_effect=fake_run,
            ):
                result = runner.run_pass(
                    context=context,
                    prompt="Apply a safe fix",
                    pass_type="demo pass",
                    block_index=1,
                    search_enabled=False,
                    reasoning_effort="xhigh",
                )

            self.assertEqual(len(observed_commands), 1)
            self.assertIn("--print", observed_commands[0])
            self.assertIn("--output-format", observed_commands[0])
            self.assertIn("json", observed_commands[0])
            self.assertIn("--bare", observed_commands[0])
            self.assertIn("--dangerously-skip-permissions", observed_commands[0])
            self.assertIn("--model", observed_commands[0])
            self.assertIn(CLAUDE_DEFAULT_MODEL, observed_commands[0])
            self.assertIn("--effort", observed_commands[0])
            self.assertIn("max", observed_commands[0])
            self.assertIsNone(observed_inputs[0])
            self.assertEqual(observed_envs[0]["ANTHROPIC_API_KEY"], "claude-secret")
            self.assertEqual(observed_envs[0]["ANTHROPIC_BASE_URL"], "https://anthropic.example.test")
            self.assertEqual(result.last_message, "Claude response")
            self.assertEqual(result.usage["input_tokens"], 17)
            self.assertEqual(result.usage["cached_input_tokens"], 5)
            self.assertEqual(result.usage["output_tokens"], 8)
            self.assertEqual(result.usage["total_tokens"], 25)

    def test_run_pass_routes_deepseek_through_claude_compatible_env(self) -> None:
        with _TemporaryTestDir() as temp_root:
            repo_dir = temp_root / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            manager = WorkspaceManager(temp_root / "workspace")
            context = manager.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=RuntimeOptions(
                    model_provider="deepseek",
                    provider_api_key_env="DEEPSEEK_API_KEY",
                    provider_base_url="https://api.deepseek.com/anthropic",
                    model=DEEPSEEK_DEFAULT_MODEL,
                    effort="medium",
                    codex_path="claude.cmd",
                ),
            )
            runner = CodexRunner("claude.cmd")
            observed_commands: list[list[str]] = []
            observed_envs: list[dict[str, str]] = []

            def fake_run(command, scope_id=None, label="", input_bytes=None, env=None, cwd=None, **_kwargs):
                observed_commands.append(command)
                observed_envs.append(dict(env or {}))
                payload = {
                    "result": "DeepSeek response",
                    "usage": {
                        "input_tokens": 13,
                        "output_tokens": 6,
                        "total_tokens": 19,
                    },
                }
                return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload).encode("utf-8"), stderr=b"")

            with mock.patch.dict("os.environ", {"DEEPSEEK_API_KEY": "deepseek-secret"}, clear=False), mock.patch(
                "jakal_flow.codex_runner.run_subprocess_capture",
                side_effect=fake_run,
            ):
                result = runner.run_pass(
                    context=context,
                    prompt="Apply a safe DeepSeek-backed fix",
                    pass_type="demo pass",
                    block_index=1,
                    search_enabled=False,
                )

            self.assertEqual(len(observed_commands), 1)
            self.assertIn("--print", observed_commands[0])
            self.assertIn(DEEPSEEK_DEFAULT_MODEL, observed_commands[0])
            self.assertEqual(observed_envs[0]["ANTHROPIC_API_KEY"], "deepseek-secret")
            self.assertEqual(observed_envs[0]["ANTHROPIC_AUTH_TOKEN"], "deepseek-secret")
            self.assertEqual(observed_envs[0]["ANTHROPIC_BASE_URL"], "https://api.deepseek.com/anthropic")
            self.assertEqual(observed_envs[0]["ANTHROPIC_MODEL"], DEEPSEEK_DEFAULT_MODEL)
            self.assertEqual(result.last_message, "DeepSeek response")
            self.assertEqual(result.usage["total_tokens"], 19)

    def test_run_pass_applies_kimi_openai_compatible_defaults(self) -> None:
        with _TemporaryTestDir() as temp_root:
            repo_dir = temp_root / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            manager = WorkspaceManager(temp_root / "workspace")
            context = manager.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=RuntimeOptions(
                    model_provider="kimi",
                    provider_base_url="https://api.moonshot.cn/v1",
                    provider_api_key_env="MOONSHOT_API_KEY",
                    model=KIMI_DEFAULT_MODEL,
                    effort="medium",
                ),
            )
            runner = CodexRunner("codex.cmd")
            observed_commands: list[list[str]] = []
            observed_envs: list[dict[str, str]] = []

            def fake_run(command, scope_id=None, label="", input_bytes=None, env=None, **_kwargs):
                observed_commands.append(command)
                observed_envs.append(dict(env or {}))
                output_file = Path(command[command.index("-o") + 1])
                output_file.write_text("Kimi response", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

            with mock.patch.dict("os.environ", {"MOONSHOT_API_KEY": "kimi-secret"}, clear=False), mock.patch(
                "jakal_flow.codex_runner.run_subprocess_capture",
                side_effect=fake_run,
            ):
                runner.run_pass(
                    context=context,
                    prompt="Use the Kimi endpoint",
                    pass_type="demo pass",
                    block_index=1,
                    search_enabled=False,
                )

            self.assertEqual(len(observed_commands), 1)
            self.assertIn('openai_base_url="https://api.moonshot.cn/v1"', observed_commands[0])
            self.assertIn(KIMI_DEFAULT_MODEL, observed_commands[0])
            self.assertEqual(observed_envs[0]["OPENAI_API_KEY"], "kimi-secret")
            self.assertEqual(observed_envs[0]["OPENAI_BASE_URL"], "https://api.moonshot.cn/v1")

    def test_run_pass_uses_qwen_code_headless_mode(self) -> None:
        with _TemporaryTestDir() as temp_root:
            repo_dir = temp_root / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            manager = WorkspaceManager(temp_root / "workspace")
            context = manager.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=RuntimeOptions(
                    model_provider="qwen_code",
                    provider_api_key_env="DASHSCOPE_API_KEY",
                    provider_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                    model=QWEN_CODE_DEFAULT_MODEL,
                    effort="medium",
                    codex_path="qwen.cmd",
                ),
            )
            runner = CodexRunner("qwen.cmd")
            observed_commands: list[list[str]] = []
            observed_envs: list[dict[str, str]] = []
            observed_inputs: list[bytes | None] = []

            def fake_run(command, scope_id=None, label="", input_bytes=None, env=None, cwd=None, **_kwargs):
                observed_commands.append(command)
                observed_envs.append(dict(env or {}))
                observed_inputs.append(input_bytes)
                payload = [
                    {"type": "system", "subtype": "session_start"},
                    {
                        "type": "assistant",
                        "message": {
                            "content": [{"type": "text", "text": "Qwen response"}],
                        },
                    },
                    {
                        "type": "result",
                        "subtype": "success",
                        "result": "Qwen response",
                        "usage": {
                            "input_tokens": 21,
                            "cached_input_tokens": 3,
                            "output_tokens": 9,
                            "total_tokens": 30,
                        },
                    },
                ]
                return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload).encode("utf-8"), stderr=b"")

            with mock.patch.dict("os.environ", {"DASHSCOPE_API_KEY": "dashscope-secret"}, clear=False), mock.patch(
                "jakal_flow.codex_runner.run_subprocess_capture",
                side_effect=fake_run,
            ):
                result = runner.run_pass(
                    context=context,
                    prompt="Apply the requested fix with Qwen Code",
                    pass_type="demo pass",
                    block_index=1,
                    search_enabled=False,
                )

            self.assertEqual(len(observed_commands), 1)
            self.assertIn("--output-format", observed_commands[0])
            self.assertIn("json", observed_commands[0])
            self.assertIn("--yolo", observed_commands[0])
            self.assertIn("--include-directories", observed_commands[0])
            self.assertIn("-p", observed_commands[0])
            self.assertIsNone(observed_inputs[0])
            self.assertEqual(observed_envs[0]["OPENAI_API_KEY"], "dashscope-secret")
            self.assertEqual(observed_envs[0]["OPENAI_BASE_URL"], "https://dashscope.aliyuncs.com/compatible-mode/v1")
            self.assertEqual(observed_envs[0]["OPENAI_MODEL"], QWEN_CODE_DEFAULT_MODEL)
            self.assertEqual(result.last_message, "Qwen response")
            self.assertEqual(result.usage["input_tokens"], 21)
            self.assertEqual(result.usage["cached_input_tokens"], 3)
            self.assertEqual(result.usage["output_tokens"], 9)
            self.assertEqual(result.usage["total_tokens"], 30)

    def test_run_pass_strips_inherited_pythonpath_from_child_env(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp_root = Path(raw_temp)
            context = self._context(temp_root)
            runner = CodexRunner("codex.cmd")
            observed_envs: list[dict[str, str]] = []

            def fake_run(command, scope_id=None, label="", input_bytes=None, env=None, **_kwargs):
                observed_envs.append(dict(env or {}))
                output_file = Path(command[command.index("-o") + 1])
                output_file.write_text("Sanitized response", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

            with mock.patch.dict("os.environ", {"PYTHONPATH": r"C:\leaked\src"}, clear=False), mock.patch(
                "jakal_flow.codex_runner.run_subprocess_capture",
                side_effect=fake_run,
            ):
                runner.run_pass(
                    context=context,
                    prompt="Apply the requested fix",
                    pass_type="demo pass",
                    block_index=1,
                    search_enabled=False,
                )

            self.assertEqual(len(observed_envs), 1)
            self.assertNotIn("PYTHONPATH", observed_envs[0])


if __name__ == "__main__":
    unittest.main()
