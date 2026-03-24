# AGENTS.md

This repository builds and maintains `codex-auto`, a multi-repository automation CLI.

## Operating Rules

1. Preserve the current modular layout under `src/codex_auto/`.
2. Keep the tool multi-repository. Do not collapse state, logs, memory, or docs into a single-repository design.
3. Prefer standard-library Python unless a dependency clearly improves reliability enough to justify itself.
4. Treat traceability as a first-class requirement. New behavior should keep or improve structured logs, state files, and report generation.
5. Do not weaken rollback or safe-revision handling.
6. Do not make `LONG_TERM_PLAN.md` mutable by default.
7. Keep README examples aligned with the actual CLI.
8. Add tests when practical, but avoid fake or non-executable pseudo-tests.
9. Preserve the Tkinter GUI entrypoint unless there is a strong reason to replace it.

## Implementation Bias

- Favor small explicit modules over monolithic scripts.
- Use strong typing and dataclasses for persisted state.
- Keep subprocess interactions explicit and error-aware.
- Do not claim support for Codex CLI flags that are not actually wired into the implementation.
- Keep GUI work on background threads when invoking long-running repository operations.
