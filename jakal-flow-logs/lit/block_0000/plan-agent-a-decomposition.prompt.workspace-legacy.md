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
2. Identify any shared contracts, schemas, interfaces, entrypoints, or file skeletons that should be fixed before broad fan-out work starts.
3. Decide whether a narrow skeleton/bootstrap step is needed. Only recommend one if it reduces downstream merge risk or unlocks safe parallel waves.
4. Group the implementation ideas into candidate testable blocks. Each candidate block must represent one locally judgeable outcome that Codex can realistically finish in one focused pass.
5. Mark likely parallel tracks and call out any broad shared roots that should be avoided.
6. Leave final task ids, final DAG edges, final owned_paths, and final reasoning effort choices to Planner Agent B.

Parallel decomposition rules:
- Prefer candidate blocks with narrow ownership boundaries.
- Prefer exact files or leaf directories over broad package roots.
- If a small contract-freezing or skeleton step can unlock a wide safe fan-out, recommend it explicitly.
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
