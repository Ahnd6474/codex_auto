from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .models import RuntimeOptions
from .orchestrator import Orchestrator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Multi-repository Codex CLI orchestrator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_shared_arguments(target: argparse.ArgumentParser, include_repo: bool = True) -> None:
        if include_repo:
            target.add_argument("--repo-url", required=True, help="GitHub repository URL")
            target.add_argument("--branch", default="main", help="Target branch")
        target.add_argument(
            "--workspace-root",
            default=".codex-auto-workspace",
            help="Root directory for isolated managed projects",
        )
        target.add_argument("--model", default="gpt-5.4", help="Model slug passed to Codex CLI")
        target.add_argument("--effort", default="medium", help="Reasoning effort override: low, medium, high, xhigh")
        target.add_argument("--extra-prompt", default="", help="Additional user instructions appended to Codex prompts")
        target.add_argument(
            "--plan-prompt",
            default="",
            help="Optional prompt used by Codex to draft the initial project plan",
        )
        target.add_argument("--approval-mode", default="never", help="Codex approval mode")
        target.add_argument("--sandbox-mode", default="workspace-write", help="Codex sandbox mode")
        target.add_argument("--test-cmd", default="python -m pytest", help="Validation command to run after passes")
        target.add_argument("--max-blocks", type=int, default=1, help="Maximum blocks to execute in one run")
        target.add_argument("--allow-push", action="store_true", help="Push safe commits to origin")
        target.add_argument("--plan-file", type=Path, help="Optional path to seed PLAN.md")
        target.add_argument("--resume", action="store_true", help="Resume an existing managed repository")

    init_parser = subparsers.add_parser("init-repo", help="Initialize and register a managed repository")
    add_shared_arguments(init_parser)

    run_parser = subparsers.add_parser("run", help="Run one or more improvement blocks")
    add_shared_arguments(run_parser)

    resume_parser = subparsers.add_parser("resume", help="Resume a managed repository run")
    add_shared_arguments(resume_parser)
    resume_parser.set_defaults(resume=True)

    list_parser = subparsers.add_parser("list-repos", help="List repositories managed in the workspace")
    add_shared_arguments(list_parser, include_repo=False)

    status_parser = subparsers.add_parser("status", help="Show repository status")
    add_shared_arguments(status_parser)

    history_parser = subparsers.add_parser("history", help="Show block history")
    add_shared_arguments(history_parser)
    history_parser.add_argument("--limit", type=int, default=10, help="Number of history items to show")

    report_parser = subparsers.add_parser("report", help="Generate a machine-readable report")
    add_shared_arguments(report_parser)

    return parser


def runtime_from_args(args: argparse.Namespace) -> RuntimeOptions:
    return RuntimeOptions(
        model=args.model,
        effort=args.effort,
        extra_prompt=args.extra_prompt,
        init_plan_prompt=args.plan_prompt,
        approval_mode=args.approval_mode,
        sandbox_mode=args.sandbox_mode,
        test_cmd=args.test_cmd,
        max_blocks=args.max_blocks,
        allow_push=args.allow_push,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    orchestrator = Orchestrator(Path(args.workspace_root))

    try:
        if args.command == "list-repos":
            projects = orchestrator.list_projects()
            payload = [
                {
                    "repo_id": item.metadata.repo_id,
                    "slug": item.metadata.slug,
                    "repo_url": item.metadata.repo_url,
                    "branch": item.metadata.branch,
                    "status": item.metadata.current_status,
                    "last_run_at": item.metadata.last_run_at,
                    "safe_revision": item.metadata.current_safe_revision,
                }
                for item in projects
            ]
            print(json.dumps(payload, indent=2))
            return 0

        runtime = runtime_from_args(args)

        if args.command == "init-repo":
            context = orchestrator.init_repo(
                repo_url=args.repo_url,
                branch=args.branch,
                runtime=runtime,
                plan_path=args.plan_file,
            )
            print(json.dumps(context.metadata.to_dict(), indent=2))
            return 0

        if args.command in {"run", "resume"}:
            context = orchestrator.run(
                repo_url=args.repo_url,
                branch=args.branch,
                runtime=runtime,
                plan_path=args.plan_file,
                resume=args.resume,
            )
            print(json.dumps(context.loop_state.to_dict(), indent=2))
            return 0

        if args.command == "status":
            context = orchestrator.status(args.repo_url, args.branch)
            print(json.dumps({"metadata": context.metadata.to_dict(), "loop_state": context.loop_state.to_dict()}, indent=2))
            return 0

        if args.command == "history":
            print(orchestrator.history(args.repo_url, args.branch, limit=args.limit))
            return 0

        if args.command == "report":
            path = orchestrator.report(args.repo_url, args.branch)
            print(str(path))
            return 0

        parser.error(f"Unsupported command: {args.command}")
        return 2
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
