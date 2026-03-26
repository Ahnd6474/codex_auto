# Research Notes

- 2026-03-26: Core repository spine now exposes deterministic branch refs, commit metadata, DAG helpers (`merge_base`, `is_ancestor`, first-parent replay planning), and explicit merge/rebase state snapshots so later command nodes can build branch/merge/rebase behavior without reopening `.lit` storage details.
