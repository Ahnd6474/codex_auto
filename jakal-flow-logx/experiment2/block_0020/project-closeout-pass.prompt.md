You are performing final closeout for the managed repository at C:\Users\alber\OneDrive\문서\GitHub\experiment2.
Follow any AGENTS.md rules in the repository.
All planned execution tasks are already marked complete. This pass is for final cleanup and handoff quality only.
Managed planning documents live outside the repo at C:\Users\alber\.jakal-flow-workspace\projects\c-users-alber-onedrive-github-experiment2-main-cfffe43b21\docs.
Primary verification command: python -m pytest.

Project title:
Jakal-flow Local Harness

Original user request:
jakal-flow(https://github.com/Ahnd6474/Jakal-flow)의 실행 환경을 구축해줘

Execution summary:
First remove the real Windows blocker by making bootstrap and target materialization long-path-safe within the fixed `.local/` layout. Once that contract is stable, fan out into a runtime verification task that turns `jakal-flow-local` into a clean materialize-install-smoke flow and a documentation task that publishes the same shipped operator contract so the harness is both runnable and handoff-ready.

Completed tasks:
- ST1: Harden Windows Materialization :: Bootstrap and remote target materialization both use an explicit long-path-safe Git strategy, and a dedicated offline regression proves a deeply nested synthetic repository can populate `.local/upstream` and `.local/targets` from the current repo root without `Filename too long` checkout failure.

Repository summary:
README:
# experiment2

AGENTS:
AGENTS.md not found.

Docs:
## docs\ARCHITECTURE.md
# Harness Architecture

Local experiment harness contract: tracked repository code only defines scripts,
profiles, fixtures, and docs. All generated state, upstream checkouts, and
managed workspaces live under `.local/`. Every entry script must load
`config/experiment.example.json` through `scripts/profile-common.ps...

Additional user instructions:
None.

Required closeout work:
1. Review the full repository and remove obvious dead code, redundant paths, duplicated logic, throwaway scaffolding, or low-value leftovers introduced during implementation when it is safe to do so.
2. Verify the user request is actually satisfied end-to-end and tighten rough edges where needed.
3. Run and/or improve executable tests so the repository remains in a coherent verified state.
4. If the project is realistically runnable on the local machine without heavy external infrastructure, run the most relevant local entrypoint or smoke check and fix small safe issues found there.
5. Remove obviously unnecessary generated or temporary directories left behind by implementation work when they are safe to delete and are not part of the product or test fixtures.
6. Write a concise future-maintainer guide and closeout summary to C:\Users\alber\.jakal-flow-workspace\projects\c-users-alber-onedrive-github-experiment2-main-cfffe43b21\docs\CLOSEOUT_REPORT.md. Include what was completed, how to continue later, important files, and remaining risks or follow-up ideas.
7. Treat README.md as a first-class closeout deliverable. Audit installation, setup, commands, workflow, configuration, architecture notes, limitations, and operator guidance against the verified implementation, and tighten README.md when it is stale, thin, or missing important verified context.
8. Update README or repository docs only when they match verified implementation. If README.md is already accurate enough, say that explicitly in C:\Users\alber\.jakal-flow-workspace\projects\c-users-alber-onedrive-github-experiment2-main-cfffe43b21\docs\CLOSEOUT_REPORT.md.

Execution rules:
- Use one focused closeout pass.
- Prefer small safe cleanup over speculative refactors.
- Do not expand scope into new features.
- If a requested closeout item is not safely feasible, explain that clearly in C:\Users\alber\.jakal-flow-workspace\projects\c-users-alber-onedrive-github-experiment2-main-cfffe43b21\docs\CLOSEOUT_REPORT.md.
