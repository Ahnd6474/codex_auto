from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from .errors import RuntimeConfigError
from .failure_logs import write_runtime_failure_log
from .interactive_cli import configure_shell_parser, main as interactive_main, run_shell_from_namespace
from .models import RuntimeOptions
from .orchestrator import Orchestrator
from .project_snapshot import context_execution_snapshot
from .runtime_config import load_runtime_from_sources, parse_runtime_overrides


CLI_HANDLED_EXCEPTIONS = (
    RuntimeError,
    ValueError,
    KeyError,
    FileNotFoundError,
    OSError,
    json.JSONDecodeError,
    subprocess.SubprocessError,
    RuntimeConfigError,
)


def _add_workspace_argument(target: argparse.ArgumentParser) -> None:
    target.add_argument(
        "--workspace-root",
        default=".jakal-flow-workspace",
        help="Root directory for isolated managed projects",
    )


def _add_repo_arguments(target: argparse.ArgumentParser) -> None:
    target.add_argument("--repo-url", required=True, help="GitHub repository URL")
    target.add_argument("--branch", default="main", help="Target branch")


def _add_runtime_config_arguments(target: argparse.ArgumentParser) -> None:
    target.add_argument(
        "--config",
        type=Path,
        help="Runtime configuration file (.json or .toml). Use top-level keys or a [runtime] / runtime object.",
    )
    target.add_argument(
        "--set",
        dest="runtime_overrides",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Override one runtime setting after loading --config. VALUE may be JSON when needed.",
    )


def _add_legacy_runtime_arguments(target: argparse.ArgumentParser) -> None:
    hidden = argparse.SUPPRESS
    target.add_argument("--model-provider", default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--local-model-provider", default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--model", default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--provider-base-url", default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--provider-api-key-env", default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--billing-mode", default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--input-cost-per-million-usd", type=float, default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--cached-input-cost-per-million-usd", type=float, default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--output-cost-per-million-usd", type=float, default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--reasoning-output-cost-per-million-usd", type=float, default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--per-pass-cost-usd", type=float, default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--fast", action="store_true", default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--compact-planning", action="store_true", default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--word-report", action="store_true", default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--effort", default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--planning-effort", default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--workflow-mode", default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--ml-max-cycles", type=int, default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--extra-prompt", default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--plan-prompt", default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--approval-mode", default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--sandbox-mode", default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--test-cmd", default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--max-blocks", type=int, default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--optimization-mode", default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--optimization-large-file-lines", type=int, default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--optimization-long-function-lines", type=int, default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--optimization-duplicate-block-lines", type=int, default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--optimization-max-files", type=int, default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--allow-push", action="store_true", default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--parallel-worker-mode", default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--parallel-workers", type=int, default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--parallel-memory-per-worker-gib", type=float, default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--allow-background-queue", action="store_true", default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--background-queue-priority", type=int, default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--save-project-logs", action="store_true", default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--auto-merge-pull-request", action="store_true", default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--codex-path", default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--git-user-name", default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--git-user-email", default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--require-checkpoint-approval", action="store_true", default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--checkpoint-interval-blocks", type=int, default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--no-progress-limit", type=int, default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--regression-limit", type=int, default=argparse.SUPPRESS, help=hidden)
    target.add_argument("--empty-cycle-limit", type=int, default=argparse.SUPPRESS, help=hidden)


def _add_runtime_command_arguments(target: argparse.ArgumentParser, *, include_repo: bool = True) -> None:
    if include_repo:
        _add_repo_arguments(target)
    _add_workspace_argument(target)
    _add_runtime_config_arguments(target)
    target.add_argument("--plan-file", type=Path, help="Optional path to seed PLAN.md")
    _add_legacy_runtime_arguments(target)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Multi-repository AI CLI orchestrator",
        epilog="Run 'jakal-flow' with no arguments to open the interactive flow console.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    shell_parser = subparsers.add_parser("shell", help="Open the interactive flow console")
    configure_shell_parser(shell_parser)

    init_parser = subparsers.add_parser("init-repo", help="Initialize and register a managed repository")
    _add_runtime_command_arguments(init_parser)

    run_parser = subparsers.add_parser("run", help="Run one or more improvement blocks")
    _add_runtime_command_arguments(run_parser)

    resume_parser = subparsers.add_parser("resume", help="Resume a managed repository run")
    _add_runtime_command_arguments(resume_parser)
    resume_parser.set_defaults(resume=True)

    list_parser = subparsers.add_parser("list-repos", help="List repositories managed in the workspace")
    _add_workspace_argument(list_parser)

    status_parser = subparsers.add_parser("status", help="Show repository status")
    _add_workspace_argument(status_parser)
    _add_repo_arguments(status_parser)

    history_parser = subparsers.add_parser("history", help="Show block history")
    _add_workspace_argument(history_parser)
    _add_repo_arguments(history_parser)
    history_parser.add_argument("--limit", type=int, default=10, help="Number of history items to show")

    report_parser = subparsers.add_parser("report", help="Generate a machine-readable report")
    _add_workspace_argument(report_parser)
    _add_repo_arguments(report_parser)

    logx_parser = subparsers.add_parser("logx", help="Collect and refresh project log index")
    _add_workspace_argument(logx_parser)
    logx_parser.add_argument(
        "--repo-url",
        help="Managed repository URL/path to write logx under (omit when using --source-repo-dir)",
    )
    logx_parser.add_argument("--branch", default="main", help="Target branch")
    logx_parser.add_argument(
        "--source-repo-dir",
        type=Path,
        default=None,
        help="Local repository directory to collect logs from",
    )
    logx_parser.add_argument(
        "--max-artifacts",
        type=int,
        default=400,
        help="Maximum number of log artifacts to track",
    )

    return parser


def _legacy_runtime_overrides(args: argparse.Namespace) -> dict[str, object]:
    mapping = {
        "model_provider": "model_provider",
        "local_model_provider": "local_model_provider",
        "model": "model",
        "provider_base_url": "provider_base_url",
        "provider_api_key_env": "provider_api_key_env",
        "billing_mode": "billing_mode",
        "input_cost_per_million_usd": "input_cost_per_million_usd",
        "cached_input_cost_per_million_usd": "cached_input_cost_per_million_usd",
        "output_cost_per_million_usd": "output_cost_per_million_usd",
        "reasoning_output_cost_per_million_usd": "reasoning_output_cost_per_million_usd",
        "per_pass_cost_usd": "per_pass_cost_usd",
        "fast": "use_fast_mode",
        "compact_planning": "use_fast_mode",
        "word_report": "generate_word_report",
        "effort": "effort",
        "planning_effort": "planning_effort",
        "workflow_mode": "workflow_mode",
        "ml_max_cycles": "ml_max_cycles",
        "extra_prompt": "extra_prompt",
        "plan_prompt": "init_plan_prompt",
        "approval_mode": "approval_mode",
        "sandbox_mode": "sandbox_mode",
        "test_cmd": "test_cmd",
        "max_blocks": "max_blocks",
        "optimization_mode": "optimization_mode",
        "optimization_large_file_lines": "optimization_large_file_lines",
        "optimization_long_function_lines": "optimization_long_function_lines",
        "optimization_duplicate_block_lines": "optimization_duplicate_block_lines",
        "optimization_max_files": "optimization_max_files",
        "allow_push": "allow_push",
        "parallel_worker_mode": "parallel_worker_mode",
        "parallel_workers": "parallel_workers",
        "parallel_memory_per_worker_gib": "parallel_memory_per_worker_gib",
        "allow_background_queue": "allow_background_queue",
        "background_queue_priority": "background_queue_priority",
        "save_project_logs": "save_project_logs",
        "auto_merge_pull_request": "auto_merge_pull_request",
        "codex_path": "codex_path",
        "git_user_name": "git_user_name",
        "git_user_email": "git_user_email",
        "require_checkpoint_approval": "require_checkpoint_approval",
        "checkpoint_interval_blocks": "checkpoint_interval_blocks",
        "no_progress_limit": "no_progress_limit",
        "regression_limit": "regression_limit",
        "empty_cycle_limit": "empty_cycle_limit",
    }
    overrides: dict[str, object] = {}
    for attr_name, runtime_key in mapping.items():
        if hasattr(args, attr_name):
            overrides[runtime_key] = getattr(args, attr_name)
    return overrides


def runtime_from_args(args: argparse.Namespace) -> RuntimeOptions:
    config_path = getattr(args, "config", None)
    runtime_override_items = getattr(args, "runtime_overrides", []) or []
    legacy_overrides = _legacy_runtime_overrides(args)
    override_payload = {**legacy_overrides, **parse_runtime_overrides(runtime_override_items)}
    return load_runtime_from_sources(
        config_path=config_path,
        overrides=override_payload,
    )


def _list_repo_status(orchestrator: Orchestrator, project) -> str:
    raw_status = str(project.metadata.current_status or "").strip()
    if project.loop_state.pending_checkpoint_approval:
        return "awaiting_checkpoint_approval"
    if raw_status and raw_status.lower() != "awaiting_checkpoint_approval":
        return raw_status
    try:
        plan_state = orchestrator.load_execution_plan_state(project)
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
        return raw_status or "setup_ready"
    return context_execution_snapshot(project, plan_state).current_status


def _best_effort_project(orchestrator: Orchestrator, args: argparse.Namespace):
    repo_url = str(getattr(args, "repo_url", "") or "").strip()
    branch = str(getattr(args, "branch", "") or "").strip() or "main"
    if repo_url:
        return orchestrator.workspace.find_project(repo_url, branch)
    return None


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if not raw_argv:
        return interactive_main([])
    parser = build_parser()
    args = parser.parse_args(raw_argv)
    if args.command == "shell":
        try:
            return run_shell_from_namespace(args)
        except CLI_HANDLED_EXCEPTIONS as exc:
            write_runtime_failure_log(
                Path(args.workspace_root).expanduser().resolve(),
                source="cli",
                command="shell",
                exc=exc,
                payload=vars(args),
                project=None,
            )
            print(f"error: {exc}", file=sys.stderr)
            return 1
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
                    "status": _list_repo_status(orchestrator, item),
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
                resume=bool(getattr(args, "resume", False)),
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

        if args.command == "logx":
            source_repo_dir = getattr(args, "source_repo_dir", None)
            if not str(getattr(args, "repo_url", "")).strip() and source_repo_dir is None:
                parser.error("logx requires either --repo-url or --source-repo-dir.")
            path = orchestrator.logx(
                args.repo_url or "",
                args.branch,
                max_artifacts=int(getattr(args, "max_artifacts", 400)),
                source_repo_dir=Path(source_repo_dir).expanduser().resolve() if source_repo_dir else None,
            )
            print(str(path))
            return 0

        parser.error(f"Unsupported command: {args.command}")
        return 2
    except CLI_HANDLED_EXCEPTIONS as exc:
        write_runtime_failure_log(
            Path(args.workspace_root).expanduser().resolve(),
            source="cli",
            command=str(getattr(args, "command", "") or "unknown"),
            exc=exc,
            payload=vars(args),
            project=_best_effort_project(orchestrator, args),
        )
        print(f"error: {exc}", file=sys.stderr)
        return 1
