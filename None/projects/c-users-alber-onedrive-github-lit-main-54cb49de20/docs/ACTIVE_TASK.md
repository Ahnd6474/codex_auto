# Active Task

- Selected at: 2026-03-26T13:25:53+00:00
- Candidate: ST1
- Scope refs: ST1

## Task
Stabilize Core Repository Spine

## Rationale
UI description: Create the shared storage, history, and command-module foundation.. Execution instruction: Refactor the current Python skeleton into the smallest sustainable architecture for `lit`: preserve the deterministic `.lit` on-disk layout, add commit metadata and DAG traversal helpers needed by branch/merge/rebase, expose reusable repository primitives for applying trees and tracking in-progress operations, and split CLI dispatch so later commands can live in isolated modules instead of reserved placeholders.. Owned paths: src/lit/cli.py, src/lit/repository.py, src/lit/commits.py, src/lit/refs.py, src/lit/state.py, src/lit/commands. Verification command: python -m pytest. Success criteria: The codebase has reusable repository APIs that can represent commit ancestry, branch refs, and merge/rebase operation state deterministically, and the CLI entrypoint is structured to load real command modules rather than pending stubs.

## Memory Context
No strongly relevant prior memory found.
