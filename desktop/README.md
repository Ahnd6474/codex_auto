# jakal-flow Desktop

`desktop/` contains the React + Tauri shell for `jakal-flow`.

It does not replace the Python orchestration backend. The Tauri side calls `python -m jakal_flow.ui_bridge` and keeps the existing multi-repository workspace layout, plan files, logs, reports, and rollback behavior intact.

## Prerequisites

- Node.js 20+
- Rust toolchain
- Tauri system prerequisites for your OS
- Python 3.11+ available on `PATH`, or set `JAKAL_FLOW_PYTHON`

## Development

From the repository root:

```bash
cd desktop
npm install
npm run test
npm run tauri:dev
```

Build the desktop app:

```bash
cd desktop
npm run tauri:build
```

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
