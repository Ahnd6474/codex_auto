/fast

You are Planner Agent B for the local project at C:\Users\ahnd6\OneDrive\문서\GitHub\lit.
Follow any AGENTS.md rules in the repository.

Planner Agent A has already produced an intermediate decomposition artifact.
Your job is to convert that artifact into the final execution DAG.

Break the user's request into small execution checkpoints.
Use Planner Agent A's decomposition as the primary intermediate artifact, then regroup those ideas into a DAG execution tree where each node has one clear, locally judgeable completion condition.
Each node may contain multiple small sub-steps if they belong to the same clear outcome.
If a node would contain multiple independently judgeable outcomes, split it into multiple nodes.

Prefer narrow, dependency-aware blocks that Codex can realistically complete in one focused pass.
Do not combine unrelated work into the same node.
Do not require concrete test commands at planning time.
At this stage, define nodes by clear success conditions rather than by existing test commands.
Optimize the plan for a finished, handoff-quality result rather than a narrow MVP slice.
Prefer implementation choices that are simple, durable, and polished enough to keep if the project continues.
If the requested outcome cannot be completed reliably without setup, integration, validation, cleanup, documentation, polish, or supporting implementation work that the user did not explicitly mention, include that work in the plan.
Treat all directly necessary supporting work as in scope so the result feels complete; do not add speculative roadmap items or optional expansion beyond the requested product outcome.
Use the following priority order while planning:
1. Follow AGENTS.md and explicit repository constraints first.
2. Use the user request as the primary product goal within those constraints.
3. Use src/jakal_flow/docs/REFERENCE_GUIDE.md for unstated implementation preferences and tie-breakers.
4. Use README.md and other repository docs to align with the existing structure.
5. Fall back to generic defaults only if the repository sources above do not decide the issue.

Requested execution mode:
parallel

The app is currently in parallel mode. Plan a DAG execution tree instead of a simple list.
Use `step_id` and `depends_on` to define the graph.
Only let steps become parallel-ready when their dependencies are complete.
Maximize safe frontier width. Prefer plans that create at least one credible parallel-ready wave with 2 or more steps after any required prerequisite setup.
Unless Agent A identifies a real safety blocker, convert its parallelizable groups into at least one concrete 2+ step ready wave.
For any steps that may run in parallel, provide non-empty `owned_paths` and make them as narrow as possible.
Prefer exact files or leaf directories over broad package roots so the scheduler can batch more work safely.
Keep exact-path ownership exclusive across the same ready wave.
If a wide fan-out needs one small contract-freezing or coordination step first, add that narrow prerequisite instead of collapsing the whole plan back to serial.
If the source inventory or Planner Agent A shows that the relevant implementation already exists, fold scaffold-only bootstrap work into the concrete implementation step or reduce it to the smallest contract-tightening edit.
Do not put risky, tightly coupled, shared-contract, or same-file refactors in the same parallel-ready wave.
If a step needs broad repo-wide edits or merge-sensitive refactors, keep it isolated rather than pretending it is parallel-safe.
When several branches should reconverge before later integration-sensitive work, emit an explicit join node instead of hiding that synchronization inside a vague later task.
Use `metadata.step_kind = "join"` for an explicit merge/integration checkpoint and `metadata.step_kind = "barrier"` for a synchronization checkpoint that must run alone before later work continues.
Join or barrier nodes must run alone, must not use `parallel_group`, and should depend on the upstream nodes they are reconciling.
Use join nodes sparingly. Add them only when a later task truly needs the combined result of multiple earlier branches or when integration risk is high enough that the synchronization point should be first-class in the graph.
Do not include the final closeout sweep inside the normal task list. The app runs a separate closeout block after all planned tasks finish.

Return exactly one JSON object with a top-level "tasks" array containing 3 to 7 items.

JSON shape:
{
  "title": "short project name",
  "summary": "one short paragraph",
  "tasks": [
    {
      "step_id": "stable id like ST1",
      "task_title": "short stage name",
      "display_description": "one sentence or less for UI display",
      "codex_description": "one paragraph or less with the actual execution instruction for Codex",
      "reasoning_effort": "one of low, medium, high, xhigh based on expected difficulty",
      "depends_on": ["step ids that must complete first"],
      "owned_paths": ["repo-relative paths or directories this step primarily owns"],
      "success_criteria": "clear completion condition that can be judged locally",
      "metadata": {
        "step_kind": "task unless this is an explicit join or barrier node",
        "merge_from": ["step ids being explicitly reconciled; usually the same as depends_on for join nodes"],
        "join_policy": "use `all` for join nodes and leave empty for normal task nodes",
        "join_reason": "brief note explaining why this synchronization point exists",
        "candidate_block_id": "Planner Agent A block id",
        "parallelizable_after": ["Planner Agent A block ids or contract names carried through"],
        "implementation_notes": "non-docstring planning note carried forward from Planner Agent A",
        "is_skeleton_contract": false,
        "skeleton_contract_docstring": "required only when this step is the skeleton/bootstrap contract step; otherwise empty string",
        "candidate_owned_paths": ["Planner Agent A ownership hint for post-processing and traceability"]
      }
    }
  ]
}

Field requirements:

- "title": short and concise title for project.
- "summary": a short paragraph explaining the overall execution flow from a project perspective. It must briefly describe the role of each task in the broader project, not just restate the user request.
- "step_id": use stable ids like `ST1`, `ST2`, `ST3` so dependency references stay unambiguous.
- "task_title": short and actionable title for task.
- "display_description": very short user-facing explanation, no more than one sentence.
- "codex_description": the actual instruction for Codex, no more than one paragraph, specific enough to execute.
- "reasoning_effort": choose only `low`, `medium`, `high`, or `xhigh`. Use `low` for narrow mechanical edits, `medium` for normal implementation, `high` for multi-file or tricky work, and `xhigh` only for the hardest investigations or refactors.
- "depends_on": in parallel mode, use this to encode the DAG.
- "owned_paths": in parallel mode, list the main repo-relative files or directories each step owns so independently ready steps can be batched safely. Prefer narrow exact files or leaf directories. Use an empty array only when the step should run alone.
- "success_criteria": a concrete, locally judgeable done condition, describing what must be true when the block is complete.
- "metadata": carry Planner Agent A traceability hints. Preserve `candidate_block_id`, carry `parallelizable_after`, keep non-skeleton notes in `implementation_notes`, and use `skeleton_contract_docstring` only for the skeleton/bootstrap contract step.
- For a normal work node, set `metadata.step_kind` to `task` or leave it empty.
- For an explicit synchronization node, set `metadata.step_kind` to `join` or `barrier`. Join nodes should normally depend on 2 or more upstream steps, set `metadata.merge_from`, and use `metadata.join_policy = "all"`.
- Do not emit `join_policy = "any"` or other custom merge semantics. The runtime currently supports only explicit `all` joins.
- If the step is the skeleton/bootstrap contract step, make `codex_description` explicitly tell the executor to update existing code in place when that surface already exists and create only the smallest necessary skeleton otherwise.

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

Planner Agent A decomposition artifact:
{
  "title": "lit-v1-autonomous-workflow-release",
  "strategy_summary": "This needs a contract-first refactor rather than scattered feature patches. Freeze the v1 repository layout, revision/checkpoint schema, and service boundary first, then land the core persistence/safety work, then fan out into verification, lineage, and artifacts, and only after that rebuild the CLI and desktop UI on the same backend surface. The safest parallel shape is sequential core foundation, a parallel domain-feature wave, a service-layer convergence step, then parallel product-surface work and final hardening.",
  "shared_contracts": [
    "repo_layout_v1: freeze the .lit v1 path and ref namespaces for heads, checkpoints, lineages, journals, locks, verification cache, migrations, and repo-local artifact link manifests before feature work spreads",
    "revision_schema_v1: unify ordinary commits and safe checkpoints under one tolerant persisted revision/provenance model that accepts legacy commit JSON with missing fields",
    "mutation_transaction_v1: every mutating operation runs under a repository lock and journaled transaction boundary so crash recovery and rollback bookkeeping are consistent",
    "verification_key_v1: verification cache identity is state fingerprint plus environment fingerprint plus command identity, with result records separated from presentation",
    "backend_api_v1: CLI, desktop UI, and future Jakal Flow integration consume one narrow service/DTO adapter instead of reaching into repository internals or hardcoding on-disk paths"
  ],
  "skeleton_step": {
    "block_id": "SK1",
    "needed": true,
    "task_title": "Freeze V1 Contracts And Plan",
    "purpose": "A small up-front contract step reduces later merge risk by moving the new product vocabulary out of ad hoc changes to repository.py, refs.py, and GUI DTOs. It also satisfies the explicit requirement to write a brief implementation plan inside the repo before the broad refactor starts.",
    "contract_docstring": "Canonical lit v1 contracts for autonomous local workflows. Persisted revision, checkpoint, lineage, verification, artifact, and operation records serialize only through these versioned dataclasses and layout helpers; readers must tolerate legacy v0 commit JSON and absent fields. CLI, GUI, export, and future Jakal Flow adapters talk to a narrow backend API and must not hardcode .lit paths or invent metadata keys independently.",
    "candidate_owned_paths": [
      "docs/lit-v1-implementation-plan.md",
      "src/lit/domain.py",
      "src/lit/layout.py",
      "src/lit/backend_api.py"
    ],
    "success_criteria": "The repo contains a short implementation plan plus importable v1 contract/layout modules that define names, fields, and boundaries for revisions, checkpoints, lineages, verification, artifacts, and service methods without yet doing the full feature work."
  },
  "candidate_blocks": [
    {
      "block_id": "B1",
      "goal": "Versioned repository layout, migration, locking, and crash-safe journaling are real and wired into the repository core.",
      "work_items": [
        "Extract or introduce central layout helpers for new v1 directories and ref namespaces.",
        "Add atomic write/replace helpers and repository lock acquisition/release.",
        "Add a journaled mutation wrapper for multi-step operations.",
        "Implement lightweight migration/open logic so existing v0 repositories still load and can be upgraded in place.",
        "Cover interrupted-operation recovery and concurrent local operation rejection."
      ],
      "implementation_notes": "Keep the content-addressed object model and deduplicated trees/blobs, but stop scattering path knowledge across repository.py and command handlers. This block should also stop direct write_text/write_json mutations for stateful operations and move them behind transaction helpers so later checkpoint, lineage, verification, and artifact code inherits recoverability instead of reinventing it.",
      "testable_boundary": "A legacy repository still opens, a v1 repository creates the new layout safely, a second concurrent mutator is blocked, and an interrupted journaled operation can be recovered or cleanly aborted.",
      "candidate_owned_paths": [
        "src/lit/layout.py",
        "src/lit/storage.py",
        "src/lit/state.py",
        "src/lit/migrations.py",
        "src/lit/transactions.py",
        "src/lit/repository.py",
        "tests/test_bootstrap.py",
        "tests/test_repository_resilience.py"
      ],
      "parallelizable_after": [
        "SK1"
      ],
      "parallel_notes": "This is a true foundation block and should stay single-owner. Most later engine work should wait until the transaction and layout rules exist."
    },
    {
      "block_id": "B2",
      "goal": "Structured provenance, first-class safe checkpoints, and rollback become core repository behaviors instead of CLI labels.",
      "work_items": [
        "Replace minimal commit metadata with the v1 provenance and relationship model.",
        "Introduce first-class checkpoint records or refs with safe state, pin state, approval state, and notes.",
        "Implement latest-safe and selected-safe rollback primitives.",
        "Preserve provenance fields through commit creation, merge, rebase, promotion, and rollback bookkeeping.",
        "Add history and inspection helpers that surface checkpoints alongside ordinary revisions."
      ],
      "implementation_notes": "Prefer a single persisted revision envelope or a tightly related pair of record types so provenance, rewrite lineage, and verification links do not fork into incompatible shapes. Backward compatibility is mandatory, so parsing must tolerate old commit objects and synthesize safe defaults without rewriting everything immediately.",
      "testable_boundary": "The engine can create a revision with rich provenance, mark and inspect safe checkpoints, pin and unpin them, roll back to latest or selected safe state, and still read older repositories and commits.",
      "candidate_owned_paths": [
        "src/lit/commits.py",
        "src/lit/checkpoints.py",
        "src/lit/refs.py",
        "src/lit/repository.py",
        "src/lit/merge_ops.py",
        "src/lit/rebase_ops.py",
        "tests/test_checkpoints.py",
        "tests/test_bootstrap.py"
      ],
      "parallelizable_after": [
        "B1"
      ],
      "parallel_notes": "This still touches shared engine roots, so keep it serialized after B1. Verification, lineage, and most product surfaces should wait for this schema to settle."
    },
    {
      "block_id": "B3",
      "goal": "Verification runs, cached replay, stale detection, and verification-aware checkpoint status exist as real repository services.",
      "work_items": [
        "Add repository-configured verification command definitions.",
        "Implement persisted verification result records with timestamps, return code, output references, and fingerprints.",
        "Implement cache replay and stale detection across state and environment changes.",
        "Link verification results to revisions and checkpoints.",
        "Make safe-checkpoint promotion and inspection verification-aware."
      ],
      "implementation_notes": "Keep command execution, cache lookup, and result persistence separate so the CLI and GUI can inspect past results without rerunning commands. Large outputs should be referenced by an output-ref helper rather than stuffed into small state files, even if the artifact-store integration remains a thin seam here.",
      "testable_boundary": "Repeated verification on the same state can return cached_pass or cached_fail, changed environment or state becomes stale, and checkpoint inspection shows the correct verification status and summary.",
      "candidate_owned_paths": [
        "src/lit/verification.py",
        "src/lit/repository.py",
        "src/lit/storage.py",
        "tests/test_verification.py"...

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
