You are working inside the managed repository at C:\Users\alber\OneDrive\문서\GitHub\experiment2.
Follow any AGENTS.md rules in the repository.
Treat the saved execution plan as the current scope boundary unless the user explicitly updates it.
You are executing one node of a saved DAG execution tree.
Do not expand scope beyond the active task, dependency boundary, and scope guard.
Managed planning documents live outside the repo at C:\Users\alber\.jakal-flow-workspace\projects\c-users-alber-onedrive-github-experiment2-main-cfffe43b21\docs.
Verification command for this step: python -m pytest.

Current task:
- Title: Harden Windows Materialization
- UI description: Make bootstrap and target cloning long-path-safe under `.local/`.
- Success criteria: Bootstrap and remote target materialization both use an explicit long-path-safe Git strategy, and a dedicated offline regression proves a deeply nested synthetic repository can populate `.local/upstream` and `.local/targets` from the current repo root without `Filename too long` checkout failure.
- Depends on: none
- Owned paths:
- scripts/bootstrap.ps1
- scripts/materialize-target.ps1
- tests/test_jakal_flow_longpaths.py
- Step metadata:
{
  "candidate_block_id": "B1",
  "candidate_owned_paths": [
    "scripts/bootstrap.ps1",
    "scripts/materialize-target.ps1",
    "tests/test_jakal_flow_longpaths.py"
  ],
  "implementation_notes": "Real runs against upstream failed in both the source checkout and target clone paths with `Filename too long`. Fix the scripts rather than moving state outside `.local/`, and keep the regression isolated in its own test module so later profile and verification work can proceed independently.",
  "is_skeleton_contract": false,
  "join_reason": "",
  "parallelizable_after": [],
  "skeleton_contract_docstring": ""
}

Codex execution instruction:
Update the harness Git calls in `scripts/bootstrap.ps1` and `scripts/materialize-target.ps1` so source refresh and target materialization succeed on Windows long paths without changing the `.local/` contract, then add a dedicated offline regression that reproduces the failure with a synthetic deep-path repository.

Memory context:
Relevant prior memory:
- [success] block 11: Freeze Shared Harness Contract :: Completed block with one search-enabled Codex pass.

Plan snapshot:
# Execution Plan

- Repository: experiment2
- Working directory: C:\Users\alber\OneDrive\문서\GitHub\experiment2
- Source: https://github.com/Ahnd6474/experiment.git
- Branch: main
- Generated at: 2026-03-29T01:18:34+00:00

## Plan Title
Jakal-flow Local Harness

## User Prompt
jakal-flow(https://github.com/Ahnd6474/Jakal-flow)의 실행 환경을 구축해줘

## Execution Summary
First remove the real Windows blocker by making bootstrap and target materialization long-path-safe within the fixed `.local/` layout. Once that contract is stable, fan out into a runtime verification task that turns `jakal-flow-local` into a clean materialize-install-smoke flow and a documentation task that publishes the same shipped operator contract so the harness is both runnable and handoff-ready.

## Workflow Mode
standard

## Execution Mode
parallel

## Planned Steps
- ST1: Harden Windows Materialization
  - UI description: Make bootstrap and target cloning long-path-safe under `.local/`.
  - Codex instruction: Update the harness Git calls in `scripts/bootstrap.ps1` and `scripts/materialize-target.ps1` so source refresh and target materialization succeed on Windows long paths without changing the `.local/` contract, then add a dedicated offline regression that reproduces the failure with a synthetic deep-path repository.
  - Step kind: task
  - Model provider: openai -> openai (step override)
  - Model: gpt-5.4 -> gpt-5.4
  - GPT reasoning: high
  - Parallel group: none
  - Depends on: none
  - Owned paths: scripts/bootstrap.ps1, scripts/materialize-target.ps1, tests/test_jakal_flow_longpaths.py
  - Verification: python -m pytest
  - Success criteria: Bootstrap and remote target materialization both use an explicit long-path-safe Git strategy, and a dedicated offline regression proves a deeply nested synthetic repository can populate `.local/upstream` and `.local/targets` from the current repo root without `Filename too long` checkout failure.
  - Metadata: {"candidate_block_id": "B1", "candidate_owned_paths": ["scripts/bootstrap.ps1", "scripts/materialize-target.ps1", "tests/test_jakal_flow_longpaths.py"], "implementation_notes": "Real runs against upstream failed in both the source checkout and target clone paths with `Filename too long`. Fix the scripts rather than moving state outside `.local/`, and keep the regression isolated in its own test module so later profile and verification work can proceed independently.", "is_skeleton_contract": false, "join_reason": "", "parallelizable_after": [], "skeleton_contract_docstring": ""}

## Non-Goals
- Do not skip verification for any planned step.
- Do not widen scope beyond the current prompt unless the user updates the plan.

## Operating Constraints
- Treat each planned step as a checkpoint.
- In parallel mode, only dependency-ready steps with disjoint owned paths may run together.
- Commit and push after a verified step when an origin remote is configured.
- Users may edit only steps that have not started yet.

Mid-term plan:
# Mid-Term Plan

This block follows the user-reviewed execution step.

- [ ] MT1 -> ST1: Harden Windows Materialization

Scope guard:
# Scope Guard

- Repository URL: https://github.com/Ahnd6474/experiment.git
- Branch: main
- Project slug: c-users-alber-onedrive-github-experiment2-main-cfffe43b21

## Rules

1. Treat the saved project plan and reviewed execution steps as the current scope boundary unless the user explicitly changes them.
2. Mid-term planning must stay a strict subset of the saved plan.
3. Prefer small, reversible, test-backed changes.
4. Do not widen product scope automatically.
5. Only update README or docs to reflect verified repository state, and reserve README.md edits for planning-time alignment or the final closeout pass.
6. Roll back to the current safe revision when validation regresses.

Research notes:
# Research Notes

- 2026-03-28: Restored the shared harness contract bundle from `origin/main`
  into the managed repository worktree. Tightened the fixture ambiguity by
  keeping `jakal-flow-local` as the default remote profile while making
  `sample-local` normalize through `scripts/profile-common.ps1` into the same
  helper output shape: absolute source metadata, target/workspace paths,
  optional materializer script, environment lists, prerequisite overlays, and
  ordered verification phases. Also excluded `_tmp_*` clone directories in
  `conftest.py` so repository verification does not collect transient external
  test suites.

Additional user instructions:
None.

Required workflow:
1. Inspect the relevant project files first so function names, module boundaries, and terminology stay consistent with the codebase.
2. Determine the smallest safe change set that satisfies the task instruction and success criteria.
3. Add or update executable tests that locally verify the task.
4. Implement the task in code.
5. Run the verification command and keep docs aligned only with verified behavior.
6. Do not edit README.md during normal execution steps. Reserve README updates for planning artifacts outside the repo or the final closeout pass unless the user explicitly says otherwise.
7. Record concise research or implementation notes in C:\Users\alber\.jakal-flow-workspace\projects\c-users-alber-onedrive-github-experiment2-main-cfffe43b21\docs\RESEARCH_NOTES.md when they materially help traceability.
8. If the task cannot be completed safely in one pass, explain why in docs/BLOCK_REVIEW.md instead of making speculative edits.

Execution rules:
- Treat the owned paths above as the primary write scope for this node.
- Avoid editing files that are primarily owned by other pending nodes unless a tiny compatibility adjustment is strictly required.
- Do not assume sibling nodes have already landed.
- If the task would require a broad cross-node refactor, stop and document the blocker instead of making merge-sensitive edits.
- If `step_metadata.step_kind` is `join` or `barrier`, treat this node as an explicit integration checkpoint on the current branch rather than a normal isolated feature pass.
- For join or barrier nodes, focus on reconciling already-completed upstream work, validating the combined behavior, and making only the smallest integration-safe edits needed to satisfy the success criteria.
- Keep the change set merge-friendly, traceable, and limited.
- Leave repository-wide handoff docs like README.md alone during step execution.
- Use web search only when directly necessary for official documentation or narrowly scoped factual verification.
