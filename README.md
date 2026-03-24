# codex-auto

`codex-auto` is a production-oriented Python CLI for managing multiple repositories inside an isolated workspace and repeatedly running a traceable Codex-driven improvement loop against them.

It is designed around two planning layers:

- `docs/LONG_TERM_PLAN.md`: created once or seeded from a user-provided file; treated as immutable unless explicitly changed by the user
- `docs/MID_TERM_PLAN.md`: regenerated at block boundaries and kept as a strict subset of the long-term plan

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

## GUI

Launch the desktop GUI:

```bash
codex-auto-gui
```

Or:

```bash
python -m codex_auto.gui
```

Without installing the package first:

```bash
python gui_main.py
```

The GUI lets you:

- configure repo URL, branch, workspace root, model, sandbox, approval mode, test command, and max blocks
- choose reasoning effort from `low`, `medium`, `high`, `xhigh`
- add extra user prompt instructions that are appended to Codex implementation prompts
- browse GitHub repositories from inside the app using the GitHub REST API
- initialize, run, and resume managed repositories
- browse managed repositories in the current workspace
- inspect status, history, and generated reports without leaving the app
- view aggregate Codex token usage pulled from saved JSON event logs

GitHub integration notes:

- public repository search works without a token
- listing your own repositories requires a GitHub Personal Access Token
- the GUI keeps the token in memory only; it is not persisted by this app

## Main Commands

Initialize a managed repository:

```bash
python -m codex_auto init-repo \
  --repo-url https://github.com/example/project.git \
  --branch main \
  --workspace-root .codex-auto-workspace \
  --model gpt-5.4 \
  --effort medium \
  --approval-mode never \
  --sandbox-mode workspace-write \
  --test-cmd "python -m pytest"
```

Run two improvement blocks:

```bash
python -m codex_auto run \
  --repo-url https://github.com/example/project.git \
  --branch main \
  --workspace-root .codex-auto-workspace \
  --model gpt-5.4 \
  --effort medium \
  --approval-mode never \
  --sandbox-mode workspace-write \
  --test-cmd "python -m pytest" \
  --max-blocks 2
```

Resume a managed repository:

```bash
python -m codex_auto resume \
  --repo-url https://github.com/example/project.git \
  --branch main \
  --workspace-root .codex-auto-workspace \
  --model gpt-5.4 \
  --effort medium \
  --approval-mode never \
  --sandbox-mode workspace-write \
  --test-cmd "python -m pytest" \
  --max-blocks 1
```

List all managed repositories:

```bash
python -m codex_auto list-repos --workspace-root .codex-auto-workspace
```

Inspect status, history, and reports:

```bash
python -m codex_auto status --repo-url https://github.com/example/project.git --branch main
python -m codex_auto history --repo-url https://github.com/example/project.git --branch main --limit 20
python -m codex_auto report --repo-url https://github.com/example/project.git --branch main
```

## How It Works

Initialization:

1. Creates an isolated project directory under the workspace
2. Clones or updates the target repository into `repo/`
3. Scans `README.md`, `AGENTS.md`, and `repo/docs/**`
4. Creates `docs/LONG_TERM_PLAN.md`, `docs/SCOPE_GUARD.md`, `docs/MID_TERM_PLAN.md`, memory files, and loop state
5. Records the current safe git revision

Each run block:

1. Retrieves relevant memory from prior attempts
2. Rebuilds a mid-term plan from the long-term plan
3. Generates 2-3 candidate tasks and selects one
4. Runs two implementation passes with `codex exec --json`
5. Runs a research-backed pass with Codex web search enabled
6. Runs tests after each pass
7. Commits only safe validated changes
8. Rolls back to the previous safe revision on regression
9. Saves structured logs, reports, block review, and memory summaries

## Repository Files Managed Per Project

The tool creates or maintains these files for each managed repository project:

- `docs/LONG_TERM_PLAN.md`
- `docs/MID_TERM_PLAN.md`
- `docs/SCOPE_GUARD.md`
- `docs/ACTIVE_TASK.md`
- `docs/BLOCK_REVIEW.md`
- `docs/RESEARCH_NOTES.md`
- `docs/attempt_history.md`
- `state/LOOP_STATE.json`
- `memory/success_patterns.jsonl`
- `memory/failure_patterns.jsonl`
- `memory/task_summaries.jsonl`
- `logs/passes.jsonl`
- `logs/blocks.jsonl`
- `reports/latest_report.json`
- `metadata.json`
- `project_config.json`

Sample planning template:

- `templates/LONG_TERM_PLAN.sample.md`

## Notes

- `codex exec` is invoked through subprocess in non-interactive mode and JSON event streams are saved under `logs/block_*/`
- `reasoning.effort` is passed through to Codex using `low`, `medium`, `high`, or `xhigh`
- token usage is aggregated from `turn.completed` JSON events and surfaced in the GUI dashboard and pass logs
- each repository gets its own isolated workspace subtree; no mutable state is shared across projects
- local git user identity is configured in the managed clone for automated commits
- `--allow-push` pushes safe commits to `origin` after successful blocks
- default `--max-blocks` is `1` for safer operation; increase it explicitly when needed
