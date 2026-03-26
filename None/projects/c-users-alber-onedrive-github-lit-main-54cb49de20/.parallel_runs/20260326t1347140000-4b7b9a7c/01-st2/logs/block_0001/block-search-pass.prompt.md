You are working inside the managed repository at C:\Users\alber\OneDrive\문서\GitHub\codex_auto\None\projects\c-users-alber-onedrive-github-lit-main-54cb49de20\.parallel_runs\20260326t1347140000-4b7b9a7c\01-st2\repo.
Follow any AGENTS.md rules in the repository.
Treat the saved execution plan as the current scope boundary unless the user explicitly updates it.
Do not expand scope beyond the active task and scope guard.
Managed planning documents live outside the repo at C:\Users\alber\OneDrive\문서\GitHub\codex_auto\None\projects\c-users-alber-onedrive-github-lit-main-54cb49de20\.parallel_runs\20260326t1347140000-4b7b9a7c\01-st2\docs.
Verification command for this step: python -m pytest.

Current task:
- Title: Finish Branch and Checkout Workflows
- UI description: Implement local branch creation, switching, and revision navigation.
- Success criteria: Users can create branches, inspect them, switch between branches or commits, and restore tracked content while keeping repository metadata and working-tree state internally consistent.
- Depends on: ST1
- Owned paths:
- src/lit/commands/branch.py
- src/lit/commands/checkout.py
- src/lit/branching.py

Codex execution instruction:
Using the shared repository APIs, implement real `branch`, `checkout`, and related `restore` navigation behavior for ordinary local cases: create and inspect branches, switch HEAD safely, apply commit trees to the working directory, keep nested paths correct, and make the command behavior and help text consistent with the supported local workflow.

Memory context:
Relevant prior memory:
- [success] block 1: Stabilize Core Repository Spine :: Completed block with one search-enabled Codex pass.

Plan snapshot:
# Execution Plan

- Repository: lit
- Working directory: C:\Users\alber\OneDrive\문서\GitHub\lit
- Source: https://github.com/Ahnd6474/lit.git
- Branch: main
- Generated at: 2026-03-26T13:47:14+00:00

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

This block follows the user-reviewed execution step.

- [ ] MT1 -> ST2: Finish Branch and Checkout Workflows

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

Additional user instructions:
None.

Required workflow:
1. Inspect the relevant project files first so function names, module boundaries, and terminology stay consistent with the codebase.
2. Determine the smallest safe change set that satisfies the task instruction and success criteria.
3. Add or update executable tests that locally verify the task.
4. Implement the task in code.
5. Run the verification command and keep docs aligned only with verified behavior.
6. Do not edit README.md during normal execution steps. Reserve README updates for planning artifacts outside the repo or the final closeout pass unless the user explicitly says otherwise.
7. Record concise research or implementation notes in C:\Users\alber\OneDrive\문서\GitHub\codex_auto\None\projects\c-users-alber-onedrive-github-lit-main-54cb49de20\.parallel_runs\20260326t1347140000-4b7b9a7c\01-st2\docs\RESEARCH_NOTES.md when they materially help traceability.
8. If the task cannot be completed safely in one pass, explain why in docs/BLOCK_REVIEW.md instead of making speculative edits.

Execution rules:
- Focus on one sequential checkpoint.
- Use a single focused pass to inspect, write tests, implement, and verify.
- Prefer direct, repository-consistent naming over new abstractions.
- Keep changes traceable and limited.
- Leave repository-wide handoff docs like README.md alone during step execution.
- Use web search only when directly necessary for official documentation or narrowly scoped factual verification.
