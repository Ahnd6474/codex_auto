# jakal-flow

`jakal-flow` is a production-oriented Python CLI for managing multiple repositories inside an isolated workspace and repeatedly running a traceable Codex-driven improvement loop against them through Codex CLI, including OpenAI/Codex cloud models, OpenAI-compatible providers such as OpenRouter or OpenCDK, and local model backends ranging from Codex OSS mode to generic OpenAI-compatible local servers.

It is designed around a saved project plan:

- `docs/PLAN.md`: stores the current project plan or reviewed execution plan snapshot
- `docs/MID_TERM_PLAN.md`: regenerated at block boundaries and kept as a strict subset of the saved plan
- `docs/CHECKPOINT_TIMELINE.md`: derived from the saved plan and used for review boundaries

## Flow

![jakal-flow flow chart](assets/readme-flow-ko.svg)

## Project Layout

```text
workspace_root/
  projects/
    <repo_slug>/
      repo/
      docs/
      memory/
      logs/
      reports/
      state/
      metadata.json
      project_config.json
```

## Install

```bash
python -m pip install -e .
```

## Desktop UI

The current desktop UI lives under `desktop/` as a React + Tauri app.

Development prerequisites:

- Node.js 20+
- Rust toolchain with Tauri prerequisites for your OS
- Python 3.11+ available to the Tauri shell so it can call `python -m jakal_flow.ui_bridge`

Run the desktop shell in development:

```bash
cd desktop
npm.cmd install
npm.cmd run tauri:dev
```

The Tauri shell keeps the Python orchestration backend and adds:

- a React setup screen for managed projects, GitHub link mode, model preset selection, and verification commands
- OpenAI/Codex cloud, OpenRouter, OpenCDK, local OpenAI-compatible endpoints, and local OSS model-provider selection
- a flow screen with prompt editing, plan generation, step editing, run control, closeout, and stop-after-step requests
- estimated execution time and cost panels, including live remaining-time updates while a run is active
- background job polling through a Python JSON bridge instead of keeping UI execution state only in memory
- desktop UI trace files under each managed project for stop requests and UI event history

The desktop app lets you:

- start from a managed project screen with working directory, display name, GitHub connection mode, and verification command inputs
- keep managed projects in a reusable list with saved status, summaries, and runtime settings
- generate, edit, reorder, and persist execution-plan steps
- choose serial execution or a parallel DAG execution tree for the remaining steps and inspect activity/snapshot traces
- request stop-after-step and run a separate closeout block after all plan steps complete
- generate a temporary read-only monitoring link, copy it, and revoke it from the desktop UI
- keep the Python orchestration backend, workspace layout, logs, reports, and rollback behavior intact

Static website assets are kept separately under `website/`, including the share viewer served by the local monitoring server.

The read-only monitoring flow supports both local-only access and external access through either a user-provided public base URL or an automatic Cloudflare Quick Tunnel:

1. start the desktop app
2. if you want a stable custom domain, start your own reverse proxy or tunnel and note its public base URL
3. open a managed project, set the share bind host to `0.0.0.0`, optionally enter a public base URL, then generate a share link
4. if `public_base_url` is empty and `cloudflared` is installed, `jakal-flow` will start a temporary Cloudflare Quick Tunnel automatically and use that public URL
5. open the generated link on another browser or device
6. the remote page opens a live event stream for masked status, current task, recent logs, latest test result, and last updated time, with 5-second polling as a fallback
7. revoke the link in the desktop UI to deny further access

The core app still keeps network exposure separate from orchestration. It starts the local share server, stores temporary share sessions, and can generate links that use either a manually supplied public base URL or an automatic temporary Cloudflare Quick Tunnel. Quick Tunnels are convenient for free ad-hoc phone access, but they still depend on your local machine being online and are not a replacement for permanent hosting.

## Main Commands

Initialize a managed repository:

```bash
python -m jakal_flow init-repo \
  --repo-url https://github.com/example/project.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --model gpt-5.4 \
  --effort high \
  --plan-prompt "Build a safe project plan for this repository focused on a narrow MVP and strong tests." \
  --approval-mode never \
  --sandbox-mode workspace-write \
  --test-cmd "python -m pytest"
```

Run two improvement blocks:

```bash
python -m jakal_flow run \
  --repo-url https://github.com/example/project.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --model gpt-5.4 \
  --effort high \
  --approval-mode never \
  --sandbox-mode workspace-write \
  --test-cmd "python -m pytest" \
  --max-blocks 2
```

Run against a local OSS model through Codex CLI's local-provider mode:

```bash
python -m jakal_flow run \
  --repo-url https://github.com/example/project.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --model-provider oss \
  --local-model-provider ollama \
  --model qwen2.5-coder:0.5b \
  --effort medium \
  --approval-mode never \
  --sandbox-mode workspace-write \
  --test-cmd "python -m pytest" \
  --max-blocks 1
```

Run against an OpenAI-compatible provider such as OpenRouter:

```bash
python -m jakal_flow run \
  --repo-url https://github.com/example/project.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --model-provider openrouter \
  --provider-base-url https://openrouter.ai/api/v1 \
  --provider-api-key-env OPENROUTER_API_KEY \
  --billing-mode token \
  --model openai/gpt-4.1-mini \
  --effort medium \
  --approval-mode never \
  --sandbox-mode workspace-write \
  --test-cmd "python -m pytest" \
  --max-blocks 1
```

Resume a managed repository:

```bash
python -m jakal_flow resume \
  --repo-url https://github.com/example/project.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --model gpt-5.4 \
  --effort high \
  --approval-mode never \
  --sandbox-mode workspace-write \
  --test-cmd "python -m pytest" \
  --max-blocks 1
```

List all managed repositories:

```bash
python -m jakal_flow list-repos --workspace-root .jakal-flow-workspace
```

Inspect status, history, and reports:

```bash
python -m jakal_flow status --repo-url https://github.com/example/project.git --branch main
python -m jakal_flow history --repo-url https://github.com/example/project.git --branch main --limit 20
python -m jakal_flow report --repo-url https://github.com/example/project.git --branch main
```

## How It Works

Initialization:

1. Creates an isolated project directory under the workspace
2. Clones or updates the target repository into `repo/`
3. Scans `README.md`, `AGENTS.md`, and `repo/docs/**`
4. Uses `src/jakal_flow/docs/REFERENCE_GUIDE.md` as the default planning preference guide when the request leaves implementation choices unspecified
5. Creates or refreshes `docs/PLAN.md` from repository context or an optional plan prompt
6. Creates `docs/SCOPE_GUARD.md`, `docs/MID_TERM_PLAN.md`, memory files, and loop state
7. Builds a checkpoint timeline from the saved plan
8. Records the current safe git revision

Each run block:

1. Retrieves relevant memory from prior attempts
2. Rebuilds a mid-term plan from the saved plan
3. Generates 2-3 candidate tasks and selects one
4. Runs one search-enabled Codex pass for the selected block
5. Runs tests after the pass
   If the repository tree, verification command, and environment fingerprint exactly match a prior validated run, `jakal-flow` replays the cached verification result instead of rerunning the same suite.
6. Commits only safe validated changes
7. Stops at checkpoint boundaries for user review when approval is required
8. Pushes to GitHub when the user approves a checkpoint in the GUI
9. Rolls back to the previous safe revision on regression
10. Saves structured logs, reports, block review, and memory summaries
11. When a failure occurs, writes a PR-ready failure bundle under `reports/` and tries to post it to the open PR if a GitHub token is available
12. When a parallel cherry-pick merge hits a Git conflict, aborts to the last safe revision and records the conflict procedure instead of auto-picking source code blindly

## Repository Files Managed Per Project

The tool creates or maintains these files for each managed repository project:

- `docs/PLAN.md`
- `docs/MID_TERM_PLAN.md`
- `docs/SCOPE_GUARD.md`
- `docs/ACTIVE_TASK.md`
- `docs/BLOCK_REVIEW.md`
- `docs/CHECKPOINT_TIMELINE.md`
- `docs/CLOSEOUT_REPORT.md`
- `docs/RESEARCH_NOTES.md`
- `docs/attempt_history.md`
- `state/LOOP_STATE.json`
- `state/CHECKPOINTS.json`
- `state/verification_cache/*.json`
- `state/share_sessions.json`
- `memory/success_patterns.jsonl`
- `memory/failure_patterns.jsonl`
- `memory/task_summaries.jsonl`
- `logs/passes.jsonl`
- `logs/blocks.jsonl`
- `logs/ui_events.jsonl`
- `reports/latest_report.json`
- `reports/*pr_failure.json`
- `reports/*pr_failure.md`
- `reports/latest_pr_failure_status.json`
- `metadata.json`
- `project_config.json`
- `state/UI_RUN_CONTROL.json`

Source prompt and scope templates:

- `src/jakal_flow/docs/REFERENCE_GUIDE.md`
- `src/jakal_flow/docs/PLAN_GENERATION_SERIAL_PROMPT.txt`
- `src/jakal_flow/docs/PLAN_GENERATION_PARALLEL_PROMPT.txt`
- `src/jakal_flow/docs/STEP_EXECUTION_SERIAL_PROMPT.txt`
- `src/jakal_flow/docs/STEP_EXECUTION_PARALLEL_PROMPT.txt`
- `src/jakal_flow/docs/FINALIZATION_PROMPT.txt`
- `src/jakal_flow/docs/SCOPE_GUARD_TEMPLATE.md`

## Notes

- `codex exec` is invoked through subprocess in non-interactive mode and JSON event streams are saved under `logs/block_*/`
- local OSS runs are still executed through Codex CLI, using its `--oss` and `--local-provider` flags when a project runtime selects a local provider
- the GUI saves both the resolved execution model slug and the selected preset in `project_config.json`; auto-model presets are normalized to `auto`, `low`, `medium`, `high`, or `xhigh`, and previously saved custom model slugs are still preserved
- `reasoning.effort` is passed through to Codex using `low`, `medium`, `high`, or `xhigh`; saved execution-plan steps can override the project default per step
- token usage is aggregated from `turn.completed` JSON events and surfaced in the GUI dashboard and pass logs
- each repository gets its own isolated workspace subtree; no mutable state is shared across projects
- local git user identity is configured in the managed clone for automated commits
- `--allow-push` pushes safe commits to `origin` after successful blocks
- set `JAKAL_FLOW_GITHUB_TOKEN`, `GITHUB_TOKEN`, or `GH_TOKEN` if you want automatic PR failure comments
- default `--max-blocks` is `1` for safer operation; increase it explicitly when needed
