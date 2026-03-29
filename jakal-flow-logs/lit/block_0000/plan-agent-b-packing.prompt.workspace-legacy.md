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
Optimize the plan for a fully runnable and maintainable prototype.
Prefer implementation choices that are simple but not obviously disposable if the project continues.
If the requested outcome cannot be completed reliably without setup, integration, validation, cleanup, or supporting implementation work that the user did not explicitly mention, include that work in the plan.
Treat only directly necessary supporting work as in scope; do not add speculative roadmap items or optional expansion beyond the requested prototype outcome.
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
Do not put risky, tightly coupled, shared-contract, or same-file refactors in the same parallel-ready wave.
If a step needs broad repo-wide edits or merge-sensitive refactors, keep it isolated rather than pretending it is parallel-safe.
Do not include the final closeout sweep inside the normal task list. The app runs a separate closeout block after all planned tasks finish.

Return exactly one JSON object with a top-level "tasks" array containing 3 to 5 items.

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
- If the step is the skeleton/bootstrap contract step, make `codex_description` explicitly tell the executor to write the skeleton code with the provided docstring.

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

## 2. Prototype Standards

- A prototype is not just a script that happens to run.
- Even a minimal prototype should be runnable, maintainable, and extensible.
- Prefer the smallest sustainable implementation over the fastest possible shortcut.
- Do not make obviously disposable structure the default choice.

## 3. Technology Selection

- When the stack is not specified, choose based on a balance of simplicity, maintainability, and extensibility.
- Respect the existing stack, but do not use stack consistency alone to justify a poor-quality decision.
- Add new tools or dependencies only when they provide a clear practical benefit.
- Do not choose an approach only because it is the easiest thing to implement immediately.
- For this repository, prefer the existing `React + Tauri + JavaScri...

Docs:
No markdown files under repo/docs.

Planner Agent A decomposition artifact:
{
  "title": "lit desktop gui",
  "strategy_summary": "Build the milestone as a new PySide6 desktop package in `src/lit_gui`, using the existing Python `lit` APIs directly through a thin normalized service layer instead of CLI text parsing or a new JS/Rust backend. Freeze the three-pane shell, DTOs, and shared diff/detail slots first, then fan out the major views against that contract, and reserve shared-state polish, smoke coverage, and docs for the final integration wave.",
  "shared_contracts": [
    "Freeze the desktop stack early as Python 3.12 + PySide6 in a new `src/lit_gui` package with a `lit-gui` entrypoint; do not introduce a separate Node/Rust/Tauri toolchain for this MVP.",
    "All repository reads and writes must go through one typed `RepositorySession` / backend service boundary; view modules must not import `lit.repository` or parse CLI stdout directly.",
    "Lock the core DTO surface before parallel fan-out: `RepoHomeEntry`, `RepoSnapshot`, `StatusSnapshot`, `ChangeItem`, `HistoryEntry`, `CommitDetail`, `BranchEntry`, `FileNode`, `FilePreview`, `OperationSnapshot`, and `ActionResult`.",
    "Keep the top-level shell fixed as left sidebar, center stacked view, and right contextual detail panel so feature blocks can land without rewriting app structure.",
    "Use one shared diff and preview presentation contract for Changes, History, and Files views; avoid separate renderers with divergent behavior.",
    "Persist recent repositories in an app-side JSON store outside user repositories; the GUI must not write extra metadata into working folders beyond the existing `.lit` data.",
    "After every mutation (`init`, `add`, `commit`, `restore`, `checkout`, `branch`, `merge`, `rebase`, abort actions), the session refreshes and emits a full normalized snapshot plus an actionable error/result message."
  ],
  "skeleton_step": {
    "block_id": "SK1",
    "needed": true,
    "task_title": "Freeze PySide6 shell and backend DTO boundary",
    "purpose": "There is no GUI scaffold today, so a narrow bootstrap step reduces merge risk by fixing the package layout, entrypoint, pane ownership, and view-model contracts before separate feature views start landing.",
    "contract_docstring": "Desktop GUI boundary: `lit_gui` is a PySide6 client over the existing Python `lit` backend. `RepositorySession` is the only query and mutation gateway and returns immutable DTOs for all views. The shell owns three stable regions (sidebar, active center view, right detail panel); feature views may fill slots but must not rewire the shell. Views do not import `lit.repository` directly and do not persist metadata inside user repositories.",
    "candidate_owned_paths": [
      "pyproject.toml",
      "src/lit_gui/app.py",
      "src/lit_gui/contracts.py",
      "src/lit_gui/shell/",
      "src/lit_gui/views/",
      "src/lit_gui/widgets/shared/"
    ],
    "success_criteria": "The app launches into a three-pane shell with placeholder Home, Changes, History, Branches, and Files views; navigation works; shared detail slots exist; typed DTO contracts are written down; and later blocks can implement against the scaffold without competing for top-level structure."
  },
  "candidate_blocks": [
    {
      "block_id": "B1",
      "goal": "Implement the real backend adapter and session layer over the existing Python repository APIs.",
      "work_items": [
        "Wrap `Repository`, `merge_revision`, and `rebase_onto` in a typed backend service.",
        "Normalize repository status, history, branches, file tree, file preview, and active operation state into DTOs.",
        "Compute commit changed-file summaries and commit-vs-parent text diffs in the adapter layer.",
        "Centralize error mapping, refresh behavior, and mutation result messages.",
        "Add adapter tests for clean, unborn, dirty, merge-conflict, and rebase-conflict repository states."
      ],
      "implementation_notes": "Keep this logic inside `src/lit_gui/backend/` so the existing `lit` package remains largely untouched. Use direct Python imports instead of CLI parsing, and derive missing view data from existing repository/tree APIs before considering any small backend helper. The session layer should be the only place that knows how to refresh, preserve selection hints, and translate backend exceptions into user-facing messages.",
      "testable_boundary": "Given temporary repositories, the adapter can open or initialize repos, return typed snapshots for primary states, and execute supported mutations with deterministic refreshed results and specific errors.",
      "candidate_owned_paths": [
        "src/lit_gui/backend/",
        "src/lit_gui/session.py",
        "tests/gui/backend/"
      ],
      "parallelizable_after": [
        "SK1"
      ],
      "parallel_notes": "This should land before real feature completion in the view blocks. Once the DTO contract is frozen, view work can proceed in parallel against the session API without touching backend internals."
    },
    {
      "block_id": "B2",
      "goal": "Deliver the repository home screen with open, initialize, invalid-folder messaging, and recent repositories.",
      "work_items": [
        "Build the empty-state home screen and recent repository list.",
        "Add folder open flow for existing local repositories.",
        "Add initialize-in-folder flow for new local repositories.",
        "Explain non-repository folders clearly and offer an init action.",
        "Persist and reload recent repository entries in local app storage."
      ],
      "implementation_notes": "This screen should stay honest about the product identity: open a local folder, initialize a local repository, or revisit a recent local repo. Recent-path persistence belongs in app data, not inside `.lit` or the working tree. The home screen should hand off cleanly into the active-repository shell without inventing clone, sync, or account flows.",
      "testable_boundary": "A fresh app can open a valid repository, initialize a new one, remember recent paths, and explain a non-`lit` folder without dead ends.",
      "candidate_owned_paths": [
        "src/lit_gui/views/home/",
        "src/lit_gui/persistence/recents.py",
        "tests/gui/views/test_home.py"
      ],
      "parallelizable_after": [
        "SK1",
        "B1"
      ],
      "parallel_notes": "Safe to parallelize once the session API exists. It is mostly isolated to home-screen and persistence code."
    },
    {
      "block_id": "B3",
      "goal": "Implement the Changes view as the default working-repo workflow with stage, diff, and commit.",
      "work_items": [
        "Render staged, modified, deleted, and untracked file groups with clear counts.",
        "Drive the right detail panel from the selected file diff.",
        "Support staging the selected path or supported grouped paths through the backend adapter.",
        "Add commit message input, validation, and commit action.",
        "Surface backend errors and refresh the view after add or commit."
      ],
      "implementation_notes": "Keep the UX aligned with the actual backend model: path or directory staging is supported, but advanced hunk staging is not. The diff shown here should reflect the current backend behavior against the current commit, and the commit action must stay disabled when there is nothing staged or the message is blank. This is the highest-value daily-use screen, so bias toward a clean and reliable flow over extra controls.",
      "testable_boundary": "On an active repository, a user can inspect a file diff, stage supported paths, enter a commit message, create a commit, and see the view refresh correctly.",
      "candidate_owned_paths": [
        "src/lit_gui/views/changes/",
        "tests/gui/views/test_changes.py"
      ],
      "parallelizable_after": [
        "SK1",
        "B1"
      ],
      "parallel_notes": "Safe in parallel with History, Branches, and Files once the shared detail/diff...

User request:
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
- Selecting a file shows contents or a helpful preview
- Do not attempt a full IDE
- The goal is repository orientation similar to GitHub Web’s code browsing, not editing-heavy functionality

6. Restore / checkout / merge / rebase action flows
- Provide guided action UI for:
  - restore
  - checkout
  - merge
  - rebase
- If merge or rebase enters a conflict/manual-resolution-required state, clearly explain:
  - what happened
  - which files are conflicted
  - what the user must do next
  - how to abort if supported
- Do not attempt an advanced visual conflict editor unless it is genuinely small and clean
- It is acceptable to provide a conflict guidance panel plus file opening/navigation instead of a full merge editor

GitHub Web inspirations to borrow
Borrow these ideas, adapted for local-only use:
- clean repository file browsing
- obvious branch context
- readable commit list
- clear selected-item detail panel
- sensible layout hierarchy
- good empty/loading/error states

GitHub Desktop inspirations to borrow
Borrow these ideas, adapted for local-only use:
- simple Changes tab
- obvious commit flow
- approachable branch switching
- desktop-friendly action bar
- guided, low-friction local workflow

Non-goals for this milestone
Do not spend time on these unless they are nearly free:
- remote repository management
- authentication
- plugin systems
- background sync
- live collaboration
- code editor replacement
- advanced blame/search features
- stash/cherry-pick/reflog/submodules/hooks/LFS support
- heavy theming system
- complex settings pages
- web deployment
- mobile support

Technical expectations
Choose a practical stack that fits the repo and yields a real desktop app.
Prefer a modern desktop approach such as Tauri + React if that fits the repository direction well.
Keep architecture simple and maintainable:
- clear separation between GUI state and lit command/backend integration
- small reusable components
- typed API boundary where possible
- testable action wrappers around backend operations
- avoid giant monolithic components
- avoid overengineering

Backend integration expectations
- Reuse the existing lit functionality rather than reimplementing version control logic in the frontend
- Prefer a thin UI bridge / command adapter layer
- Normalize backend responses into UI-friendly structures
- Surface backend errors cleanly and specifically
- Keep command execution deterministic and inspectable

Design expectations
Aim for a serious desktop developer-tool feel:
- clean spacing
- restrained visual style
- high information density without clutter
- excellent readability
- keyboard and mouse friendly
- obvious primary actions
- minimal decorative noise

The GUI should look credible enough that it could be shown as:
- the first serious GUI release of lit
- a strong portfolio/demo milestone
- a good example project produced through a Jakal-flow execution loop

Implementation plan requirements
Before coding, create a short implementation plan that splits the work into clear execution blocks.
The plan must optimize for a 3-5 day delivery window and prioritize a usable end-to-end result early.
Prefer blocks with one clear completion condition each.

Recommended execution order
1. inspect repository structure and existing backend entry points
2. choose/confirm GUI stack and folder structure
3. implement app shell and repository open/init flow
4. implement Changes view with commit flow
5. implement History view
6. implement Branches view and checkout flow
7. implement Files view
8. implement restore/merge/rebase guided flows
9. improve state handling, empty states, and error UX
10. add tests and documentation
11. polish UI consistency and final demo readiness

Required deliverables
Produce all of the following if practical within the milestone:

A. Runnable desktop GUI
- A user can launch the app locally and interact with a lit repository

B. Clear app shell
- Sidebar / main panel / detail panel layout
- Coherent navigation between key views

C. Core repository workflows
- open/init repository
- status/change inspection
- commit flow
- log/history browsing
- branch creation/listing/switching
- restore / checkout / merge / rebase entry points with guidance

D. Conflict/manual-state UX
- Visible state when merge/rebase needs manual resolution
- abort actions where supported
- useful guidance text

E. Documentation
- Update README with GUI usage instructions
- Add a short developer section explaining how to run the GUI in development
- If needed, add a concise architecture note for the GUI bridge/state model

F. Basic tests
Add tests where reasonable for:
- backend adapter / bridge logic
- response normalization
- important state transitions
- critical UI rendering logic for major empty/error states
Do not chase exhaustive frontend test coverage at the expense of shipping the product.

Quality bar
The final result should satisfy all of these:
- launches locally with straightforward setup
- core repository workflows actually work
- UI is coherent and intentionally designed
- scope stays faithful to lit’s local-only identity
- no fake GitHub cloud features appear
- no major dead-end screens
- no obviously broken primary workflow
- documentation is enough for a new user to try it

Important behavior rules
- Do not silently invent backend support that does not exist
- If a desired UI action is blocked by missing backend support, expose that honestly and gracefully
- Prefer one reliable simple flow over three half-working advanced flows
- Prefer a polished MVP over a broad but messy feature set
- Keep changes focused on this milestone; do not rewrite unrelated parts of the repository

Definition of done
This task is complete when:
1. the GUI can be launched locally
2. a user can open or initialize a lit repo
3. a user can inspect changes and make a commit
4. a user can browse history and inspect commits
5. a user can inspect branches and switch/create branches
6. a user can access restore/checkout/merge/rebase actions through the GUI
7. conflict/manual-resolution states are clearly surfaced
8. README/developer instructions are updated
9. the result feels like a credible “GitHub Web + GitHub Desktop for local-only lit” MVP

When making decisions, use this priority order
1. correctness and runnable behavior
2. clarity of local workflow UX
3. consistency with lit’s offline-only identity
4. maintainability of code
5. visual polish
6. extra features

Start by inspecting the repository, identifying the best integration path for the GUI, and then implement the milestone in small, validated steps.
