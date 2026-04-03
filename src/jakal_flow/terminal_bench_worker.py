from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path

from .orchestrator import Orchestrator
from .runtime_config import load_runtime_from_sources


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run jakal-flow inside a Terminal-Bench task container")
    parser.add_argument("--task-description-base64", required=True, help="Base64-encoded task description")
    parser.add_argument("--workspace-root", default="/tmp/jakal-flow-workspace", help="Workspace root for artifacts")
    parser.add_argument("--branch", default="", help="Optional branch override")
    parser.add_argument("--display-name", default="terminal-bench-task", help="Project display name")
    parser.add_argument("--config", default="", help="Optional runtime config file inside the container")
    return parser


def _runtime_from_env(config_path: str) -> object:
    raw_overrides = os.environ.get("JAKAL_FLOW_RUNTIME_OVERRIDES", "").strip()
    overrides: dict[str, object] = {}
    if raw_overrides:
        parsed = json.loads(raw_overrides)
        if isinstance(parsed, dict):
            overrides = parsed

    model_provider = os.environ.get("JAKAL_FLOW_MODEL_PROVIDER", "").strip() or "openai"
    model = os.environ.get("JAKAL_FLOW_MODEL", "").strip() or "gpt-5.4"
    effort = os.environ.get("JAKAL_FLOW_EFFORT", "").strip() or "high"
    max_blocks = int(os.environ.get("JAKAL_FLOW_MAX_BLOCKS", "12") or "12")
    test_cmd = os.environ.get("JAKAL_FLOW_TEST_CMD", "").strip() or "python -m jakal_flow.terminal_bench_verify"
    payload = {
        "model_provider": model_provider,
        "model": model,
        "effort": effort,
        "approval_mode": "never",
        "sandbox_mode": "danger-full-access",
        "test_cmd": test_cmd,
        "max_blocks": max(1, max_blocks),
        "allow_push": False,
        "require_checkpoint_approval": False,
        "checkpoint_interval_blocks": 999999,
        "save_project_logs": True,
    }
    payload.update(overrides)
    return load_runtime_from_sources(
        config_path=Path(config_path) if config_path else None,
        overrides=payload,
    )


def _detect_branch(repo_dir: Path, fallback: str) -> str:
    if fallback.strip():
        return fallback.strip()
    git_head = repo_dir / ".git" / "HEAD"
    try:
        head_contents = git_head.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return "main"
    prefix = "ref: refs/heads/"
    if head_contents.startswith(prefix):
        return head_contents[len(prefix) :].strip() or "main"
    return "main"


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    repo_dir = Path.cwd().resolve()
    task_description = base64.b64decode(args.task_description_base64.encode("ascii")).decode("utf-8")
    runtime = _runtime_from_env(args.config)
    orchestrator = Orchestrator(Path(args.workspace_root))
    context = orchestrator.run_local(
        project_dir=repo_dir,
        runtime=runtime,
        branch=_detect_branch(repo_dir, args.branch),
        origin_url=os.environ.get("JAKAL_FLOW_REPO_URL", "").strip(),
        plan_input=task_description,
        resume=False,
        display_name=args.display_name,
        preserve_repo_state=True,
    )
    return 0 if "failed" not in str(context.metadata.current_status or "").lower() else 1


if __name__ == "__main__":
    raise SystemExit(main())
