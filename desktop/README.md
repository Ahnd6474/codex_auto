# jakal-flow Desktop

`desktop/` contains the React + Tauri shell for `jakal-flow`.

It does not replace the Python orchestration backend. The Tauri side calls `python -m jakal_flow.ui_bridge` and keeps the existing multi-repository workspace layout, plan files, logs, reports, and rollback behavior intact.

## Prerequisites

- Node.js 20+
- Rust toolchain
- Tauri system prerequisites for your OS
- Python 3.11+ available on `PATH`, or set `JAKAL_FLOW_PYTHON`, when building the desktop app

## Development

From the repository root:

```bash
cd desktop
npm install
npm run test
npm run tauri:dev
```

Or use the root launcher after `python -m pip install -e .`:

```bash
jakal-flow-desktop dev
jakal-flow-desktop test
jakal-flow-desktop build
jakal-flow-desktop build-python
```

On Windows you can also build the installer directly from the repository root:

```powershell
.\build-desktop-release.ps1 -Profile python
```

Build the desktop app:

```bash
cd desktop
npm run tauri:build
```

Build the recommended Windows app profile with only the Python runtime bundled:

```bash
cd desktop
npm run tauri:build:python
```

Build the lean installer without bundled runtimes:

```bash
cd desktop
npm run tauri:build:lean
```

`npm run tauri:build` now prepares a bundled runtime under `rt/` before Tauri packages the app. The full installer embeds:

- the Python runtime used for the bridge
- `src/jakal_flow`
- a bundled Node runtime plus any detected global npm provider CLIs

On this machine that means Codex CLI and Gemini CLI are embedded. Claude Code and Qwen Code remain optional because they were not installed at build time.

`npm run tauri:build:python` also prepares `rt/`, but it bundles only the Python runtime used by the bridge. Provider CLIs are not embedded, so the installed app can stay lightweight and install Codex/Gemini/Ollama later from the AI Tools tab.

`npm run tauri:build:lean` skips the bundled runtime and only packages the desktop shell plus `src/jakal_flow`. The target machine must already have Python 3.11+ and any required provider CLIs on `PATH`.

Run the desktop unit tests:

```bash
cd desktop
npm run test
```

## Architecture

- `src/`: React UI for the setup and flow stages
- `src-tauri/`: Tauri shell and background job manager
- `src/jakal_flow/ui_bridge.py`: JSON bridge used by the desktop shell

The desktop shell queues background jobs and respects the configured program-level concurrency limit so project execution stays predictable.
