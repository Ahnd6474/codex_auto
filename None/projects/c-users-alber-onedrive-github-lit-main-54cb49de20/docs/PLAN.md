# Execution Plan

- Repository: lit
- Working directory: C:\Users\alber\OneDrive\문서\GitHub\lit
- Source: https://github.com/Ahnd6474/lit.git
- Branch: main
- Generated at: 2026-03-26T13:25:53+00:00

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

## Execution Summary
First stabilize the shared `.lit` repository model and command architecture so later work can land without merge-heavy refactors. Then split the feature build into two parallel tracks: one for branch and checkout-style navigation, and one for merge/rebase plus conflict handling. After those converge, finish the prototype with integration-style CLI tests and, in parallel, publish a concise README and a simple static English website that explains the tool and its limits.

## Workflow Mode
standard

## Execution Mode
parallel

## Planned Steps
- ST1: Stabilize Core Repository Spine
  - UI description: Create the shared storage, history, and command-module foundation.
  - Codex instruction: Refactor the current Python skeleton into the smallest sustainable architecture for `lit`: preserve the deterministic `.lit` on-disk layout, add commit metadata and DAG traversal helpers needed by branch/merge/rebase, expose reusable repository primitives for applying trees and tracking in-progress operations, and split CLI dispatch so later commands can live in isolated modules instead of reserved placeholders.
  - GPT reasoning: high
  - Parallel group: none
  - Depends on: none
  - Owned paths: src/lit/cli.py, src/lit/repository.py, src/lit/commits.py, src/lit/refs.py, src/lit/state.py, src/lit/commands
  - Verification: python -m pytest
  - Success criteria: The codebase has reusable repository APIs that can represent commit ancestry, branch refs, and merge/rebase operation state deterministically, and the CLI entrypoint is structured to load real command modules rather than pending stubs.
- ST2: Finish Branch and Checkout Workflows
  - UI description: Implement local branch creation, switching, and revision navigation.
  - Codex instruction: Using the shared repository APIs, implement real `branch`, `checkout`, and related `restore` navigation behavior for ordinary local cases: create and inspect branches, switch HEAD safely, apply commit trees to the working directory, keep nested paths correct, and make the command behavior and help text consistent with the supported local workflow.
  - GPT reasoning: high
  - Parallel group: none
  - Depends on: ST1
  - Owned paths: src/lit/commands/branch.py, src/lit/commands/checkout.py, src/lit/branching.py
  - Verification: python -m pytest
  - Success criteria: Users can create branches, inspect them, switch between branches or commits, and restore tracked content while keeping repository metadata and working-tree state internally consistent.
- ST3: Implement Merge and Rebase Engine
  - UI description: Add real local merge and rebase with predictable conflict handling.
  - Codex instruction: Implement simplified but real local `merge` and `rebase` flows on top of the shared commit graph: compute merge bases, apply tree changes, write merge commits or rewritten commits, persist operation state when conflicts occur, and make conflict behavior explicit and deterministic for ordinary text-file cases instead of leaving placeholders.
  - GPT reasoning: high
  - Parallel group: none
  - Depends on: ST1
  - Owned paths: src/lit/commands/merge.py, src/lit/commands/rebase.py, src/lit/merge_ops.py, src/lit/rebase_ops.py
  - Verification: python -m pytest
  - Success criteria: Local branches can be merged and rebased for normal cases, and at least one basic conflict path produces clear conflict state and user-visible results instead of silent failure or unimplemented output.
- ST4: Cover Core Workflows with CLI Tests
  - UI description: Add integration-style tests for the required command behavior.
  - Codex instruction: Expand the test suite around real CLI workflows, favoring end-to-end repository scenarios over superficial output checks: cover init, add/commit, modified and deleted detection, nested directories, restore/checkout correctness, log ordering and commit metadata, diff/status basics, branch creation and switching, merge success, rebase success, and at least one basic conflict scenario.
  - GPT reasoning: high
  - Parallel group: none
  - Depends on: ST2, ST3
  - Owned paths: tests
  - Verification: python -m pytest
  - Success criteria: The repository contains automated tests that locally verify each required workflow end to end, including both normal cases and at least one merge or rebase conflict case.
- ST5: Publish README and Static Website
  - UI description: Document lit with a concise README and simple English local website.
  - Codex instruction: Create a lightweight documentation surface with no heavy site stack: add a concise `README.md` and a simple static English website that explains what `lit` is, why to use it, local/offline-only constraints, installation and setup, quick start, command overview, example workflows, Git similarities and differences, and current limitations honestly.
  - GPT reasoning: medium
  - Parallel group: none
  - Depends on: ST2, ST3
  - Owned paths: README.md, website
  - Verification: python -m pytest
  - Success criteria: A new developer can read the README or open the local website and find accurate English instructions for installing, running, and understanding `lit`, including its supported workflows, local-only design, and non-goals.

## Non-Goals
- Do not skip verification for any planned step.
- Do not widen scope beyond the current prompt unless the user updates the plan.

## Operating Constraints
- Treat each planned step as a checkpoint.
- In parallel mode, only dependency-ready steps with disjoint owned paths may run together.
- Commit and push after a verified step when an origin remote is configured.
- Users may edit only steps that have not started yet.
