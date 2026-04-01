# jakal-flow

Traceable multi-repository automation for Codex-style workflows.

`jakal-flow` keeps each managed repository in its own isolated workspace and persists plans, logs, reports, memory, and rollback state per project. The Python CLI is the primary interface, and the React + Tauri desktop shell uses the same backend instead of replacing it.

- Korean guide: [README.ko.md](README.ko.md)
- Recent additions: `list-repos`, `history`, `logx --source-repo-dir`, `--set KEY=VALUE`, and `--plan-file`.

## Requirements

- Python 3.11+
- Codex CLI on `PATH`
- Optional for the desktop shell: Node.js 20+, Rust, and Tauri prerequisites

## Install

```bash
python -m pip install -e .
```

Installed entrypoints:

- `jakal-flow`
- `jakal-flow-ui-bridge`

Check the live CLI surface from this checkout:

```bash
$env:PYTHONPATH='src'; python -m jakal_flow --help
```

## Quick Start

Create a runtime config:

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

Initialize a managed repository:

```bash
jakal-flow init-repo \
  --repo-url https://github.com/Ahnd6474/lit.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --config .jakal-flow.runtime.toml
```

Run work:

```bash
jakal-flow run \
  --repo-url https://github.com/Ahnd6474/lit.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --config .jakal-flow.runtime.toml
```

Useful follow-up commands:

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

## Workspace Layout

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

This keeps multi-repository history and traceability separate by design.

Contract-wave metadata stays inside each project's `state/` and `docs/` folders, including `SPINE.json`, `COMMON_REQUIREMENTS.json`, `CONTRACT_WAVE_AUDIT.jsonl`, `state/lineage_manifests/`, and `docs/SHARED_CONTRACTS.md`.
Planning caches and telemetry are persisted alongside the project as `state/PLANNING_INPUTS_CACHE.json`, `state/PLANNING_PROMPT_CACHE.json`, `state/BLOCK_PLAN_CACHE.json`, and `logs/planning_metrics.jsonl`.

## Desktop UI

The desktop app is a React + Tauri shell over the same Python backend.
The `Contracts` sidebar surfaces shared-contract state, lets operators resolve/reopen/edit/delete CRRs, records spine checkpoints, and shows the recent contract-wave audit trail.

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
