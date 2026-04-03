# Terminal-Bench 2.0

`jakal-flow` can be evaluated on `terminal-bench@2.0` by using the official harness and exposing a custom installed agent.

## What this integration does

- Uses the official Terminal-Bench custom-agent flow with `--agent-import-path`.
- Installs `jakal-flow` and Codex CLI inside the task container with `terminal_bench_setup.sh`.
- Runs `jakal-flow` against the task container's current repository instead of recloning a remote.
- Stores logs and state in the managed workspace rather than polluting the task repository with `jakal-flow-logs/`.

## Leaderboard command

Use the official 2.0 custom-agent entrypoint:

```bash
harbor run -d terminal-bench@2.0 \
  --agent-import-path "jakal_flow.terminal_bench_agent:JakalFlowInstalledAgent" \
  -k 5
```

Terminal-Bench 2.0 leaderboard submissions may not modify timeouts or resources:

- Reference: https://www.tbench.ai/leaderboard/terminal-bench/2.0

## Recommended environment

Set the model and auth you want the installed agent to use:

```bash
export OPENAI_API_KEY="..."
export JAKAL_FLOW_MODEL_PROVIDER="openai"
export JAKAL_FLOW_MODEL="gpt-5.4"
export JAKAL_FLOW_EFFORT="high"
export JAKAL_FLOW_MAX_BLOCKS="12"
```

Optional:

```bash
export JAKAL_FLOW_GIT_URL="https://github.com/Ahnd6474/Jakal-flow.git"
export JAKAL_FLOW_GIT_REF="main"
export JAKAL_FLOW_AGENT_NAME="Jakal Flow"
```

`JAKAL_FLOW_RUNTIME_OVERRIDES` may also be set to a JSON object to override runtime options inside the task container.

## Local smoke test

When you want to test the current local checkout before pushing a branch, use the repository root script:

```powershell
.\run-terminal-bench.ps1 -Mode smoke
```

That script mounts the current checkout into the task container and sets `JAKAL_FLOW_GIT_URL=/opt/jakal-flow-src` so the installed agent uses the working tree you are editing now.

## Notes

- The benchmark worker uses the task description as the planning prompt.
- Verification defaults to `python -m jakal_flow.terminal_bench_verify`, which picks a common test command heuristically from the repository contents.
- Final benchmark scoring is still determined by the Terminal-Bench harness.
- For leaderboard listing, run the official benchmark command and then contact the maintainers using the submission instructions in the Terminal-Bench docs.
