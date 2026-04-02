from __future__ import annotations

import json
from pathlib import Path
import sys

from .models import ExecutionStep, ProjectContext


def main() -> int:
    try:
        raw_payload = sys.stdin.buffer.read()
        if not raw_payload.strip():
            raise ValueError("Lineage worker payload is required.")
        payload = json.loads(raw_payload.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Lineage worker payload must be a JSON object.")
        context = ProjectContext.from_dict(payload.get("lineage_context"))
        step = ExecutionStep.from_dict(payload.get("step") if isinstance(payload.get("step"), dict) else {})
        if not context.paths.workspace_root:
            raise ValueError("Lineage worker context is missing workspace_root.")
        from .orchestrator import Orchestrator

        orchestrator = Orchestrator(Path(context.paths.workspace_root).expanduser().resolve())
        result = orchestrator._run_lineage_step_worker_local(context, step)
        json.dump(result, sys.stdout, ensure_ascii=False)
        sys.stdout.flush()
        return 0
    except Exception as exc:
        message = str(exc).strip() or exc.__class__.__name__
        sys.stderr.write(f"{message}\n")
        sys.stderr.flush()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
