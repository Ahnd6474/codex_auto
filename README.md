# codex-auto

`codex-auto` is a production-oriented Python CLI for managing multiple repositories inside an isolated workspace and repeatedly running a traceable Codex-driven improvement loop against them.

It is designed around a saved project plan:

- `docs/PLAN.md`: stores the current project plan or reviewed execution plan snapshot
- `docs/MID_TERM_PLAN.md`: regenerated at block boundaries and kept as a strict subset of the saved plan
- `docs/CHECKPOINT_TIMELINE.md`: derived from the saved plan and used for review boundaries

## Flow

![codex-auto flow chart](assets/readme-flow-ko.svg)

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

- stage the workflow into two screens: environment setup first, prompt-driven execution second
- choose the local project directory that Codex will work in
- prepare the project directory with `.venv` and `.gitignore`
- run Codex with `approval=never` and `sandbox=danger-full-access` from the GUI
- choose the runtime model either as a direct slug or as a Codex slug built from editable slug parts
- generate a test-driven execution plan from a free-form prompt
- edit the Codex prompt templates in `src/codex_auto/docs/`
- review a setup-stage runtime flow chart and an interactive flow chart of the generated steps
- edit pending steps, including add/delete/reorder, UI descriptions, Codex instructions, and per-step test commands
- execute the remaining steps sequentially and show progress directly in the flow chart
- run a final closeout pass after all steps complete to optimize, verify, smoke-test when feasible, and write a handoff report
- execute each step with one search-enabled Codex pass instead of multiple implementation passes
- treat each completed step as a checkpoint and push after verification when `origin` is configured
- return to the setup screen and open any previously managed project flow later

Static website assets are kept separately under `website/`.

## Main Commands

Initialize a managed repository:

```bash
python -m codex_auto init-repo \
  --repo-url https://github.com/example/project.git \
  --branch main \
  --workspace-root .codex-auto-workspace \
  --model gpt-5.4 \
  --effort medium \
  --plan-prompt "Build a safe project plan for this repository focused on a narrow MVP and strong tests." \
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
4. Creates or refreshes `docs/PLAN.md` from repository context or an optional plan prompt
5. Creates `docs/SCOPE_GUARD.md`, `docs/MID_TERM_PLAN.md`, memory files, and loop state
6. Builds a checkpoint timeline from the saved plan
7. Records the current safe git revision

Each run block:

1. Retrieves relevant memory from prior attempts
2. Rebuilds a mid-term plan from the saved plan
3. Generates 2-3 candidate tasks and selects one
4. Runs one search-enabled Codex pass for the selected block
5. Runs tests after the pass
6. Commits only safe validated changes
7. Stops at checkpoint boundaries for user review when approval is required
8. Pushes to GitHub when the user approves a checkpoint in the GUI
9. Rolls back to the previous safe revision on regression
10. Saves structured logs, reports, block review, and memory summaries

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
- `memory/success_patterns.jsonl`
- `memory/failure_patterns.jsonl`
- `memory/task_summaries.jsonl`
- `logs/passes.jsonl`
- `logs/blocks.jsonl`
- `reports/latest_report.json`
- `metadata.json`
- `project_config.json`

Source prompt and scope templates:

- `src/codex_auto/docs/PLAN_GENERATION_PROMPT.txt`
- `src/codex_auto/docs/STEP_EXECUTION_PROMPT.txt`
- `src/codex_auto/docs/FINALIZATION_PROMPT.txt`
- `src/codex_auto/docs/SCOPE_GUARD_TEMPLATE.md`

## Notes

- `codex exec` is invoked through subprocess in non-interactive mode and JSON event streams are saved under `logs/block_*/`
- the GUI saves the resolved execution model as a slug in `project_config.json`, so newly released model slugs can be entered without a code update
- `reasoning.effort` is passed through to Codex using `low`, `medium`, `high`, or `xhigh`
- token usage is aggregated from `turn.completed` JSON events and surfaced in the GUI dashboard and pass logs
- each repository gets its own isolated workspace subtree; no mutable state is shared across projects
- local git user identity is configured in the managed clone for automated commits
- `--allow-push` pushes safe commits to `origin` after successful blocks
- default `--max-blocks` is `1` for safer operation; increase it explicitly when needed
