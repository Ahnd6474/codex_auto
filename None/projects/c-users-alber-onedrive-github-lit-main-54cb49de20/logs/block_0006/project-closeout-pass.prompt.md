You are performing final closeout for the managed repository at C:\Users\alber\OneDrive\문서\GitHub\lit.
Follow any AGENTS.md rules in the repository.
All planned execution tasks are already marked complete. This pass is for final cleanup and handoff quality only.
Managed planning documents live outside the repo at C:\Users\alber\OneDrive\문서\GitHub\codex_auto\None\projects\c-users-alber-onedrive-github-lit-main-54cb49de20\docs.
Primary verification command: python -m pytest.

Project title:
lit local VCS prototype

Original user request:
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
- prioritize clarity over visual complexity

Non-goals / do not add:
- no remote repository support
- no network sync
- no user accounts
- no hosted service
- no collaboration or multi-user features
- no enterprise architecture
- no unnecessary plugin system
- no large infrastructure dependencies
- no speculative future-proofing abstractions
- no GUI application unless the CLI and website are already complete and working

Implementation guidance:
- Start with the smallest complete architecture that can support the required workflows.
- Before coding, inspect the whole project structure and decide the minimal clean layout.
- Implement core repository storage and commit model first.
- Then implement CLI workflows.
- Then implement branching, merging, and rebasing.
- Then add tests.
- Then add the English documentation website.
- Keep the project runnable and understandable throughout.

Testing requirements:
Add automated tests for at least:
- init
- add + commit flow
- modified file detection
- deleted file detection
- nested directory tracking
- restore/checkout correctness
- log ordering and commit metadata
- diff/status correctness for basic scenarios
- branch creation and switching
- merge basic success cases
- rebase basic success cases
- at least one basic conflict scenario for merge or rebase

Testing style:
- Prefer integration-style CLI tests for the main workflows.
- Add unit tests only where they clearly help core logic.
- Tests should verify real behavior, not just superficial output.

Quality bar:
- Another developer should be able to clone the repo and run it locally with clear instructions.
- Core commands must be covered by tests.
- Behavior should be predictable and maintainable.
- The implementation should remain lightweight.
- Performance should feel reasonable for ordinary local use.
- The README should clearly explain what is implemented and what is not.

Deliverables:
1. A runnable local CLI project for lit
2. Core Git-like local workflows implemented
3. Local branch / merge / rebase support
4. Automated tests for the core flows
5. A concise README
6. A simple English website explaining how to use lit

Important constraints:
- This project is for validating whether an AI coding system can build a nontrivial but achievable local version control tool.
- Prioritize a working, coherent, lightweight implementation over copying every Git feature.
- Bias toward a small, efficient implementation that fully works, rather than a more ambitious design that is incomplete, fragile, or slow.

Execution summary:
First stabilize the shared `.lit` repository model and command architecture so later work can land without merge-heavy refactors. Then split the feature build into two parallel tracks: one for branch and checkout-style navigation, and one for merge/rebase plus conflict handling. After those converge, finish the prototype with integration-style CLI tests and, in parallel, publish a concise README and a simple static English website that explains the tool and its limits.

Completed tasks:
- ST1: Stabilize Core Repository Spine :: The codebase has reusable repository APIs that can represent commit ancestry, branch refs, and merge/rebase operation state deterministically, and the CLI entrypoint is structured to load real command modules rather than pending stubs.
- ST2: Finish Branch and Checkout Workflows :: Users can create branches, inspect them, switch between branches or commits, and restore tracked content while keeping repository metadata and working-tree state internally consistent.
- ST3: Implement Merge and Rebase Engine :: Local branches can be merged and rebased for normal cases, and at least one basic conflict path produces clear conflict state and user-visible results instead of silent failure or unimplemented output.
- ST4: Cover Core Workflows with CLI Tests :: The repository contains automated tests that locally verify each required workflow end to end, including both normal cases and at least one merge or rebase conflict case.
- ST5: Publish README and Static Website :: A new developer can read the README or open the local website and find accurate English instructions for installing, running, and understanding `lit`, including its supported workflows, local-only design, and non-goals.

Repository summary:
README:
# lit

`lit` means "local git." It is a lightweight, local-only version control prototype for one computer.

`lit` is useful when you want Git-like checkpoints without any server, account, remote, or network dependency. It works fully offline and focuses on small, practical local workflows instead of collaboration features.

## What lit Does

- Initializes a repository inside any local folder.
- Stages files and directories with `lit add`.
- Creates local commits with `lit commit -m`.
- Shows local history with `lit log`.
- Reports staged, modified, deleted, and untracked files with `lit status`.
- Shows working tree diffs against the current commit with `lit diff`.
- Restores tracked files from a revision with `lit restore`.
- Switches branches or detaches `HEAD` with `lit checkout`.
- Creates and lists local branches with `lit branch`.
- Merges another local branch or commit with `lit merge`.
- Rebases the current branch onto another local branch or commit with `lit rebase`.

## Local-Only Design

`lit` is intentionally local-only and offline-only.

- No remote repositories
- No `push`, `pull`, `fetch`, or `clone`
- No accounts, login, sync, or cloud service
- No collaboration workflow
- No background daemon or server

If you need multi-machine sync or team collaboration, use Git instead.

## Installation

`lit` targets Python 3.12+.

From the repository root:

```bash
python -m pip install -e .
```

That installs the `lit` console command. During development, you can also run commands as `python -m lit ...` after installation.

## Quick Start

```bash
mkdir demo
cd demo
lit init
printf "hello\n" > note.txt
lit add note.txt
lit commit -m "Create first checkpoint"
lit status
lit log
```

To open the static local website, open `website/index.html` in a browser.

## Command Overview

| Command | Purpose |
| --- | --- |
| `lit init [path]` | Create a `.lit` repository. |
| `lit add <paths...>` | Stage files or directories. |
| `lit commit -m "message"` | Write the...

AGENTS:
AGENTS.md not found.

Docs:
No markdown files under repo/docs.

Additional user instructions:
None.

Required closeout work:
1. Review the full repository and remove obvious dead code, redundant paths, duplicated logic, throwaway scaffolding, or low-value leftovers introduced during implementation when it is safe to do so.
2. Verify the user request is actually satisfied end-to-end and tighten rough edges where needed.
3. Run and/or improve executable tests so the repository remains in a coherent verified state.
4. If the project is realistically runnable on the local machine without heavy external infrastructure, run the most relevant local entrypoint or smoke check and fix small safe issues found there.
5. Remove obviously unnecessary generated or temporary directories left behind by implementation work when they are safe to delete and are not part of the product or test fixtures.
6. Write a concise future-maintainer guide and closeout summary to C:\Users\alber\OneDrive\문서\GitHub\codex_auto\None\projects\c-users-alber-onedrive-github-lit-main-54cb49de20\docs\CLOSEOUT_REPORT.md. Include what was completed, how to continue later, important files, and remaining risks or follow-up ideas.
7. Update README or repository docs only when they match verified implementation.

Execution rules:
- Use one focused closeout pass.
- Prefer small safe cleanup over speculative refactors.
- Do not expand scope into new features.
- If a requested closeout item is not safely feasible, explain that clearly in C:\Users\alber\OneDrive\문서\GitHub\codex_auto\None\projects\c-users-alber-onedrive-github-lit-main-54cb49de20\docs\CLOSEOUT_REPORT.md.
