# Active Task

- Selected at: 2026-03-26T13:47:14+00:00
- Candidate: ST2
- Scope refs: ST2

## Task
Finish Branch and Checkout Workflows

## Rationale
UI description: Implement local branch creation, switching, and revision navigation.. Execution instruction: Using the shared repository APIs, implement real `branch`, `checkout`, and related `restore` navigation behavior for ordinary local cases: create and inspect branches, switch HEAD safely, apply commit trees to the working directory, keep nested paths correct, and make the command behavior and help text consistent with the supported local workflow.. Dependencies: ST1. Owned paths: src/lit/commands/branch.py, src/lit/commands/checkout.py, src/lit/branching.py. Verification command: python -m pytest. Success criteria: Users can create branches, inspect them, switch between branches or commits, and restore tracked content while keeping repository metadata and working-tree state internally consistent.

## Memory Context
Relevant prior memory:
- [success] block 1: Stabilize Core Repository Spine :: Completed block with one search-enabled Codex pass.
