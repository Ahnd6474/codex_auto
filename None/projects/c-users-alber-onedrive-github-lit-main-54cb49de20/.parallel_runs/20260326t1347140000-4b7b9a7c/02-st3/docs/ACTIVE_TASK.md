# Active Task

- Selected at: 2026-03-26T13:47:14+00:00
- Candidate: ST3
- Scope refs: ST3

## Task
Implement Merge and Rebase Engine

## Rationale
UI description: Add real local merge and rebase with predictable conflict handling.. Execution instruction: Implement simplified but real local `merge` and `rebase` flows on top of the shared commit graph: compute merge bases, apply tree changes, write merge commits or rewritten commits, persist operation state when conflicts occur, and make conflict behavior explicit and deterministic for ordinary text-file cases instead of leaving placeholders.. Dependencies: ST1. Owned paths: src/lit/commands/merge.py, src/lit/commands/rebase.py, src/lit/merge_ops.py, src/lit/rebase_ops.py. Verification command: python -m pytest. Success criteria: Local branches can be merged and rebased for normal cases, and at least one basic conflict path produces clear conflict state and user-visible results instead of silent failure or unimplemented output.

## Memory Context
Relevant prior memory:
- [success] block 1: Stabilize Core Repository Spine :: Completed block with one search-enabled Codex pass.
