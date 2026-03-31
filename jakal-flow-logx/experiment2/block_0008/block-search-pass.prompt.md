You are working inside the managed repository at C:\Users\alber\OneDrive\문서\GitHub\experiment2.
Follow any AGENTS.md rules in the repository.
Treat the saved execution plan as the current scope boundary unless the user explicitly updates it.
You are executing one node of a saved DAG execution tree.
Do not expand scope beyond the active task, dependency boundary, and scope guard.
Managed planning documents live outside the repo at C:\Users\alber\.jakal-flow-workspace\projects\c-users-alber-onedrive-github-experiment2-main-cfffe43b21\docs.
Verification command for this step: python -m pytest.

Current task:
- Title: Freeze Shared Harness Contract
- UI description: Restore and tighten the repo-wide harness contract surface.
- Success criteria: The repository contains the shared contract bundle from `origin/main`, the canonical helper surface and fixed entry script ids are present, and config, docs, and contract tests all agree on a single normalized profile contract without ambiguity about `.local/` state ownership or the `jakal-flow-local` default profile.
- Depends on: none
- Owned paths:
- .gitignore
- .env.example
- config/experiment.example.json
- config/profiles/jakal-flow-local.json
- config/profiles/sample-local.json
- docs/ARCHITECTURE.md
- scripts/profile-common.ps1
- scripts/common.ps1
- tests/test_harness_contract.py
- conftest.py
- Step metadata:
{
  "candidate_block_id": "B1",
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
  "implementation_notes": "This block should mostly restore the already-working contract bundle from `origin/main` rather than inventing new paths or names. The only intentional tightening is the current ambiguity around whether `profile-common.ps1` truly supports fixture profiles; that needs one consistent answer reflected in config, docs, and tests. After this lands, later blocks should avoid reopening these files unless a contract bug is discovered.",
  "is_skeleton_contract": false,
  "join_reason": "",
  "parallelizable_after": [],
  "skeleton_contract_docstring": ""
}

Codex execution instruction:
Restore the shared contract bundle from `origin/main` into the current repository, then tighten the helper/profile contract in place so `scripts/profile-common.ps1` exposes one stable normalized shape that generic orchestration can consume for both `jakal-flow-local` and `sample-local`, while keeping `.local/` ownership, the fixed entry script ids, and the default profile contract consistent across config, docs, and tests.

Memory context:
Relevant prior memory:
- [failure] block 7: Freeze Shared Harness Contract :: Freeze Shared Harness Contract Codex pass failed and changes were rolled back. Cause: 2026-03-28T12:43:49.408042Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: UTF-8 encoding error: failed to convert header to a str for header name 'x-codex-turn-metadata' with value: "{\"turn_id\":\"019d3478-d9ac-7fd0-aa7b-de1612049683\",\"work...
- [failure] block 6: Freeze Shared Harness Contract :: Freeze Shared Harness Contract Codex pass failed and changes were rolled back. Cause: 2026-03-28T12:43:41.463632Z ERROR codex_api::endpoint::responses_websocket: failed to connect to websocket: UTF-8 encoding error: failed to convert header to a str for header name 'x-codex-turn-metadata' with value: "{\"turn_id\":\"019d3478-ba81-78e3-b386-50d28edf9593\",\"work...

Plan snapshot:
# Execution Plan

- Repository: experiment2
- Working directory: C:\Users\alber\OneDrive\문서\GitHub\experiment2
- Source: https://github.com/Ahnd6474/experiment.git
- Branch: main
- Generated at: 2026-03-28T12:43:40+00:00

## Plan Title
Experiment Harness Setup

## User Prompt
https://github.com/Ahnd6474/experiment 실행 환경을 구축해줘

## Execution Summary
Restore the shared harness contract bundle from `origin/main` first so paths, profiles, helper functions, and entrypoint ids are frozen in one place. Then fan out into two parallel branches: one restores the default remote-target lifecycle for prerequisite checks, upstream bootstrap, and safe local cleanup, while the other restores the tracked sample fixture profile and network-free materialization lane. After both branches converge, add the still-missing generic materialization and verification entrypoints so the repository surface is complete, runnable, and aligned with the declared config contract.

## Workflow Mode
standard

## Execution Mode
parallel

## Planned Steps
- ST1: Freeze Shared Harness Contract
  - UI description: Restore and tighten the repo-wide harness contract surface.
  - Codex instruction: Restore the shared contract bundle from `origin/main` into the current repository, then tighten the helper/profile contract in place so `scripts/profile-common.ps1` exposes one stable normalized shape that generic orchestration can consume for both `jakal-flow-local` and `sample-local`, while keeping `.local/` ownership, the fixed entry script ids, and the default profile contract consistent across config, docs, and tests.
  - Step kind: task
  - Model provider: auto -> openai (AGENTS.md Codex preference)
  - Model: auto -> kimi-k2.5
  - GPT reasoning: high
  - Parallel group: none
  - Depends on: none
  - Owned paths: .gitignore, .env.example, config/experiment.example.json, config/profiles/jakal-flow-local.json, config/profiles/sample-local.json, docs/ARCHITECTURE.md, scripts/profile-common.ps1, scripts/common.ps1, tests/test_harness_contract.py, conftest.py
  - Verification: python -m pytest
  - Success criteria: The repository contains the shared contract bundle from `origin/main`, the canonical helper surface and fixed entry script ids are present, and config, docs, and contract tests all agree on a single normalized profile contract without ambiguity about `.local/` state ownership or the `jakal-flow-local` default profile.
  - Metadata: {"candidate_block_id": "B1", "candidate_owned_paths": [".gitignore", ".env.example", "config/experiment.example.json", "config/profiles", "docs/ARCHITECTURE.md", "scripts/profile-common.ps1", "scripts/common.ps1", "tests/test_harness_contract.py", "conftest.py"], "implementation_notes": "This block should mostly restore the already-working contract bundle from `origin/main` rather than inventing new paths or names. The only intentional tightening is the current ambiguity around whether `profile-common.ps1` truly supports fixture profiles; that needs one consistent answer reflected in config, docs, and tests. After this lands, later blocks should avoid reopening these files unless a contract bug is discovered.", "is_skeleton_contract": false, "join_reason": "", "parallelizable_after": [], "skeleton_contract_docstring": ""}
- ST2: Restore Remote Bootstrap Lifecycle
  - UI description: Reinstate prerequisite checks, upstream bootstrap, and safe local cleanup for the default remote target.
  - Codex instruction: Restore or adapt the prerequisite-check, upstream bootstrap, and local cleanup scripts from `origin/main` so the default `jakal-flow-local` lifecycle runs from the shared config/helper surface, refreshes `.local/upstream/jakal-flow`, manages the repo-local virtual environment deterministically, and keeps local-state deletion safely bounded to `.local/`; keep the lifecycle behavior reflected in focused script tests.
  - Step kind: task
  - Model provider: auto -> openai (AGENTS.md Codex preference)
  - Model: auto -> kimi-k2.5
  -...

Mid-term plan:
# Mid-Term Plan

This block follows the user-reviewed execution step.

- [ ] MT1 -> ST1: Freeze Shared Harness Contract

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
