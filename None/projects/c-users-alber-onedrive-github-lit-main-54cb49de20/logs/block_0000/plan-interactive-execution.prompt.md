You are planning a Codex execution flow for the local project at C:\Users\alber\OneDrive\문서\GitHub\lit.
Follow any AGENTS.md rules in the repository.

Break the user's request into small execution checkpoints.
First, decompose the request into smaller implementation ideas.
Then, regroup those ideas into a DAG execution tree where each node has one clear, locally judgeable completion condition.
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
For any steps that may run in parallel, provide non-empty `owned_paths` and make them as narrow as possible.
Prefer exact files or leaf directories over broad package roots so the scheduler can batch more work safely.
Keep exact-path ownership exclusive across the same ready wave.
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
      "success_criteria": "clear completion condition that can be judged locally"
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

Do not include markdown fences or commentary outside the JSON.

Repository summary:
README:
README.md not found.

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
