{
  "candidate_blocks": [
    {
      "block_id": "B1",
      "candidate_owned_paths": [
        "src/tetris/__init__.py",
        "src/tetris/__main__.py",
        "src/tetris/actions.py",
        "src/tetris/app.py"
      ],
      "forbidden_core_candidates": [],
      "goal": "\ud604\uc7ac \ucf54\ub4dc\ub97c \uc9c0\uc6b0\uace0, \uc77c\ubc18\uc801\uc778 \ud14c\ud2b8\ub9ac\uc2a4 \uc571\uc744 \uac1c\ubc1c\ud574\uc918\n\n1. 40\uc904 \ubaa8\ub4dc\n2. \ube14\ub9ac\uce20\n3. \uc5f0\uc2b5 \ubaa8\ub4dc",
      "implementation_notes": "Use the repository summary to keep file ownership narrow. Prefer edits to existing code paths and let Planner Agent B split the work further only when there are truly independent outcomes.",
      "parallel_notes": "Only create a parallel-ready wave when the owned paths stay narrow and non-overlapping.",
      "parallelizable_after": [],
      "primary_scope_candidates": [
        "src/tetris/__init__.py",
        "src/tetris/__main__.py",
        "src/tetris/actions.py",
        "src/tetris/app.py"
      ],
      "scope_class_hint": "free_owned",
      "shared_contracts": [],
      "shared_reviewed_candidates": [],
      "spine_version_hint": "spine-v1",
      "step_type_hint": "feature",
      "testable_boundary": "The final execution plan maps the request onto small, locally judgeable checkpoints.",
      "verification_profile_hint": "default",
      "work_items": [
        "Identify the smallest safe implementation slice that directly satisfies the user request.",
        "Reuse or extend existing modules before creating new boundaries.",
        "Preserve verification and traceability artifacts while shaping the final DAG."
      ]
    }
  ],
  "packing_notes": [
    "Preserve any directly relevant AGENTS.md constraints and existing repository structure.",
    "Favor a minimal prerequisite step only when a shared contract or entrypoint clearly needs to be frozen first.",
    "Keep the resulting plan compact enough for fast iteration while still being handoff-quality."
  ],
  "shared_contracts": [],
  "skeleton_step": {
    "block_id": "SK1",
    "candidate_owned_paths": [],
    "contract_docstring": "",
    "forbidden_core_candidates": [],
    "needed": false,
    "primary_scope_candidates": [],
    "purpose": "",
    "scope_class_hint": "shared_reviewed",
    "shared_contracts": [],
    "shared_reviewed_candidates": [],
    "spine_version_hint": "spine-v1",
    "step_type_hint": "contract",
    "success_criteria": "",
    "task_title": "",
    "verification_profile_hint": "default"
  },
  "strategy_summary": "Compact planning mode: skip the separate decomposition pass, keep the DAG narrow, and prefer direct edits to existing implementation surfaces before introducing new scaffolding.",
  "title": "\ud604\uc7ac \ucf54\ub4dc\ub97c \uc9c0\uc6b0\uace0, \uc77c\ubc18\uc801\uc778 \ud14c\ud2b8\ub9ac\uc2a4 \uc571\uc744 \uac1c\ubc1c\ud574\uc918\n\n1. 40\uc904 \ubaa8\ub4dc\n2. \ube14\ub9ac\uce20\n3. \uc5f0\uc2b5 \ubaa8\ub4dc"
}