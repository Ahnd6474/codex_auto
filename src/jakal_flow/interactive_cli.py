from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass, fields
from pathlib import Path
import shlex
import sys
from threading import Thread
from typing import Any

from .chat_sessions import execute_conversation_turn
from .interactive_flow import apply_flow_edit, render_ascii_flow, render_plan_table
from .models import ExecutionPlanState, ProjectContext, RuntimeOptions
from .orchestrator import Orchestrator
from .reporting import Reporter
from .runtime_config import load_runtime_from_sources, parse_runtime_overrides, runtime_from_payload
from .ui_bridge import run_command
from .utils import now_utc_iso, read_jsonl_tail


@dataclass(slots=True)
class ShellJob:
    name: str
    thread: Thread
    started_at: str
    allow_chat: bool
    result: Any = None
    error: BaseException | None = None


def configure_shell_parser(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "--workspace-root",
        default=".jakal-flow-workspace",
        help="Workspace root for managed projects",
    )
    parser.add_argument(
        "--project-dir",
        type=Path,
        help="Optional local repository to open immediately",
    )
    parser.add_argument("--branch", default="main", help="Default branch for local project setup")
    parser.add_argument("--origin-url", default="", help="Optional origin URL for local project setup")
    parser.add_argument("--display-name", default="", help="Optional display name for the opened project")
    parser.add_argument(
        "--config",
        type=Path,
        help="Runtime configuration file (.json or .toml).",
    )
    parser.add_argument(
        "--set",
        dest="runtime_overrides",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Override one runtime setting after loading --config.",
    )
    return parser


def build_shell_parser() -> argparse.ArgumentParser:
    return configure_shell_parser(
        argparse.ArgumentParser(
            description="Interactive flow-oriented shell for jakal-flow",
        )
    )


def main(argv: list[str] | None = None) -> int:
    args = build_shell_parser().parse_args(argv)
    return run_shell_from_namespace(args)


def run_shell_from_namespace(args: argparse.Namespace) -> int:
    runtime = load_runtime_from_sources(
        config_path=getattr(args, "config", None),
        overrides=parse_runtime_overrides(getattr(args, "runtime_overrides", None) or []),
    )
    shell = FlowShell(
        workspace_root=Path(args.workspace_root).expanduser().resolve(),
        runtime=runtime,
        initial_project_dir=getattr(args, "project_dir", None),
        branch=str(getattr(args, "branch", "main") or "main").strip() or "main",
        origin_url=str(getattr(args, "origin_url", "") or "").strip(),
        display_name=str(getattr(args, "display_name", "") or "").strip(),
    )
    return shell.run()


class FlowShell:
    def __init__(
        self,
        *,
        workspace_root: Path,
        runtime: RuntimeOptions,
        initial_project_dir: Path | None = None,
        branch: str = "main",
        origin_url: str = "",
        display_name: str = "",
    ) -> None:
        self.workspace_root = workspace_root
        self.orchestrator = Orchestrator(workspace_root)
        self.runtime = runtime
        self.current_project_dir = initial_project_dir.expanduser().resolve() if initial_project_dir is not None else None
        self.current_branch = branch
        self.current_origin_url = origin_url
        self.current_display_name = display_name
        self.chat_mode = "conversation"
        self.active_job: ShellJob | None = None
        self._step_field_names = {item.name for item in fields(RuntimeOptions)}

    def run(self) -> int:
        self._bootstrap()
        self._print_banner()
        self._print_startup_state()
        while True:
            self._drain_job()
            try:
                line = input(self._prompt()).strip()
            except EOFError:
                self._print("")
                return 0
            except KeyboardInterrupt:
                self._print("")
                if self.active_job is not None:
                    self._print("background work is still running; use /pause or /wait")
                    continue
                return 0
            if not line:
                continue
            try:
                if line.startswith("/"):
                    if self._handle_action_command(line[1:].strip()):
                        return 0
                    continue
                if line.startswith("$"):
                    self._handle_flow_command(line[1:].strip())
                    continue
                if line.startswith("!"):
                    self._handle_settings_command(line[1:].strip())
                    continue
                if line.startswith("@"):
                    self._handle_project_command(line[1:].strip())
                    continue
                self._handle_chat(line)
            except Exception as exc:
                self._print(f"error: {exc}", stream=sys.stderr)

    def _bootstrap(self) -> None:
        if self.current_project_dir is not None:
            self._open_project(self.current_project_dir)
            return
        current = self.orchestrator.local_project(Path.cwd())
        if current is not None:
            self._sync_from_context(current)

    def _print(self, text: str, *, stream=None) -> None:
        print(text, file=stream or sys.stdout)

    def _print_banner(self) -> None:
        self._print("jakal-flow flow console")
        self._print("plain text=chat  /=actions  $=flow edits  !=runtime  @=projects")
        self._print("type /help for command syntax")

    def _print_startup_state(self) -> None:
        if self.current_project_dir is None:
            self._print("no project selected; use @open . or @list")
            return
        self._print(self._project_summary())
        self._show_flow()

    def _prompt(self) -> str:
        project = self._project_name()
        mode = "review" if self.chat_mode == "review" else "chat"
        if self.active_job is not None:
            return f"{project}|{mode}|{self.active_job.name}> "
        return f"{project}|{mode}> "

    def _project_name(self) -> str:
        if self.current_project_dir is None:
            return "no-project"
        return self.current_display_name or self.current_project_dir.name

    def _project_summary(self) -> str:
        context = self._require_context()
        plan_state = self.orchestrator.load_execution_plan_state(context)
        return (
            f"project={context.metadata.display_name or context.metadata.slug} "
            f"path={context.metadata.repo_path} branch={context.metadata.branch} "
            f"status={context.metadata.current_status} steps={len(plan_state.steps)} "
            f"closeout={plan_state.closeout_status}"
        )

    def _require_context(self) -> ProjectContext:
        if self.current_project_dir is None:
            raise RuntimeError("No project is selected. Use @open . or @use first.")
        context = self.orchestrator.local_project(self.current_project_dir)
        if context is None:
            raise RuntimeError(f"Managed project not found for {self.current_project_dir}. Use @open again.")
        self._sync_from_context(context)
        return context

    def _sync_from_context(self, context: ProjectContext) -> None:
        self.current_project_dir = context.metadata.repo_path.resolve()
        self.current_branch = context.metadata.branch
        self.current_origin_url = str(context.metadata.origin_url or "").strip()
        self.current_display_name = str(context.metadata.display_name or context.metadata.slug).strip()
        self.runtime = context.runtime

    def _persist_runtime(self) -> None:
        if self.current_project_dir is None:
            return
        context = self._require_context()
        context.runtime = self.runtime
        if self.current_display_name:
            context.metadata.display_name = self.current_display_name
        context.metadata.branch = self.current_branch
        context.metadata.origin_url = self.current_origin_url or None
        self.orchestrator.workspace.save_project(context)
        self._sync_from_context(context)

    def _load_plan_state(self) -> ExecutionPlanState:
        context = self._require_context()
        return self.orchestrator.load_execution_plan_state(context)

    def _save_plan_state(self, plan_state: ExecutionPlanState) -> None:
        context, _saved = self.orchestrator.update_execution_plan(
            project_dir=self._require_context().metadata.repo_path,
            runtime=self.runtime,
            plan_state=plan_state,
            branch=self.current_branch,
            origin_url=self.current_origin_url,
        )
        self._sync_from_context(context)

    def _show_flow(self) -> None:
        context = self._require_context()
        plan_state = self.orchestrator.load_execution_plan_state(context)
        block_entries = read_jsonl_tail(context.paths.block_log_file, 120)
        self._print(render_ascii_flow(plan_state, block_entries=block_entries))

    def _show_status(self) -> None:
        context = self._require_context()
        plan_state = self.orchestrator.load_execution_plan_state(context)
        self._print(self._project_summary())
        self._print(
            f"runtime provider={self.runtime.model_provider} model={self.runtime.model} "
            f"chat_provider={self.runtime.chat_model_provider or '-'} chat_model={self.runtime.chat_model or '-'} "
            f"execution_mode={self.runtime.execution_mode} workflow_mode={self.runtime.workflow_mode}"
        )
        if context.loop_state.pending_checkpoint_approval:
            self._print("checkpoint approval is pending; use /approve")
        self._print(render_plan_table(plan_state))

    def _flow_payload(self, plan_state: ExecutionPlanState, runtime: RuntimeOptions | None = None) -> dict[str, Any]:
        return {
            "project_dir": str(self._require_context().metadata.repo_path),
            "branch": self.current_branch,
            "origin_url": self.current_origin_url,
            "display_name": self.current_display_name,
            "runtime": (runtime or self.runtime).to_dict(),
            "plan": plan_state.to_dict(),
        }

    def _start_job(self, name: str, worker, *, allow_chat: bool) -> None:
        if self.active_job is not None:
            raise RuntimeError(f"{self.active_job.name} is already running.")
        job = ShellJob(
            name=name,
            thread=Thread(target=lambda: self._run_job(job, worker), daemon=True, name=f"jakal-flow-{name}"),
            started_at=now_utc_iso(),
            allow_chat=allow_chat,
        )
        job.thread.start()
        self.active_job = job

    @staticmethod
    def _run_job(job: ShellJob, worker) -> None:
        try:
            job.result = worker()
        except BaseException as exc:
            job.error = exc

    def _drain_job(self) -> None:
        if self.active_job is None or self.active_job.thread.is_alive():
            return
        self.active_job.thread.join(timeout=0.1)
        finished = self.active_job
        self.active_job = None
        if finished.error is not None:
            self._print(f"[{finished.name}] failed: {finished.error}", stream=sys.stderr)
        else:
            self._print(f"[{finished.name}] finished at {now_utc_iso()}")
        if self.current_project_dir is not None:
            try:
                self._show_flow()
            except Exception as exc:
                self._print(f"warning: could not refresh flow: {exc}", stream=sys.stderr)

    def _handle_chat(self, message: str) -> None:
        if self.active_job is not None and not self.active_job.allow_chat:
            raise RuntimeError(f"{self.active_job.name} is running; chat is locked until it finishes.")
        context = self._require_context()
        result = execute_conversation_turn(
            context,
            plan_state=self.orchestrator.load_execution_plan_state(context),
            user_message=message,
            mode=self.chat_mode,
        )
        chat = result.get("chat", {}) if isinstance(result, dict) else {}
        messages = chat.get("messages", []) if isinstance(chat, dict) else []
        if messages:
            last = messages[-1]
            self._print(str(last.get("text", "")).strip() or "(empty response)")
        if result.get("error"):
            self._print(f"chat-error: {result['error']}", stream=sys.stderr)
        self._show_flow()

    def _handle_action_command(self, command_text: str) -> bool:
        parts = command_text.split(maxsplit=1)
        command = parts[0].strip().lower()
        rest = parts[1].strip() if len(parts) > 1 else ""
        if command in {"exit", "quit"}:
            return True
        if command in {"help", "commands"}:
            self._print_help()
            return False
        if command == "flow":
            self._show_flow()
            return False
        if command == "status":
            self._show_status()
            return False
        if command == "mode":
            normalized = rest.strip().lower()
            if normalized not in {"chat", "conversation", "review"}:
                raise ValueError("Use /mode chat or /mode review.")
            self.chat_mode = "review" if normalized == "review" else "conversation"
            self._print(f"chat mode set to {self.chat_mode}")
            return False
        if command == "plan":
            self._assert_no_mutating_job("plan generation")
            prompt = self._resolve_body(rest, label="plan")
            self._run_plan_generation(prompt)
            return False
        if command == "execute":
            self._assert_no_mutating_job("execution")
            self._start_execute()
            return False
        if command in {"pause", "stop"}:
            self._request_pause()
            return False
        if command == "wait":
            self._wait_for_job()
            return False
        if command == "debug":
            self._assert_no_mutating_job("manual debugger recovery")
            prompt = self._resolve_body(rest, label="debug")
            self._run_manual_recovery("run-manual-debugger", prompt)
            return False
        if command == "merge":
            self._assert_no_mutating_job("manual merger recovery")
            prompt = self._resolve_body(rest, label="merge")
            self._run_manual_recovery("run-manual-merger", prompt)
            return False
        if command in {"close", "closeout"}:
            self._assert_no_mutating_job("closeout")
            self._run_closeout()
            return False
        if command == "approve":
            self._assert_no_mutating_job("checkpoint approval")
            self._approve_checkpoint(rest)
            return False
        if command == "history":
            self._show_history(rest)
            return False
        if command == "report":
            self._write_report()
            return False
        if command == "checkpoints":
            self._show_checkpoints()
            return False
        raise ValueError(f"Unsupported action command: /{command}")

    def _print_help(self) -> None:
        self._print("/help                show this help")
        self._print("/plan [prompt]       generate a fresh execution plan")
        self._print("/execute             run the saved plan in the background")
        self._print("/debug [prompt]      run manual debugger recovery")
        self._print("/merge [prompt]      run manual merger recovery")
        self._print("/closeout            run closeout for the current plan")
        self._print("/approve [notes]     approve a pending checkpoint")
        self._print("/pause               request stop for the active execution job")
        self._print("/wait                wait for the active background job to finish")
        self._print("/flow                show the ASCII execution board")
        self._print("/status              show project and runtime status")
        self._print("/history [limit]     show recent block history")
        self._print("/report              write the latest JSON status report")
        self._print("/mode chat|review    switch plain-text chat mode")
        self._print("$show                redraw the flow board")
        self._print("$list                print a compact step table")
        self._print("$add TITLE :: DESC   append a new plan step")
        self._print("$set ST1 FIELD :: V  edit a step field")
        self._print("$drop ST2            remove a step")
        self._print("$swap ST1 ST2        reorder two steps")
        self._print("$closeout FIELD :: V edit closeout metadata")
        self._print("!show                print runtime settings")
        self._print("!set key=value ...   update runtime settings")
        self._print("!reset key ...       reset runtime keys to defaults")
        self._print("!providers           show provider/tooling status")
        self._print("@list                list managed projects")
        self._print("@open [path]         open or register a local project")
        self._print("@use selector        switch to a managed project")
        self._print("@where               print the selected project path")
        self._print("plain text           send a chat message without changing the plan")

    def _resolve_body(self, inline_text: str, *, label: str) -> str:
        if inline_text.strip():
            return inline_text.strip()
        self._print(f"enter {label} text, finish with a single '.' line")
        lines: list[str] = []
        while True:
            line = input(f"{label}> ")
            if line.strip() == ".":
                break
            lines.append(line)
        body = "\n".join(lines).strip()
        if not body:
            raise ValueError(f"{label} text is required.")
        return body

    def _assert_no_mutating_job(self, label: str) -> None:
        if self.active_job is not None:
            raise RuntimeError(f"{self.active_job.name} is already running; {label} is locked.")

    def _run_plan_generation(self, prompt: str) -> None:
        context, plan_state = self.orchestrator.generate_execution_plan(
            project_dir=self._require_context().metadata.repo_path,
            runtime=self.runtime,
            project_prompt=prompt,
            branch=self.current_branch,
            max_steps=max(1, int(self.runtime.max_blocks or 1)),
            origin_url=self.current_origin_url,
            progress_callback=self._planning_progress,
        )
        self._sync_from_context(context)
        self._print(f"planned {len(plan_state.steps)} step(s)")
        self._show_flow()

    def _planning_progress(
        self,
        _context: ProjectContext,
        event_type: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> None:
        stage_key = str((details or {}).get("stage_key", "")).strip()
        prefix = f"[{stage_key}]" if stage_key else f"[{event_type}]"
        self._print(f"{prefix} {message}")

    def _start_execute(self) -> None:
        plan_state = self._load_plan_state()
        if not plan_state.steps and str(plan_state.closeout_status).strip().lower() == "completed":
            raise RuntimeError("No pending work exists for the selected project.")
        payload = self._flow_payload(plan_state)
        self._start_job(
            "execute",
            lambda: run_command("run-plan", self.workspace_root, payload),
            allow_chat=True,
        )
        self._print("execution started in background; plain text chat stays available")

    def _wait_for_job(self) -> None:
        if self.active_job is None:
            self._print("no background job is running")
            return
        self.active_job.thread.join()
        self._drain_job()

    def _request_pause(self) -> None:
        if self.active_job is None or self.active_job.name != "execute":
            raise RuntimeError("No active execution job is running.")
        result = run_command(
            "request-stop",
            self.workspace_root,
            {
                "project_dir": str(self._require_context().metadata.repo_path),
                "source": "interactive-shell",
            },
        )
        self._print(f"pause requested: {result.get('run_control', {}).get('request_source', 'interactive-shell')}")

    def _run_manual_recovery(self, command_name: str, prompt: str) -> None:
        plan_state = self._load_plan_state()
        runtime = runtime_from_payload(
            {"extra_prompt": prompt},
            defaults=self.runtime,
        )
        run_command(command_name, self.workspace_root, self._flow_payload(plan_state, runtime=runtime))
        self._show_flow()

    def _run_closeout(self) -> None:
        run_command("run-closeout", self.workspace_root, self._flow_payload(self._load_plan_state()))
        self._show_flow()

    def _approve_checkpoint(self, raw_text: str) -> None:
        tokens = shlex.split(raw_text)
        push = True
        notes: list[str] = []
        for token in tokens:
            normalized = token.strip().lower()
            if normalized == "--no-push":
                push = False
                continue
            if normalized == "--push":
                push = True
                continue
            notes.append(token)
        context = self._require_context()
        result = self.orchestrator.approve_checkpoint(
            context.metadata.repo_url,
            context.metadata.branch,
            review_notes=" ".join(notes).strip(),
            push=push,
        )
        self._print(
            f"approved checkpoint {result.get('checkpoint_id', '') or result.get('title', '')} push={result.get('pushed', False)}"
        )
        self._show_flow()

    def _show_history(self, rest: str) -> None:
        limit = 10
        if rest.strip():
            limit = max(1, int(rest.strip()))
        self._print(Reporter(self._require_context()).render_history(limit=limit))

    def _write_report(self) -> None:
        path = Reporter(self._require_context()).write_status_report()
        self._print(str(path))

    def _show_checkpoints(self) -> None:
        context = self._require_context()
        payload = self.orchestrator.checkpoints(context.metadata.repo_url, context.metadata.branch)
        checkpoints = payload.get("checkpoints", []) if isinstance(payload, dict) else []
        if not checkpoints:
            self._print("No checkpoints recorded.")
            return
        for item in checkpoints:
            self._print(
                f"{item.get('checkpoint_id', '')} status={item.get('status', '')} "
                f"target={item.get('target_block', '')} title={item.get('title', '')}"
            )

    def _handle_flow_command(self, command_text: str) -> None:
        self._assert_no_mutating_job("flow editing")
        plan_state = deepcopy(self._load_plan_state())
        result = apply_flow_edit(plan_state, command_text)
        if command_text.split(maxsplit=1)[0].strip().lower() == "list":
            self._print(render_plan_table(plan_state))
            return
        if result.changed:
            self._save_plan_state(result.plan_state)
        self._print(result.message)
        self._show_flow()

    def _handle_settings_command(self, command_text: str) -> None:
        self._assert_no_mutating_job("runtime editing")
        if not command_text or command_text.strip().lower() == "show":
            self._show_runtime_settings()
            return
        tokens = shlex.split(command_text)
        if not tokens:
            self._show_runtime_settings()
            return
        action = tokens[0].strip().lower()
        if action == "providers":
            payload = run_command(
                "get-tooling-status",
                self.workspace_root,
                {"force_refresh": True, "refresh_codex_status": True},
            )
            self._print(self._format_provider_status(payload))
            return
        if action == "reset":
            self._reset_runtime_keys(tokens[1:])
            return
        if action == "set":
            tokens = tokens[1:]
        if not tokens:
            raise ValueError("Provide one or more key=value overrides.")
        overrides = parse_runtime_overrides(tokens)
        self.runtime = load_runtime_from_sources(
            config_payload=self.runtime.to_dict(),
            overrides=overrides,
        )
        self._persist_runtime()
        self._print("runtime updated")
        self._show_runtime_settings()

    def _reset_runtime_keys(self, keys: list[str]) -> None:
        if not keys:
            raise ValueError("Provide one or more runtime keys to reset.")
        defaults = RuntimeOptions().to_dict()
        payload = self.runtime.to_dict()
        for key in keys:
            normalized = str(key or "").strip()
            if normalized not in self._step_field_names:
                raise ValueError(f"Unknown runtime key: {normalized}")
            payload[normalized] = defaults.get(normalized)
        self.runtime = runtime_from_payload(payload)
        self._persist_runtime()
        self._print("runtime keys reset")
        self._show_runtime_settings()

    def _show_runtime_settings(self) -> None:
        self._print(
            f"provider={self.runtime.model_provider} model={self.runtime.model} "
            f"chat_provider={self.runtime.chat_model_provider or '-'} chat_model={self.runtime.chat_model or '-'}"
        )
        self._print(
            f"workflow_mode={self.runtime.workflow_mode} execution_mode={self.runtime.execution_mode} "
            f"effort={self.runtime.effort} planning_effort={self.runtime.planning_effort or self.runtime.effort}"
        )
        self._print(
            f"approval_mode={self.runtime.approval_mode} sandbox_mode={self.runtime.sandbox_mode} "
            f"max_blocks={self.runtime.max_blocks} test_cmd={self.runtime.test_cmd}"
        )
        self._print(
            f"parallel_mode={self.runtime.parallel_worker_mode} parallel_workers={self.runtime.parallel_workers} "
            f"checkpoint_every={self.runtime.checkpoint_interval_blocks} require_checkpoint_approval={self.runtime.require_checkpoint_approval}"
        )

    @staticmethod
    def _format_provider_status(payload: dict[str, Any]) -> str:
        lines: list[str] = []
        codex_status = payload.get("codex_status", {}) if isinstance(payload, dict) else {}
        tooling_statuses = payload.get("tooling_statuses", {}) if isinstance(payload, dict) else {}
        provider_statuses = codex_status.get("provider_statuses", {}) if isinstance(codex_status, dict) else {}
        for provider, status in sorted(provider_statuses.items()):
            if not isinstance(status, dict):
                continue
            lines.append(
                f"{provider}: available={bool(status.get('available'))} authenticated={bool(status.get('authenticated'))}"
            )
        if tooling_statuses:
            lines.append("")
            for tool, status in sorted(tooling_statuses.items()):
                if not isinstance(status, dict):
                    continue
                lines.append(f"tool:{tool} available={bool(status.get('available'))} version={status.get('version', '')}")
        return "\n".join(lines) if lines else "No provider status available."

    def _handle_project_command(self, command_text: str) -> None:
        self._assert_no_mutating_job("project switching")
        parts = command_text.split(maxsplit=1)
        action = parts[0].strip().lower() if parts and parts[0].strip() else "where"
        rest = parts[1].strip() if len(parts) > 1 else ""
        if action == "list":
            self._list_projects()
            return
        if action == "open":
            target = Path(rest).expanduser().resolve() if rest else Path.cwd().resolve()
            self._open_project(target)
            return
        if action == "use":
            self._use_project(rest)
            return
        if action == "where":
            if self.current_project_dir is None:
                self._print("no project selected")
            else:
                self._print(str(self.current_project_dir))
            return
        raise ValueError(f"Unsupported project command: @{action}")

    def _list_projects(self) -> None:
        projects = self.orchestrator.list_projects()
        if not projects:
            self._print("No managed projects found.")
            return
        for index, context in enumerate(projects, start=1):
            self._print(
                f"{index:>2}. {context.metadata.display_name or context.metadata.slug} "
                f"status={context.metadata.current_status} path={context.metadata.repo_path}"
            )

    def _open_project(self, project_dir: Path) -> None:
        if not project_dir.exists():
            raise FileNotFoundError(f"Project path does not exist: {project_dir}")
        context = self.orchestrator.setup_local_project(
            project_dir=project_dir,
            runtime=self.runtime,
            branch=self.current_branch,
            origin_url=self.current_origin_url,
            display_name=self.current_display_name or project_dir.name,
        )
        self._sync_from_context(context)
        self._print(f"opened {self._project_name()}")

    def _use_project(self, selector: str) -> None:
        if not selector.strip():
            raise ValueError("Provide an index, slug, repo id, or managed repo path.")
        projects = self.orchestrator.list_projects()
        normalized = selector.strip()
        if normalized.isdigit():
            index = int(normalized) - 1
            if not (0 <= index < len(projects)):
                raise ValueError(f"Project index out of range: {selector}")
            self._sync_from_context(projects[index])
            self._print(f"selected {self._project_name()}")
            return
        candidate_path = Path(normalized).expanduser()
        if candidate_path.exists():
            project = self.orchestrator.local_project(candidate_path.resolve())
            if project is None:
                raise ValueError(f"No managed project exists for {candidate_path.resolve()}.")
            self._sync_from_context(project)
            self._print(f"selected {self._project_name()}")
            return
        for project in projects:
            if normalized in {
                project.metadata.repo_id,
                project.metadata.slug,
                str(project.metadata.display_name or "").strip(),
            }:
                self._sync_from_context(project)
                self._print(f"selected {self._project_name()}")
                return
        raise ValueError(f"Could not find a project matching: {selector}")
