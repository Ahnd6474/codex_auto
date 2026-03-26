# Research Notes

- 2026-03-26: Core repository spine now exposes deterministic branch refs, commit metadata, DAG helpers (`merge_base`, `is_ancestor`, first-parent replay planning), and explicit merge/rebase state snapshots so later command nodes can build branch/merge/rebase behavior without reopening `.lit` storage details.
- 2026-03-26: Recovered the merged ST2/ST3 cherry-pick by resolving `tests/test_bootstrap.py` to keep both the checkout parser assertion from branch/checkout work and the explicit merge/rebase parser assertions from the merge/rebase engine work. `python -m pytest` passed after the conflict resolution.
- 2026-03-27: Recovered the merged ST4/ST5 batch by resolving the `tests/test_bootstrap.py` cherry-pick conflict to keep both the CLI workflow coverage from ST4 and the README/website verification from ST5. `python -m pytest` passed after staging the merged test file, leaving the repository ready for `git cherry-pick --continue`.
