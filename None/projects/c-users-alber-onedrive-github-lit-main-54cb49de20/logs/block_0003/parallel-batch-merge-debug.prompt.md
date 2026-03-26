You are debugging a failed DAG execution node, a merged parallel batch, or an unresolved parallel cherry-pick conflict inside the managed repository at C:\Users\alber\OneDrive\문서\GitHub\lit.
Follow any AGENTS.md rules in the repository.
Treat the saved execution plan as the current scope boundary unless the user explicitly updates it.
You are repairing work that already failed verification after execution.
Managed planning documents live outside the repo at C:\Users\alber\OneDrive\문서\GitHub\codex_auto\None\projects\c-users-alber-onedrive-github-lit-main-54cb49de20\docs.
The verification command that must pass: python -m pytest.

Current task:
- Title: Recover merged parallel batch ST2, ST3
- UI description: Repair merged verification failures for ST2, ST3.
- Success criteria: The verification command `python -m pytest` exits successfully for the merged batch.
- Depends on: ST2, ST3
- Owned paths:
- src/lit/commands/branch.py
- src/lit/commands/checkout.py
- src/lit/branching.py
- src/lit/commands/merge.py
- src/lit/commands/rebase.py
- src/lit/merge_ops.py
- src/lit/rebase_ops.py

Original task instruction:
Inspect the merged batch failure, use the provided verification logs, and repair the implementation so the batch passes without broad refactors or unnecessary test changes.

Candidate rationale:
UI description: Repair merged verification failures for ST2, ST3.. Execution instruction: Inspect the merged batch failure, use the provided verification logs, and repair the implementation so the batch passes without broad refactors or unnecessary test changes.. Dependencies: ST2, ST3. Owned paths: src/lit/commands/branch.py, src/lit/commands/checkout.py, src/lit/branching.py, src/lit/commands/merge.py, src/lit/commands/rebase.py, src/lit/merge_ops.py, src/lit/rebase_ops.py. Verification command: python -m pytest. Success criteria: The verification command `python -m pytest` exits successfully for the merged batch.

Memory context:
Relevant prior memory:
- [summary] block 1: Stabilize Core Repository Spine :: python -m pytest exited with 0
- [success] block 1: Stabilize Core Repository Spine :: Completed block with one search-enabled Codex pass.

Plan snapshot:
# Execution Plan

- Repository: lit
- Working directory: C:\Users\alber\OneDrive\문서\GitHub\lit
- Source: https://github.com/Ahnd6474/lit.git
- Branch: main
- Generated at: 2026-03-26T13:55:13+00:00

## Plan Title
lit local VCS prototype

## User Prompt
You are building a new repository from scratch.

Project name:
lit

Meaning:
local git

High-level goal:
Build lit as a lightweight, fast, local-only Git-like version control and checkpointing tool, plus a simple English website that explains how to use it.

Core product definition:
- lit is a local-only version control / checkpointing tool for a single computer.
- It must work fully offline.
- It must not require any account, login, server, remote repository, sync service, or network access.
- It should feel similar to Git for local workflows.
- It should be lightweight, fast, and practical for everyday local use.
- The project should prioritize a working core over unnecessary complexity.

Primary requirements:
1. Local-only
   - Fully usable on one computer.
   - No online features.
   - No cloud.
   - No remote push/pull/fetch/clone.
   - No account system.
   - No collaboration features.

2. Git-like workflow
   - The basic usage model should resemble Git.
   - Support core local versioning flows and a limited but real branch/merge/rebase workflow.

3. Lightweight and fast
   - Keep the implementation lean.
   - Prefer standard library and small dependencies unless a dependency clearly improves the core system.
   - Avoid heavy frameworks, database servers, background daemons, and overengineered abstractions.
   - Optimize for quick local usage on small to medium repositories.

Product scope:
Implement lit as a CLI-first tool with a clean, minimal internal design and a simple, deterministic on-disk repository format.

Required commands and capabilities:
- init
- add
- commit
- log
- status
- diff
- restore or checkout
- branch
- merge
- rebase

Required behavior:
- initialize a repository in any local folder
- stage one or more files
- create commits/checkpoints with messages
- inspect commit history
- inspect working tree status, including:
  - staged
  - modified
  - deleted
  - untracked
- compare working tree against the last committed state
- restore or check out previous local commits
- support nested directories
- handle file additions, modifications, and deletions
- create and switch branches
- merge branches locally
- rebase one branch onto another locally

Design expectations:
- CLI first
- clean and understandable code
- deterministic local storage format
- minimal but real implementation, not a fake mockup
- simplified Git-like internals are acceptable, but the workflows must actually work
- keep naming and behavior consistent across the codebase
- prefer completion and correctness over ambitious architecture

Merge and rebase expectations:
- These features should be real, not placeholders.
- They may be simplified compared to full Git, but they must work for ordinary local cases.
- Handle at least basic conflict scenarios in a clear and predictable way.
- If conflict handling is simplified, document the supported behavior clearly.

Website requirement:
Also create a simple English website that explains how to use lit.

Website goals:
- Explain lit in simple English.
- Assume the reader may be a beginner.
- Clearly explain that lit is local-only and offline-only.
- Show the main commands and example workflows.
- Explain how lit is similar to Git and how it is different.
- Explain current limitations honestly.

Website content should include:
- what lit is
- why someone would use it
- installation / local setup
- quick start
- command overview
- example workflow:
  - init
  - add
  - commit
  - branch
  - merge
  - rebase
  - restore/checkout
- local-only / offline-only design
- limitations and non-goals

Website implementation expectations:
- keep it simple
- make it easy to run locally
- do not build an unnecessarily heavy website stack
- prioritize clarity o...

Mid-term plan:
# Mid-Term Plan

This plan is the user-reviewed execution sequence for the current local project.

- [ ] MT1 -> ST1: Stabilize Core Repository Spine
- [ ] MT2 -> ST2: Finish Branch and Checkout Workflows
- [ ] MT3 -> ST3: Implement Merge and Rebase Engine
- [ ] MT4 -> ST4: Cover Core Workflows with CLI Tests
- [ ] MT5 -> ST5: Publish README and Static Website

Scope guard:
# Scope Guard

- Repository URL: https://github.com/Ahnd6474/lit.git
- Branch: main
- Project slug: c-users-alber-onedrive-github-lit-main-54cb49de20

## Rules

1. Treat the saved project plan and reviewed execution steps as the current scope boundary unless the user explicitly changes them.
2. Mid-term planning must stay a strict subset of the saved plan.
3. Prefer small, reversible, test-backed changes.
4. Do not widen product scope automatically.
5. Only update README or docs to reflect verified repository state, and reserve README.md edits for planning-time alignment or the final closeout pass.
6. Roll back to the current safe revision when validation regresses.

Research notes:
# Research Notes

- 2026-03-26: Core repository spine now exposes deterministic branch refs, commit metadata, DAG helpers (`merge_base`, `is_ancestor`, first-parent replay planning), and explicit merge/rebase state snapshots so later command nodes can build branch/merge/rebase behavior without reopening `.lit` storage details.

Failing execution context:
- Failed pass: parallel-batch-merge
- Verification summary: git cherry-pick 9b96d5c147157e4ecc2406e71d52336d1da21cbe conflicted on tests/test_bootstrap.py

Failing test stdout:
Auto-merging tests/test_bootstrap.py
CONFLICT (content): Merge conflict in tests/test_bootstrap.py

Failing test stderr:
error: could not apply 9b96d5c... jakal-flow(block 1 block-search-pass): Implement Merge and Rebase Engine
hint: After resolving the conflicts, mark them with
hint: "git add/rm <pathspec>", then run
hint: "git cherry-pick --continue".
hint: You can instead skip this commit with "git cherry-pick --skip".
hint: To abort and get back to the state before "git cherry-pick",
hint: run "git cherry-pick --abort".
hint: Disable this message with "git config set advice.mergeConflict false"

Additional user instructions:
None.

Required debugging workflow:
1. Inspect the relevant implementation files and the failing test logs before editing anything.
2. Diagnose the concrete root cause of the verification failure or merge conflict from the logs and merged code state.
3. Fix the implementation or conflict resolution with the smallest safe change set that satisfies the original task and success criteria.
4. Re-run the verification command and leave the repository in a passing state or a cleanly continuable cherry-pick state.
5. Do not edit README.md during debugger recovery. Reserve README updates for planning artifacts outside the repo or the final closeout pass unless the user explicitly says otherwise.
6. Record concise debugging notes in C:\Users\alber\OneDrive\문서\GitHub\codex_auto\None\projects\c-users-alber-onedrive-github-lit-main-54cb49de20\docs\RESEARCH_NOTES.md when they materially improve traceability.
7. If the failure cannot be resolved safely, explain the blocker in docs/BLOCK_REVIEW.md instead of making speculative edits.

Debugger rules:
- Treat the owned paths above as the primary write scope for this repair.
- Prefer fixing compatibility or integration issues in product code before touching tests.
- If the failure is a cherry-pick conflict, resolve the final merged code intentionally instead of blindly taking one side.
- Do not modify tests unless they are objectively incorrect, stale relative to the verified intended behavior, or missing a minimal required fixture.
- If a test change is truly necessary, keep it minimal, executable, and explain why in C:\Users\alber\OneDrive\문서\GitHub\codex_auto\None\projects\c-users-alber-onedrive-github-lit-main-54cb49de20\docs\RESEARCH_NOTES.md.
- Avoid broad cross-node refactors or ownership-breaking changes unless a tiny compatibility patch is strictly required to make the verified batch coherent.
- Keep the change set merge-friendly, traceable, and limited to the failing task or merged batch.
- Leave repository-wide handoff docs like README.md alone during debugger recovery.
