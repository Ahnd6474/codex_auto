# codex-auto Desktop

`desktop/` contains the React + Tauri shell for `codex-auto`.

It does not replace the Python orchestration backend. The Tauri side calls `python -m codex_auto.ui_bridge` and keeps the existing multi-repository workspace layout, plan files, logs, reports, and rollback behavior intact.

## Prerequisites

- Node.js 20+
- Rust toolchain
- Tauri system prerequisites for your OS
- Python 3.11+ available on `PATH`, or set `CODEX_AUTO_PYTHON`

## Development

From the repository root:

```bash
cd desktop
npm.cmd install
npm.cmd run test
npm.cmd run tauri:dev
```

Build the desktop app:

```bash
cd desktop
npm.cmd run tauri:build
```

Run the desktop unit tests:

```bash
cd desktop
npm.cmd run test
```

## Architecture

- `src/`: React UI for the setup and flow stages
- `src-tauri/`: Tauri shell and background job manager
- `src/codex_auto/ui_bridge.py`: JSON bridge used by the desktop shell

The desktop shell keeps one background job at a time so project execution stays predictable.
