# jakal-flow

`jakal-flow` is a production-oriented Python CLI and desktop shell for running a traceable Codex-driven improvement loop across multiple repositories inside an isolated workspace. It keeps orchestration, logs, plans, memory, reports, rollback state, and share sessions separated per managed repository instead of collapsing everything into a single repo-local state model.

For the Korean guide, see [README.ko.md](README.ko.md).

## Flow

![jakal-flow flow chart (EN)](assets/readme-flow.svg)

## Highlights

- Multi-repository workspace management under `projects/<repo_slug>/`
- Python-first orchestration with a React + Tauri desktop shell on top
- OpenAI / Codex cloud, OpenRouter, OpenCDK, local OpenAI-compatible servers, and Codex OSS local-provider runs
- Standard software workflow and ML experiment workflow with automatic cycle replanning
- Parallel DAG step execution with owned-path safety checks and safe-revision rollback
- Structured project artifacts: plans, checkpoints, logs, memory, reports, SVG views, and UI event history
- Read-only monitoring links backed by the local share server, optional public base URL, or automatic Cloudflare Quick Tunnel

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

This installs:

- `jakal-flow`
- `jakal-flow-ui-bridge`

## Desktop UI

The desktop shell lives under `desktop/` and keeps the Python orchestration backend intact through `python -m jakal_flow.ui_bridge`.

Development prerequisites:

- Node.js 20+
- Rust toolchain with Tauri prerequisites for your OS
- Python 3.11+ on `PATH`, or set `JAKAL_FLOW_PYTHON`

Run it in development:

```bash
cd desktop
npm.cmd install
npm.cmd run test
npm.cmd run tauri:dev
```

Build it:

```bash
cd desktop
npm.cmd run tauri:build
```

The desktop app adds:

- managed-project setup with saved runtime settings and project summaries
- model preset and provider selection, including local-provider discovery for OSS runs
- plan generation, step editing, stop-after-step requests, closeout, and background job polling
- estimated time and cost panels driven by runtime billing settings and Codex usage events
- read-only share link creation and revocation without replacing the Python workspace model

## Runtime Support

Provider presets currently wired into the implementation:

- `openai`
- `openrouter`
- `opencdk`
- `local_openai`
- `oss`

Local OSS runs support:

- `ollama`
- `lmstudio`

Workflow modes:

- `standard`
- `ml`

Execution mode is currently normalized to the parallel DAG scheduler across CLI and desktop flows.

## Share Viewer

The read-only monitoring flow is backed by the local Python share server and keeps public access separate from orchestration:

1. Start the desktop app.
2. Open a managed project.
3. Configure the share bind host and optional public base URL.
4. Generate a share link.
5. If `public_base_url` is empty and `cloudflared` is installed, `jakal-flow` can start a temporary Cloudflare Quick Tunnel automatically.
6. Open the generated link from another browser or device.
7. Revoke the session from the desktop UI when you are done.

The shared page exposes masked status, current task, recent logs, latest test result, and last-updated time.

## CLI Examples

Initialize a managed repository and generate the first saved plan:

```bash
python -m jakal_flow init-repo \
  --repo-url https://github.com/Ahnd6474/lit.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --model gpt-5.4 \
  --effort high \
  --plan-prompt "Build a safe project plan focused on a narrow MVP and strong tests." \
  --approval-mode never \
  --sandbox-mode workspace-write \
  --test-cmd "python -m pytest"
```

Run two standard improvement blocks and generate a Word closeout report:

```bash
python -m jakal_flow run \
  --repo-url https://github.com/Ahnd6474/lit.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --model gpt-5.4 \
  --effort high \
  --word-report \
  --approval-mode never \
  --sandbox-mode workspace-write \
  --test-cmd "python -m pytest" \
  --max-blocks 2
```

Run through Codex OSS mode with a local provider:

```bash
python -m jakal_flow run \
  --repo-url https://github.com/Ahnd6474/lit.git \
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

Run against an OpenAI-compatible endpoint such as OpenRouter:

```bash
python -m jakal_flow run \
  --repo-url https://github.com/Ahnd6474/lit.git \
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

Run against a local OpenAI-compatible server:

```bash
python -m jakal_flow run \
  --repo-url https://github.com/Ahnd6474/lit.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --model-provider local_openai \
  --provider-base-url http://127.0.0.1:1234/v1 \
  --model llama-3.1-8b-instruct \
  --effort medium \
  --approval-mode never \
  --sandbox-mode workspace-write \
  --test-cmd "python -m pytest" \
  --max-blocks 1
```

Run an ML workflow with automatic cycle replanning:

```bash
python -m jakal_flow run \
  --repo-url https://github.com/Ahnd6474/lit.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --model gpt-5.4 \
  --effort high \
  --workflow-mode ml \
  --ml-max-cycles 3 \
  --approval-mode never \
  --sandbox-mode workspace-write \
  --test-cmd "python -m pytest" \
  --max-blocks 6
```

Resume a managed repository:

```bash
python -m jakal_flow resume \
  --repo-url https://github.com/Ahnd6474/lit.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --model gpt-5.4 \
  --effort high \
  --approval-mode never \
  --sandbox-mode workspace-write \
  --test-cmd "python -m pytest" \
  --max-blocks 1
```

Inspect managed repositories and reports:

```bash
python -m jakal_flow list-repos --workspace-root .jakal-flow-workspace
python -m jakal_flow status --repo-url https://github.com/Ahnd6474/lit.git --branch main --workspace-root .jakal-flow-workspace
python -m jakal_flow history --repo-url https://github.com/Ahnd6474/lit.git --branch main --workspace-root .jakal-flow-workspace --limit 20
python -m jakal_flow report --repo-url https://github.com/Ahnd6474/lit.git --branch main --workspace-root .jakal-flow-workspace
```

## How It Works

Initialization:

1. Creates an isolated project directory under the workspace.
2. Clones or updates the target repository into `repo/`.
3. Scans `README.md`, `AGENTS.md`, and `repo/docs/**`.
4. Uses `src/jakal_flow/docs/REFERENCE_GUIDE.md` as a planning preference guide when the repository does not resolve a choice.
5. Creates or refreshes `docs/PLAN.md`, `docs/SCOPE_GUARD.md`, `docs/MID_TERM_PLAN.md`, memory files, and loop state.
6. Builds the checkpoint timeline and records the current safe revision.

Each run block:

1. Loads memory and the saved plan context.
2. Rebuilds the mid-term subset from the saved plan.
3. Generates or updates the execution plan.
4. Executes dependency-ready steps through the parallel scheduler.
5. Runs verification, with cache replay when repository state and test fingerprint match a validated run exactly.
6. Commits only safe validated changes.
7. Rolls back to the previous safe revision on regression or unsafe merge outcomes.
8. Writes logs, reports, SVG summaries, review notes, and memory updates.
9. Optionally pushes validated commits when `--allow-push` is enabled and an `origin` remote is configured.

## Managed Project Artifacts

Each managed project can contain files such as:

- `docs/PLAN.md`
- `docs/MID_TERM_PLAN.md`
- `docs/SCOPE_GUARD.md`
- `docs/ACTIVE_TASK.md`
- `docs/BLOCK_REVIEW.md`
- `docs/CHECKPOINT_TIMELINE.md`
- `docs/CLOSEOUT_REPORT.md`
- `docs/EXECUTION_FLOW.svg`
- `docs/ML_EXPERIMENT_REPORT.md`
- `docs/ML_EXPERIMENT_RESULTS.svg`
- `docs/RESEARCH_NOTES.md`
- `docs/attempt_history.md`
- `memory/success_patterns.jsonl`
- `memory/failure_patterns.jsonl`
- `memory/task_summaries.jsonl`
- `logs/passes.jsonl`
- `logs/blocks.jsonl`
- `logs/test_runs.jsonl`
- `logs/ui_events.jsonl`
- `reports/latest_report.json`
- `reports/*pr_failure.json`
- `reports/*pr_failure.md`
- `reports/latest_pr_failure_status.json`
- `state/LOOP_STATE.json`
- `state/CHECKPOINTS.json`
- `state/ML_MODE_STATE.json`
- `state/ML_STEP_REPORT.json`
- `state/UI_RUN_CONTROL.json`
- `state/ml_experiments/*.json`
- `state/share_sessions.json`
- `state/verification_cache/*.json`
- `metadata.json`
- `project_config.json`

## Notes

- `codex exec` is invoked non-interactively and JSON event streams are persisted under `logs/block_*/`.
- Local OSS runs still go through Codex CLI, using its OSS and local-provider flow.
- The desktop bridge forces UTF-8 stdio on Windows so JSON payloads and Korean text survive the bridge boundary.
- Default CLI behavior is conservative: `--max-blocks` defaults to `1`, and pushing requires explicit `--allow-push`.
