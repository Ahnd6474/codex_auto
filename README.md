# jakal-flow

> Traceable multi-repository automation for Codex-style workflows.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Desktop UI](https://img.shields.io/badge/Desktop-React%20%2B%20Tauri-24C8DB)](#desktop-ui)
[![GitHub stars](https://img.shields.io/github/stars/Ahnd6474/Jakal-flow?style=flat)](https://github.com/Ahnd6474/Jakal-flow/stargazers)

`jakal-flow` is a production-oriented automation CLI for teams running AI-assisted work across multiple repositories.
Instead of flattening everything into one workspace, it keeps every managed repository isolated and preserves the artifacts you need to trust the run later: plans, logs, reports, memory, checkpoints, and rollback state.

- Korean guide: [README.ko.md](README.ko.md)
- Live CLI surface from this checkout: `$env:PYTHONPATH='src'; python -m jakal_flow --help`
- Recent additions: `list-repos`, `history`, `logx --source-repo-dir`, `--set KEY=VALUE`, `--plan-file`

## Why It Stands Out

Unlike general-purpose agent runners that optimize for a single session, `jakal-flow` is designed around repeatable, traceable operations across many repositories.

- `Per-repo isolation first`: each repository gets its own `repo/`, `docs/`, `memory/`, `logs/`, `reports/`, and `state/`.
- `Traceability by default`: execution logs, planning caches, contract-wave audit data, and reports stay attached to the project that produced them.
- `Rollback-safe orchestration`: safe revisions and recovery flow are part of the implementation, not an afterthought.
- `CLI and desktop together`: the React + Tauri app sits on top of the same Python backend instead of forking the product into a separate path.
- `Operations-friendly`: status, history, reports, and log indexing are built into the normal workflow.

## At A Glance

<p align="center">
  <img src="assets/readme-flow.svg" alt="jakal-flow architecture overview" width="100%" />
</p>

## Quick Start

### 1. Install

```bash
python -m pip install -e .
```

Installed entrypoints:

- `jakal-flow`
- `jakal-flow-ui-bridge`

Requirements:

- Python 3.11+
- Codex CLI on `PATH`
- Optional for desktop: Node.js 20+, Rust, and Tauri prerequisites

### 2. Create a runtime config

```toml
[runtime]
model_provider = "openai"
model = "gpt-5.4"
effort = "high"
approval_mode = "never"
sandbox_mode = "workspace-write"
test_cmd = "python -m pytest"
max_blocks = 2
```

### 3. Register a repository

```bash
jakal-flow init-repo \
  --repo-url https://github.com/Ahnd6474/lit.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --config .jakal-flow.runtime.toml
```

### 4. Run work

```bash
jakal-flow run \
  --repo-url https://github.com/Ahnd6474/lit.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --config .jakal-flow.runtime.toml
```

## Core Commands

```bash
jakal-flow list-repos --workspace-root .jakal-flow-workspace
jakal-flow resume --repo-url https://github.com/Ahnd6474/lit.git --branch main --workspace-root .jakal-flow-workspace --config .jakal-flow.runtime.toml
jakal-flow status --repo-url https://github.com/Ahnd6474/lit.git --branch main --workspace-root .jakal-flow-workspace
jakal-flow history --repo-url https://github.com/Ahnd6474/lit.git --branch main --workspace-root .jakal-flow-workspace --limit 10
jakal-flow report --repo-url https://github.com/Ahnd6474/lit.git --branch main --workspace-root .jakal-flow-workspace
jakal-flow logx --repo-url https://github.com/Ahnd6474/lit.git --branch main --workspace-root .jakal-flow-workspace
jakal-flow logx --workspace-root .jakal-flow-workspace --source-repo-dir D:/GitHub/lit
jakal-flow run --repo-url https://github.com/Ahnd6474/lit.git --branch main --workspace-root .jakal-flow-workspace --config .jakal-flow.runtime.toml --set max_blocks=3
jakal-flow run --repo-url https://github.com/Ahnd6474/lit.git --branch main --workspace-root .jakal-flow-workspace --plan-file PLAN.md
```

## What You Keep Per Project

Each managed repository gets its own isolated subtree:

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
```

That separation is the point. `jakal-flow` keeps multi-repository history readable and auditable instead of mixing outputs from unrelated runs.

Contract-wave metadata stays inside each project's `state/` and `docs/`, including:

- `SPINE.json`
- `COMMON_REQUIREMENTS.json`
- `CONTRACT_WAVE_AUDIT.jsonl`
- `state/lineage_manifests/`
- `docs/SHARED_CONTRACTS.md`

Planning caches and telemetry are also persisted per project:

- `state/PLANNING_INPUTS_CACHE.json`
- `state/PLANNING_PROMPT_CACHE.json`
- `state/BLOCK_PLAN_CACHE.json`
- `logs/planning_metrics.jsonl`

## Desktop UI

The desktop app is a React + Tauri shell over the same Python backend.
It gives operators a visual workflow without sacrificing the CLI's traceability model.

- Project setup and run control
- Plan editing and checkpoint handling
- Share actions and bridge-driven refresh
- `Contracts` sidebar for shared-contract state, CRR resolve/reopen/edit/delete flows, spine checkpoints, and recent contract-wave audit trail

Development:

```bash
cd desktop
npm install
npm run tauri:dev
```

Production build:

```bash
cd desktop
npm run tauri:build
```

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=Ahnd6474/Jakal-flow&type=Date)](https://www.star-history.com/#Ahnd6474/Jakal-flow&Date)
