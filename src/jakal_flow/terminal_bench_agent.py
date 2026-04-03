from __future__ import annotations

import base64
import os
import shlex
from pathlib import Path

from terminal_bench.agents.installed_agents.abstract_installed_agent import AbstractInstalledAgent
from terminal_bench.terminal.models import TerminalCommand


_FORWARDED_ENV_VARS = (
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "JAKAL_FLOW_MODEL",
    "JAKAL_FLOW_MODEL_PROVIDER",
    "JAKAL_FLOW_EFFORT",
    "JAKAL_FLOW_MAX_BLOCKS",
    "JAKAL_FLOW_TEST_CMD",
    "JAKAL_FLOW_RUNTIME_OVERRIDES",
    "JAKAL_FLOW_REPO_URL",
    "JAKAL_FLOW_GIT_URL",
    "JAKAL_FLOW_GIT_REF",
    "JAKAL_FLOW_AGENT_NAME",
)


class JakalFlowInstalledAgent(AbstractInstalledAgent):
    @staticmethod
    def name() -> str:
        return os.environ.get("JAKAL_FLOW_AGENT_NAME", "Jakal Flow").strip() or "Jakal Flow"

    @property
    def _env(self) -> dict[str, str]:
        env: dict[str, str] = {}
        for key in _FORWARDED_ENV_VARS:
            value = os.environ.get(key)
            if value:
                env[key] = value
        return env

    @property
    def _install_agent_script_path(self) -> os.PathLike:
        return Path(__file__).resolve().with_name("terminal_bench_setup.sh")

    def _run_agent_commands(self, task_description: str) -> list[TerminalCommand]:
        encoded_description = base64.b64encode(task_description.encode("utf-8")).decode("ascii")
        command = (
            "python -m jakal_flow.terminal_bench_worker "
            f"--task-description-base64 {shlex.quote(encoded_description)}"
        )
        return [
            TerminalCommand(
                command=command,
                max_timeout_sec=float("inf"),
                block=True,
            )
        ]
