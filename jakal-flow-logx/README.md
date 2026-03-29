# jakal-flow logx

This folder is a copied archive of `jakal-flow` runtime artifacts.
Original files were not moved or deleted.

Scope used in this archive:
- `workspace-projects/`: per-project managed artifacts copied from each workspace project root
- `workspace-roots/`: workspace-level share and registry files
- `local-repo-logs/`: repo-root `jakal-flow-logs/` trees

What is included for each project:
- `metadata.json`
- `project_config.json`
- `logs/`
- `reports/`
- `docs/`
- `memory/`
- `state/`
- `.parallel_runs/`
- `.parallel_agents/` when present

Workspace root files copied when present:
- `registry.json`
- `public_tunnel.json`
- `share_server.json`
- `share_server.log`
- `share_server_config.json`
- `share_sessions.json`
- `share_session_events.jsonl`
- `history/` if non-empty

Current archive summary:
- `workspace-projects/codex-auto-workspace/c-users-alber-onedrive-github-calculator-main-b2c8e74450`
  - source repo: `C:\Users\alber\OneDrive\문서\GitHub\calculator`
  - copied files: 112
- `workspace-projects/codex-auto-workspace/c-users-alber-onedrive-github-lit-main-54cb49de20`
  - source repo: `C:\Users\alber\OneDrive\문서\GitHub\lit`
  - copied files: 24
- `workspace-projects/none/c-users-alber-onedrive-github-lit-main-54cb49de20`
  - source repo: `C:\Users\alber\OneDrive\문서\GitHub\lit`
  - copied files: 135
- `workspace-projects/codex-auto-workspace-localtest/c-users-alber-onedrive-github-codex-auto-main-eb8d404f06`
  - source repo: internal `.codex-auto-workspace-localtest` test project
  - copied files: 4
- `workspace-projects/codex-auto-workspace-test/repo-main-d1b7ce84a6`
  - source repo: internal `.codex-auto-workspace-test` test project
  - copied files: 4
- `local-repo-logs/codex_auto`
  - source repo: `C:\Users\alber\OneDrive\문서\GitHub\codex_auto`
  - copied files: 130

Notes:
- The first archive pass missed nested files under `jakal-flow-logs/` and some traceability artifacts outside `logs/`.
- This archive was expanded to include project docs, state, memory, workspace share logs, and parallel-run artifacts.
- The `lit` project exists in multiple workspace snapshots, so each snapshot was kept separately.
