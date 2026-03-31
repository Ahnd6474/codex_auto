You are Planner Agent B for the local project at C:\Users\alber\OneDrive\문서\GitHub\experiment2.
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
# experiment2

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
No markdown files under repo/docs.

Source inventory:
No obvious implementation files detected under src/, app/, lib/, or desktop/src. A narrow skeleton/bootstrap step is acceptable only if it establishes the first real contract, entrypoint, or module.

Planner Agent A decomposition artifact:
{
  "title": "experiment harness environment",
  "strategy_summary": "Use `origin/main` as the restore source for the existing harness implementation instead of redesigning it from scratch. Freeze the shared config/profile/helper contract first, then fan out in parallel across the remote-bootstrap lifecycle and the sample-fixture track, and finish with the still-missing generic orchestration entrypoints that the config already declares but the current upstream implementation does not yet provide.",
  "shared_contracts": [
    "All generated state stays under `.local/`; tracked top-level deliverables remain in `config/`, `docs/`, `fixtures/`, `scripts/`, and `tests/`.",
    "`config/experiment.example.json` stays at `schemaVersion: 1` with top-level `paths`, `runtime`, `entryScripts`, and `prerequisites`, and `runtime.defaultProfile` remains `jakal-flow-local`.",
    "Fixed entry script ids are `checkPrereqs`, `bootstrap`, `cleanLocalState`, `materializeTarget`, and `invokeVerification`; `scripts/profile-common.ps1` is the canonical resolver surface and `scripts/common.ps1` remains only a compatibility loader.",
    "`Normalize-ExperimentProfile` should yield one stable normalized shape that generic orchestration can consume for both the default remote target and the tracked sample fixture profile, instead of leaving sample-profile handling ambiguous.",
    "`config/profiles/jakal-flow-local.json` remains the default remote-target contract with required `OPENAI_API_KEY`, optional `GITHUB_TOKEN`, upstream checkout at `.local/upstream/jakal-flow`, and ordered verification phases.",
    "`fixtures/sample-seed` plus `sample-local` remain the network-free smoke target used to validate local materialization and verification behavior."
  ],
  "skeleton_step": {
    "block_id": "",
    "needed": false,
    "task_title": "",
    "purpose": "",
    "contract_docstring": "",
    "candidate_owned_paths": [],
    "success_criteria": ""
  },
  "candidate_blocks": [
    {
      "block_id": "B1",
      "goal": "Restore and freeze the shared harness contract bundle in the local repo.",
      "work_items": [
        "Restore `.gitignore` and `.env.example` so `.local/` state and secret inputs are documented correctly.",
        "Restore `config/experiment.example.json` and the tracked profiles under `config/profiles/` from `origin/main`.",
        "Restore `docs/ARCHITECTURE.md`, `scripts/profile-common.ps1`, and `scripts/common.ps1` as the canonical shared contract surface.",
        "Restore `tests/test_harness_contract.py` and `conftest.py` to lock the shared contract in automation.",
        "Tighten the helper/profile contract so fixture-profile handling is either fully normalized or explicitly narrowed with no doc/test mismatch."
      ],
      "implementation_notes": "This block should mostly restore the already-working contract bundle from `origin/main` rather than inventing new paths or names. The only intentional tightening is the current ambiguity around whether `profile-common.ps1` truly supports fixture profiles; that needs one consistent answer reflected in config, docs, and tests. After this lands, later blocks should avoid reopening these files unless a contract bug is discovered.",
      "testable_boundary": "`pytest tests/test_harness_contract.py` passes and the shared config/helper/docs surface exists with stable names.",
      "candidate_owned_paths": [
        ".gitignore",
        ".env.example",
        "config/experiment.example.json",
        "config/profiles",
        "docs/ARCHITECTURE.md",
        "scripts/profile-common.ps1",
        "scripts/common.ps1",
        "tests/test_harness_contract.py",
        "conftest.py"
      ],
      "parallelizable_after": [],
      "parallel_notes": "This is the broad shared root for the rest of the work and should run first; later blocks should treat it as frozen."
    },
    {
      "block_id": "B2",
      "goal": "Restore prerequisite checking, upstream bootstrap, and local-st...

User request:
https://github.com/Ahnd6474/experiment 실행 환경을 구축해줘
