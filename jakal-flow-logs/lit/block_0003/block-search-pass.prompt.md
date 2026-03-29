/fast

You are working inside the managed repository at C:\Users\ahnd6\OneDrive\문서\GitHub\lit.
Follow any AGENTS.md rules in the repository.
Treat the saved execution plan as the current scope boundary unless the user explicitly updates it.
You are executing one node of a saved DAG execution tree.
Do not expand scope beyond the active task, dependency boundary, and scope guard.
Managed planning documents live outside the repo at C:\Users\ahnd6\.jakal-flow-workspace\projects\c-users-ahnd6-onedrive-github-lit-main-679f7c0bcc\docs.
Verification command for this step: python -m pytest.

Current task:
- Title: Deliver Entry And Browsing Surfaces
- UI description: Add repository open/init flow, recent repositories, and the Files browser.
- Success criteria: From a fresh launch, the app shows clear empty and invalid-folder states, can open or initialize a `lit` repository, remembers recent repository paths without writing into user repos, and the Files view browses the repository tree with useful preview behavior for selected files.
- Depends on: ST2
- Owned paths:
- src/lit_gui/views/home
- src/lit_gui/views/files
- src/lit_gui/persistence
- tests/gui/views/test_home_files.py

Codex execution instruction:
Implement the real Home surface and repository entry flow: open an existing folder, initialize a new repo, explain non-repository folders with an init path, persist recent repositories in app data outside working trees, and build the Files view with a simple repository tree and readable file preview so users can enter and orient themselves in a repo through the fixed shell.

Memory context:
Relevant prior memory:
- [success] block 2: Build Session Adapter :: Completed block with one search-enabled Codex pass.
- [success] block 1: Freeze GUI Skeleton :: Completed block with one search-enabled Codex pass.

Plan snapshot:
# Execution Plan

- Repository: lit
- Working directory: C:\Users\ahnd6\OneDrive\문서\GitHub\lit
- Source: https://github.com/Ahnd6474/lit.git
- Branch: main
- Generated at: 2026-03-27T02:13:49+00:00

## Plan Title
lit desktop gui mvp

## User Prompt
You are working in the repository at {repo_dir}.

Follow any AGENTS.md rules in the repository.

This is a 3-5 day implementation task for a strong, runnable desktop GUI milestone.
Optimize for a real, usable prototype with clean architecture, not for maximum feature count.
Do not bloat the scope. Deliver a polished, coherent MVP that feels intentionally designed.

Project identity and hard constraints
- This project is `lit` = "local git".
- `lit` is intentionally local-only and offline-only.
- Do not add or imply any remote/network/collaboration features.
- Absolutely do not implement or simulate:
  - push / pull / fetch / clone
  - hosted remotes
  - login / account / sync / cloud backup
  - pull requests / issues / discussions / code review comments from a server
  - team collaboration workflows
- The GUI may borrow the usability patterns of GitHub Web and GitHub Desktop, but only for local repository workflows.
- The GUI must be honest about what the product is: a local-only Git-like version control app for one computer.

Current product capabilities to respect
Build the GUI around the repository’s existing local workflows rather than inventing unsupported backend behavior:
- init
- add
- commit
- log
- status
- diff
- restore
- checkout
- branch
- merge
- rebase

Product goal
Create a desktop GUI for `lit` that combines:
1. the repository browsing clarity and commit-history readability of GitHub Web
2. the local workflow friendliness and approachable desktop UX of GitHub Desktop

Target user experience
The result should feel like:
- a lightweight local repository manager
- easy enough for ordinary developers to understand without reading many docs
- visually structured like a serious developer tool, not a toy
- fast to use for everyday local checkpointing, branching, diff inspection, restore, merge, and rebase
- clearly local-first and single-machine oriented

Primary UX concept
Design the GUI around a 3-pane desktop workflow:
- Left sidebar:
  - repository/home navigation
  - current branch
  - branch list
  - history / changes / workspace sections
- Center main area:
  - default switches between Changes, History, Branches, and Repository/Files views
- Right detail panel:
  - selected file diff
  - selected commit metadata
  - selected branch details
  - merge/rebase state and action guidance

Main views to implement
Implement these views as the core of the milestone:

1. Repository/Home screen
- Open an existing folder as a lit repository
- Initialize a new lit repository in a chosen folder
- Show recent repositories
- Show friendly empty states
- If folder is not a lit repo, explain how to initialize it

2. Changes view
- Show staged, modified, deleted, and untracked files
- Allow selecting files to inspect diffs
- Allow staging relevant files or groups using the backend capabilities that exist
- Provide commit message input and commit action
- Disable commit when not valid
- Surface clear error messages
- Make this the default view for active repositories

3. History view
- Show commit history in a readable timeline/list
- Selecting a commit should show:
  - commit id
  - message
  - parent/basic metadata that exists
  - changed files
- Allow viewing per-file diff for a selected commit if practical with existing backend support
- Emphasize readability and navigation over advanced filtering

4. Branches view
- Show current branch clearly
- Show branch list
- Allow creating a branch
- Allow checkout to another branch or commit if supported
- Make branch switching safe and explicit
- Warn clearly when checkout is blocked by repository state

5. Repository/Files view
- Provide a simple local file tree / repository browser
- Selecting a file shows contents or a helpful previ...

Mid-term plan:
# Mid-Term Plan

This block follows the user-reviewed execution step.

- [ ] MT1 -> ST3: Deliver Entry And Browsing Surfaces

Scope guard:
# Scope Guard

- Repository URL: https://github.com/Ahnd6474/lit.git
- Branch: main
- Project slug: c-users-ahnd6-onedrive-github-lit-main-679f7c0bcc

## Rules

1. Treat the saved project plan and reviewed execution steps as the current scope boundary unless the user explicitly changes them.
2. Mid-term planning must stay a strict subset of the saved plan.
3. Prefer small, reversible, test-backed changes.
4. Do not widen product scope automatically.
5. Only update README or docs to reflect verified repository state, and reserve README.md edits for planning-time alignment or the final closeout pass.
6. Roll back to the current safe revision when validation regresses.

Research notes:
# Research Notes

- 2026-03-27: Freeze GUI Skeleton keeps all writes inside `pyproject.toml`, `src/lit_gui`, and a focused GUI bootstrap test file.
- 2026-03-27: Local verification environment does not have `PySide6` installed, so GUI tests install a narrow fake `PySide6` module in-process and verify shell structure, navigation routing, immutable DTOs, and the `lit-gui` entrypoint declaration without widening runtime scope.
- 2026-03-27: Build Session Adapter adds a pure snapshot builder in `src/lit_gui/backend` plus `LitRepositorySession` in `src/lit_gui/session.py`; the session preserves selections across refreshes when possible, funnels success/error messages into detail guidance, and backend tests now cover unborn, clean, dirty, merge-conflict, and rebase-conflict repository states with `python -m pytest`.

Additional user instructions:
None.

Required workflow:
1. Inspect the relevant project files first so function names, module boundaries, and terminology stay consistent with the codebase.
2. Determine the smallest safe change set that satisfies the task instruction and success criteria.
3. Add or update executable tests that locally verify the task.
4. Implement the task in code.
5. Run the verification command and keep docs aligned only with verified behavior.
6. Do not edit README.md during normal execution steps. Reserve README updates for planning artifacts outside the repo or the final closeout pass unless the user explicitly says otherwise.
7. Record concise research or implementation notes in C:\Users\ahnd6\.jakal-flow-workspace\projects\c-users-ahnd6-onedrive-github-lit-main-679f7c0bcc\docs\RESEARCH_NOTES.md when they materially help traceability.
8. If the task cannot be completed safely in one pass, explain why in docs/BLOCK_REVIEW.md instead of making speculative edits.

Execution rules:
- Treat the owned paths above as the primary write scope for this node.
- Avoid editing files that are primarily owned by other pending nodes unless a tiny compatibility adjustment is strictly required.
- Do not assume sibling nodes have already landed.
- If the task would require a broad cross-node refactor, stop and document the blocker instead of making merge-sensitive edits.
- Keep the change set merge-friendly, traceable, and limited.
- Leave repository-wide handoff docs like README.md alone during step execution.
- Use web search only when directly necessary for official documentation or narrowly scoped factual verification.
