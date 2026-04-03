# jakal-flow

> Traceable multi-repository automation for Codex-style workflows.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Desktop UI](https://img.shields.io/badge/Desktop-React%20%2B%20Tauri-24C8DB)](#desktop-app)
[![GitHub stars](https://img.shields.io/github/stars/Ahnd6474/Jakal-flow?style=flat)](https://github.com/Ahnd6474/Jakal-flow/stargazers)

`jakal-flow` runs AI-assisted coding work across many repositories without flattening everything into one shared workspace. Each managed project keeps its own planning docs, memory, logs, reports, checkpoints, and rollback state, so you can inspect what happened after the run instead of guessing.

- Korean guide: [README.ko.md](README.ko.md)
- Installed entrypoints: `jakal-flow`, `jakal-flow-ui-bridge`, `jakal-flow-desktop`
- Live CLI surface from this checkout: `$env:PYTHONPATH='src'; python -m jakal_flow --help`

## Table of contents

- [What it does](#what-it-does)
- [Install](#install)
- [Quick start](#quick-start)
- [Runtime config](#runtime-config)
- [CLI surface](#cli-surface)
- [Workspace layout](#workspace-layout)
- [Desktop app](#desktop-app)
- [Development](#development)
- [Star history](#star-history)

## What it does

`jakal-flow` is built around traceability and recovery, not just one successful agent session.

- Every managed repository gets its own project root under the workspace.
- Planning state, checkpoint state, reports, and memory stay attached to that project.
- Safe revisions and rollback-aware execution stay part of the normal flow.
- Parallel execution and background queueing are first-class runtime controls.
- The desktop app uses the same Python backend as the CLI, so there is one source of truth.
- The desktop workspace can expose remote monitor/share sessions without changing the core project model.

Current workflow support includes normal coding runs and ML-style experiment loops, with separate reports and state for each cycle when `workflow_mode = "ml"`.

## At a glance

<p align="center">
  <img src="assets/readme-flow.svg" alt="jakal-flow architecture overview" width="100%" />
</p>

## Install

Clone the repository and install the Python package in editable mode:

```bash
git clone https://github.com/Ahnd6474/Jakal-flow.git
cd Jakal-flow
python -m pip install -e .
```

If you plan to work on the desktop shell too:

```bash
cd desktop
npm install
```

Requirements:

- Python 3.11+
- Git
- Codex CLI on `PATH` for the default `openai` provider
- Matching CLI or API credentials for any other provider you choose
- Node.js 20+, Rust, and Tauri prerequisites for desktop development and packaging

## Quick start

### 1. Create a runtime config

`--config` accepts either JSON or TOML. You can use top-level keys or wrap them under `runtime` / `[runtime]`.

```toml
[runtime]
model_provider = "openai"
model = "gpt-5.4"
effort = "high"
approval_mode = "never"
sandbox_mode = "workspace-write"
workflow_mode = "standard"
test_cmd = "python -m pytest"
max_blocks = 2
allow_background_queue = true
parallel_worker_mode = "auto"
require_checkpoint_approval = true
```

### 2. Register a repository

```bash
jakal-flow init-repo \
  --repo-url https://github.com/Ahnd6474/lit.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --config .jakal-flow.runtime.toml
```

### 3. Run work

```bash
jakal-flow run \
  --repo-url https://github.com/Ahnd6474/lit.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --config .jakal-flow.runtime.toml
```

You can override any runtime key after loading the config file:

```bash
jakal-flow run \
  --repo-url https://github.com/Ahnd6474/lit.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --config .jakal-flow.runtime.toml \
  --set max_blocks=3 \
  --set optimization_mode=light
```

You can also seed a plan file:

```bash
jakal-flow run \
  --repo-url https://github.com/Ahnd6474/lit.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --config .jakal-flow.runtime.toml \
  --plan-file PLAN.md
```

### 4. Inspect the result

```bash
jakal-flow list-repos --workspace-root .jakal-flow-workspace
jakal-flow status --repo-url https://github.com/Ahnd6474/lit.git --branch main --workspace-root .jakal-flow-workspace
jakal-flow history --repo-url https://github.com/Ahnd6474/lit.git --branch main --workspace-root .jakal-flow-workspace --limit 10
jakal-flow report --repo-url https://github.com/Ahnd6474/lit.git --branch main --workspace-root .jakal-flow-workspace
jakal-flow logx --repo-url https://github.com/Ahnd6474/lit.git --branch main --workspace-root .jakal-flow-workspace
jakal-flow logx --workspace-root .jakal-flow-workspace --source-repo-dir D:/GitHub/lit
```

Use `resume` when a managed project already exists and you want to continue it:

```bash
jakal-flow resume \
  --repo-url https://github.com/Ahnd6474/lit.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --config .jakal-flow.runtime.toml
```

## Runtime config

The runtime surface is intentionally broad, but you usually only need a handful of keys.

| Key | Example | What it controls |
| --- | --- | --- |
| `model_provider` | `openai` | Provider preset and backend path |
| `model` | `gpt-5.4` | Explicit model slug for the selected provider |
| `effort` | `medium`, `high` | Reasoning effort |
| `workflow_mode` | `standard`, `ml` | Normal coding flow or ML experiment loop |
| `test_cmd` | `python -m pytest` | Verification command |
| `max_blocks` | `2` | Maximum improvement blocks per run |
| `allow_background_queue` | `true` | Allow the project to wait in the workspace queue |
| `background_queue_priority` | `10` | Queue priority when background queueing is enabled |
| `parallel_worker_mode` | `auto`, `manual` | How worker count is chosen |
| `parallel_workers` | `4` | Worker count when `parallel_worker_mode = "manual"` |
| `parallel_memory_per_worker_gib` | `3.0` | Memory budget used when sizing parallel workers |
| `optimization_mode` | `off`, `light`, `refactor` | Static optimization scan intensity |
| `require_checkpoint_approval` | `true` | Require approval before checkpoint promotion |
| `allow_push` | `false` | Allow automated push from a run |
| `auto_merge_pull_request` | `false` | Request auto-merge when PR automation is active |
| `approval_mode` | `never` | Provider approval mode |
| `sandbox_mode` | `workspace-write` | Provider sandbox mode |

Provider presets currently include:

- `openai`
- `ensemble`
- `claude`
- `gemini`
- `ollama`
- `oss`
- `qwen_code`
- `deepseek`
- `kimi`
- `minimax`
- `glm`
- `openrouter`
- `opencdk`
- `local_openai`

For local OSS runs, `local_model_provider` currently accepts `ollama` or `lmstudio`.

## CLI surface

The CLI commands exposed by `python -m jakal_flow --help` are:

| Command | What it does |
| --- | --- |
| `init-repo` | Register a remote repository inside the workspace |
| `run` | Execute one or more improvement blocks |
| `resume` | Continue a managed project |
| `list-repos` | List active managed repositories in the workspace |
| `status` | Show the current repository status |
| `history` | Show block history for a project |
| `report` | Generate the latest machine-readable report |
| `logx` | Refresh the searchable log index for a managed project or local source tree |

Shared flags:

- `init-repo`, `run`, and `resume` accept `--config`, `--set KEY=VALUE`, and `--plan-file`.
- `status`, `history`, `report`, and `logx` all work against an existing managed project.
- `logx` can target either a managed repo with `--repo-url` or a local repo with `--source-repo-dir`.

## Workspace layout

The workspace root keeps active projects, archived history, and desktop-level share state:

```text
workspace_root/
  registry.json
  projects/
    <repo_slug>/
      repo/
      docs/
      memory/
      reports/
      state/
  history/
    <archive_slug>/
      ...
  share_server.json
  share_sessions.json
  share_session_events.jsonl
```

Inside each managed project:

- `docs/` holds operator-facing artifacts such as `PLAN.md`, `BLOCK_REVIEW.md`, `CLOSEOUT_REPORT.md`, `SHARED_CONTRACTS.md`, and `EXECUTION_FLOW.svg`.
- `state/` holds runtime state such as `LOOP_STATE.json`, `EXECUTION_PLAN.json`, `CHECKPOINTS.json`, planning caches, lineage manifests, and contract-wave audit files.
- `memory/` holds accumulated summaries and pattern logs in JSONL form.
- `reports/` holds `latest_report.json` plus optional closeout exports.

Archived projects move from `projects/` to `history/`, so you keep the old state tree instead of overwriting it.

One local-project detail is worth calling out: when the desktop app manages a local source tree, run logs are written beside that repository in `jakal-flow-logs/`. The managed workspace still keeps the project's docs, state, memory, and reports.

## Desktop app

The desktop app is a React + Tauri shell on top of the same Python backend and UI bridge. It is not a separate product line with its own orchestration rules.

Desktop features include:

- project setup for local repositories
- plan generation and editing
- run control, queue visibility, and checkpoint handling
- contracts and shared-contract review flows
- workspace sharing and remote monitor sessions

Run it directly from `desktop/`:

```bash
cd desktop
npm run tauri:dev
```

Or use the installed launcher from the repository root:

```bash
jakal-flow-desktop dev
jakal-flow-desktop build
jakal-flow-desktop test
jakal-flow-desktop web-dev
jakal-flow-desktop web-build
```

`jakal-flow-desktop` forwards extra arguments after `--` to the underlying npm script:

```bash
jakal-flow-desktop web-dev -- --host 127.0.0.1 --port 1420
```

Useful desktop packaging commands:

```bash
cd desktop
npm run tauri:build
npm run tauri:build:lean
npm run tauri:build:all
```

- `tauri:build` builds the full installer flow.
- `tauri:build:lean` builds an installer that expects Python and provider CLIs to already exist on the target machine.
- `tauri:build:all` runs the full and lean variants.

## Development

Python tests:

```bash
python -m pytest
```

Desktop tests and builds:

```bash
cd desktop
npm test
npm run build
npm run build:budget
```

If you want the raw module entrypoints while developing from source:

```bash
$env:PYTHONPATH='src'; python -m jakal_flow --help
$env:PYTHONPATH='src'; python -m jakal_flow.ui_bridge --help
```

The bundled desktop runtime can also be prepared directly:

```bash
$env:PYTHONPATH='src'; python -m jakal_flow.desktop_runtime_bundle --target rt
```

That command writes a runtime bundle under `rt/`, including the packaged Python runtime and the CLI shims used by the desktop installer flow.

## Star history

[![GitHub stars](https://img.shields.io/github/stars/Ahnd6474/Jakal-flow?style=social)](https://www.star-history.com/#Ahnd6474/Jakal-flow&Date)

[Live Star History chart](https://www.star-history.com/#Ahnd6474/Jakal-flow&Date)
