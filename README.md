# jakal-flow

<p align="center">
  <strong>Traceable multi-repository Codex automation with a Python-first CLI, a React + Tauri desktop shell, and a masked remote monitor.</strong>
</p>

<p align="center">
  Keep plans, checkpoints, logs, memory, reports, rollback state, share sessions, and archived run history isolated per managed repository.
</p>

<p align="center">
  <a href="https://github.com/Ahnd6474/Jakal-flow/stargazers"><img src="https://img.shields.io/github/stars/Ahnd6474/Jakal-flow?style=for-the-badge" alt="GitHub stars"></a>
  <a href="https://github.com/Ahnd6474/Jakal-flow/issues"><img src="https://img.shields.io/github/issues/Ahnd6474/Jakal-flow?style=for-the-badge" alt="GitHub issues"></a>
  <a href="https://github.com/Ahnd6474/Jakal-flow/commits/main"><img src="https://img.shields.io/github/last-commit/Ahnd6474/Jakal-flow?style=for-the-badge" alt="Last commit"></a>
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white&style=for-the-badge" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/Desktop-React%20%2B%20Tauri-24C8DB?logo=tauri&logoColor=white&style=for-the-badge" alt="React and Tauri">
  <img src="https://img.shields.io/badge/Execution-Parallel%20DAG-0F766E?style=for-the-badge" alt="Parallel DAG execution">
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> &middot;
  <a href="#what-it-supports">What It Supports</a> &middot;
  <a href="#desktop-ui">Desktop UI</a> &middot;
  <a href="#configuration">Configuration</a> &middot;
  <a href="#how-it-works">How It Works</a> &middot;
  <a href="#workspace-layout">Workspace Layout</a> &middot;
  <a href="#star-history">Star History</a> &middot;
  <a href="README.ko.md">Korean Guide</a>
</p>

`jakal-flow` is built for long-running repository automation rather than one-off patches. The Python orchestration core owns planning, execution, verification, rollback, checkpointing, reporting, and project isolation. The desktop app and share viewer sit on top of that same backend instead of replacing it.

## Architecture

High-level surfaces and isolated workspace layout:

![jakal-flow flow chart (EN)](assets/readme-flow.svg)

Backend planning, execution, verification, rollback, and reporting flow:

![jakal-flow backend code generation flow (EN)](assets/backend-codegen-flow.svg)

## Quick Start

Recommended runtime:

- Python 3.11+
- Codex CLI on `PATH`
- For the desktop shell: Node.js 20+, Rust, and Tauri prerequisites

Install the Python package in editable mode:

```bash
python -m pip install -e .
```

That installs:

- `jakal-flow`
- `jakal-flow-ui-bridge`

Initialize a managed repository:

```bash
python -m jakal_flow init-repo \
  --repo-url https://github.com/Ahnd6474/lit.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --model gpt-5.4 \
  --effort high \
  --plan-prompt "Build a safe project plan aimed at a finished, well-integrated result with strong verification and closeout." \
  --approval-mode never \
  --sandbox-mode workspace-write \
  --test-cmd "python -m pytest"
```

Run a verified improvement loop:

```bash
python -m jakal_flow run \
  --repo-url https://github.com/Ahnd6474/lit.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --model gpt-5.4 \
  --effort high \
  --approval-mode never \
  --sandbox-mode workspace-write \
  --test-cmd "python -m pytest" \
  --max-blocks 2
```

Inspect status later:

```bash
python -m jakal_flow list-repos --workspace-root .jakal-flow-workspace
python -m jakal_flow status --repo-url https://github.com/Ahnd6474/lit.git --branch main --workspace-root .jakal-flow-workspace
python -m jakal_flow history --repo-url https://github.com/Ahnd6474/lit.git --branch main --workspace-root .jakal-flow-workspace --limit 20
python -m jakal_flow report --repo-url https://github.com/Ahnd6474/lit.git --branch main --workspace-root .jakal-flow-workspace
```

Open the desktop shell in development:

```bash
cd desktop
npm install
npm run test
npm run tauri:dev
```

## Why jakal-flow

- Multi-repository by design: every managed repository gets its own isolated workspace subtree.
- Traceability first: plans, checkpoints, UI events, verification runs, block logs, reports, SVG summaries, and task memory are persisted.
- Safe execution: safe revisions, rollback, checkpoint review, and verified-only commits stay in the core loop.
- One backend, multiple surfaces: use the CLI directly, supervise the same run from the desktop shell, or expose a temporary masked monitor link.
- Flexible routing: run through OpenAI/Codex cloud, Claude Code, Gemini CLI, Qwen Code, OpenAI-compatible providers, Anthropic-compatible providers, or local OSS backends.
- Long-lived project history: the desktop shell can archive finished managed workspaces into `history/` without collapsing them into one shared state tree.

## What It Supports

### Surfaces

| Surface | Supported |
| --- | --- |
| CLI | `init-repo`, `run`, `resume`, `list-repos`, `status`, `history`, `report` |
| Desktop UI | Register existing local repos, save runtime defaults, generate and edit plans, run or stop work, approve checkpoints, archive or delete managed history, and manage share sessions |
| Remote monitor | Local share server, temporary share sessions, masked status/log views, execution-flow SVG access, optional public base URL, optional Cloudflare Quick Tunnel, remote pause, and remote resume when pending work remains |

### Workflow Modes

| Capability | Supported |
| --- | --- |
| Standard software workflow | Yes |
| ML experiment workflow | Yes, via `--workflow-mode ml` |
| Automatic ML replanning | Yes, up to `--ml-max-cycles` |
| Planning model | Planner Agent A decomposition plus Planner Agent B packing |
| Execution mode | Parallel DAG scheduling is the normalized execution mode |
| Hybrid lineage / join / barrier steps | Yes |
| Closeout pass | Yes, separate from normal planned steps |
| Stop after current step | Yes, through desktop run control and shared monitor pause |
| Immediate stop | Yes, through desktop run control |

### Model / Provider Support

| Provider preset | Supported | Notes |
| --- | --- | --- |
| `openai` | Yes | OpenAI / Codex cloud flow |
| `ensemble` | Yes | Uses OpenAI as the default planning/general backend while allowing step-level routing for UI or explicitly pinned work |
| `claude` | Yes | Claude Code print-mode flow |
| `gemini` | Yes | Gemini CLI headless flow |
| `qwen_code` | Yes | Qwen Code headless flow |
| `deepseek` | Yes | Claude Code against DeepSeek's Anthropic-compatible endpoint |
| `kimi` | Yes | Codex/OpenAI-compatible flow against Moonshot Kimi |
| `minimax` | Yes | Claude Code against MiniMax's Anthropic-compatible endpoint |
| `glm` | Yes | Claude Code against Zhipu GLM's Anthropic-compatible endpoint |
| `openrouter` | Yes | OpenAI-compatible endpoint |
| `opencdk` | Yes | OpenAI-compatible endpoint |
| `local_openai` | Yes | Local OpenAI-compatible server such as LM Studio, vLLM, llama.cpp, or LocalAI |
| `oss` | Yes | Codex OSS mode through a local provider |

Local providers for `--model-provider oss`:

- `ollama`
- `lmstudio`

Reasoning effort levels:

- `low`
- `medium`
- `high`
- `xhigh`

### Planning, Execution, and Review

| Capability | Supported |
| --- | --- |
| Saved project plan generation | Yes |
| Planner Agent A outline persistence | Yes, `docs/PLAN_AGENT_A_OUTLINE.md` |
| Mid-term subset regeneration | Yes |
| Dependency-aware execution tree | Yes |
| Per-step provider/model overrides | Yes |
| Per-step reasoning effort | Yes |
| Per-step success criteria | Yes |
| Per-step verification command overrides | Yes |
| Owned-path based parallel safety | Yes |
| Manual step editing before execution | Yes |
| Background polling from desktop UI | Yes |
| Checkpoint timeline and approval state | Yes |

### Safety, Recovery, and Outputs

| Capability | Supported |
| --- | --- |
| Safe revision capture | Yes |
| Rollback on regression | Yes |
| Verified-only commit flow | Yes |
| Optional push after safe runs | Yes, when `--allow-push` is enabled and `origin` exists |
| Verification cache replay | Yes |
| PR-ready failure bundle generation | Yes |
| Optional PR failure reporting with GitHub token | Yes |
| Closeout markdown report | Yes |
| Word closeout report | Yes, with `--word-report` or desktop toggle |
| Execution flow SVG | Yes |
| ML experiment results SVG | Yes |
| Runtime time/cost estimates | Yes |
| Codex usage aggregation | Yes |

## Desktop UI

The desktop shell keeps the Python backend intact and adds a control layer for planning, execution, monitoring, and project history management.

What you can do from the desktop app:

- register an existing local repository as a managed project
- save runtime defaults such as provider, model, Codex path, checkpoint rules, and parallel worker settings
- generate an execution plan, edit the DAG, and rerun planning without losing project state
- inspect dependencies, owned paths, hybrid lineage steps, recent logs, and generated reports
- run the plan, request immediate stop, pause after the current step, and trigger closeout
- review estimated remaining time, estimated cost, actual recent cost, and Codex usage windows
- create, copy, and revoke temporary remote monitor links
- archive finished managed workspaces into history and delete old history entries
- change dashboard cards, theme, language, and background concurrency limits

Build the desktop app:

```bash
cd desktop
npm run tauri:build
```

Related files:

- [desktop/README.md](desktop/README.md)
- [website/README.md](website/README.md)

## Configuration

`jakal-flow` supports both CLI runtime options and desktop-managed defaults.

### CLI / Runtime Settings

| Group | Supported settings |
| --- | --- |
| Repository targeting | `--repo-url`, `--branch`, `--workspace-root`, `--plan-file`, `--resume` |
| Model selection | `--model-provider`, `--local-model-provider`, `--model`, `--effort`, `--fast` |
| Provider connection | `--provider-base-url`, `--provider-api-key-env` |
| Cost estimation | `--billing-mode`, `--input-cost-per-million-usd`, `--cached-input-cost-per-million-usd`, `--output-cost-per-million-usd`, `--reasoning-output-cost-per-million-usd`, `--per-pass-cost-usd` |
| Workflow control | `--workflow-mode`, `--ml-max-cycles`, `--max-blocks`, `--extra-prompt`, `--plan-prompt` |
| Optimization controls | `--optimization-mode`, `--optimization-large-file-lines`, `--optimization-long-function-lines`, `--optimization-duplicate-block-lines`, `--optimization-max-files` |
| Safety and validation | `--approval-mode`, `--sandbox-mode`, `--test-cmd`, `--allow-push` |
| Reporting | `--word-report` |

To inspect the current command surface from your local checkout:

```bash
python -m jakal_flow --help
python -m jakal_flow run --help
```

### Desktop-managed Defaults

The desktop shell additionally manages:

- `planning_effort`
- `parallel_worker_mode`, `parallel_workers`, and `parallel_memory_per_worker_gib`
- `checkpoint_interval_blocks`
- `require_checkpoint_approval`
- `codex_path`
- `allow_push`
- `save_project_logs`
- dashboard visibility preferences
- UI theme and language
- share server bind host and public base URL
- background job concurrency limit

### Cost Modes

Supported billing estimation modes:

- `included`
- `token`
- `per_pass`

### Example Provider Setups

Ensemble routing:

```bash
python -m jakal_flow run \
  --repo-url https://github.com/Ahnd6474/lit.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --model-provider ensemble \
  --model gpt-5.4 \
  --effort high \
  --approval-mode never \
  --sandbox-mode workspace-write \
  --test-cmd "python -m pytest" \
  --max-blocks 1
```

OpenRouter:

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

Gemini CLI:

```bash
python -m jakal_flow run \
  --repo-url https://github.com/Ahnd6474/lit.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --model-provider gemini \
  --model gemini-3-flash-preview \
  --approval-mode never \
  --sandbox-mode workspace-write \
  --test-cmd "python -m pytest" \
  --max-blocks 1
```

Claude Code:

```bash
python -m jakal_flow run \
  --repo-url https://github.com/Ahnd6474/lit.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --model-provider claude \
  --model claude-sonnet-4-6 \
  --approval-mode never \
  --sandbox-mode workspace-write \
  --test-cmd "python -m pytest" \
  --max-blocks 1
```

Qwen Code:

```bash
python -m jakal_flow run \
  --repo-url https://github.com/Ahnd6474/lit.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --model-provider qwen_code \
  --model qwen3-coder-plus \
  --approval-mode never \
  --sandbox-mode workspace-write \
  --test-cmd "python -m pytest" \
  --max-blocks 1
```

Local OSS via Ollama:

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

ML workflow:

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

## How It Works

### Short version

```text
CLI / Desktop UI / Share monitor
            |
            v
      Python orchestration core
            |
            +-- planning.py
            +-- codex_runner.py
            +-- git_ops.py
            +-- workspace.py
            +-- memory.py
            +-- reporting.py
            |
            v
  projects/<repo_slug>/
    repo/ docs/ memory/ logs/ reports/ state/
```

### Initialization

1. Create an isolated project directory under the workspace root.
2. Clone or refresh a remote repository into `repo/`, or register an existing local repository path from the desktop shell.
3. Scan `README.md`, `AGENTS.md`, and `repo/docs/**`.
4. Generate or refresh the saved plan, scope guard, Planner Agent A outline, and checkpoint timeline.
5. Record the current safe revision and persist project metadata outside the repository working tree.

### Each run block

1. Load saved plan context, runtime settings, and task memory.
2. Rebuild the mid-term subset and refresh ready steps.
3. Run dependency-ready steps through the parallel DAG scheduler.
4. Verify changes, reusing cached verification results when the fingerprint matches.
5. Commit only safe validated changes.
6. Roll back to the last safe revision on regression or unsafe merge outcomes.
7. Write logs, reports, SVG summaries, and memory updates.
8. Run a separate closeout pass when planned work is complete.

## Workspace Layout

Every managed repository gets its own isolated subtree:

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
  history/
    <archived_run_slug>/
  registry.json
```

Common project artifacts can include:

- `docs/PLAN.md`
- `docs/PLAN_AGENT_A_OUTLINE.md`
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
- `reports/*.prfail.json`
- `reports/*.prfail.md`
- `reports/latest_pr_failure_status.json`
- `reports/CLOSEOUT_REPORT.docx`
- `state/LOOP_STATE.json`
- `state/CHECKPOINTS.json`
- `state/EXECUTION_PLAN.json`
- `state/LINEAGES.json`
- `state/ML_MODE_STATE.json`
- `state/ML_STEP_REPORT.json`
- `state/PROJECT_DETAIL_CACHE_CORE.json`
- `state/PROJECT_DETAIL_CACHE_FULL.json`
- `state/UI_RUN_CONTROL.json`
- `state/ml_experiments/*.json`
- `state/share_sessions.json`
- `state/verification_cache/*.json`
- `metadata.json`
- `project_config.json`

For local projects, runtime log files are also written directly under `<repo>/jakal-flow-logs/`.

Workspace-level sidecar files can additionally include:

- `registry.json`
- `share_sessions.json`
- `share_session_events.jsonl`
- `share_server.json`
- `share_server_config.json`
- `share_server.log`
- `public_tunnel.json`

## Notes

- `codex exec` is invoked non-interactively and JSON event streams are saved under `logs/block_*/`.
- Claude Code uses print-mode JSON output and Gemini CLI uses headless JSON output, but both are normalized into the same trace files.
- Local OSS runs still go through Codex CLI rather than bypassing it.
- The desktop bridge forces UTF-8 stdio on Windows so JSON payloads and Korean text survive the bridge boundary.
- CLI defaults stay conservative: `--max-blocks` defaults to `1`, `--allow-push` is opt-in, and examples in this README use `python -m jakal_flow ...` so they work from a source checkout.
- Desktop-managed defaults are stored per project and can be more permissive than the CLI examples.
- Temporary public share links can use a configured public base URL or a Cloudflare Quick Tunnel; on Windows the app can install `cloudflared` via `winget` when needed.

## Star History

<p align="center">
  <a href="https://www.star-history.com/#Ahnd6474/Jakal-flow&type=date&legend=top-left">
    <img
      src="https://api.star-history.com/svg?repos=Ahnd6474/Jakal-flow&type=date&legend=top-left"
      alt="Star History Chart for Jakal-flow"
    />
  </a>
</p>

<p align="center">
  If the chart does not render in your GitHub view, open it directly:
  <a href="https://www.star-history.com/#Ahnd6474/Jakal-flow&type=date&legend=top-left">Star History</a>
</p>
