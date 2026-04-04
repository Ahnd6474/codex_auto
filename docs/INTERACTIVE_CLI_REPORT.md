# Interactive CLI Report

## Summary

This change adds a new interactive `jakal-flow` shell that opens when the CLI is started without arguments.
The existing subcommand-oriented CLI remains available.

The shell is intentionally distinct from Codex CLI and Gemini CLI:

- Plain text sends chat messages.
- `/` triggers run actions.
- `$` edits the execution flow.
- `!` edits runtime settings.
- `@` switches projects.

## What Was Added

### 1. Interactive shell entry

- `jakal-flow` with no arguments now opens the shell.
- `jakal-flow shell` is also available as an explicit entry.
- Existing commands such as `run`, `status`, `history`, and `logx` are still supported.

Files:

- `src/jakal_flow/cli.py`
- `src/jakal_flow/interactive_cli.py`

### 2. ASCII execution board

- The shell renders the saved execution plan as an ASCII board.
- Step states are colorized when the terminal supports ANSI colors.
- The board resolves current step states from recent block logs before rendering.

Files:

- `src/jakal_flow/interactive_flow.py`

### 3. Flow editing commands

The shell supports editing the saved execution plan from the terminal:

- `$show`
- `$list`
- `$add TITLE :: DESCRIPTION`
- `$set STEP FIELD :: VALUE`
- `$drop STEP`
- `$swap STEP_A STEP_B`
- `$closeout FIELD :: VALUE`

Supported step fields:

- `title`
- `desc`
- `codex`
- `test`
- `success`
- `provider`
- `model`
- `effort`
- `status`
- `deps`
- `group`
- `paths`
- `notes`

Supported closeout fields:

- `title`
- `desc`
- `codex`
- `success`
- `provider`
- `model`
- `effort`
- `status`
- `paths`
- `notes`

### 4. Action commands

The shell exposes the current plan and recovery flows through action commands:

- `/plan`
- `/execute`
- `/debug`
- `/merge`
- `/closeout`
- `/approve`
- `/pause`
- `/wait`
- `/flow`
- `/status`
- `/history`
- `/report`
- `/checkpoints`
- `/mode chat|review`

Behavior notes:

- `/execute` runs in the background.
- While `/execute` is active, plain-text chat remains available.
- Mutating commands are locked while a background execution job is active.

### 5. Runtime settings commands

Runtime and model settings can be updated from the shell:

- `!show`
- `!set key=value ...`
- `!reset key ...`
- `!providers`

This covers model/provider selection, execution mode, approval mode, sandbox mode, checkpoints, and related runtime settings.

### 6. Project commands

Project selection is handled inside the shell:

- `@list`
- `@open [path]`
- `@use selector`
- `@where`

This keeps the shell oriented around one selected project at a time without removing the existing multi-project workspace model.

## Tests Added

- `tests/test_interactive_cli.py`

Coverage added:

- no-arg CLI dispatch enters the shell
- flow edit add/set/swap behavior
- ASCII execution board rendering

## Verification

Commands run:

```powershell
python -m py_compile src\jakal_flow\interactive_cli.py src\jakal_flow\interactive_flow.py src\jakal_flow\cli.py
$env:PYTHONPATH='src'; python -m pytest tests\test_interactive_cli.py -q
$env:PYTHONPATH='src'; python -m pytest tests\test_ui_bridge.py -q -k "runtime_from_args"
$env:PYTHONPATH='src'; cmd /c "echo /exit|python -m jakal_flow shell"
$env:PYTHONPATH='src'; cmd /c "echo /exit|python -m jakal_flow"
```

Notes:

- The new interactive CLI tests passed.
- A wider filtered run of older UI bridge tests hit an environment issue because `lit` is not installed in this shell, so those were not used as the final verification gate for this change.
