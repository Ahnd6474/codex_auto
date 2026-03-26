from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jakal_flow.codex_runner import CodexRunner
from jakal_flow.models import RuntimeOptions
from jakal_flow.workspace import WorkspaceManager


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
        with tempfile.TemporaryDirectory() as raw_temp:
            temp_root = Path(raw_temp)
            context = self._context(temp_root)
            runner = CodexRunner("codex.cmd")
            attempts = {"count": 0}

            def fake_run(command, input, capture_output, check, env=None):
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

            with mock.patch("jakal_flow.codex_runner.subprocess.run", side_effect=fake_run), mock.patch(
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
        with tempfile.TemporaryDirectory() as raw_temp:
            temp_root = Path(raw_temp)
            context = self._context(temp_root)
            runner = CodexRunner("codex.cmd")
            attempts = {"count": 0}

            def fake_run(command, input, capture_output, check, env=None):
                attempts["count"] += 1
                return subprocess.CompletedProcess(
                    command,
                    1,
                    stdout=b"",
                    stderr=b"authentication failed",
                )

            with mock.patch("jakal_flow.codex_runner.subprocess.run", side_effect=fake_run), mock.patch(
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
        with tempfile.TemporaryDirectory() as raw_temp:
            temp_root = Path(raw_temp)
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

            def fake_run(command, input, capture_output, check, env=None):
                observed_commands.append(command)
                output_file = Path(command[command.index("-o") + 1])
                output_file.write_text("Auto response", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

            with mock.patch("jakal_flow.codex_runner.subprocess.run", side_effect=fake_run):
                runner.run_pass(
                    context=context,
                    prompt="Use the default model routing",
                    pass_type="demo pass",
                    block_index=1,
                    search_enabled=False,
                )

            self.assertEqual(len(observed_commands), 1)
            self.assertNotIn("-m", observed_commands[0])

    def test_run_pass_prefixes_fast_command_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp_root = Path(raw_temp)
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

            def fake_run(command, input, capture_output, check, env=None):
                observed_inputs.append(input)
                output_file = Path(command[command.index("-o") + 1])
                output_file.write_text("Fast response", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

            with mock.patch("jakal_flow.codex_runner.subprocess.run", side_effect=fake_run):
                runner.run_pass(
                    context=context,
                    prompt="Apply the requested fix",
                    pass_type="demo pass",
                    block_index=1,
                    search_enabled=False,
                )

            self.assertEqual(len(observed_inputs), 1)
            self.assertEqual(observed_inputs[0].decode("utf-8"), "/fast\n\nApply the requested fix")

    def test_run_pass_adds_oss_flags_for_local_models(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp_root = Path(raw_temp)
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

            def fake_run(command, input, capture_output, check, env=None):
                observed_commands.append(command)
                output_file = Path(command[command.index("-o") + 1])
                output_file.write_text("OSS response", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

            with mock.patch("jakal_flow.codex_runner.subprocess.run", side_effect=fake_run):
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

    def test_run_pass_applies_openrouter_base_url_and_api_key_env(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp_root = Path(raw_temp)
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

            def fake_run(command, input, capture_output, check, env=None):
                observed_commands.append(command)
                observed_envs.append(dict(env or {}))
                output_file = Path(command[command.index("-o") + 1])
                output_file.write_text("OpenRouter response", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

            with mock.patch.dict("os.environ", {"OPENROUTER_API_KEY": "router-secret"}, clear=False), mock.patch(
                "jakal_flow.codex_runner.subprocess.run",
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


if __name__ == "__main__":
    unittest.main()
