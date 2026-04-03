from __future__ import annotations

import base64
import os
import shlex
from pathlib import Path

from harbor.agents.installed.base import BaseInstalledAgent, with_prompt_template
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext


_FORWARDED_ENV_VARS = (
    "CODEX_HOME",
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


class JakalFlowInstalledAgent(BaseInstalledAgent):
    @staticmethod
    def name() -> str:
        return os.environ.get("JAKAL_FLOW_AGENT_NAME", "Jakal Flow").strip() or "Jakal Flow"

    def _container_env(self) -> dict[str, str]:
        env: dict[str, str] = {}
        for key in _FORWARDED_ENV_VARS:
            value = os.environ.get(key)
            if value:
                env[key] = value
        return env

    def populate_context_post_run(self, context: AgentContext) -> None:
        if context.metadata is None:
            context.metadata = {}
        context.metadata.setdefault("runner", "jakal-flow")

    async def install(self, environment: BaseEnvironment) -> None:
        setup_script_path = Path(__file__).resolve().with_name("terminal_bench_setup.sh")
        await environment.upload_file(setup_script_path, "/installed-agent/install-agent.sh")
        await self.exec_as_root(
            environment,
            command="chmod +x /installed-agent/install-agent.sh && /installed-agent/install-agent.sh",
            env=self._container_env(),
        )

    @with_prompt_template
    async def run(
        self, instruction: str, environment: BaseEnvironment, context: AgentContext
    ) -> None:
        encoded_instruction = base64.b64encode(instruction.encode("utf-8")).decode("ascii")
        worker_command = (
            "python -m jakal_flow.terminal_bench_worker "
            f"--task-description-base64 {shlex.quote(encoded_instruction)}"
        )
        await self.exec_as_agent(
            environment,
            command=worker_command,
            env=self._container_env(),
        )
