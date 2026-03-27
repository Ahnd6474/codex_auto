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
- Maintain at least basic consistency in layout, state display, error messaging, and interaction flow.

## 5. Architecture and Separation of Concerns

- Separate core logic, UI, storage, and external integrations whenever practical.
- Avoid over-abstraction, but do not force unrelated responsibilities into one file.
- Keep role boundaries clear even in small projects.
- Prefer structures that are less likely to break when features are added later.
- In this repository, keep UI concerns under `desktop/` and orchestration or automation logic under `src/jakal_flow/`.

## 6. State Management

- Avoid overusing global mutable state.
- Keep state traceable and assign clear ownership to it.
- Do not mix configuration values with runtime state.
- Do not depend on hidden hard-coded state.

## 7. Testing

- Write core logic so it can be verified when practical, even if the user did not explicitly request tests.
- Prioritize checks for behavior that is easy to break and easy to validate locally.
- Do not build an excessive test framework for a trivial change.
- Do not leave important logic completely unverified without a clear reason.

## 8. Configuration, Environment Variables, and Secrets

- Do not hard-code API keys, tokens, local paths, or similar environment-specific values.
- Separate environment-specific values into configuration files or environment variables.
- When configuration is required, provide an example template or a clear default structure.

## 9. Data and Storage

- Choose storage based on the actual scope of the project.
- Lightweight storage is acceptable for a local single-user tool.
- Do not couple storage choices too tightly to core logic.
- Prefer clear boundaries so the storage layer can be replaced later if needed.
- Preserve the multi-repository operating model. Do not collapse state, logs, memory, or docs into a single-repository design.

## 10. Error Handling

- Give failure-prone operations at least basic exception handling and recovery flow.
- Do not fail silently.
- Make error messages reveal the likely cause and the next useful action whenever possible.
- Do not stop at implementing only the happy path.

## 11. Logging and Debuggability

- Keep important execution flow traceable.
- Do not make logs so noisy that they lose value, but do not make them too sparse to debug.
- Treat traceability as more important in automation, asynchronous work, and multi-step flows.
- Preserve or improve structured logs, state files, and report generation when behavior changes.

## 12. Documentation

- Keep README and usage documents aligned with the actual implementation.
- Do not describe unimplemented behavior as if it already exists.
- Reflect execution steps, configuration requirements, and important structural changes in the docs when they change.

## 13. Dependency Threshold

- Add dependencies only when they provide a meaningful benefit to implementation quality, productivity, or maintainability.
- Do not attach heavy dependencies to minor tasks.
- Do not avoid a good library so aggressively that the resulting implementation becomes worse.
- Prefer Python standard-library solutions unless an external dependency clearly improves reliability or maintainability enough to justify it.

## 14. Performance

- Prioritize correctness and clarity first.
- Avoid premature optimization when no real bottleneck has been identified.
- Do not ignore obvious inefficiency on a core path.
