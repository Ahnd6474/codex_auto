You are performing a pre-closeout optimization pass for the managed repository at C:\Users\alber\OneDrive\문서\GitHub\experiment2.
Follow any AGENTS.md rules in the repository.
All planned execution tasks are already complete. This pass is optional cleanup before final closeout.
Managed planning documents live outside the repo at C:\Users\alber\.jakal-flow-workspace\projects\c-users-alber-onedrive-github-experiment2-main-cfffe43b21\docs.
Primary verification command: python -m pytest.

Project title:
Jakal-flow Local Harness

Original user request:
jakal-flow(https://github.com/Ahnd6474/Jakal-flow)의 실행 환경을 구축해줘

Execution summary:
First remove the real Windows blocker by making bootstrap and target materialization long-path-safe within the fixed `.local/` layout. Once that contract is stable, fan out into a runtime verification task that turns `jakal-flow-local` into a clean materialize-install-smoke flow and a documentation task that publishes the same shipped operator contract so the harness is both runnable and handoff-ready.

Optimization mode:
light

Scanned files:
400

Candidate files:
- .local/targets/jakal-flow-materialize-longpaths-test/src/jakal_flow/ui_bridge_payloads.py
- .local/targets/jakal-flow-materialize-no-longpaths-test/src/jakal_flow/ui_bridge_payloads.py
- .local/upstream/jakal-flow/src/jakal_flow/ui_bridge_payloads.py

Candidate findings:
[
  {
    "category": "bottleneck",
    "details": "Cache, narrow, or extract repeated file-system and repository reads to keep closeout lightweight.",
    "line": 765,
    "path": ".local/targets/jakal-flow-materialize-longpaths-test/src/jakal_flow/ui_bridge_payloads.py",
    "score": 13,
    "summary": "Function build_activity_lines mixes 3 filesystem or repository scan signals",
    "symbol": "build_activity_lines"
  },
  {
    "category": "bottleneck",
    "details": "Cache, narrow, or extract repeated file-system and repository reads to keep closeout lightweight.",
    "line": 765,
    "path": ".local/targets/jakal-flow-materialize-no-longpaths-test/src/jakal_flow/ui_bridge_payloads.py",
    "score": 13,
    "summary": "Function build_activity_lines mixes 3 filesystem or repository scan signals",
    "symbol": "build_activity_lines"
  },
  {
    "category": "bottleneck",
    "details": "Cache, narrow, or extract repeated file-system and repository reads to keep closeout lightweight.",
    "line": 765,
    "path": ".local/upstream/jakal-flow/src/jakal_flow/ui_bridge_payloads.py",
    "score": 13,
    "summary": "Function build_activity_lines mixes 3 filesystem or repository scan signals",
    "symbol": "build_activity_lines"
  },
  {
    "category": "bottleneck",
    "details": "Cache, narrow, or extract repeated file-system and repository reads to keep closeout lightweight.",
    "line": 691,
    "path": ".local/targets/jakal-flow-materialize-longpaths-test/src/jakal_flow/ui_bridge_payloads.py",
    "score": 3,
    "summary": "Function bottom_panel_payload mixes 3 filesystem or repository scan signals",
    "symbol": "bottom_panel_payload"
  },
  {
    "category": "bottleneck",
    "details": "Cache, narrow, or extract repeated file-system and repository reads to keep closeout lightweight.",
    "line": 691,
    "path": ".local/targets/jakal-flow-materialize-no-longpaths-test/src/jakal_flow/ui_bridge_payloads.py",
    "score": 3,
    "summary": "Function bottom_panel_payload mixes 3 filesystem or repository scan signals",
    "symbol": "bottom_panel_payload"
  },
  {
    "category": "bottleneck",
    "details": "Cache, narrow, or extract repeated file-system and repository reads to keep closeout lightweight.",
    "line": 691,
    "path": ".local/upstream/jakal-flow/src/jakal_flow/ui_bridge_payloads.py",
    "score": 3,
    "summary": "Function bottom_panel_payload mixes 3 filesystem or repository scan signals",
    "symbol": "bottom_panel_payload"
  }
]

Additional user instructions:
None.

Required optimization rules:
1. Inspect the listed candidate files first and keep the pass focused on those areas unless a tiny supporting edit is necessary.
2. Prefer small safe optimizations: split overly large files, extract duplicated logic, break up multi-responsibility functions, or remove obvious low-value bottlenecks.
3. Preserve behavior. Do not add features, do not weaken rollback or traceability, and do not make speculative rewrites.
4. If a candidate is not safely actionable, leave it alone.
5. Keep verification executable. Add or update tests only when they materially protect the optimization.
6. If there is nothing worth changing after inspection, leave the repository unchanged.
