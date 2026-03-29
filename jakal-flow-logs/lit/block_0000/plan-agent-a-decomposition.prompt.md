/fast

You are Planner Agent A for the local project at C:\Users\ahnd6\OneDrive\문서\GitHub\lit.
Follow any AGENTS.md rules in the repository.

Your job is not to emit the final execution DAG yet.
First, produce a machine-readable decomposition artifact that Planner Agent B will later convert into the final execution plan.

Requested execution mode:
parallel

Workflow mode:
standard

Required planning workflow:
1. Decompose the request into the smallest meaningful implementation ideas.
2. Identify any shared contracts, schemas, interfaces, entrypoints, or file skeletons that are genuinely missing or that must be tightened in existing code before broad fan-out work starts.
3. Decide whether a narrow skeleton/bootstrap step is needed. Only recommend one if it reduces downstream merge risk or unlocks safe parallel waves, and shrink or omit it when the relevant implementation already exists.
4. Group the implementation ideas into candidate testable blocks. Each candidate block must represent one locally judgeable outcome that Codex can realistically finish in one focused pass.
5. Mark likely parallel tracks and call out any broad shared roots that should be avoided.
6. Leave final task ids, final DAG edges, final owned_paths, and final reasoning effort choices to Planner Agent B.

Parallel decomposition rules:
- Plan toward a finished, handoff-quality result instead of a narrow MVP slice.
- Prefer candidate blocks with narrow ownership boundaries.
- Prefer exact files or leaf directories over broad package roots.
- If a small contract-freezing or skeleton step can unlock a wide safe fan-out, recommend it explicitly.
- If the source inventory already shows relevant implementation, prefer editing or extending that code and avoid scaffold-only bootstrap work.
- Do not fake parallelism for risky, same-file, or shared-contract heavy work.

Return exactly one JSON object in this shape:
{
  "title": "short project name",
  "strategy_summary": "short paragraph",
  "shared_contracts": ["shared contract or interface decisions to freeze early"],
  "skeleton_step": {
    "block_id": "SK1",
    "needed": true,
    "task_title": "short skeleton/bootstrap title",
    "purpose": "why this small step helps later execution",
    "contract_docstring": "docstring text that should be written into the skeleton code to lock the contract and boundaries",
    "candidate_owned_paths": ["narrow repo-relative files or directories"],
    "success_criteria": "what makes the skeleton good enough"
  },
  "candidate_blocks": [
    {
      "block_id": "B1",
      "goal": "one clear outcome",
      "work_items": ["small implementation ideas inside this block"],
      "implementation_notes": "2-5 sentence planning note describing intended interfaces, constraints, and implementation shape",
      "testable_boundary": "local completion condition",
      "candidate_owned_paths": ["narrow repo-relative files or directories"],
      "parallelizable_after": ["block ids or contract names that must exist first"],
      "parallel_notes": "why this could or could not be parallel later"
    }
  ],
  "packing_notes": [
    "notes for Planner Agent B about wave formation, ownership width, or ordering"
  ]
}

If no skeleton/bootstrap step is needed, keep `skeleton_step.needed` false and leave the other fields empty.
Do not include markdown fences or commentary outside the JSON.

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

## Desktop GUI MVP

After `python -m pip install -e .`, launch the desktop app with either command:

```bash
lit-gui
# or
python -m lit_gui.app
```

Local GUI smoke test:

1. Open or initialize a folder from Home.
2. Use Changes to stage files and create a commit.
3. Use History to inspect commit metadata and per-file diffs.
4. Use Branches to create a branch, checkout another branch or commit, restore a path, and start a merge or rebas...

AGENTS:
AGENTS.md not found.

Reference notes (src/jakal_flow/docs/REFERENCE_GUIDE.md):
# Reference Guide

Use this document when the user prompt leaves implementation details unspecified and the repository needs a default direction.

The user prompt always takes priority.
If this guide conflicts with the user prompt, follow the prompt instead.
This guide defines baseline implementation principles. It is not an expansion-ideas document.

## 1. Roles and Priority

- Use this guide to fill in missing implementation detail when the prompt does not specify it.
- Treat the user prompt as the highest-priority instruction.
- Do not follow this guide when it conflicts with the prompt.
- Use this guide as a default implementation standard, not as a source of speculative feature ideas.

## 2. Delivery Standards

- Aim for a finished, handoff-quality result within the requested scope, not the narrowest possible MVP slice.
- Even a small delivery should be runnable, maintainable, and extensible.
- Prefer the smallest sustainable implementation over the fastest possible shortcut.
- Do not make obviously disposable structure the default choice.

## 3. Technology Selection

- When the stack is not specified, choose based on a balance of simplicity, maintainability, and extensibility.
- Respect the existing stack, but do not use stack consistency alone to justify a poor-quality decision.
- Add new tools or dependencies only when they provide a clear practical benefit.
- Do not choose an approach only because it is the easiest thing to implement immediately.
- If a well-known algorithm, data structure, or engineering technique already fits the problem, use it proactively instead of inventing an ad hoc approach.
- Prefer established named approaches when they improve correctness, explainability, or maintainability.
- For this repository, prefer the existing `React + Tauri + JavaScript` desktop path and keep the Python UI bridge unless there is a strong reason to change it.

## 4. UI and User Experience

- Choose user-facing UI approaches with maintainability and future extension in mind.
- Do not default to temporary low-level GUI approaches when a more durable structure already exists.
- Keep UI code separate from domain logic.
- Maintain at least basic consiste...

Docs:
## docs\gui-architecture.md
# GUI Architecture

`lit_gui` is a thin PySide6 desktop shell over the existing local-only `lit` backend.

## Run Locally

From the repository root:

```bash
python -m pip install -e .
lit-gui
```

You can also launch the same app with:

```bash
python -m lit_gui.app
```

Run the verified test suite with:

```bash
python -m pytest
```

## Shell Layout

- Left sidebar: repository identity, current branch, repository status, and high-attention workflow state.
- Center view: Home, Changes, History, Branches, and Files.
- Right detail panel: selected item details, metadata, and action guidance...

Source inventory:
Existing implementation files detected. Prefer extending or editing these paths instead of adding scaffold-only skeleton steps unless a genuinely new boundary is required: src/lit/cli.py, src/lit/commits.py, src/lit/index.py, src/lit/merge_ops.py, src/lit/rebase_ops.py, src/lit/refs.py, src/lit/repository.py, src/lit/state.py, src/lit/storage.py, src/lit/trees.py, src/lit/working_tree.py, src/lit/__init__.py, plus 40 more.

User request:
You are working in the lit repository.

Mission:
Ship lit as a release-grade v1 product for autonomous local coding workflows and as the intended future repository backend for Jakal Flow.

This is not a prototype, foundation slice, or intermediate milestone task.
Do not optimize for partial progress.
Deliver a cohesive end-to-end product.

Product identity:
- lit is not a “local Git clone.”
- lit is a local execution VCS for long-running autonomous coding workflows on one machine.
- Its core promises are:
  1) human-controlled autonomy
  2) complete rollback
  3) structured multi-agent provenance
  4) safe validated checkpoints
  5) parallel lineage isolation and promotion
  6) local-first artifact and state management
  7) installable CLI and desktop UI
- Git-like commands may remain for familiarity, but Git parity is not the goal.

Primary user:
- The primary user is Jakal Flow operating on a local machine for long tasks.
- The system must support agent roles such as planner, executor, debugger, merge resolver, optimizer, closeout, and scheduler-supervised parallel workers.
- Human review and override must remain possible at plan, checkpoint, and promotion boundaries.

End-state requirement:
Build the complete v1, not a stepping stone.
At the end of this task, lit must feel like a real standalone product and a credible future backend for Jakal Flow with minimal conceptual mismatch.

Required product capabilities:

1. Repository engine
- Preserve and harden the content-addressed storage model.
- Keep snapshots fast, deduplicated, and cheap on local disks.
- Support ordinary commits plus first-class safe checkpoints.
- Support atomic rollback to the latest safe checkpoint or a selected safe checkpoint.
- Add crash-safe journaling for multi-step operations.
- Add repository locking for concurrent local operations.

2. Structured provenance
- Replace minimal authorship with structured provenance stored in the commit/checkpoint model and exposed throughout the product.
- Every commit/checkpoint must be able to record:
  - actor_role
  - actor_id
  - prompt_template or agent_family
  - run_id
  - block_id
  - step_id
  - lineage_id
  - verification_status
  - verification_summary
  - committed_at
  - origin_commit
  - rewritten_from
  - promoted_from
- Metadata must survive merge, rebase, lineage promotion, rollback bookkeeping, export, and history display.
- Backward compatibility with older commits lacking these fields is mandatory.

3. Safe checkpoint system
- Safe checkpoints must be first-class objects or refs, not a CLI-only label.
- Support:
  - mark checkpoint safe
  - list safe checkpoints
  - inspect checkpoint details
  - show latest safe checkpoint
  - rollback to latest safe checkpoint
  - rollback to selected safe checkpoint
  - pin / unpin safe checkpoints
  - optional checkpoint approval state / note
- Safe checkpoints must be visible in both CLI and desktop UI.
- A safe checkpoint is the canonical last-known-good state.

4. Verification-aware workflow
- Implement a real verification result model.
- Support repository-configured verification commands and per-checkpoint/commit verification recording.
- Store verification results using:
  - state fingerprint
  - environment fingerprint
  - command identity
  - timestamps
  - return code
  - output references
- Implement local verification cache replay.
- Support statuses such as:
  - never_verified
  - passed
  - failed
  - cached_pass
  - cached_fail
  - stale
- Safe checkpoint promotion must be verification-aware by design.

5. Lineage and parallel work isolation
- Add first-class lineage support for parallel agent work.
- A lineage must track:
  - lineage_id
  - base checkpoint
  - current head
  - owned paths
  - status
  - promoted/discarded state
  - created_at / updated_at
- Support:
  - create lineage
  - list lineage
  - inspect lineage
  - switch lineage
  - promote lineage
  - discard lineage
  - preview conflicts before promotion
- Prevent unsafe overlapping work by default using owned-path reservation or an equivalent explicit rule.
- Branch semantics may remain as a compatibility layer, but lineage is the real product center.

6. Local artifact store
- Implement a lit-native local artifact store as the answer to large files and run artifacts.
- Do not optimize for Git LFS protocol compatibility first.
- Support:
  - content-addressed deduplicated artifact storage
  - large artifact references
  - pinning
  - quota / size reporting
  - resumable writes
  - garbage collection
  - clear linkage from artifacts to commits/checkpoints/lineages when relevant
- Use a configurable global storage home, defaulting to a lithub-style directory under the user home, while still allowing repositories to live anywhere on disk.

7. CLI
- Keep the CLI coherent and production-usable.
- Preserve familiar commands where reasonable, but make the real product surface task-oriented:
  - init
  - add
  - commit
  - status
  - diff
  - restore
  - log / history
  - checkpoint ...
  - rollback ...
  - verify ...
  - lineage ...
  - artifact ...
  - gc
  - doctor
  - export git
- Support both human-readable output and structured JSON output where appropriate.
- Avoid noisy defaults, but make detailed inspection available.

8. Desktop UI
- Treat the desktop UI as a real product surface, not a demo.
- Extend it to support:
  - safe checkpoint timeline
  - provenance inspection
  - verification results and cache hits
  - lineage creation / review / promotion
  - conflict review
  - rollback actions
  - artifact usage / storage inspection
  - repository health / doctor views
- The UI must reflect real repository state and use the same backend logic as the CLI.

9. Packaging and installation
- Make lit easy to install and run from PATH.
- Keep CLI/core usage lightweight.
- Ensure GUI dependencies can be optional if that improves headless CLI usage.
- Make desktop packaging practical and documented.
- Clean installation on supported platforms matters.

10. Performance and resilience
- Optimize for low-end local machines.
- Avoid unnecessary full-tree rewrites.
- Prefer atomic file operations and local recoverability over clever but fragile behavior.
- Interrupted operations must be recoverable or safely abortable.
- Add performance smoke tests or simple benchmarks for common workflows:
  - repeated checkpointing
  - rollback
  - lineage creation/promotion
  - verification cache hits

11. Git interoperability
- Do not chase full Git on-disk compatibility.
- Provide pragmatic interoperability where useful.
- At minimum:
  - export a current lineage or safe checkpoint into a Git-compatible representation
  - preserve provenance via trailers, notes, or another explicit mapping
  - document limitations honestly
- This is an interoperability bridge, not the product core.

12. Jakal Flow backend readiness
- Design lit so it can credibly replace the subset of Git functionality Jakal Flow currently relies on.
- Provide a narrow backend interface or adapter layer that supports:
  - current revision lookup
  - changed file listing
  - commit with structured actor identity
  - safe checkpoint lookup
  - safe rollback
  - lineage creation/promotion/discard
  - conflict preview / resolution helpers
  - verification status lookup
  - artifact linkage
- You do not need to modify the Jakal Flow repository in this task, but the resulting lit API and docs must make the intended integration path obvious and realistic.

Architecture expectations:
- Inspect the whole repository before coding.
- Identify every path that creates, rewrites, merges, rebases, restores, logs, exports, or rolls back commits/checkpoints.
- Refactor aggressively where needed.
- Do not bolt product-level concepts onto a Git-shaped prototype in a shallow way.
- Preserve backward compatibility for existing lit repositories through migration or tolerant parsing.
- Keep the on-disk format explicit, inspectable, and debuggable.

What not to do:
- Do not stop after a “foundation” layer.
- Do not submit a thin metadata patch with no real workflow changes.
- Do not keep the README/product language centered on “local git.”
- Do not prioritize remotes, network sync, or team collaboration.
- Do not fake product features in CLI messaging while the repository/domain model stays incomplete.
- Do not leave UI, docs, or tests behind the engine work.

Required deliverables:
- Repository core changes
- CLI changes
- Desktop UI changes
- Packaging / install improvements
- Migration / backward compatibility handling
- End-to-end tests and targeted unit tests
- Updated README and command help
- A concrete design/product document describing:
  - lit’s new identity
  - ordinary commit vs safe checkpoint
  - provenance model
  - verification/cache model
  - lineage model
  - artifact store
  - Git interoperability boundary
  - Jakal Flow backend interface
- A short release / upgrade note for existing lit users

Definition of done:
The task is done only when all of the following are true:

- A user can initialize a repository and use lit as a stable local versioning tool.
- A user can create commits with rich provenance.
- A user can mark, inspect, pin, and roll back safe checkpoints.
- A user can run verification, reuse cached verification results, and inspect those results clearly.
- A user can create isolated lineages for parallel work and promote or discard them.
- A user can inspect and manage stored artifacts.
- A user can use both CLI and desktop UI for the core workflows.
- Older lit repositories still open and function.
- Documentation reflects the new product honestly.
- Tests cover the new core behavior.
- The final result feels like a coherent v1 release, not an internal intermediate milestone.

Execution approach:
- Audit the current engine, object model, refs/state handling, CLI surface, UI surface, and storage layout first.
- Write a brief implementation plan inside the repo before major refactors.
- Then implement the full product end-to-end.
- When tradeoffs are necessary, prefer correctness, rollback safety, crash recovery, and Jakal Flow alignment over Git familiarity.

Final instruction:
Ship a cohesive, release-grade lit v1 for autonomous local coding workflows.
Do not optimize for a halfway result.

Scope control:
Do not re-scope this task into a narrow slice.
If the full target requires broad refactoring across engine, CLI, UI, docs, tests, and packaging, do that.
Avoid placeholder abstractions, TODO-heavy scaffolding, or “future work” deferrals for core product requirements.
Prefer fewer but fully vertical, shippable workflows over many half-built concepts, but the following verticals are mandatory and must all land in working form:
- safe checkpoints and rollback
- structured provenance
- verification and cache replay
- lineage isolation and promotion
- local artifact store
- CLI and desktop coverage
- installability
- documentation
- tests
