# Scope Guard

- Repository URL: {repo_url}
- Branch: {branch}
- Project slug: {repo_slug}

## Rules

1. Long-term strategy is locked by default. Do not edit `docs/LONG_TERM_PLAN.md` unless the user explicitly requests it.
2. Mid-term planning must stay a strict subset of the long-term plan.
3. Prefer small, reversible, test-backed changes.
4. Do not widen product scope automatically.
5. Only update README or docs to reflect verified repository state.
6. Roll back to the current safe revision when validation regresses.
