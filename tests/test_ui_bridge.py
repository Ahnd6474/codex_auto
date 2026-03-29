from __future__ import annotations

from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import unittest
from unittest import mock
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jakal_flow.cli import build_parser, main as cli_main, runtime_from_args
from jakal_flow.bridge_events import bridge_event_context
from jakal_flow.chat_sessions import CHAT_HOME_ENV_VAR, execute_conversation_turn, load_chat_sessions
from jakal_flow.errors import RuntimeConfigError
from jakal_flow.execution_control import ImmediateStopRequested
import jakal_flow.ui_bridge as ui_bridge
import jakal_flow.ui_bridge_payloads as ui_bridge_payloads
from jakal_flow.models import ExecutionPlanState, ExecutionStep, LoopState, ProjectContext, ProjectPaths, RepoMetadata, RuntimeOptions
from jakal_flow.share import share_server_status_payload
from jakal_flow.status_views import effective_project_status
from jakal_flow.ui_bridge import default_workspace_root, progress_caption, run_command, runtime_from_payload
from jakal_flow.step_models import (
    CLAUDE_DEFAULT_MODEL,
    DEEPSEEK_DEFAULT_MODEL,
    GEMINI_DEFAULT_MODEL,
    GLM_DEFAULT_MODEL,
    KIMI_DEFAULT_MODEL,
    MINIMAX_DEFAULT_MODEL,
    QWEN_CODE_DEFAULT_MODEL,
    provider_execution_preflight_error,
    provider_statuses_payload,
)
from jakal_flow.utils import read_jsonl
from jakal_flow.workspace import WorkspaceManager


def local_temp_root() -> Path:
    root = Path(__file__).resolve().parents[1] / ".tub"
    root.mkdir(parents=True, exist_ok=True)
    return root


class TemporaryTestDir:
    def __enter__(self) -> Path:
        self.path = local_temp_root() / f"c{uuid.uuid4().hex[:8]}"
        self.path.mkdir(parents=True, exist_ok=True)
        return self.path

    def __exit__(self, exc_type, exc, tb) -> None:
        shutil.rmtree(self.path, ignore_errors=True)


def fake_codex_snapshot() -> mock.Mock:
    payload = {
        "checked_at": "2026-03-26T00:00:00+00:00",
        "available": True,
        "model_catalog": [
            {
                "id": "auto",
                "model": "auto",
                "display_name": "Auto",
                "description": "Use Codex default model routing from the installed CLI.",
                "hidden": False,
                "is_default": True,
                "default_reasoning_effort": "medium",
                "supported_reasoning_efforts": ["low", "medium", "high", "xhigh"],
            },
            {
                "id": "gpt-5.3-codex-spark",
                "model": "gpt-5.3-codex-spark",
                "display_name": "GPT-5.3-Codex-Spark",
                "description": "Ultra-fast coding model.",
                "hidden": False,
                "is_default": False,
                "default_reasoning_effort": "high",
                "supported_reasoning_efforts": ["low", "medium", "high", "xhigh"],
            },
        ],
        "account": {
            "authenticated": True,
            "requires_openai_auth": True,
            "type": "chatgpt",
            "email": "demo@example.com",
            "plan_type": "pro",
        },
        "rate_limits": {
            "default_limit_id": "codex",
            "items": [
                {
                    "limit_id": "codex",
                    "limit_name": None,
                    "plan_type": "pro",
                    "primary": {
                        "used_percent": 11,
                        "remaining_percent": 89,
                        "window_duration_mins": 300,
                        "resets_at": "2026-03-26T12:00:00+00:00",
                    },
                    "secondary": None,
                    "credits": None,
                }
            ],
        },
        "error": "",
    }
    return mock.Mock(model_catalog=payload["model_catalog"], to_dict=mock.Mock(return_value=payload))


def build_test_project_context(
    temp_dir: Path,
    *,
    repo_id: str = "repo-1",
    slug: str = "repo-1",
    display_name: str = "Repo",
) -> ProjectContext:
    workspace_root = temp_dir / "workspace"
    project_root = workspace_root / "projects" / slug
    repo_dir = temp_dir / "repo"
    docs_dir = project_root / "docs"
    memory_dir = project_root / "memory"
    logs_dir = project_root / "logs"
    reports_dir = project_root / "reports"
    state_dir = project_root / "state"
    lineage_manifests_dir = state_dir / "lineage_manifests"

    for directory in (workspace_root, project_root, repo_dir, docs_dir, memory_dir, logs_dir, reports_dir, state_dir, lineage_manifests_dir):
        directory.mkdir(parents=True, exist_ok=True)

    for path, content in (
        (docs_dir / "PLAN.md", "# Plan\n"),
        (docs_dir / "SCOPE_GUARD.md", "# Scope Guard\n"),
        (docs_dir / "RESEARCH_NOTES.md", "# Research Notes\n"),
    ):
        path.write_text(content, encoding="utf-8")

    metadata = RepoMetadata(
        repo_id=repo_id,
        slug=slug,
        repo_url=f"https://example.invalid/{slug}.git",
        branch="main",
        project_root=project_root,
        repo_path=repo_dir,
        created_at="2026-03-29T00:00:00+00:00",
        current_status="setup_ready",
        repo_kind="local",
        display_name=display_name,
    )
    paths = ProjectPaths(
        workspace_root=workspace_root,
        projects_root=workspace_root / "projects",
        project_root=project_root,
        repo_dir=repo_dir,
        docs_dir=docs_dir,
        memory_dir=memory_dir,
        logs_dir=logs_dir,
        reports_dir=reports_dir,
        state_dir=state_dir,
        metadata_file=project_root / "metadata.json",
        project_config_file=project_root / "project_config.json",
        loop_state_file=state_dir / "LOOP_STATE.json",
        plan_file=docs_dir / "PLAN.md",
        mid_term_plan_file=docs_dir / "MID_TERM_PLAN.md",
        scope_guard_file=docs_dir / "SCOPE_GUARD.md",
        active_task_file=docs_dir / "ACTIVE_TASK.md",
        block_review_file=docs_dir / "BLOCK_REVIEW.md",
        checkpoint_timeline_file=docs_dir / "CHECKPOINT_TIMELINE.md",
        research_notes_file=docs_dir / "RESEARCH_NOTES.md",
        attempt_history_file=docs_dir / "attempt_history.md",
        success_patterns_file=memory_dir / "success_patterns.jsonl",
        failure_patterns_file=memory_dir / "failure_patterns.jsonl",
        task_summaries_file=memory_dir / "task_summaries.jsonl",
        pass_log_file=logs_dir / "passes.jsonl",
        block_log_file=logs_dir / "blocks.jsonl",
        checkpoint_state_file=state_dir / "CHECKPOINTS.json",
        execution_plan_file=state_dir / "EXECUTION_PLAN.json",
        lineage_state_file=state_dir / "LINEAGES.json",
        spine_file=state_dir / "SPINE.json",
        common_requirements_file=docs_dir / "COMMON_REQUIREMENTS.md",
        ml_mode_state_file=state_dir / "ML_MODE_STATE.json",
        ml_step_report_file=state_dir / "ML_STEP_REPORT.json",
        ml_experiment_reports_dir=state_dir / "ml_experiments",
        lineage_manifests_dir=lineage_manifests_dir,
        ui_control_file=state_dir / "UI_RUN_CONTROL.json",
        ui_event_log_file=logs_dir / "ui_events.jsonl",
        execution_flow_svg_file=docs_dir / "EXECUTION_FLOW.svg",
        closeout_report_file=docs_dir / "CLOSEOUT_REPORT.md",
        closeout_report_docx_file=reports_dir / "CLOSEOUT_REPORT.docx",
        closeout_report_pptx_file=reports_dir / "CLOSEOUT_REPORT.pptx",
        ml_experiment_report_file=docs_dir / "ML_EXPERIMENT_REPORT.md",
        ml_experiment_results_svg_file=docs_dir / "ML_EXPERIMENT_RESULTS.svg",
        shared_contracts_file=docs_dir / "SHARED_CONTRACTS.md",
    )
    runtime = RuntimeOptions(
        model_provider="openai",
        model="gpt-5.4",
        test_cmd="python -m unittest",
        max_blocks=5,
    )
    loop_state = LoopState(repo_id=repo_id, repo_slug=slug)
    return ProjectContext(metadata=metadata, runtime=runtime, paths=paths, loop_state=loop_state)


class UIBridgeTests(unittest.TestCase):
    def test_workspace_save_project_emits_bridge_ui_event_for_running_state(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            project_dir = temp_dir / "repo"
            workspace = WorkspaceManager(workspace_root)
            context = workspace.initialize_local_project(project_dir, "main", runtime_from_payload({}), display_name="Demo")
            context.metadata.current_status = "running:st1"
            context.metadata.last_run_at = "2026-03-28T10:00:00+00:00"
            context.loop_state.current_task = "Execute ST1"

            events: list[tuple[str, dict]] = []

            class Sink:
                def emit(self, event: str, payload: dict | None = None) -> None:
                    events.append((event, payload or {}))

            with bridge_event_context(Sink()):
                workspace.save_project(context)

            self.assertEqual(len(events), 1)
            event_name, payload = events[0]
            self.assertEqual(event_name, "project.ui_event")
            self.assertEqual(payload["repo_id"], context.metadata.repo_id)
            self.assertEqual(payload["project_dir"], str(context.metadata.repo_path))
            self.assertEqual(payload["project_status"], "running:st1")
            self.assertEqual(payload["event"]["event_type"], "project-state-synced")
            self.assertEqual(payload["event"]["details"]["current_task"], "Execute ST1")
            self.assertTrue(payload["event"]["details"]["last_run_at"])

    def test_workspace_save_project_skips_bridge_ui_event_for_idle_state(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            project_dir = temp_dir / "repo"
            workspace = WorkspaceManager(workspace_root)
            context = workspace.initialize_local_project(project_dir, "main", runtime_from_payload({}), display_name="Demo")
            context.metadata.current_status = "plan_ready"
            context.loop_state.current_task = None
            context.loop_state.pending_checkpoint_approval = False

            events: list[tuple[str, dict]] = []

            class Sink:
                def emit(self, event: str, payload: dict | None = None) -> None:
                    events.append((event, payload or {}))

            with bridge_event_context(Sink()):
                workspace.save_project(context)

            self.assertEqual(events, [])

    def test_local_project_logs_are_written_under_repo_root_folder(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            project_dir = temp_dir / "repo"
            workspace = WorkspaceManager(workspace_root)
            context = workspace.initialize_local_project(project_dir, "main", runtime_from_payload({}), display_name="Demo")

            self.assertEqual(context.paths.logs_dir, project_dir.resolve() / "jakal-flow-logs")
            self.assertEqual(context.paths.pass_log_file, project_dir.resolve() / "jakal-flow-logs" / "passes.jsonl")
            self.assertEqual(context.paths.block_log_file, project_dir.resolve() / "jakal-flow-logs" / "blocks.jsonl")
            self.assertEqual(context.paths.ui_event_log_file, project_dir.resolve() / "jakal-flow-logs" / "ui_events.jsonl")

            ui_bridge.append_ui_event(context, "step-started", "Running ST1", {"step_id": "ST1"})

            events = read_jsonl(project_dir.resolve() / "jakal-flow-logs" / "ui_events.jsonl")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event_type"], "step-started")
            self.assertEqual(events[0]["details"]["step_id"], "ST1")

    def test_loading_local_project_migrates_legacy_workspace_logs_into_repo_root_folder(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            project_dir = temp_dir / "repo"
            workspace = WorkspaceManager(workspace_root)
            context = workspace.initialize_local_project(project_dir, "main", runtime_from_payload({}), display_name="Demo")

            legacy_logs_dir = context.paths.project_root / "logs"
            legacy_logs_dir.mkdir(parents=True, exist_ok=True)
            (legacy_logs_dir / "passes.jsonl").write_text('{"event":"legacy"}\n', encoding="utf-8")
            legacy_block_dir = legacy_logs_dir / "block_0001"
            legacy_block_dir.mkdir(parents=True, exist_ok=True)
            (legacy_block_dir / "debug.txt").write_text("legacy-debug", encoding="utf-8")

            context.paths.logs_dir.mkdir(parents=True, exist_ok=True)
            context.paths.pass_log_file.write_text('{"event":"current"}\n', encoding="utf-8")

            loaded = workspace.load_project_from_root(context.paths.project_root)

            self.assertEqual(loaded.paths.logs_dir, project_dir.resolve() / "jakal-flow-logs")
            self.assertFalse(legacy_logs_dir.exists())
            self.assertTrue((loaded.paths.logs_dir / "block_0001" / "debug.txt").exists())
            self.assertEqual((loaded.paths.logs_dir / "block_0001" / "debug.txt").read_text(encoding="utf-8"), "legacy-debug")
            self.assertEqual(
                read_jsonl(loaded.paths.pass_log_file),
                [{"event": "legacy"}, {"event": "current"}],
            )

    def test_start_share_server_process_replaces_stale_state_file(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            workspace_root.mkdir(parents=True, exist_ok=True)
            stale_port = 54321
            stale_pid = 999999
            (workspace_root / "share_server.json").write_text(
                json.dumps(
                    {
                        "host": "0.0.0.0",
                        "port": stale_port,
                        "pid": stale_pid,
                        "started_at": "2026-03-28T00:00:00+00:00",
                        "viewer_path": "/share/view",
                    }
                ),
                encoding="utf-8",
            )

            try:
                status = ui_bridge.start_share_server_process(workspace_root)
                self.assertTrue(status["running"])
                self.assertNotEqual(status["pid"], stale_pid)
                self.assertNotEqual(status["port"], stale_port)
                stored_state = json.loads((workspace_root / "share_server.json").read_text(encoding="utf-8"))
                self.assertEqual(stored_state["pid"], status["pid"])
                self.assertEqual(stored_state["port"], status["port"])
            finally:
                ui_bridge.stop_share_server_process(workspace_root)

    def test_default_workspace_root_prefers_explicit_jakal_flow_env(self) -> None:
        with TemporaryTestDir() as temp_dir:
            explicit = temp_dir / "custom-workspace"
            with mock.patch.dict(os.environ, {"JAKAL_FLOW_GUI_WORKSPACE": str(explicit)}, clear=True), mock.patch(
                "jakal_flow.ui_bridge.Path.cwd",
                return_value=temp_dir,
            ), mock.patch(
                "jakal_flow.ui_bridge.Path.home",
                return_value=temp_dir / "home",
            ):
                resolved = default_workspace_root()

        self.assertEqual(resolved, explicit.resolve())

    def test_default_workspace_root_ignores_legacy_codex_auto_locations(self) -> None:
        with TemporaryTestDir() as temp_dir:
            legacy = temp_dir / ".codex-auto-workspace"
            legacy.mkdir(parents=True, exist_ok=True)
            home_dir = temp_dir / "home"
            home_dir.mkdir(parents=True, exist_ok=True)
            with mock.patch.dict(os.environ, {"CODEX_AUTO_GUI_WORKSPACE": str(legacy)}, clear=True), mock.patch(
                "jakal_flow.ui_bridge.Path.cwd",
                return_value=temp_dir,
            ), mock.patch(
                "jakal_flow.ui_bridge.Path.home",
                return_value=home_dir,
            ):
                resolved = default_workspace_root()

        self.assertEqual(resolved, (home_dir / ".jakal-flow-workspace").resolve())

    def test_progress_caption_reports_ready_nodes_for_parallel_dag(self) -> None:
        caption = progress_caption(
            ExecutionPlanState(
                execution_mode="parallel",
                steps=[
                    ExecutionStep(step_id="ST1", title="Root", status="completed"),
                    ExecutionStep(step_id="ST2", title="Frontend", depends_on=["ST1"], owned_paths=["desktop/src"]),
                    ExecutionStep(step_id="ST3", title="Backend", depends_on=["ST1"], owned_paths=["src/jakal_flow"]),
                    ExecutionStep(step_id="ST4", title="Closeout", depends_on=["ST2", "ST3"], owned_paths=["docs"]),
                ],
            )
        )

        self.assertEqual(caption, "Completed 1/4 steps, ready: ST2, ST3")

    def test_progress_caption_reports_running_nodes_for_parallel_dag(self) -> None:
        caption = progress_caption(
            ExecutionPlanState(
                execution_mode="parallel",
                steps=[
                    ExecutionStep(step_id="ST1", title="Root", status="completed"),
                    ExecutionStep(step_id="ST2", title="Frontend", depends_on=["ST1"], owned_paths=["desktop/src"], status="running"),
                    ExecutionStep(step_id="ST3", title="Backend", depends_on=["ST1"], owned_paths=["src/jakal_flow"], status="running"),
                ],
            )
        )

        self.assertEqual(caption, "Completed 1/3 steps, running: ST2, ST3")

    def test_progress_caption_reports_integrating_nodes_for_parallel_dag(self) -> None:
        caption = progress_caption(
            ExecutionPlanState(
                execution_mode="parallel",
                steps=[
                    ExecutionStep(step_id="ST1", title="Root", status="completed"),
                    ExecutionStep(step_id="ST2", title="Frontend", depends_on=["ST1"], owned_paths=["desktop/src"], status="integrating"),
                    ExecutionStep(step_id="ST3", title="Backend", depends_on=["ST1"], owned_paths=["src/jakal_flow"], status="running"),
                ],
            )
        )

        self.assertEqual(caption, "Completed 1/3 steps, running: ST3; integrating: ST2")

    def test_effective_project_status_prefers_parallel_plan_status_when_steps_are_running(self) -> None:
        status = effective_project_status(
            "running:st2",
            ExecutionPlanState(
                execution_mode="parallel",
                steps=[
                    ExecutionStep(step_id="ST1", title="Root", status="completed"),
                    ExecutionStep(step_id="ST2", title="Frontend", depends_on=["ST1"], owned_paths=["desktop/src"], status="running"),
                    ExecutionStep(step_id="ST3", title="Backend", depends_on=["ST1"], owned_paths=["src/jakal_flow"], status="running"),
                ],
            ),
            mock.Mock(pending_checkpoint_approval=False),
        )

        self.assertEqual(status, "running:parallel")

    def test_effective_project_status_preserves_explicit_merge_phase(self) -> None:
        status = effective_project_status(
            "running:merging",
            ExecutionPlanState(
                execution_mode="parallel",
                steps=[
                    ExecutionStep(step_id="ST1", title="Root", status="completed"),
                    ExecutionStep(step_id="ST2", title="Frontend", depends_on=["ST1"], owned_paths=["desktop/src"], status="integrating"),
                    ExecutionStep(step_id="ST3", title="Backend", depends_on=["ST1"], owned_paths=["src/jakal_flow"], status="running"),
                ],
            ),
            mock.Mock(pending_checkpoint_approval=False),
        )

        self.assertEqual(status, "running:merging")

    def test_effective_project_status_clears_stale_running_step_when_plan_is_idle(self) -> None:
        status = effective_project_status(
            "running:st1",
            ExecutionPlanState(
                execution_mode="parallel",
                steps=[
                    ExecutionStep(step_id="ST1", title="Root", status="completed"),
                    ExecutionStep(step_id="ST2", title="Frontend", status="pending"),
                ],
            ),
            mock.Mock(pending_checkpoint_approval=False),
        )

        self.assertEqual(status, "plan_ready")

    def test_runtime_from_payload_coerces_invalid_scalar_values(self) -> None:
        runtime = runtime_from_payload(
            {
                "model": "gpt-5.4-mini",
                "model_preset": "missing",
                "max_blocks": "not-a-number",
                "allow_push": "false",
                "require_checkpoint_approval": "true",
                "execution_mode": "PARALLEL",
                "parallel_workers": "bogus",
                "parallel_memory_per_worker_gib": "bogus",
                "no_progress_limit": "-3",
                "regression_limit": "bogus",
                "empty_cycle_limit": 0,
                "checkpoint_interval_blocks": "0",
                "optimization_mode": "turbo",
                "optimization_large_file_lines": "0",
                "optimization_long_function_lines": "bogus",
                "optimization_duplicate_block_lines": 1,
                "optimization_max_files": "0",
                "allow_background_queue": "false",
                "background_queue_priority": "7",
            }
        )

        self.assertEqual(runtime.model, "gpt-5.4-mini")
        self.assertEqual(runtime.model_preset, "")
        self.assertEqual(runtime.max_blocks, 5)
        self.assertFalse(runtime.allow_push)
        self.assertTrue(runtime.auto_merge_pull_request)
        self.assertTrue(runtime.require_checkpoint_approval)
        self.assertEqual(runtime.execution_mode, "parallel")
        self.assertEqual(runtime.parallel_worker_mode, "manual")
        self.assertEqual(runtime.parallel_workers, 2)
        self.assertEqual(runtime.parallel_memory_per_worker_gib, 3)
        self.assertEqual(runtime.no_progress_limit, 1)
        self.assertEqual(runtime.regression_limit, 3)
        self.assertEqual(runtime.empty_cycle_limit, 1)
        self.assertEqual(runtime.checkpoint_interval_blocks, 1)
        self.assertEqual(runtime.optimization_mode, "light")
        self.assertEqual(runtime.optimization_large_file_lines, 50)
        self.assertEqual(runtime.optimization_long_function_lines, 80)
        self.assertEqual(runtime.optimization_duplicate_block_lines, 3)
        self.assertEqual(runtime.optimization_max_files, 1)
        self.assertFalse(runtime.allow_background_queue)
        self.assertEqual(runtime.background_queue_priority, 7)

    def test_runtime_from_payload_defaults_parallel_workers_to_auto_mode(self) -> None:
        runtime = runtime_from_payload({"execution_mode": "parallel"})

        self.assertEqual(runtime.execution_mode, "parallel")
        self.assertEqual(runtime.parallel_worker_mode, "auto")
        self.assertEqual(runtime.parallel_workers, 0)
        self.assertEqual(runtime.parallel_memory_per_worker_gib, 3)

    def test_runtime_from_payload_ignores_unknown_runtime_keys(self) -> None:
        runtime = runtime_from_payload(
            {
                "model_provider": "ensemble",
                "ensemble_claude_model": "claude-3.7-sonnet",
                "future_runtime_field": "ignored",
            }
        )

        self.assertEqual(runtime.model_provider, "ensemble")
        self.assertEqual(runtime.ensemble_claude_model, "claude-3.7-sonnet")

    def test_workspace_load_project_ignores_unknown_runtime_keys(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            project_dir = temp_dir / "repo"
            workspace = WorkspaceManager(workspace_root)
            context = workspace.initialize_local_project(project_dir, "main", RuntimeOptions())

            config = json.loads(context.paths.project_config_file.read_text(encoding="utf-8"))
            config["ensemble_claude_model"] = "claude-3.7-sonnet"
            config["future_runtime_field"] = "ignored"
            context.paths.project_config_file.write_text(json.dumps(config), encoding="utf-8")

            reloaded = workspace.load_project_by_id(context.metadata.repo_id)

        self.assertEqual(reloaded.runtime.ensemble_claude_model, "claude-3.7-sonnet")

    def test_runtime_from_payload_uses_platform_default_codex_path_when_missing(self) -> None:
        with mock.patch("jakal_flow.ui_bridge.default_codex_path", return_value="codex"):
            runtime = runtime_from_payload({"execution_mode": "parallel", "codex_path": ""})

        self.assertEqual(runtime.codex_path, "codex")

    def test_common_project_inputs_recovers_project_dir_from_repo_id(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            workspace = WorkspaceManager(workspace_root)
            context = workspace.initialize_local_project(repo_dir, "main", RuntimeOptions())
            orchestrator = ui_bridge.orchestrator_for(workspace_root)

            project_dir, runtime, branch, origin_url, display_name = ui_bridge.common_project_inputs(
                {
                    "repo_id": context.metadata.repo_id,
                    "project_dir": "",
                    "runtime": {"model": "gpt-5.4"},
                },
                orchestrator,
            )

        self.assertEqual(project_dir, repo_dir.resolve())
        self.assertEqual(runtime.model, "gpt-5.4")
        self.assertEqual(branch, "main")
        self.assertEqual(origin_url, "")
        self.assertEqual(display_name, "")

    def test_runtime_from_payload_upgrades_legacy_serial_mode_to_parallel(self) -> None:
        runtime = runtime_from_payload({"execution_mode": "serial"})

        self.assertEqual(runtime.execution_mode, "parallel")
        self.assertEqual(runtime.parallel_worker_mode, "auto")

    def test_runtime_from_payload_accepts_manual_parallel_worker_mode(self) -> None:
        runtime = runtime_from_payload(
            {
                "execution_mode": "parallel",
                "parallel_worker_mode": "manual",
                "parallel_workers": "3",
                "parallel_memory_per_worker_gib": "5",
            }
        )

        self.assertEqual(runtime.execution_mode, "parallel")
        self.assertEqual(runtime.parallel_worker_mode, "manual")
        self.assertEqual(runtime.parallel_workers, 3)
        self.assertEqual(runtime.parallel_memory_per_worker_gib, 5)

    def test_runtime_from_payload_accepts_tenth_gib_memory_budget(self) -> None:
        runtime = runtime_from_payload(
            {
                "execution_mode": "parallel",
                "parallel_worker_mode": "manual",
                "parallel_workers": "2",
                "parallel_memory_per_worker_gib": "1.55",
            }
        )

        self.assertEqual(runtime.execution_mode, "parallel")
        self.assertEqual(runtime.parallel_worker_mode, "manual")
        self.assertEqual(runtime.parallel_workers, 2)
        self.assertAlmostEqual(runtime.parallel_memory_per_worker_gib, 1.6)

    def test_runtime_from_payload_defaults_planning_effort_to_execution_effort(self) -> None:
        runtime = runtime_from_payload(
            {
                "model": "gpt-5.4",
                "effort": "high",
            }
        )

        self.assertEqual(runtime.effort, "high")
        self.assertEqual(runtime.planning_effort, "high")

    def test_cli_runtime_from_args_loads_toml_config_and_set_overrides(self) -> None:
        with TemporaryTestDir() as temp_dir:
            config_path = temp_dir / "runtime.toml"
            config_path.write_text(
                "\n".join(
                    [
                        "[runtime]",
                        'model_provider = "gemini"',
                        'model = "gemini-3-flash-preview"',
                        "max_blocks = 7",
                        "allow_push = true",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            args = build_parser().parse_args(
                [
                    "run",
                    "--repo-url",
                    "https://example.com/demo.git",
                    "--branch",
                    "main",
                    "--config",
                    str(config_path),
                    "--set",
                    "max_blocks=2",
                    "--set",
                    "allow_push=false",
                ]
            )

            runtime = runtime_from_args(args)

        self.assertEqual(runtime.model_provider, "gemini")
        self.assertEqual(runtime.model, "gemini-3-flash-preview")
        self.assertEqual(runtime.max_blocks, 2)
        self.assertFalse(runtime.allow_push)

    def test_cli_runtime_from_args_rejects_invalid_config_file(self) -> None:
        with TemporaryTestDir() as temp_dir:
            config_path = temp_dir / "runtime.json"
            config_path.write_text("{not-json", encoding="utf-8")
            args = build_parser().parse_args(
                [
                    "run",
                    "--repo-url",
                    "https://example.com/demo.git",
                    "--branch",
                    "main",
                    "--config",
                    str(config_path),
                ]
            )

            with self.assertRaises(RuntimeConfigError):
                runtime_from_args(args)

    def test_provider_statuses_payload_requires_all_three_installed_backends_for_ensemble(self) -> None:
        fake_snapshot = mock.Mock(
            to_dict=mock.Mock(
                return_value={
                    "available": True,
                    "account": {"authenticated": True},
                    "error": "",
                }
            )
        )
        with mock.patch("jakal_flow.step_models.fetch_codex_backend_snapshot", return_value=fake_snapshot), mock.patch(
            "jakal_flow.step_models._command_available",
            side_effect=lambda command: str(command).strip().lower() in {"codex.cmd", "gemini.cmd"},
        ), mock.patch("jakal_flow.step_models._openai_auth_env_configured", return_value=True), mock.patch(
            "jakal_flow.step_models._claude_auth_env_configured",
            return_value=False,
        ), mock.patch("jakal_flow.step_models._gemini_auth_env_configured", return_value=True), mock.patch(
            "jakal_flow.step_models._gemini_settings_file_configured",
            return_value=False,
        ), mock.patch("jakal_flow.step_models.discover_local_model_catalog", return_value=[]):
            statuses = provider_statuses_payload()

        self.assertTrue(statuses["openai"]["available"])
        self.assertFalse(statuses["claude"]["available"])
        self.assertTrue(statuses["gemini"]["available"])
        self.assertFalse(statuses["ensemble"]["available"])
        self.assertIn("missing claude", statuses["ensemble"]["reason"].lower())
        self.assertFalse(statuses["deepseek"]["available"])
        self.assertTrue(statuses["openrouter"]["available"])

    def test_provider_statuses_payload_accepts_windows_claude_executable_without_cmd_shim(self) -> None:
        fake_snapshot = mock.Mock(
            to_dict=mock.Mock(
                return_value={
                    "available": True,
                    "account": {"authenticated": True},
                    "error": "",
                }
            )
        )
        with mock.patch("jakal_flow.step_models.resolve_codex_path",
            side_effect=lambda command: r"C:\Users\alber\.local\bin\claude.exe" if str(command).strip().lower() == "claude.cmd" else command,
        ), mock.patch(
            "jakal_flow.step_models._openai_auth_env_configured",
            return_value=True,
        ), mock.patch(
            "jakal_flow.step_models._claude_auth_env_configured",
            return_value=False,
        ), mock.patch(
            "jakal_flow.step_models._gemini_auth_env_configured",
            return_value=True,
        ), mock.patch(
            "jakal_flow.step_models._gemini_settings_file_configured",
            return_value=False,
        ), mock.patch(
            "jakal_flow.step_models.discover_local_model_catalog",
            return_value=[],
        ), mock.patch(
            "jakal_flow.step_models.Path.exists",
            autospec=True,
            side_effect=lambda path: str(path).lower() == r"c:\users\alber\.local\bin\claude.exe",
        ), mock.patch(
            "jakal_flow.step_models.shutil.which",
            side_effect=lambda command: {"codex.cmd": r"C:\tools\codex.cmd", "gemini.cmd": r"C:\tools\gemini.cmd"}.get(str(command).strip().lower()),
        ):
            statuses = provider_statuses_payload(fetch_snapshot=lambda _command: fake_snapshot)

        self.assertTrue(statuses["claude"]["available"])
        self.assertTrue(statuses["claude"]["usable"])
        self.assertTrue(statuses["deepseek"]["available"])
        self.assertTrue(statuses["ensemble"]["available"])

    def test_provider_statuses_payload_marks_openai_unusable_when_quota_is_exhausted(self) -> None:
        fake_snapshot = mock.Mock(
            to_dict=mock.Mock(
                return_value={
                    "available": True,
                    "account": {"authenticated": True},
                    "rate_limits": {
                        "default_limit_id": "codex",
                        "items": [
                            {
                                "limit_id": "codex",
                                "primary": {
                                    "remaining_percent": 0,
                                    "used_percent": 100,
                                    "resets_at": "2026-03-30T00:00:00+00:00",
                                },
                            }
                        ],
                    },
                    "error": "",
                }
            )
        )
        with mock.patch(
            "jakal_flow.step_models._command_available",
            side_effect=lambda command: str(command).strip().lower() == "codex.cmd",
        ), mock.patch(
            "jakal_flow.step_models._openai_auth_env_configured",
            return_value=False,
        ), mock.patch(
            "jakal_flow.step_models._claude_auth_env_configured",
            return_value=False,
        ), mock.patch(
            "jakal_flow.step_models._gemini_auth_env_configured",
            return_value=False,
        ), mock.patch(
            "jakal_flow.step_models._gemini_settings_file_configured",
            return_value=False,
        ), mock.patch(
            "jakal_flow.step_models.discover_local_model_catalog",
            return_value=[],
        ):
            statuses = provider_statuses_payload(fetch_snapshot=lambda _command: fake_snapshot)

        self.assertTrue(statuses["openai"]["available"])
        self.assertFalse(statuses["openai"]["usable"])
        self.assertEqual(statuses["openai"]["quota_available"], False)
        self.assertIn("quota window is exhausted", statuses["openai"]["reason"].lower())

    def test_provider_execution_preflight_error_blocks_openai_when_quota_is_exhausted(self) -> None:
        fake_snapshot = mock.Mock(
            to_dict=mock.Mock(
                return_value={
                    "available": True,
                    "account": {"authenticated": True},
                    "rate_limits": {
                        "default_limit_id": "codex",
                        "items": [
                            {
                                "limit_id": "codex",
                                "primary": {
                                    "remaining_percent": 0,
                                    "used_percent": 100,
                                    "resets_at": "2026-03-30T00:00:00+00:00",
                                },
                            }
                        ],
                    },
                    "error": "",
                }
            )
        )
        with mock.patch("jakal_flow.step_models._command_available", return_value=True), mock.patch(
            "jakal_flow.step_models.fetch_codex_backend_snapshot",
            return_value=fake_snapshot,
        ):
            error = provider_execution_preflight_error("openai", codex_path="codex.cmd")

        self.assertIn("quota window is exhausted", error.lower())

    def test_bootstrap_payload_includes_provider_statuses(self) -> None:
        with TemporaryTestDir() as temp_dir, mock.patch(
            "jakal_flow.ui_bridge._codex_snapshot_service",
            new=mock.Mock(get_snapshot=mock.Mock(return_value=fake_codex_snapshot())),
        ), mock.patch(
            "jakal_flow.ui_bridge.provider_statuses_payload",
            return_value={"openai": {"available": True}},
        ):
            payload = ui_bridge.bootstrap_payload(temp_dir / "workspace")

        self.assertIn("provider_statuses", payload["codex_status"])
        self.assertEqual(payload["codex_status"]["provider_statuses"]["openai"]["available"], True)

    def test_runtime_from_payload_normalizes_legacy_auto_model_presets(self) -> None:
        runtime = runtime_from_payload(
            {
                "model": "auto",
                "model_preset": "auto-high",
                "effort": "medium",
            }
        )

        self.assertEqual(runtime.model, "auto")
        self.assertEqual(runtime.model_preset, "high")
        self.assertEqual(runtime.effort, "high")

    def test_runtime_from_payload_coerces_fast_mode_flag(self) -> None:
        runtime = runtime_from_payload(
            {
                "model": "gpt-5.4",
                "use_fast_mode": "true",
            }
        )

        self.assertEqual(runtime.model, "gpt-5.4")
        self.assertTrue(runtime.use_fast_mode)

    def test_runtime_from_payload_coerces_word_report_flag(self) -> None:
        runtime = runtime_from_payload(
            {
                "model": "gpt-5.4",
                "generate_word_report": "true",
            }
        )

        self.assertEqual(runtime.model, "gpt-5.4")
        self.assertTrue(runtime.generate_word_report)

    def test_runtime_from_payload_coerces_save_project_logs_flag(self) -> None:
        runtime = runtime_from_payload(
            {
                "model": "gpt-5.4",
                "save_project_logs": "true",
            }
        )

        self.assertEqual(runtime.model, "gpt-5.4")
        self.assertTrue(runtime.save_project_logs)

    def test_runtime_from_payload_normalizes_local_model_provider(self) -> None:
        runtime = runtime_from_payload(
            {
                "model_provider": "oss",
                "local_model_provider": "",
                "model": "qwen2.5-coder:0.5b",
                "model_preset": "high",
            }
        )

        self.assertEqual(runtime.model_provider, "oss")
        self.assertEqual(runtime.local_model_provider, "ollama")
        self.assertEqual(runtime.model, "qwen2.5-coder:0.5b")
        self.assertEqual(runtime.model_preset, "")

    def test_runtime_from_payload_accepts_ollama_provider_alias(self) -> None:
        runtime = runtime_from_payload(
            {
                "model_provider": "ollama",
                "local_model_provider": "lmstudio",
                "model": "qwen2.5-coder:0.5b",
            }
        )

        self.assertEqual(runtime.model_provider, "ollama")
        self.assertEqual(runtime.local_model_provider, "ollama")
        self.assertEqual(runtime.model, "qwen2.5-coder:0.5b")

    def test_provider_statuses_payload_exposes_ollama_status_separately(self) -> None:
        local_models = [
            {"model": "qwen2.5-coder:0.5b", "local_provider": "ollama"},
            {"model": "deepseek-r1:8b", "local_provider": "ollama"},
        ]
        fake_snapshot = mock.Mock(
            to_dict=mock.Mock(
                return_value={
                    "available": True,
                    "account": {"authenticated": True},
                    "error": "",
                }
            )
        )
        with mock.patch(
            "jakal_flow.step_models._command_available",
            side_effect=lambda command: str(command).strip().lower() == "codex.cmd",
        ), mock.patch(
            "jakal_flow.step_models._openai_auth_env_configured",
            return_value=True,
        ), mock.patch(
            "jakal_flow.step_models._claude_auth_env_configured",
            return_value=False,
        ), mock.patch(
            "jakal_flow.step_models._gemini_auth_env_configured",
            return_value=False,
        ), mock.patch(
            "jakal_flow.step_models._gemini_settings_file_configured",
            return_value=False,
        ), mock.patch(
            "jakal_flow.step_models.discover_local_model_catalog",
            return_value=local_models,
        ):
            statuses = provider_statuses_payload(fetch_snapshot=lambda _command: fake_snapshot)

        self.assertTrue(statuses["ollama"]["available"])
        self.assertTrue(statuses["ollama"]["usable"])
        self.assertEqual(statuses["ollama"]["default_model"], "qwen2.5-coder:0.5b")
        self.assertIn("ollama", statuses["ollama"]["reason"].lower())

    def test_runtime_from_payload_normalizes_ml_workflow_values(self) -> None:
        runtime = runtime_from_payload(
            {
                "workflow_mode": "ML",
                "ml_max_cycles": "0",
                "execution_mode": "parallel",
            }
        )

        self.assertEqual(runtime.workflow_mode, "ml")
        self.assertEqual(runtime.ml_max_cycles, 1)
        self.assertEqual(runtime.execution_mode, "parallel")

    def test_runtime_from_payload_applies_openrouter_defaults(self) -> None:
        runtime = runtime_from_payload(
            {
                "model_provider": "openrouter",
                "model_slug_input": "openai/gpt-4.1-mini",
                "billing_mode": "token",
            }
        )

        self.assertEqual(runtime.model_provider, "openrouter")
        self.assertEqual(runtime.provider_base_url, "https://openrouter.ai/api/v1")
        self.assertEqual(runtime.provider_api_key_env, "OPENROUTER_API_KEY")
        self.assertEqual(runtime.model, "openai/gpt-4.1-mini")
        self.assertEqual(runtime.billing_mode, "token")

    def test_runtime_from_payload_applies_gemini_defaults(self) -> None:
        runtime = runtime_from_payload(
            {
                "model_provider": "gemini",
            }
        )

        self.assertEqual(runtime.model_provider, "gemini")
        self.assertEqual(runtime.provider_api_key_env, "GEMINI_API_KEY")
        self.assertEqual(runtime.provider_base_url, "")
        self.assertEqual(runtime.codex_path, "gemini.cmd" if os.name == "nt" else "gemini")
        self.assertEqual(runtime.model, GEMINI_DEFAULT_MODEL)
        self.assertEqual(runtime.model_slug_input, GEMINI_DEFAULT_MODEL)

    def test_runtime_from_payload_applies_claude_defaults(self) -> None:
        runtime = runtime_from_payload(
            {
                "model_provider": "claude",
            }
        )

        self.assertEqual(runtime.model_provider, "claude")
        self.assertEqual(runtime.provider_api_key_env, "ANTHROPIC_API_KEY")
        self.assertEqual(runtime.provider_base_url, "")
        self.assertEqual(runtime.codex_path, "claude.cmd" if os.name == "nt" else "claude")
        self.assertEqual(runtime.model, CLAUDE_DEFAULT_MODEL)
        self.assertEqual(runtime.model_slug_input, CLAUDE_DEFAULT_MODEL)

    def test_runtime_from_payload_applies_qwen_code_defaults(self) -> None:
        runtime = runtime_from_payload(
            {
                "model_provider": "qwen_code",
            }
        )

        self.assertEqual(runtime.model_provider, "qwen_code")
        self.assertEqual(runtime.provider_api_key_env, "DASHSCOPE_API_KEY")
        self.assertEqual(runtime.provider_base_url, "https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.assertEqual(runtime.codex_path, "qwen.cmd" if os.name == "nt" else "qwen")
        self.assertEqual(runtime.model, QWEN_CODE_DEFAULT_MODEL)
        self.assertEqual(runtime.model_slug_input, QWEN_CODE_DEFAULT_MODEL)

    def test_runtime_from_payload_applies_deepseek_defaults(self) -> None:
        runtime = runtime_from_payload(
            {
                "model_provider": "deepseek",
            }
        )

        self.assertEqual(runtime.model_provider, "deepseek")
        self.assertEqual(runtime.provider_api_key_env, "DEEPSEEK_API_KEY")
        self.assertEqual(runtime.provider_base_url, "https://api.deepseek.com/anthropic")
        self.assertEqual(runtime.codex_path, "claude.cmd" if os.name == "nt" else "claude")
        self.assertEqual(runtime.model, DEEPSEEK_DEFAULT_MODEL)
        self.assertEqual(runtime.model_slug_input, DEEPSEEK_DEFAULT_MODEL)

    def test_runtime_from_payload_applies_kimi_defaults(self) -> None:
        runtime = runtime_from_payload(
            {
                "model_provider": "kimi",
            }
        )

        self.assertEqual(runtime.model_provider, "kimi")
        self.assertEqual(runtime.provider_api_key_env, "MOONSHOT_API_KEY")
        self.assertEqual(runtime.provider_base_url, "https://api.moonshot.cn/v1")
        self.assertEqual(runtime.codex_path, "codex.cmd" if os.name == "nt" else "codex")
        self.assertEqual(runtime.model, KIMI_DEFAULT_MODEL)
        self.assertEqual(runtime.model_slug_input, KIMI_DEFAULT_MODEL)

    def test_runtime_from_payload_applies_minimax_defaults(self) -> None:
        runtime = runtime_from_payload(
            {
                "model_provider": "minimax",
            }
        )

        self.assertEqual(runtime.model_provider, "minimax")
        self.assertEqual(runtime.provider_api_key_env, "MINIMAX_API_KEY")
        self.assertEqual(runtime.provider_base_url, "https://api.minimax.io/anthropic/v1")
        self.assertEqual(runtime.codex_path, "claude.cmd" if os.name == "nt" else "claude")
        self.assertEqual(runtime.model, MINIMAX_DEFAULT_MODEL)
        self.assertEqual(runtime.model_slug_input, MINIMAX_DEFAULT_MODEL)

    def test_runtime_from_payload_applies_glm_defaults(self) -> None:
        runtime = runtime_from_payload(
            {
                "model_provider": "glm",
            }
        )

        self.assertEqual(runtime.model_provider, "glm")
        self.assertEqual(runtime.provider_api_key_env, "ZHIPUAI_API_KEY")
        self.assertEqual(runtime.provider_base_url, "https://open.bigmodel.cn/api/anthropic")
        self.assertEqual(runtime.codex_path, "claude.cmd" if os.name == "nt" else "claude")
        self.assertEqual(runtime.model, GLM_DEFAULT_MODEL)
        self.assertEqual(runtime.model_slug_input, GLM_DEFAULT_MODEL)

    def test_runtime_from_payload_applies_ensemble_defaults(self) -> None:
        runtime = runtime_from_payload(
            {
                "model_provider": "ensemble",
            }
        )

        self.assertEqual(runtime.model_provider, "ensemble")
        self.assertEqual(runtime.provider_api_key_env, "OPENAI_API_KEY")
        self.assertEqual(runtime.provider_base_url, "")
        self.assertEqual(runtime.codex_path, "codex.cmd" if os.name == "nt" else "codex")
        self.assertEqual(runtime.model, "gpt-5.4")
        self.assertEqual(runtime.model_slug_input, "gpt-5.4")
        self.assertEqual(runtime.ensemble_openai_model, "gpt-5.4")
        self.assertEqual(runtime.ensemble_gemini_model, GEMINI_DEFAULT_MODEL)
        self.assertEqual(runtime.ensemble_claude_model, CLAUDE_DEFAULT_MODEL)

    def test_runtime_from_payload_preserves_custom_ensemble_models(self) -> None:
        runtime = runtime_from_payload(
            {
                "model_provider": "ensemble",
                "ensemble_openai_model": "gpt-5.4-mini",
                "ensemble_gemini_model": "gemini-2.5-pro",
                "ensemble_claude_model": "claude-3.7-sonnet",
            }
        )

        self.assertEqual(runtime.model, "gpt-5.4-mini")
        self.assertEqual(runtime.model_slug_input, "gpt-5.4-mini")
        self.assertEqual(runtime.ensemble_openai_model, "gpt-5.4-mini")
        self.assertEqual(runtime.ensemble_gemini_model, "gemini-2.5-pro")
        self.assertEqual(runtime.ensemble_claude_model, "claude-3.7-sonnet")

    def test_bootstrap_exposes_workspace_and_model_presets(self) -> None:
        with TemporaryTestDir() as temp_dir:
            with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: fake_codex_snapshot()):
                payload = run_command("bootstrap", temp_dir)

        self.assertEqual(payload["workspace_root"], str(temp_dir.resolve()))
        self.assertTrue(payload["model_presets"])
        self.assertTrue(payload["model_catalog"])
        self.assertEqual(payload["codex_status"]["account"]["plan_type"], "pro")
        self.assertEqual(payload["default_runtime"]["model"], "gpt-5.4")
        self.assertEqual(payload["default_runtime"]["model_preset"], "")
        self.assertEqual(payload["default_runtime"]["model_slug_input"], "gpt-5.4")
        self.assertTrue(payload["default_runtime"]["generate_word_report"])
        self.assertFalse(payload["default_runtime"]["save_project_logs"])
        self.assertEqual(payload["default_runtime"]["sandbox_mode"], "danger-full-access")
        self.assertEqual(payload["default_runtime"]["optimization_mode"], "light")

    def test_append_ui_event_saves_project_activity_log_when_enabled(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Log Capture Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "save_project_logs": True,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                run_command("save-project-setup", workspace_root, payload)

            project = ui_bridge.orchestrator_for(workspace_root).local_project(repo_dir)
            self.assertIsNotNone(project)
            assert project is not None

            ui_bridge.append_ui_event(project, "unit-test", "captured", {"scope": "test"})

            activity_log = project.paths.logs_dir / "project_activity.jsonl"
            self.assertTrue(activity_log.exists())
            entries = [json.loads(line) for line in activity_log.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(entries[-1]["event_type"], "unit-test")
            self.assertEqual(entries[-1]["message"], "captured")

    def test_project_setup_and_load_round_trip(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Demo Project",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            self.assertEqual(detail["project"]["display_name"], "Demo Project")
            self.assertEqual(detail["runtime"]["test_cmd"], "python -m unittest")
            self.assertEqual(detail["run_control"]["stop_after_current_step"], False)
            self.assertEqual(detail["run_control"]["stop_immediately"], False)
            self.assertIn("workspace_tree", detail)
            self.assertIn("reports", detail)
            self.assertIn("history", detail)
            self.assertIn("checkpoints", detail)
            self.assertIn("bottom_panels", detail)
            self.assertIn("github", detail)
            self.assertEqual(detail["codex_status"]["account"]["email"], "demo@example.com")
            self.assertIn("runtime_insights", detail)
            self.assertIn("runtime_insights", detail["bottom_panels"])
            self.assertIn("parallel", detail["runtime_insights"])

            listing = run_command("list-projects", workspace_root)
            self.assertEqual(len(listing["projects"]), 1)
            self.assertEqual(listing["projects"][0]["display_name"], "Demo Project")

            with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: fake_codex_snapshot()):
                loaded = run_command(
                    "load-project",
                    workspace_root,
                    {
                        "repo_id": detail["project"]["repo_id"],
                    },
                )
            self.assertIn("Demo Project", loaded["summary"])
            self.assertEqual(loaded["stats"]["total_steps"], 0)

    def test_load_project_summary_includes_word_report_path_when_present(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Report Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "effort": "medium",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            word_report_path = Path(detail["files"]["project_root"]) / "reports" / "CLOSEOUT_REPORT.docx"
            word_report_path.parent.mkdir(parents=True, exist_ok=True)
            word_report_path.write_bytes(b"demo")

            with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: fake_codex_snapshot()):
                loaded = run_command(
                    "load-project",
                    workspace_root,
                    {
                        "repo_id": detail["project"]["repo_id"],
                    },
                )

            self.assertEqual(loaded["reports"]["word_report_path"], str(word_report_path))
            self.assertIn(str(word_report_path), loaded["summary"])

    def test_load_project_exposes_powerpoint_report_target_path(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Report Target Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "effort": "medium",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            self.assertTrue(detail["files"]["powerpoint_report_file"].endswith("CLOSEOUT_REPORT.pptx"))
            self.assertTrue(detail["reports"]["powerpoint_report_target_path"].endswith("CLOSEOUT_REPORT.pptx"))
            self.assertEqual(detail["reports"]["powerpoint_report_path"], "")

    def test_save_plan_propagates_checkpoint_deadline_into_project_detail(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Checkpoint Deadline Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "effort": "medium",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }
            plan = ExecutionPlanState(
                plan_title="Deadline Plan",
                project_prompt="Track deadlines.",
                workflow_mode="standard",
                execution_mode="parallel",
                default_test_command="python -m unittest",
                steps=[
                    ExecutionStep(
                        step_id="ST1",
                        title="Prepare release",
                        display_description="Prepare release checkpoint",
                        codex_description="Prepare release checkpoint",
                        success_criteria="Release notes updated",
                        deadline_at="2026-04-05 18:00",
                        status="pending",
                    )
                ],
            ).to_dict()

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                saved = run_command("save-project-setup", workspace_root, payload)
                detail = run_command(
                    "save-plan",
                    workspace_root,
                    {
                        **payload,
                        "repo_id": saved["project"]["repo_id"],
                        "plan": plan,
                    },
                )

            self.assertEqual(detail["checkpoints"]["items"][0]["deadline_at"], "2026-04-05 18:00")
            self.assertIn("- Deadline: 2026-04-05 18:00", detail["checkpoints"]["timeline_markdown"])

    def test_archive_project_moves_managed_workspace_and_allows_same_repo_restart(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            (repo_dir / "README.md").write_text("demo", encoding="utf-8")

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Delete Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            managed_root = Path(detail["project"]["project_root"])
            self.assertTrue(managed_root.exists())

            archived = run_command(
                "archive-project",
                workspace_root,
                {
                    "repo_id": detail["project"]["repo_id"],
                },
            )

            self.assertEqual(archived["archived"]["display_name"], "Delete Demo")
            self.assertTrue(archived["archived"]["archive_id"])
            self.assertEqual(archived["projects"], [])
            self.assertEqual(len(archived["history"]), 1)
            self.assertFalse(managed_root.exists())
            self.assertTrue(repo_dir.exists())
            self.assertTrue((repo_dir / "README.md").exists())

            archived_detail = run_command(
                "load-history-entry",
                workspace_root,
                {
                    "archive_id": archived["archived"]["archive_id"],
                    "detail_level": "full",
                },
            )

            self.assertTrue(archived_detail["project"]["archived"])
            self.assertTrue(Path(archived_detail["project"]["project_root"]).exists())
            self.assertIn("<svg", archived_detail["history"]["flow_svg_text"])

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                restarted = run_command(
                    "save-project-setup",
                    workspace_root,
                    {
                        **payload,
                        "display_name": "Delete Demo Restarted",
                    },
                )

            self.assertEqual(restarted["project"]["display_name"], "Delete Demo Restarted")
            listing = run_command("list-projects", workspace_root)
            self.assertEqual(len(listing["projects"]), 1)
            self.assertEqual(len(listing["history"]), 1)

    def test_delete_project_removes_managed_workspace_without_creating_history(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            (repo_dir / "README.md").write_text("demo", encoding="utf-8")

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Delete Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            managed_root = Path(detail["project"]["project_root"])
            deleted = run_command(
                "delete-project",
                workspace_root,
                {
                    "repo_id": detail["project"]["repo_id"],
                },
            )

            self.assertEqual(deleted["deleted"]["display_name"], "Delete Demo")
            self.assertEqual(deleted["projects"], [])
            self.assertEqual(deleted["history"], [])
            self.assertFalse(managed_root.exists())
            self.assertTrue(repo_dir.exists())
            self.assertTrue((repo_dir / "README.md").exists())

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                restarted = run_command(
                    "save-project-setup",
                    workspace_root,
                    {
                        **payload,
                        "display_name": "Delete Demo Restarted",
                    },
                )

            self.assertEqual(restarted["project"]["display_name"], "Delete Demo Restarted")

    def test_delete_project_removes_readonly_git_objects_inside_managed_workspace(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            (repo_dir / "README.md").write_text("demo", encoding="utf-8")

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Readonly Delete Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            managed_root = Path(detail["project"]["project_root"])
            readonly_object = (
                managed_root
                / ".parallel_runs"
                / "demo-batch"
                / "02-st3"
                / "repo"
                / ".git"
                / "objects"
                / "22"
                / "cbf345e35e7bffda12b26f45bbc8dc86e2a97d"
            )
            readonly_object.parent.mkdir(parents=True, exist_ok=True)
            readonly_object.write_text("git-object", encoding="utf-8")
            os.chmod(readonly_object, stat.S_IREAD)

            deleted = run_command(
                "delete-project",
                workspace_root,
                {
                    "repo_id": detail["project"]["repo_id"],
                },
            )

            self.assertEqual(deleted["deleted"]["display_name"], "Readonly Delete Demo")
            self.assertFalse(managed_root.exists())
            self.assertTrue(repo_dir.exists())

    def test_archive_all_projects_moves_registry_but_keeps_local_repos(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_a = temp_dir / "repo-a"
            repo_b = temp_dir / "repo-b"
            repo_a.mkdir(parents=True, exist_ok=True)
            repo_b.mkdir(parents=True, exist_ok=True)
            (repo_a / "README.md").write_text("a", encoding="utf-8")
            (repo_b / "README.md").write_text("b", encoding="utf-8")

            for repo_dir, name in ((repo_a, "A"), (repo_b, "B")):
                payload = {
                    "project_dir": str(repo_dir),
                    "display_name": f"Project {name}",
                    "branch": "main",
                    "origin_url": "",
                    "runtime": {
                        "model": "gpt-5.4",
                        "effort": "high",
                        "test_cmd": "python -m unittest",
                        "max_blocks": 5,
                    },
                }
                with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                    "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                    side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
                ):
                    run_command("save-project-setup", workspace_root, payload)

            archived = run_command("archive-all-projects", workspace_root, {})
            self.assertTrue(archived["archived_all"])
            self.assertEqual(archived["archived_count"], 2)
            self.assertEqual(archived["projects"], [])
            self.assertEqual(len(archived["history"]), 2)
            self.assertTrue(repo_a.exists())
            self.assertTrue(repo_b.exists())
            self.assertTrue((repo_a / "README.md").exists())
            self.assertTrue((repo_b / "README.md").exists())

    def test_delete_all_projects_removes_managed_workspaces_without_history_entries(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_a = temp_dir / "repo-a"
            repo_b = temp_dir / "repo-b"
            repo_a.mkdir(parents=True, exist_ok=True)
            repo_b.mkdir(parents=True, exist_ok=True)
            (repo_a / "README.md").write_text("a", encoding="utf-8")
            (repo_b / "README.md").write_text("b", encoding="utf-8")

            for repo_dir, name in ((repo_a, "A"), (repo_b, "B")):
                payload = {
                    "project_dir": str(repo_dir),
                    "display_name": f"Project {name}",
                    "branch": "main",
                    "origin_url": "",
                    "runtime": {
                        "model": "gpt-5.4",
                        "effort": "high",
                        "test_cmd": "python -m unittest",
                        "max_blocks": 5,
                    },
                }
                with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                    "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                    side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
                ):
                    run_command("save-project-setup", workspace_root, payload)

            deleted = run_command("delete-all-projects", workspace_root, {})
            self.assertTrue(deleted["deleted_all"])
            self.assertEqual(deleted["deleted_count"], 2)
            self.assertEqual(deleted["projects"], [])
            self.assertEqual(deleted["history"], [])
            self.assertTrue(repo_a.exists())
            self.assertTrue(repo_b.exists())
            self.assertTrue((repo_a / "README.md").exists())
            self.assertTrue((repo_b / "README.md").exists())

    def test_load_history_entry_returns_saved_plan_and_flow_chart(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "History Flow Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "effort": "high",
                    "test_cmd": "python -m pytest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            plan_payload = {
                "project_dir": str(repo_dir),
                "branch": "main",
                "origin_url": "",
                "runtime": detail["runtime"],
                "plan": {
                    "plan_title": "History Flow Demo",
                    "project_prompt": "Rebuild this directory from a fresh prompt.",
                    "summary": "Preserve the flow chart for archived runs.",
                    "execution_mode": "parallel",
                    "default_test_command": "python -m pytest",
                    "steps": [
                        {
                            "step_id": "seed",
                            "title": "Capture the archived flow",
                            "display_description": "Keep the old execution graph available from history.",
                            "codex_description": "Preserve the execution graph.",
                            "test_command": "python -m pytest",
                            "success_criteria": "The archived detail still renders the flow chart.",
                            "reasoning_effort": "high",
                            "depends_on": [],
                            "owned_paths": ["src/jakal_flow/ui_bridge.py"],
                        }
                    ],
                },
            }
            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                saved = run_command("save-plan", workspace_root, plan_payload)
            archived = run_command(
                "archive-project",
                workspace_root,
                {
                    "repo_id": saved["project"]["repo_id"],
                },
            )

            loaded = run_command(
                "load-history-entry",
                workspace_root,
                {
                    "archive_id": archived["archived"]["archive_id"],
                    "detail_level": "full",
                },
            )

            self.assertEqual(loaded["plan"]["project_prompt"], "Rebuild this directory from a fresh prompt.")
            self.assertEqual(loaded["plan"]["steps"][0]["title"], "Capture the archived flow")
            self.assertIn("<svg", loaded["history"]["flow_svg_text"])

    def test_delete_history_entry_removes_archived_workspace(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            (repo_dir / "README.md").write_text("demo", encoding="utf-8")

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "History Delete Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            archived = run_command(
                "archive-project",
                workspace_root,
                {
                    "repo_id": detail["project"]["repo_id"],
                },
            )
            archived_detail = run_command(
                "load-history-entry",
                workspace_root,
                {
                    "archive_id": archived["archived"]["archive_id"],
                    "detail_level": "core",
                },
            )
            archive_root = Path(archived_detail["project"]["project_root"])

            deleted = run_command(
                "delete-history-entry",
                workspace_root,
                {
                    "archive_id": archived["archived"]["archive_id"],
                },
            )

            self.assertEqual(deleted["deleted_history"]["display_name"], "History Delete Demo")
            self.assertEqual(deleted["projects"], [])
            self.assertEqual(deleted["history"], [])
            self.assertFalse(archive_root.exists())
            self.assertTrue(repo_dir.exists())

    def test_save_plan_and_request_stop_persist_bridge_state(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            setup_payload = {
                "project_dir": str(repo_dir),
                "display_name": "Plan Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m pytest",
                    "execution_mode": "parallel",
                    "parallel_workers": 3,
                    "max_blocks": 4,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, setup_payload)

            save_plan_payload = {
                "project_dir": str(repo_dir),
                "branch": "main",
                "origin_url": "",
                "runtime": detail["runtime"],
                "plan": {
                    "plan_title": "Desktop rollout",
                    "project_prompt": "Build the React and Tauri desktop app.",
                    "summary": "Deliver the desktop shell in small verified steps.",
                    "execution_mode": "parallel",
                    "default_test_command": "python -m pytest",
                    "steps": [
                        {
                            "step_id": "custom-1",
                            "title": "Add the bridge",
                            "display_description": "Expose JSON commands for the desktop shell.",
                            "codex_description": "Create a JSON bridge for the UI.",
                            "test_command": "python -m pytest",
                            "success_criteria": "The desktop bridge can load and save projects.",
                            "reasoning_effort": "medium",
                            "depends_on": [],
                            "owned_paths": ["src/jakal_flow/ui_bridge.py", "tests/test_ui_bridge.py"],
                        },
                        {
                            "step_id": "custom-2",
                            "title": "Add the React shell",
                            "display_description": "Build the setup and flow screens.",
                            "codex_description": "Create the desktop shell with the required views.",
                            "test_command": "python -m pytest",
                            "success_criteria": "The desktop app can render the plan flow.",
                            "reasoning_effort": "xhigh",
                            "depends_on": [],
                            "owned_paths": ["desktop/src", "desktop/package.json"],
                        },
                    ],
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                saved = run_command("save-plan", workspace_root, save_plan_payload)

            self.assertEqual(saved["plan"]["steps"][0]["step_id"], "ST1")
            self.assertEqual(saved["plan"]["steps"][1]["step_id"], "ST2")
            self.assertEqual(saved["plan"]["steps"][0]["reasoning_effort"], "medium")
            self.assertEqual(saved["plan"]["steps"][1]["reasoning_effort"], "xhigh")
            self.assertEqual(saved["plan"]["execution_mode"], "parallel")
            self.assertEqual(saved["plan"]["steps"][0]["depends_on"], [])
            self.assertEqual(saved["plan"]["steps"][0]["owned_paths"], ["src/jakal_flow/ui_bridge.py", "tests/test_ui_bridge.py"])
            self.assertEqual(saved["runtime"]["execution_mode"], "parallel")
            self.assertEqual(saved["runtime"]["parallel_workers"], 3)
            self.assertEqual(saved["stats"]["total_steps"], 2)

            stop_payload = run_command(
                "request-stop",
                workspace_root,
                {
                    "project_dir": str(repo_dir),
                    "source": "unit-test",
                },
            )
            self.assertEqual(stop_payload["run_control"]["stop_immediately"], True)
            self.assertEqual(stop_payload["run_control"]["stop_after_current_step"], False)

            with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: fake_codex_snapshot()):
                loaded = run_command(
                    "load-project",
                    workspace_root,
                    {
                        "project_dir": str(repo_dir),
                    },
                )
            self.assertEqual(loaded["run_control"]["stop_immediately"], True)
            self.assertEqual(loaded["run_control"]["stop_after_current_step"], False)

            control_path = Path(loaded["files"]["ui_control_file"])
            self.assertTrue(control_path.exists())
            control_payload = json.loads(control_path.read_text(encoding="utf-8"))
            self.assertEqual(control_payload["request_source"], "unit-test")

    def test_generate_plan_handles_immediate_stop_during_planning(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Planning Stop Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            with mock.patch.object(
                ui_bridge.EXECUTION_STOP_REGISTRY,
                "clear",
                wraps=ui_bridge.EXECUTION_STOP_REGISTRY.clear,
            ) as clear_mock, mock.patch(
                "jakal_flow.orchestrator.Orchestrator.generate_execution_plan",
                side_effect=ImmediateStopRequested("Planning stopped by user."),
            ), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                stopped = run_command(
                    "generate-plan",
                    workspace_root,
                    {
                        "project_dir": str(repo_dir),
                        "branch": "main",
                        "origin_url": "",
                        "runtime": detail["runtime"],
                        "prompt": "Create a plan and then stop.",
                        "max_steps": 5,
                    },
                )

            self.assertEqual(stopped["project"]["current_status"], "setup_ready")
            self.assertEqual(stopped["run_control"]["stop_immediately"], False)
            self.assertEqual(stopped["run_control"]["stop_after_current_step"], False)
            self.assertEqual(clear_mock.call_count, 2)
            self.assertTrue(any("plan-stopped" in item for item in stopped["activity"]))

    def test_reset_plan_requests_stop_and_clears_planning_state(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            setup_payload = {
                "project_dir": str(repo_dir),
                "display_name": "Planning Reset Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m pytest",
                    "max_blocks": 4,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, setup_payload)

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                saved = run_command(
                    "save-plan",
                    workspace_root,
                    {
                        "project_dir": str(repo_dir),
                        "branch": "main",
                        "origin_url": "",
                        "runtime": detail["runtime"],
                        "plan": {
                            "plan_title": "Temporary plan",
                            "project_prompt": "This should be reset.",
                            "summary": "Temporary summary.",
                            "default_test_command": "python -m pytest",
                            "steps": [
                                {
                                    "step_id": "ST1",
                                    "title": "Temporary step",
                                    "display_description": "Will be removed.",
                                    "codex_description": "Will be removed.",
                                    "test_command": "python -m pytest",
                                    "success_criteria": "N/A",
                                }
                            ],
                        },
                    },
                )

            orchestrator = ui_bridge.orchestrator_for(workspace_root)
            project = orchestrator.workspace.load_project_by_id(saved["project"]["repo_id"])
            project.metadata.current_status = "running:generate-plan"
            orchestrator.workspace.save_project(project)

            with mock.patch.object(
                ui_bridge.EXECUTION_STOP_REGISTRY,
                "request_stop",
                wraps=ui_bridge.EXECUTION_STOP_REGISTRY.request_stop,
            ) as request_stop_mock, mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                reset = run_command(
                    "reset-plan",
                    workspace_root,
                    {
                        "project_dir": str(repo_dir),
                        "branch": "main",
                        "origin_url": "",
                        "runtime": detail["runtime"],
                    },
                )

            self.assertEqual(reset["plan"]["project_prompt"], "")
            self.assertEqual(reset["plan"]["steps"], [])
            self.assertEqual(reset["run_control"]["stop_immediately"], False)
            self.assertEqual(request_stop_mock.call_count, 1)
            self.assertTrue(any("plan-reset" in item for item in reset["activity"]))

    def test_load_project_tolerates_malformed_ui_state_files(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "State Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            control_path = Path(detail["files"]["ui_control_file"])
            control_path.write_text(
                json.dumps(
                    {
                        "stop_after_current_step": "yes",
                        "stop_immediately": "on",
                        "requested_at": 123,
                        "request_source": ["desktop"],
                    }
                ),
                encoding="utf-8",
            )
            checkpoint_path = Path(detail["project"]["project_root"]) / "state" / "CHECKPOINTS.json"
            checkpoint_path.write_text(
                json.dumps(
                    {
                        "checkpoints": [
                            {"checkpoint_id": "CP1", "status": "awaiting_review"},
                            "bad-entry",
                            99,
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: fake_codex_snapshot()):
                loaded = run_command(
                    "load-project",
                    workspace_root,
                    {
                        "project_dir": str(repo_dir),
                    },
                )

            self.assertTrue(loaded["run_control"]["stop_after_current_step"])
            self.assertTrue(loaded["run_control"]["stop_immediately"])
            self.assertEqual(loaded["run_control"]["requested_at"], "123")
            self.assertIsNone(loaded["run_control"]["request_source"])
            self.assertEqual(len(loaded["checkpoints"]["items"]), 1)
            self.assertIsNone(loaded["checkpoints"]["pending"])
            self.assertEqual(loaded["checkpoints"]["items"][0]["status"], "approved")

    def test_approve_checkpoint_respects_string_push_flag_and_clears_pending_checkpoint(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Approval Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "allow_push": True,
                    "require_checkpoint_approval": True,
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            project_root = Path(detail["project"]["project_root"])
            checkpoint_path = project_root / "state" / "CHECKPOINTS.json"
            checkpoint_path.write_text(
                json.dumps(
                    {
                        "checkpoints": [
                            {
                                "checkpoint_id": "CP1",
                                "title": "Review me",
                                "target_block": 1,
                                "status": "awaiting_review",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            loop_state_path = project_root / "state" / "LOOP_STATE.json"
            loop_state = json.loads(loop_state_path.read_text(encoding="utf-8"))
            loop_state["current_checkpoint_id"] = "CP1"
            loop_state["pending_checkpoint_approval"] = True
            loop_state_path.write_text(json.dumps(loop_state), encoding="utf-8")

            with mock.patch("jakal_flow.orchestrator.GitOps.push") as push_mock, mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                approved = run_command(
                    "approve-checkpoint",
                    workspace_root,
                    {
                        "repo_id": detail["project"]["repo_id"],
                        "push": "false",
                    },
                )

            push_mock.assert_not_called()
            self.assertIsNone(approved["checkpoints"]["pending"])
            self.assertEqual(approved["project"]["current_status"], "setup_ready")
            self.assertEqual(approved["loop_state"]["current_checkpoint_id"], None)
            self.assertFalse(approved["loop_state"]["pending_checkpoint_approval"])
            self.assertEqual(approved["checkpoints"]["items"][0]["status"], "approved")
            self.assertFalse(approved["checkpoints"]["items"][0]["pushed"])
            self.assertEqual(approved["checkpoints"]["items"][0]["push_skipped_reason"], "not_requested")

    def test_load_project_does_not_report_pending_checkpoint_without_pending_flag(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Checkpoint Sync Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "require_checkpoint_approval": False,
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            project_root = Path(detail["project"]["project_root"])
            checkpoint_path = project_root / "state" / "CHECKPOINTS.json"
            checkpoint_path.write_text(
                json.dumps(
                    {
                        "checkpoints": [
                            {
                                "checkpoint_id": "CP1",
                                "title": "Currently running",
                                "target_block": 1,
                                "status": "running",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            loop_state_path = project_root / "state" / "LOOP_STATE.json"
            loop_state = json.loads(loop_state_path.read_text(encoding="utf-8"))
            loop_state["current_checkpoint_id"] = "CP1"
            loop_state["pending_checkpoint_approval"] = False
            loop_state_path.write_text(json.dumps(loop_state), encoding="utf-8")

            with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: fake_codex_snapshot()):
                loaded = run_command(
                    "load-project",
                    workspace_root,
                    {
                        "project_dir": str(repo_dir),
                    },
                )

            self.assertEqual(loaded["checkpoints"]["items"][0]["status"], "running")
            self.assertIsNone(loaded["checkpoints"]["pending"])

    def test_run_plan_automatically_runs_closeout_after_last_completed_step(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Auto Closeout Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }

            completed_plan = {
                "plan_title": "Auto Closeout Demo",
                "project_prompt": "Finish the work",
                "summary": "Everything is ready for closeout.",
                "workflow_mode": "standard",
                "execution_mode": "parallel",
                "default_test_command": "python -m unittest",
                "steps": [
                    {
                        "step_id": "ST1",
                        "title": "Implement",
                        "display_description": "Implementation finished",
                        "codex_description": "Implementation finished",
                        "success_criteria": "Tests pass",
                        "test_command": "python -m unittest",
                        "reasoning_effort": "high",
                        "status": "completed",
                    }
                ],
            }

            def fake_run_execution_closeout(self, project_dir, runtime, branch="main", origin_url=""):
                context = self.local_project(project_dir)
                assert context is not None
                plan_state = self.load_execution_plan_state(context)
                plan_state.closeout_status = "completed"
                plan_state.closeout_started_at = "2026-03-26T00:10:00+00:00"
                plan_state.closeout_completed_at = "2026-03-26T00:12:00+00:00"
                plan_state.closeout_notes = "Closeout finished successfully."
                saved = self.save_execution_plan_state(context, plan_state)
                context.metadata.current_status = self._status_from_plan_state(saved)
                self.workspace.save_project(context)
                return context, saved

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ), mock.patch(
                "jakal_flow.orchestrator.Orchestrator.run_execution_closeout",
                new=fake_run_execution_closeout,
            ):
                result = run_command(
                    "run-plan",
                    workspace_root,
                    {
                        **payload,
                        "plan": completed_plan,
                    },
                )

            self.assertEqual(result["plan"]["closeout_status"], "completed")
            self.assertEqual(result["project"]["current_status"], "closed_out")
            self.assertTrue(any("closeout-started" in line for line in result["activity"]))
            self.assertTrue(any("closeout-finished" in line for line in result["activity"]))

    def test_run_closeout_reports_generated_word_report_path_in_activity(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Closeout Report Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                    "generate_word_report": True,
                },
            }
            completed_plan = {
                "plan_title": "Closeout Report Demo",
                "project_prompt": "Finish the work",
                "summary": "Everything is ready for closeout.",
                "workflow_mode": "standard",
                "execution_mode": "parallel",
                "default_test_command": "python -m unittest",
                "steps": [
                    {
                        "step_id": "ST1",
                        "title": "Implement",
                        "display_description": "Implementation finished",
                        "codex_description": "Implementation finished",
                        "success_criteria": "Tests pass",
                        "test_command": "python -m unittest",
                        "reasoning_effort": "high",
                        "status": "completed",
                    }
                ],
            }

            def fake_run_execution_closeout(self, project_dir, runtime, branch="main", origin_url=""):
                context = self.local_project(project_dir)
                assert context is not None
                plan_state = self.load_execution_plan_state(context)
                plan_state.closeout_status = "completed"
                plan_state.closeout_started_at = "2026-03-26T00:10:00+00:00"
                plan_state.closeout_completed_at = "2026-03-26T00:12:00+00:00"
                plan_state.closeout_notes = "Closeout finished successfully."
                context.paths.closeout_report_docx_file.parent.mkdir(parents=True, exist_ok=True)
                context.paths.closeout_report_docx_file.write_bytes(b"demo")
                saved = self.save_execution_plan_state(context, plan_state)
                context.metadata.current_status = self._status_from_plan_state(saved)
                self.workspace.save_project(context)
                return context, saved

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ), mock.patch(
                "jakal_flow.orchestrator.Orchestrator.run_execution_closeout",
                new=fake_run_execution_closeout,
            ):
                result = run_command(
                    "run-closeout",
                    workspace_root,
                    {
                        **payload,
                        "plan": completed_plan,
                    },
                )

            expected_path = str(Path(result["files"]["project_root"]) / "reports" / "CLOSEOUT_REPORT.docx")
            self.assertEqual(result["reports"]["word_report_path"], expected_path)
            self.assertTrue(any(expected_path in line for line in result["activity"]))

    def test_run_closeout_surfaces_failure_report_details_when_closeout_raises(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Closeout Failure Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }
            completed_plan = {
                "plan_title": "Closeout Failure Demo",
                "project_prompt": "Finish the work",
                "summary": "Everything is ready for closeout.",
                "workflow_mode": "standard",
                "execution_mode": "parallel",
                "default_test_command": "python -m unittest",
                "steps": [
                    {
                        "step_id": "ST1",
                        "title": "Implement",
                        "display_description": "Implementation finished",
                        "codex_description": "Implementation finished",
                        "success_criteria": "Tests pass",
                        "test_command": "python -m unittest",
                        "reasoning_effort": "high",
                        "status": "completed",
                    }
                ],
            }

            def fake_run_execution_closeout(self, project_dir, runtime, branch="main", origin_url=""):
                context = self.local_project(project_dir)
                assert context is not None
                plan_state = self.load_execution_plan_state(context)
                plan_state.closeout_status = "failed"
                plan_state.closeout_notes = "Closeout subprocess crashed."
                saved = self.save_execution_plan_state(context, plan_state)
                context.metadata.current_status = self._status_from_plan_state(saved)
                self.workspace.save_project(context)
                report_md = context.paths.reports_dir / "20260328000000_closeout_failed.prfail.md"
                report_json = context.paths.reports_dir / "20260328000000_closeout_failed.prfail.json"
                block_dir = context.paths.logs_dir / "block_0002"
                block_dir.mkdir(parents=True, exist_ok=True)
                (block_dir / "project-closeout-pass.prompt.md").write_text("prompt\n", encoding="utf-8")
                report_md.write_text("failure report\n", encoding="utf-8")
                report_json.write_text(
                    json.dumps(
                        {
                            "summary": "Closeout subprocess crashed.",
                            "block_index": 2,
                            "selected_task": "Project closeout",
                        }
                    ),
                    encoding="utf-8",
                )
                (context.paths.reports_dir / "latest_pr_failure_status.json").write_text(
                    json.dumps(
                        {
                            "generated_at": "2026-03-28T00:00:00+00:00",
                            "failure_type": "closeout_failed",
                            "posted": False,
                            "result": {"reason": "test"},
                            "report_markdown_file": str(report_md),
                            "report_json_file": str(report_json),
                        }
                    ),
                    encoding="utf-8",
                )
                raise RuntimeError("closeout explosion")

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ), mock.patch(
                "jakal_flow.orchestrator.Orchestrator.run_execution_closeout",
                new=fake_run_execution_closeout,
            ):
                with self.assertRaisesRegex(RuntimeError, "Failure report: .*closeout_failed\\.prfail\\.md"):
                    run_command(
                        "run-closeout",
                        workspace_root,
                        {
                            **payload,
                            "plan": completed_plan,
                        },
                    )

            detail = run_command(
                "load-project",
                workspace_root,
                {
                    "project_dir": str(repo_dir),
                },
            )

            self.assertEqual(detail["project"]["current_status"], "closeout_failed")
            self.assertEqual(detail["reports"]["latest_failure"]["summary"], "Closeout subprocess crashed.")
            self.assertTrue(detail["reports"]["latest_failure"]["report_markdown_file"].endswith("closeout_failed.prfail.md"))
            self.assertTrue(any(path.endswith("project-closeout-pass.prompt.md") for path in detail["reports"]["latest_failure"]["artifact_files"]))
            self.assertTrue(any("closeout-finished" in line and "Failure report:" in line for line in detail["activity"]))

    def test_generate_plan_clears_latest_failure_when_restarting_after_failure(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Retry Planning Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                saved = run_command("save-project-setup", workspace_root, payload)

            project_root = Path(saved["project"]["project_root"])
            latest_failure_file = project_root / "reports" / "latest_pr_failure_status.json"
            report_md = project_root / "reports" / "20260328000000_plan_failed.prfail.md"
            report_json = project_root / "reports" / "20260328000000_plan_failed.prfail.json"
            report_md.write_text("planning failed\n", encoding="utf-8")
            report_json.write_text(json.dumps({"summary": "Planning failed previously."}), encoding="utf-8")
            latest_failure_file.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-03-28T00:00:00+00:00",
                        "failure_type": "planning_failed",
                        "posted": False,
                        "result": {"reason": "test"},
                        "report_markdown_file": str(report_md),
                        "report_json_file": str(report_json),
                    }
                ),
                encoding="utf-8",
            )

            def fake_generate_execution_plan(self, project_dir, runtime, project_prompt, branch="main", max_steps=5, origin_url="", progress_callback=None):
                context = self.local_project(project_dir)
                assert context is not None
                assert not latest_failure_file.exists()
                plan_state = ExecutionPlanState(
                    plan_title="Retry Planning Demo",
                    project_prompt=project_prompt,
                    summary="Regenerated plan.",
                    workflow_mode="standard",
                    execution_mode="parallel",
                    default_test_command=runtime.test_cmd,
                    steps=[
                        ExecutionStep(
                            step_id="ST1",
                            title="Retry planning",
                            display_description="Generate a clean retry plan.",
                            codex_description="Generate a clean retry plan.",
                            success_criteria="Plan is ready.",
                            test_command=runtime.test_cmd,
                            reasoning_effort="high",
                        )
                    ],
                )
                project, saved_state = self.update_execution_plan(
                    project_dir=project_dir,
                    runtime=runtime,
                    plan_state=plan_state,
                    branch=branch,
                    origin_url=origin_url,
                )
                return project, saved_state

            with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: fake_codex_snapshot()), mock.patch(
                "jakal_flow.orchestrator.Orchestrator.generate_execution_plan",
                new=fake_generate_execution_plan,
            ):
                detail = run_command(
                    "generate-plan",
                    workspace_root,
                    {
                        **payload,
                        "prompt": "Regenerate the plan",
                        "max_steps": 3,
                    },
                )

            self.assertEqual(detail["reports"]["latest_failure"], {})
            self.assertFalse(latest_failure_file.exists())

    def test_run_plan_clears_latest_failure_when_restarting_after_failure(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Retry Run Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }
            completed_plan = {
                "plan_title": "Retry Run Demo",
                "project_prompt": "Retry the saved plan",
                "summary": "No remaining steps.",
                "workflow_mode": "standard",
                "execution_mode": "parallel",
                "default_test_command": "python -m unittest",
                "closeout_status": "completed",
                "steps": [
                    {
                        "step_id": "ST1",
                        "title": "Already done",
                        "display_description": "Completed previously",
                        "codex_description": "Completed previously",
                        "success_criteria": "Nothing left to do.",
                        "test_command": "python -m unittest",
                        "reasoning_effort": "high",
                        "status": "completed",
                    }
                ],
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                saved = run_command("save-project-setup", workspace_root, payload)

            project_root = Path(saved["project"]["project_root"])
            latest_failure_file = project_root / "reports" / "latest_pr_failure_status.json"
            report_md = project_root / "reports" / "20260328000000_run_failed.prfail.md"
            report_json = project_root / "reports" / "20260328000000_run_failed.prfail.json"
            report_md.write_text("run failed\n", encoding="utf-8")
            report_json.write_text(json.dumps({"summary": "Run failed previously."}), encoding="utf-8")
            latest_failure_file.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-03-28T00:00:00+00:00",
                        "failure_type": "run_failed",
                        "posted": False,
                        "result": {"reason": "test"},
                        "report_markdown_file": str(report_md),
                        "report_json_file": str(report_json),
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: fake_codex_snapshot()):
                detail = run_command(
                    "run-plan",
                    workspace_root,
                    {
                        **payload,
                        "plan": completed_plan,
                    },
                )

            self.assertEqual(detail["reports"]["latest_failure"], {})
            self.assertFalse(latest_failure_file.exists())

    def test_run_closeout_clears_latest_failure_when_restarting_after_failure(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Retry Closeout Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }
            completed_plan = {
                "plan_title": "Retry Closeout Demo",
                "project_prompt": "Retry closeout",
                "summary": "Everything is ready.",
                "workflow_mode": "standard",
                "execution_mode": "parallel",
                "default_test_command": "python -m unittest",
                "steps": [
                    {
                        "step_id": "ST1",
                        "title": "Already done",
                        "display_description": "Completed previously",
                        "codex_description": "Completed previously",
                        "success_criteria": "Nothing left to do.",
                        "test_command": "python -m unittest",
                        "reasoning_effort": "high",
                        "status": "completed",
                    }
                ],
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                saved = run_command("save-project-setup", workspace_root, payload)

            project_root = Path(saved["project"]["project_root"])
            latest_failure_file = project_root / "reports" / "latest_pr_failure_status.json"
            report_md = project_root / "reports" / "20260328000000_closeout_failed.prfail.md"
            report_json = project_root / "reports" / "20260328000000_closeout_failed.prfail.json"
            report_md.write_text("closeout failed\n", encoding="utf-8")
            report_json.write_text(json.dumps({"summary": "Closeout failed previously."}), encoding="utf-8")
            latest_failure_file.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-03-28T00:00:00+00:00",
                        "failure_type": "closeout_failed",
                        "posted": False,
                        "result": {"reason": "test"},
                        "report_markdown_file": str(report_md),
                        "report_json_file": str(report_json),
                    }
                ),
                encoding="utf-8",
            )

            def fake_run_execution_closeout(self, project_dir, runtime, branch="main", origin_url=""):
                context = self.local_project(project_dir)
                assert context is not None
                assert not latest_failure_file.exists()
                plan_state = self.load_execution_plan_state(context)
                plan_state.closeout_status = "completed"
                plan_state.closeout_started_at = "2026-03-29T00:10:00+00:00"
                plan_state.closeout_completed_at = "2026-03-29T00:12:00+00:00"
                plan_state.closeout_notes = "Closeout finished successfully."
                saved_state = self.save_execution_plan_state(context, plan_state)
                context.metadata.current_status = self._status_from_plan_state(saved_state)
                self.workspace.save_project(context)
                return context, saved_state

            with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: fake_codex_snapshot()), mock.patch(
                "jakal_flow.orchestrator.Orchestrator.run_execution_closeout",
                new=fake_run_execution_closeout,
            ):
                detail = run_command(
                    "run-closeout",
                    workspace_root,
                    {
                        **payload,
                        "plan": completed_plan,
                    },
                )

            self.assertEqual(detail["reports"]["latest_failure"], {})
            self.assertFalse(latest_failure_file.exists())

    def test_run_manual_debugger_command_updates_detail_and_activity(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Manual Debugger Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }
            plan_payload = {
                "plan_title": "Manual Debugger Demo",
                "project_prompt": "Recover the failing step manually.",
                "summary": "One failed step remains.",
                "workflow_mode": "standard",
                "execution_mode": "parallel",
                "default_test_command": "python -m unittest",
                "steps": [
                    {
                        "step_id": "ST1",
                        "title": "Recover backend",
                        "display_description": "Repair the backend.",
                        "codex_description": "Repair the backend.",
                        "success_criteria": "Tests pass",
                        "test_command": "python -m unittest",
                        "reasoning_effort": "high",
                        "status": "failed",
                    }
                ],
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                saved = run_command("save-project-setup", workspace_root, payload)

            project_root = Path(saved["project"]["project_root"])
            latest_failure_file = project_root / "reports" / "latest_pr_failure_status.json"
            report_md = project_root / "reports" / "20260329000000_manual_debugger_failed.prfail.md"
            report_json = project_root / "reports" / "20260329000000_manual_debugger_failed.prfail.json"
            report_md.write_text("manual debugger failed\n", encoding="utf-8")
            report_json.write_text(json.dumps({"summary": "Previous failure."}), encoding="utf-8")
            latest_failure_file.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-03-29T00:00:00+00:00",
                        "failure_type": "manual_debugger_failed",
                        "posted": False,
                        "result": {"reason": "test"},
                        "report_markdown_file": str(report_md),
                        "report_json_file": str(report_json),
                    }
                ),
                encoding="utf-8",
            )

            def fake_run_manual_debugger_recovery(self, project_dir, runtime, branch="main", origin_url=""):
                context = self.local_project(project_dir)
                assert context is not None
                self.clear_latest_failure_status(context)
                return context, self.load_execution_plan_state(context), {
                    "pass_name": "block-search-debug",
                    "summary": "Recovered manually.",
                    "commit_hash": "abc123",
                }

            with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: fake_codex_snapshot()), mock.patch(
                "jakal_flow.orchestrator.Orchestrator.run_manual_debugger_recovery",
                new=fake_run_manual_debugger_recovery,
            ):
                detail = run_command(
                    "run-manual-debugger",
                    workspace_root,
                    {
                        **payload,
                        "plan": plan_payload,
                    },
                )

            self.assertEqual(detail["reports"]["latest_failure"], {})
            self.assertTrue(any("manual-debugger-started" in line for line in detail["activity"]))
            self.assertTrue(any("manual-debugger-finished" in line for line in detail["activity"]))

    def test_run_manual_merger_command_updates_detail_and_activity(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Manual Merger Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }
            plan_payload = {
                "plan_title": "Manual Merger Demo",
                "project_prompt": "Resolve the merge conflict manually.",
                "summary": "One failed batch remains.",
                "workflow_mode": "standard",
                "execution_mode": "parallel",
                "default_test_command": "python -m unittest",
                "steps": [
                    {
                        "step_id": "ST1",
                        "title": "Frontend slice",
                        "display_description": "Finish the frontend slice.",
                        "codex_description": "Finish the frontend slice.",
                        "success_criteria": "Frontend slice is integrated",
                        "test_command": "python -m unittest",
                        "reasoning_effort": "high",
                        "status": "failed",
                    },
                    {
                        "step_id": "ST2",
                        "title": "Backend slice",
                        "display_description": "Finish the backend slice.",
                        "codex_description": "Finish the backend slice.",
                        "success_criteria": "Backend slice is integrated",
                        "test_command": "python -m unittest",
                        "reasoning_effort": "high",
                        "status": "failed",
                    },
                ],
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                saved = run_command("save-project-setup", workspace_root, payload)

            project_root = Path(saved["project"]["project_root"])
            latest_failure_file = project_root / "reports" / "latest_pr_failure_status.json"
            report_md = project_root / "reports" / "20260329000000_manual_merger_failed.prfail.md"
            report_json = project_root / "reports" / "20260329000000_manual_merger_failed.prfail.json"
            report_md.write_text("manual merger failed\n", encoding="utf-8")
            report_json.write_text(json.dumps({"summary": "Previous merge failure."}), encoding="utf-8")
            latest_failure_file.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-03-29T00:00:00+00:00",
                        "failure_type": "manual_merger_failed",
                        "posted": False,
                        "result": {"reason": "test"},
                        "report_markdown_file": str(report_md),
                        "report_json_file": str(report_json),
                    }
                ),
                encoding="utf-8",
            )

            def fake_run_manual_merger_recovery(self, project_dir, runtime, branch="main", origin_url=""):
                context = self.local_project(project_dir)
                assert context is not None
                self.clear_latest_failure_status(context)
                return context, self.load_execution_plan_state(context), {
                    "pass_name": "parallel-batch-merger",
                    "summary": "Merged manually.",
                    "commit_hash": "def456",
                }

            with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: fake_codex_snapshot()), mock.patch(
                "jakal_flow.orchestrator.Orchestrator.run_manual_merger_recovery",
                new=fake_run_manual_merger_recovery,
            ):
                detail = run_command(
                    "run-manual-merger",
                    workspace_root,
                    {
                        **payload,
                        "plan": plan_payload,
                    },
                )

            self.assertEqual(detail["reports"]["latest_failure"], {})
            self.assertTrue(any("manual-merger-started" in line for line in detail["activity"]))
            self.assertTrue(any("manual-merger-finished" in line for line in detail["activity"]))

    def test_load_project_chat_returns_chat_section_without_project_change_marker(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Chat Read Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            result = run_command(
                "load-project-chat",
                workspace_root,
                {
                    "repo_id": detail["project"]["repo_id"],
                },
            )

            self.assertEqual(result["loaded_sections"], {"chat": True})
            self.assertFalse(result["emit_project_changed"])
            self.assertEqual(result["chat"]["sessions"], [])
            self.assertEqual(result["chat"]["active_session_id"], "")
            self.assertTrue(result["chat"]["draft_session"])

    def test_send_chat_message_conversation_persists_txt_session_artifacts(self) -> None:
        with TemporaryTestDir() as temp_dir:
            chat_home = temp_dir / "jakal-flow-chat"
            context = build_test_project_context(
                temp_dir,
                repo_id="chat-conversation-demo",
                slug="chat-conversation-demo",
                display_name="Chat Conversation Demo",
            )
            plan_state = ExecutionPlanState(
                plan_title="Chat Conversation Demo",
                project_prompt="Summarize the current repository state.",
                summary="Chat conversation test plan.",
            )

            with mock.patch.dict(os.environ, {CHAT_HOME_ENV_VAR: str(chat_home)}), mock.patch(
                "jakal_flow.chat_sessions._run_conversation_reply",
                return_value=(0, "Conversation reply."),
            ):
                result = execute_conversation_turn(
                    context,
                    plan_state=plan_state,
                    user_message="Summarize the current repository state.",
                )

            self.assertEqual(result["error"], "")
            self.assertEqual(result["chat"]["active_session_id"], result["chat"]["active_session"]["session_id"])
            self.assertEqual([item["role"] for item in result["chat"]["messages"]], ["user", "assistant"])
            self.assertEqual(result["chat"]["messages"][-1]["text"], "Conversation reply.")

            summary_path = Path(result["chat"]["summary_file"])
            transcript_path = Path(result["chat"]["transcript_file"])
            registry_path = chat_home / "CHAT_SESSIONS.txt"
            active_path = chat_home / "active" / f"{context.metadata.repo_id}.txt"

            self.assertTrue(summary_path.exists())
            self.assertTrue(transcript_path.exists())
            self.assertTrue(registry_path.exists())
            self.assertTrue(active_path.exists())
            self.assertEqual(summary_path.suffix, ".txt")
            self.assertEqual(transcript_path.suffix, ".txt")
            self.assertEqual(result["chat"]["active_session"]["title"], transcript_path.name)
            self.assertTrue(str(summary_path).startswith(str(chat_home)))
            self.assertTrue(str(transcript_path).startswith(str(chat_home)))
            self.assertTrue(transcript_path.name.startswith("Summarize the current repository state"))
            self.assertIn("Summarize the current repository state.", transcript_path.read_text(encoding="utf-8"))
            self.assertIn("Conversation reply.", transcript_path.read_text(encoding="utf-8"))
            self.assertIn("Rolling Summary", summary_path.read_text(encoding="utf-8"))

    def test_load_chat_sessions_migrates_legacy_project_chat_storage_into_global_chat_home(self) -> None:
        with TemporaryTestDir() as temp_dir:
            chat_home = temp_dir / "jakal-flow-chat"
            context = build_test_project_context(
                temp_dir,
                repo_id="legacy-chat-demo",
                slug="legacy-chat-demo",
                display_name="Legacy Chat Demo",
            )
            session_id = "chat-20260329010101-legacy"
            legacy_registry = context.paths.state_dir / "CHAT_SESSIONS.txt"
            legacy_active = context.paths.state_dir / "CHAT_ACTIVE_SESSION.txt"
            legacy_logs_dir = context.paths.logs_dir / "chat_sessions"
            legacy_memory_dir = context.paths.memory_dir / "chat_sessions"
            legacy_logs_dir.mkdir(parents=True, exist_ok=True)
            legacy_memory_dir.mkdir(parents=True, exist_ok=True)

            legacy_log_path = legacy_logs_dir / f"{session_id}.messages.txt"
            legacy_summary_path = legacy_memory_dir / f"{session_id}.summary.txt"
            legacy_transcript_path = legacy_memory_dir / f"{session_id}.transcript.txt"
            legacy_log_path.write_text(
                json.dumps(
                    {
                        "message_id": "msg-1",
                        "role": "user",
                        "text": "Legacy chat title source",
                        "created_at": "2026-03-29T01:01:01+00:00",
                        "mode": "conversation",
                        "status": "completed",
                        "metadata": {},
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            legacy_summary_path.write_text("legacy summary\n", encoding="utf-8")
            legacy_transcript_path.write_text("legacy transcript\n", encoding="utf-8")
            legacy_registry.write_text(
                json.dumps(
                    {
                        "session_id": session_id,
                        "title": "Legacy chat title source",
                        "created_at": "2026-03-29T01:01:01+00:00",
                        "updated_at": "2026-03-29T01:01:01+00:00",
                        "message_count": 1,
                        "last_mode": "conversation",
                        "summary_file": str(legacy_summary_path),
                        "transcript_file": str(legacy_transcript_path),
                        "log_file": str(legacy_log_path),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            legacy_active.write_text(f"{session_id}\n", encoding="utf-8")

            with mock.patch.dict(os.environ, {CHAT_HOME_ENV_VAR: str(chat_home)}):
                sessions = load_chat_sessions(context)

            self.assertEqual(len(sessions), 1)
            session = sessions[0]
            self.assertEqual(session.repo_id, context.metadata.repo_id)
            self.assertEqual(session.title, Path(session.transcript_file).name)
            self.assertTrue(session.title.startswith("Legacy chat title source"))
            self.assertTrue(Path(session.summary_file).exists())
            self.assertTrue(Path(session.transcript_file).exists())
            self.assertTrue(Path(session.log_file).exists())
            self.assertTrue(str(Path(session.transcript_file)).startswith(str(chat_home)))
            self.assertFalse(legacy_registry.exists())
            self.assertFalse(legacy_active.exists())
            self.assertFalse(legacy_log_path.exists())
            self.assertFalse(legacy_summary_path.exists())
            self.assertFalse(legacy_transcript_path.exists())

    def test_send_chat_message_conversation_uses_chat_model_override(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Chat Override Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model_provider": "openai",
                    "model": "gpt-5.4",
                    "model_slug_input": "gpt-5.4",
                    "chat_model_provider": "gemini",
                    "chat_model": "gemini-2.5-pro",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            captured: dict[str, str] = {}

            def fake_run_conversation_reply(context, *, prompt, session_id):
                captured["provider"] = context.runtime.model_provider
                captured["model"] = context.runtime.model
                captured["codex_path"] = context.runtime.codex_path
                return 0, "Conversation reply."

            with mock.patch("jakal_flow.chat_sessions._run_conversation_reply", side_effect=fake_run_conversation_reply):
                result = run_command(
                    "send-chat-message",
                    workspace_root,
                    {
                        **payload,
                        "repo_id": detail["project"]["repo_id"],
                        "message": "Use the chat override.",
                        "chat_mode": "conversation",
                    },
                )

            self.assertEqual(result["error"], "")
            self.assertEqual(captured["provider"], "gemini")
            self.assertEqual(captured["model"], "gemini-2.5-pro")
            self.assertIn("gemini", captured["codex_path"])

    def test_send_chat_message_debugger_routes_message_into_manual_recovery(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Chat Debugger Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }
            plan_payload = {
                "plan_title": "Chat Debugger Demo",
                "project_prompt": "Recover the failing step manually.",
                "summary": "One failed step remains.",
                "workflow_mode": "standard",
                "execution_mode": "parallel",
                "default_test_command": "python -m unittest",
                "steps": [
                    {
                        "step_id": "ST1",
                        "title": "Recover backend",
                        "display_description": "Repair the backend.",
                        "codex_description": "Repair the backend.",
                        "success_criteria": "Tests pass",
                        "test_command": "python -m unittest",
                        "reasoning_effort": "high",
                        "status": "failed",
                    }
                ],
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            captured: dict[str, str] = {}

            def fake_run_manual_debugger_recovery(self, project_dir, runtime, branch="main", origin_url=""):
                captured["extra_prompt"] = runtime.extra_prompt
                context = self.local_project(project_dir)
                assert context is not None
                return context, self.load_execution_plan_state(context), {
                    "pass_name": "block-search-debug",
                    "summary": "Recovered via chat.",
                    "commit_hash": "abc123",
                }

            with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: fake_codex_snapshot()), mock.patch(
                "jakal_flow.orchestrator.Orchestrator.run_manual_debugger_recovery",
                new=fake_run_manual_debugger_recovery,
            ):
                result = run_command(
                    "send-chat-message",
                    workspace_root,
                    {
                        **payload,
                        "repo_id": detail["project"]["repo_id"],
                        "plan": plan_payload,
                        "message": "Focus on the latest failing backend test.",
                        "chat_mode": "debugger",
                    },
                )

            self.assertEqual(captured["extra_prompt"], "Focus on the latest failing backend test.")
            self.assertEqual(result["chat_mode"], "debugger")
            self.assertEqual(result["error"], "")
            self.assertTrue(result["emit_project_changed"])
            self.assertIn("detail", result)
            self.assertIsNotNone(result["detail"])
            self.assertEqual(result["chat"]["active_session"]["last_mode"], "debugger")
            self.assertEqual(result["chat"]["messages"][0]["role"], "user")
            self.assertEqual(result["chat"]["messages"][-1]["role"], "assistant")
            self.assertIn("Manual debugger finished.", result["chat"]["messages"][-1]["text"])

    def test_send_chat_message_merger_routes_message_into_manual_recovery(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Chat Merger Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }
            plan_payload = {
                "plan_title": "Chat Merger Demo",
                "project_prompt": "Resolve the merge conflict manually.",
                "summary": "Two failed slices remain.",
                "workflow_mode": "standard",
                "execution_mode": "parallel",
                "default_test_command": "python -m unittest",
                "steps": [
                    {
                        "step_id": "ST1",
                        "title": "Frontend slice",
                        "display_description": "Finish the frontend slice.",
                        "codex_description": "Finish the frontend slice.",
                        "success_criteria": "Frontend slice is integrated",
                        "test_command": "python -m unittest",
                        "reasoning_effort": "high",
                        "status": "failed",
                    },
                    {
                        "step_id": "ST2",
                        "title": "Backend slice",
                        "display_description": "Finish the backend slice.",
                        "codex_description": "Finish the backend slice.",
                        "success_criteria": "Backend slice is integrated",
                        "test_command": "python -m unittest",
                        "reasoning_effort": "high",
                        "status": "failed",
                    },
                ],
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            captured: dict[str, str] = {}

            def fake_run_manual_merger_recovery(self, project_dir, runtime, branch="main", origin_url=""):
                captured["extra_prompt"] = runtime.extra_prompt
                context = self.local_project(project_dir)
                assert context is not None
                return context, self.load_execution_plan_state(context), {
                    "pass_name": "parallel-batch-merger",
                    "summary": "Merged via chat.",
                    "commit_hash": "def456",
                }

            with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: fake_codex_snapshot()), mock.patch(
                "jakal_flow.orchestrator.Orchestrator.run_manual_merger_recovery",
                new=fake_run_manual_merger_recovery,
            ):
                result = run_command(
                    "send-chat-message",
                    workspace_root,
                    {
                        **payload,
                        "repo_id": detail["project"]["repo_id"],
                        "plan": plan_payload,
                        "message": "Merge the recovered slices into the main line.",
                        "chat_mode": "merger",
                    },
                )

            self.assertEqual(captured["extra_prompt"], "Merge the recovered slices into the main line.")
            self.assertEqual(result["chat_mode"], "merger")
            self.assertEqual(result["error"], "")
            self.assertTrue(result["emit_project_changed"])
            self.assertIn("detail", result)
            self.assertIsNotNone(result["detail"])
            self.assertEqual(result["chat"]["active_session"]["last_mode"], "merger")
            self.assertEqual(result["chat"]["messages"][0]["role"], "user")
            self.assertEqual(result["chat"]["messages"][-1]["role"], "assistant")
            self.assertIn("Manual merger finished.", result["chat"]["messages"][-1]["text"])

    def test_run_plan_routes_single_hybrid_task_batches_through_lineage_execution(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Hybrid Dispatch Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                    "execution_mode": "parallel",
                },
            }
            hybrid_plan = {
                "plan_title": "Hybrid Dispatch Demo",
                "project_prompt": "Keep singleton hybrid steps on lineage branches.",
                "summary": "A downstream join makes this a hybrid lineage plan.",
                "workflow_mode": "standard",
                "execution_mode": "parallel",
                "default_test_command": "python -m unittest",
                "steps": [
                    {
                        "step_id": "ST1",
                        "title": "Frontend slice",
                        "display_description": "Build the frontend slice.",
                        "codex_description": "Implement the frontend slice.",
                        "success_criteria": "Frontend slice is ready.",
                        "test_command": "python -m unittest",
                        "reasoning_effort": "high",
                        "owned_paths": ["src/shared.py"],
                    },
                    {
                        "step_id": "ST2",
                        "title": "Backend slice",
                        "display_description": "Build the backend slice.",
                        "codex_description": "Implement the backend slice.",
                        "success_criteria": "Backend slice is ready.",
                        "test_command": "python -m unittest",
                        "reasoning_effort": "high",
                        "owned_paths": ["src/shared.py"],
                    },
                    {
                        "step_id": "ST3",
                        "title": "Join both slices",
                        "display_description": "Integrate both slices.",
                        "codex_description": "Integrate the completed slices on main.",
                        "success_criteria": "Integrated branch passes verification.",
                        "test_command": "python -m unittest",
                        "reasoning_effort": "high",
                        "depends_on": ["ST1", "ST2"],
                        "metadata": {"step_kind": "join", "merge_from": ["ST1", "ST2"], "join_policy": "all"},
                    },
                ],
            }

            def fake_lineage_batch(self, project_dir, runtime, step_ids, branch="main", origin_url=""):
                context = self.local_project(project_dir)
                assert context is not None
                saved = self.load_execution_plan_state(context)
                target = next(step for step in saved.steps if step.step_id == step_ids[0])
                target.status = "failed"
                target.notes = "lineage dispatch sentinel"
                saved = self.save_execution_plan_state(context, saved)
                context.metadata.current_status = "failed"
                self.workspace.save_project(context)
                return context, saved, [target]

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ), mock.patch(
                "jakal_flow.orchestrator.Orchestrator.run_parallel_execution_batch",
                new=fake_lineage_batch,
            ) as _unused, mock.patch(
                "jakal_flow.orchestrator.Orchestrator.run_saved_execution_step",
                side_effect=AssertionError("hybrid singleton batch should not use main-step execution"),
            ), mock.patch(
                "jakal_flow.orchestrator.Orchestrator.run_join_execution_step",
                side_effect=AssertionError("first hybrid batch should not be a join step"),
            ):
                result = run_command(
                    "run-plan",
                    workspace_root,
                    {
                        **payload,
                        "plan": hybrid_plan,
                    },
                )

            self.assertEqual(result["plan"]["steps"][0]["status"], "failed")
            self.assertEqual(result["plan"]["steps"][0]["notes"], "lineage dispatch sentinel")
            self.assertEqual(result["project"]["current_status"], "failed")

    def test_load_project_normalizes_stale_awaiting_review_without_pending_flag(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Stale Review Badge Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "require_checkpoint_approval": True,
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            project_root = Path(detail["project"]["project_root"])
            checkpoint_path = project_root / "state" / "CHECKPOINTS.json"
            checkpoint_path.write_text(
                json.dumps(
                    {
                        "checkpoints": [
                            {
                                "checkpoint_id": "CP1",
                                "title": "Review me",
                                "target_block": 1,
                                "status": "awaiting_review",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            loop_state_path = project_root / "state" / "LOOP_STATE.json"
            loop_state = json.loads(loop_state_path.read_text(encoding="utf-8"))
            loop_state["current_checkpoint_id"] = None
            loop_state["pending_checkpoint_approval"] = False
            loop_state_path.write_text(json.dumps(loop_state), encoding="utf-8")

            with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: fake_codex_snapshot()):
                loaded = run_command(
                    "load-project",
                    workspace_root,
                    {
                        "project_dir": str(repo_dir),
                    },
                )

            self.assertIsNone(loaded["checkpoints"]["pending"])
            self.assertEqual(loaded["checkpoints"]["items"][0]["status"], "approved")

    def test_load_project_normalizes_stale_awaiting_checkpoint_status_without_pending_flag(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Stale Project Status Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "require_checkpoint_approval": True,
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            project_root = Path(detail["project"]["project_root"])
            metadata_path = project_root / "metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["current_status"] = "awaiting_checkpoint_approval"
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

            loop_state_path = project_root / "state" / "LOOP_STATE.json"
            loop_state = json.loads(loop_state_path.read_text(encoding="utf-8"))
            loop_state["pending_checkpoint_approval"] = False
            loop_state["current_checkpoint_id"] = None
            loop_state_path.write_text(json.dumps(loop_state), encoding="utf-8")

            with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: fake_codex_snapshot()):
                loaded = run_command(
                    "load-project",
                    workspace_root,
                    {
                        "project_dir": str(repo_dir),
                    },
                )

            self.assertEqual(loaded["project"]["current_status"], "setup_ready")
            self.assertEqual(loaded["snapshot"]["project"]["current_status"], "setup_ready")
            self.assertEqual(loaded["bottom_panels"]["git_status"]["current_status"], "setup_ready")

    def test_list_projects_normalizes_stale_awaiting_checkpoint_status_without_pending_flag(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Stale List Status Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "require_checkpoint_approval": True,
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            project_root = Path(detail["project"]["project_root"])
            metadata_path = project_root / "metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["current_status"] = "awaiting_checkpoint_approval"
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

            loop_state_path = project_root / "state" / "LOOP_STATE.json"
            loop_state = json.loads(loop_state_path.read_text(encoding="utf-8"))
            loop_state["pending_checkpoint_approval"] = False
            loop_state["current_checkpoint_id"] = None
            loop_state_path.write_text(json.dumps(loop_state), encoding="utf-8")

            listing = run_command("list-projects", workspace_root)

            self.assertEqual(listing["projects"][0]["status"], "setup_ready")
            self.assertEqual(listing["workspace"]["ready_like"], 1)
            self.assertEqual(listing["workspace"]["running"], 0)

    def test_cli_list_repos_skips_unreadable_execution_plan_state(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_one = temp_dir / "repo-one"
            repo_two = temp_dir / "repo-two"
            repo_one.mkdir(parents=True, exist_ok=True)
            repo_two.mkdir(parents=True, exist_ok=True)

            base_payload = {
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", side_effect=[repo_one / ".venv", repo_two / ".venv"]), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail_one = run_command(
                    "save-project-setup",
                    workspace_root,
                    {
                        **base_payload,
                        "project_dir": str(repo_one),
                        "display_name": "Repo One",
                    },
                )
                detail_two = run_command(
                    "save-project-setup",
                    workspace_root,
                    {
                        **base_payload,
                        "project_dir": str(repo_two),
                        "display_name": "Repo Two",
                    },
                )

            broken_plan = Path(detail_one["project"]["project_root"]) / "state" / "EXECUTION_PLAN.json"
            broken_plan.write_text("{not-json", encoding="utf-8")

            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = cli_main(["list-repos", "--workspace-root", str(workspace_root)])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(len(payload), 2)
            self.assertEqual({item["slug"] for item in payload}, {detail_one["project"]["slug"], detail_two["project"]["slug"]})
            repo_one_entry = next(item for item in payload if item["slug"] == detail_one["project"]["slug"])
            self.assertEqual(repo_one_entry["status"], "setup_ready")
            self.assertEqual(stderr.getvalue(), "")

    def test_cli_list_repos_uses_metadata_status_without_loading_plan_when_not_needed(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Lazy Status Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            stdout = io.StringIO()
            stderr = io.StringIO()
            with mock.patch(
                "jakal_flow.cli.Orchestrator.load_execution_plan_state",
                side_effect=AssertionError("list-repos should not load plan for stable metadata statuses"),
            ), redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = cli_main(["list-repos", "--workspace-root", str(workspace_root)])

            self.assertEqual(exit_code, 0)
            listed = json.loads(stdout.getvalue())
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["slug"], detail["project"]["slug"])
            self.assertEqual(listed[0]["status"], "setup_ready")
            self.assertEqual(stderr.getvalue(), "")

    def test_run_command_writes_project_crash_log_on_bridge_failure(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Bridge Crash Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            def explode(_ctx):
                raise RuntimeError("bridge exploded")

            with mock.patch("jakal_flow.ui_bridge.bridge_command_handlers", return_value={"explode": explode}):
                with self.assertRaisesRegex(RuntimeError, "bridge exploded"):
                    run_command("explode", workspace_root, {"project_dir": str(repo_dir)})

            reports_dir = Path(detail["project"]["project_root"]) / "reports"
            crash_logs = sorted(reports_dir.glob("*_ui-bridge_explode.crash.log"))
            self.assertTrue(crash_logs)
            crash_text = crash_logs[-1].read_text(encoding="utf-8")
            self.assertIn("exception_message: bridge exploded", crash_text)
            self.assertIn("Traceback", crash_text)

    def test_cli_main_writes_project_crash_log_on_failure(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "CLI Crash Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            stdout = io.StringIO()
            stderr = io.StringIO()
            with mock.patch(
                "jakal_flow.cli.Orchestrator.status",
                side_effect=RuntimeError("cli exploded"),
            ), redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = cli_main(
                    [
                        "status",
                        "--workspace-root",
                        str(workspace_root),
                        "--repo-url",
                        str(repo_dir.resolve()),
                        "--branch",
                        "main",
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertIn("error: cli exploded", stderr.getvalue())
            reports_dir = Path(detail["project"]["project_root"]) / "reports"
            crash_logs = sorted(reports_dir.glob("*_cli_status.crash.log"))
            self.assertTrue(crash_logs)
            crash_text = crash_logs[-1].read_text(encoding="utf-8")
            self.assertIn("exception_message: cli exploded", crash_text)
            self.assertIn("\"repo_url\":", crash_text)

    def test_save_project_setup_clears_stale_pending_checkpoint_when_approval_is_disabled(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            enabled_payload = {
                "project_dir": str(repo_dir),
                "display_name": "Stale Checkpoint Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "require_checkpoint_approval": True,
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, enabled_payload)

            project_root = Path(detail["project"]["project_root"])
            checkpoint_path = project_root / "state" / "CHECKPOINTS.json"
            checkpoint_path.write_text(
                json.dumps(
                    {
                        "checkpoints": [
                            {
                                "checkpoint_id": "CP1",
                                "title": "Review me",
                                "target_block": 1,
                                "status": "awaiting_review",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            loop_state_path = project_root / "state" / "LOOP_STATE.json"
            loop_state = json.loads(loop_state_path.read_text(encoding="utf-8"))
            loop_state["current_checkpoint_id"] = "CP1"
            loop_state["pending_checkpoint_approval"] = True
            loop_state["stop_reason"] = "checkpoint approval required"
            loop_state_path.write_text(json.dumps(loop_state), encoding="utf-8")

            disabled_payload = {
                **enabled_payload,
                "runtime": {
                    **enabled_payload["runtime"],
                    "require_checkpoint_approval": False,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                updated = run_command("save-project-setup", workspace_root, disabled_payload)

            self.assertIsNone(updated["checkpoints"]["pending"])
            self.assertIsNone(updated["loop_state"]["current_checkpoint_id"])
            self.assertFalse(updated["loop_state"]["pending_checkpoint_approval"])
            self.assertIsNone(updated["loop_state"]["stop_reason"])
            self.assertTrue(all(item.get("status") != "awaiting_review" for item in updated["checkpoints"]["items"]))

    def test_load_project_can_skip_codex_status_refresh(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Fast Load Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                run_command("save-project-setup", workspace_root, payload)

            with mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=AssertionError("Codex status refresh should be skipped."),
            ):
                loaded = run_command(
                    "load-project",
                    workspace_root,
                    {
                        "project_dir": str(repo_dir),
                        "refresh_codex_status": False,
                        "detail_level": "core",
                    },
                )

            self.assertEqual(loaded["project"]["display_name"], "Fast Load Demo")
            self.assertEqual(loaded["detail_level"], "core")
            self.assertIn("provider_statuses", loaded["codex_status"])
            self.assertFalse(loaded["codex_status"].get("model_catalog"))
            self.assertIn("provider_statuses", loaded["bottom_panels"]["codex_status"])
            self.assertEqual(loaded["history"]["blocks"], [])
            self.assertEqual(loaded["workspace_tree"], [])
            self.assertEqual(loaded["checkpoints"]["items"], [])
            self.assertTrue(loaded["activity"])

    def test_load_project_exposes_structured_planning_progress(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Planning Progress Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            ui_event_log_file = Path(detail["files"]["ui_event_log_file"])
            with ui_event_log_file.open("a", encoding="utf-8") as handle:
                for event in [
                    {
                        "timestamp": "2026-03-27T10:00:00Z",
                        "event_type": "plan-started",
                        "message": "Collecting repository context for planning.",
                        "details": {
                            "flow": "planning",
                            "stage_key": "context_scan",
                            "stage_index": 1,
                            "stage_count": 4,
                            "status": "running",
                        },
                    },
                    {
                        "timestamp": "2026-03-27T10:00:05Z",
                        "event_type": "planner-agent-started",
                        "message": "Planner Agent A is decomposing the work into implementation blocks.",
                        "details": {
                            "flow": "planning",
                            "stage_key": "planner_a",
                            "stage_index": 2,
                            "stage_count": 4,
                            "status": "running",
                            "agent_label": "Planner Agent A",
                        },
                    },
                ]:
                    handle.write(json.dumps(event) + "\n")

            with mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                loaded = run_command(
                    "load-project",
                    workspace_root,
                    {
                        "repo_id": detail["project"]["repo_id"],
                        "refresh_codex_status": False,
                        "detail_level": "core",
                    },
                )

            planning_progress = loaded["planning_progress"]
            self.assertEqual(planning_progress["current_stage_key"], "planner_a")
            self.assertEqual(planning_progress["current_stage_index"], 2)
            self.assertEqual(planning_progress["current_stage_label"], "Planner Agent A")
            self.assertEqual(planning_progress["current_agent_label"], "Planner Agent A")
            self.assertEqual(planning_progress["percent"], 38)
            self.assertEqual(
                [item["status"] for item in planning_progress["stages"]],
                ["completed", "running", "pending", "pending"],
            )

    def test_load_project_reuses_cached_core_payload_when_state_is_unchanged(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Cached Core Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            cache_file = Path(detail["project"]["project_root"]) / "state" / "PROJECT_DETAIL_CACHE_CORE.json"
            if cache_file.exists():
                cache_file.unlink()

            first = run_command(
                "load-project",
                workspace_root,
                {
                    "repo_id": detail["project"]["repo_id"],
                    "refresh_codex_status": False,
                    "detail_level": "core",
                },
            )

            self.assertFalse(first["payload_cache_hit"])
            self.assertTrue(cache_file.exists())

            with mock.patch(
                "jakal_flow.ui_bridge_payloads._build_project_detail_base_payload",
                side_effect=AssertionError("The cached payload should be reused."),
            ):
                second = run_command(
                    "load-project",
                    workspace_root,
                    {
                        "repo_id": detail["project"]["repo_id"],
                        "refresh_codex_status": False,
                        "detail_level": "core",
                    },
                )

            self.assertTrue(second["payload_cache_hit"])
            self.assertEqual(second["detail_level"], "core")
            self.assertEqual(second["content_signature"], first["content_signature"])
            self.assertEqual(second["detail_signature"], first["detail_signature"])
            self.assertIn("content_signature", second)
            self.assertIn("detail_signature", second)

    def test_load_project_writes_bridge_and_detail_performance_logs(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Perf Log Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)
                run_command(
                    "load-project",
                    workspace_root,
                    {
                        "repo_id": detail["project"]["repo_id"],
                        "refresh_codex_status": False,
                        "detail_level": "core",
                    },
                )

            bridge_perf_entries = read_jsonl(workspace_root / "bridge_perf.jsonl")
            self.assertTrue(bridge_perf_entries)
            latest_bridge = bridge_perf_entries[-1]
            self.assertEqual(latest_bridge["command"], "load-project")
            self.assertEqual(latest_bridge["detail_level"], "core")
            self.assertIn("duration_ms", latest_bridge)
            self.assertIn("result_size_bytes", latest_bridge)

            detail_perf_entries = read_jsonl(repo_dir / "jakal-flow-logs" / "ui_bridge_perf.jsonl")
            self.assertTrue(detail_perf_entries)
            latest_detail = detail_perf_entries[-1]
            self.assertEqual(latest_detail["event_type"], "project-detail-built")
            self.assertEqual(latest_detail["details"]["detail_level"], "core")
            self.assertIn("total_ms", latest_detail["details"])
            self.assertIn("content_signature_ms", latest_detail["details"])
            self.assertIn("cache_hit", latest_detail["details"])

    def test_load_project_core_detail_reads_each_log_tail_once_on_cache_miss(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Core Detail Tail Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            project_root = Path(detail["project"]["project_root"])
            core_cache = project_root / "state" / "PROJECT_DETAIL_CACHE_CORE.json"
            if core_cache.exists():
                core_cache.unlink()

            tail_calls: list[str] = []
            last_calls: list[str] = []
            original_tail = ui_bridge_payloads.read_jsonl_tail
            original_last = ui_bridge_payloads.read_last_jsonl

            def counting_tail(path, *args, **kwargs):
                tail_calls.append(Path(path).name)
                return original_tail(path, *args, **kwargs)

            def counting_last(path, *args, **kwargs):
                last_calls.append(Path(path).name)
                return original_last(path, *args, **kwargs)

            with mock.patch("jakal_flow.ui_bridge_payloads.read_jsonl_tail", side_effect=counting_tail), mock.patch(
                "jakal_flow.ui_bridge_payloads.read_last_jsonl",
                side_effect=counting_last,
            ), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                loaded = run_command(
                    "load-project",
                    workspace_root,
                    {
                        "repo_id": detail["project"]["repo_id"],
                        "refresh_codex_status": False,
                        "detail_level": "core",
                    },
                )

            counts = Counter(tail_calls)
            self.assertFalse(loaded["payload_cache_hit"])
            self.assertEqual(counts["ui_events.jsonl"], 1)
            self.assertEqual(counts["passes.jsonl"], 1)
            self.assertEqual(counts["test_runs.jsonl"], 1)
            self.assertNotIn("passes.jsonl", last_calls)

    def test_load_project_core_detail_uses_lightweight_share_payload(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Core Share Payload Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            with mock.patch(
                "jakal_flow.ui_bridge_payloads.project_share_payload",
                side_effect=AssertionError("core detail should not build the heavy share payload"),
            ):
                loaded = run_command(
                    "load-project",
                    workspace_root,
                    {
                        "repo_id": detail["project"]["repo_id"],
                        "refresh_codex_status": False,
                        "detail_level": "core",
                    },
                )

            self.assertEqual(loaded["detail_level"], "core")
            self.assertIn("share", loaded)
            self.assertEqual(loaded["share"]["sessions"], [])
            self.assertIsNone(loaded["share"]["active_session"])
            self.assertEqual(loaded["share"]["server"]["config"]["bind_host"], "0.0.0.0")

    def test_load_project_full_detail_reads_each_log_tail_once_on_cache_miss(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Full Detail Tail Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            project_root = Path(detail["project"]["project_root"])
            full_cache = project_root / "state" / "PROJECT_DETAIL_CACHE_FULL.json"
            if full_cache.exists():
                full_cache.unlink()

            tail_calls: list[str] = []
            last_calls: list[str] = []
            original_tail = ui_bridge_payloads.read_jsonl_tail
            original_last = ui_bridge_payloads.read_last_jsonl

            def counting_tail(path, *args, **kwargs):
                tail_calls.append(Path(path).name)
                return original_tail(path, *args, **kwargs)

            def counting_last(path, *args, **kwargs):
                last_calls.append(Path(path).name)
                return original_last(path, *args, **kwargs)

            with mock.patch("jakal_flow.ui_bridge_payloads.read_jsonl_tail", side_effect=counting_tail), mock.patch(
                "jakal_flow.ui_bridge_payloads.read_last_jsonl",
                side_effect=counting_last,
            ), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                loaded = run_command(
                    "load-project",
                    workspace_root,
                    {
                        "repo_id": detail["project"]["repo_id"],
                        "refresh_codex_status": False,
                        "detail_level": "full",
                    },
                )

            counts = Counter(tail_calls)
            self.assertFalse(loaded["payload_cache_hit"])
            self.assertEqual(counts["ui_events.jsonl"], 1)
            self.assertEqual(counts["blocks.jsonl"], 1)
            self.assertEqual(counts["passes.jsonl"], 1)
            self.assertEqual(counts["test_runs.jsonl"], 1)
            self.assertNotIn("blocks.jsonl", last_calls)
            self.assertNotIn("passes.jsonl", last_calls)

    def test_share_bridge_commands_create_and_revoke_read_only_session(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Share Bridge Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m pytest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                run_command("save-project-setup", workspace_root, payload)

            try:
                server_status = run_command("start_share_server", workspace_root, {})
                self.assertTrue(server_status["running"])
                self.assertTrue(str(server_status["base_url"]).startswith("http://0.0.0.0:"))

                with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: fake_codex_snapshot()):
                    created = run_command(
                        "create_share_session",
                        workspace_root,
                        {
                            "project_dir": str(repo_dir),
                            "created_by": "unit-test",
                            "bind_host": "0.0.0.0",
                            "public_base_url": "https://share.example.com/base",
                        },
                    )
                self.assertIn("share", created)
                self.assertIn("created_share_session", created)
                self.assertTrue(created["created_share_session"]["share_url"].startswith("https://share.example.com/base/share/view?"))
                self.assertTrue(created["created_share_session"]["local_url"].startswith("http://"))
                self.assertEqual(created["share"]["active_session"]["created_by"], "unit-test")
                self.assertEqual(created["share"]["server"]["config"]["bind_host"], "0.0.0.0")
                self.assertEqual(created["share"]["server"]["config"]["public_base_url"], "https://share.example.com/base")

                with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: fake_codex_snapshot()):
                    revoked = run_command(
                        "revoke_share_session",
                        workspace_root,
                        {
                            "project_dir": str(repo_dir),
                            "session_id": created["share"]["active_session"]["session_id"],
                        },
                    )
                self.assertIsNone(revoked["share"]["active_session"])
                self.assertIn("revoked_share_session", revoked)
            finally:
                run_command("stop_share_server", workspace_root, {})

    def test_share_bridge_revoke_accepts_workspace_active_session_from_other_project(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_one = temp_dir / "repo-one"
            repo_two = temp_dir / "repo-two"
            repo_one.mkdir(parents=True, exist_ok=True)
            repo_two.mkdir(parents=True, exist_ok=True)

            payload_one = {
                "project_dir": str(repo_one),
                "display_name": "Share Bridge Demo One",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m pytest",
                    "max_blocks": 5,
                },
            }
            payload_two = {
                "project_dir": str(repo_two),
                "display_name": "Share Bridge Demo Two",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m pytest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_one / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                run_command("save-project-setup", workspace_root, payload_one)
            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_two / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                run_command("save-project-setup", workspace_root, payload_two)

            try:
                run_command("start_share_server", workspace_root, {})
                with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: fake_codex_snapshot()):
                    created = run_command(
                        "create_share_session",
                        workspace_root,
                        {
                            "project_dir": str(repo_one),
                            "created_by": "unit-test",
                            "bind_host": "0.0.0.0",
                            "public_base_url": "https://share.example.com/base",
                        },
                    )
                active_session = created["share"]["active_session"]
                self.assertEqual(active_session["session_id"], created["created_share_session"]["session_id"])

                with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: fake_codex_snapshot()):
                    revoked = run_command(
                        "revoke_share_session",
                        workspace_root,
                        {
                            "project_dir": str(repo_two),
                            "session_id": active_session["session_id"],
                        },
                    )

                self.assertIsNone(revoked["share"]["active_session"])
                self.assertEqual(revoked["project"]["display_name"], "Share Bridge Demo Two")
            finally:
                run_command("stop_share_server", workspace_root, {})

    def test_share_bridge_can_create_workspace_share_without_project(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"

            try:
                run_command("start_share_server", workspace_root, {})
                created = run_command(
                    "create_share_session",
                    workspace_root,
                    {
                        "created_by": "unit-test",
                        "bind_host": "0.0.0.0",
                        "public_base_url": "https://share.example.com/base",
                    },
                )

                self.assertIn("share", created)
                self.assertTrue(created["created_share_session"]["share_url"].startswith("https://share.example.com/base/share/view?"))
                self.assertEqual(created["share"]["active_session"]["session_id"], created["created_share_session"]["session_id"])
                self.assertEqual(created["share"]["server"]["config"]["public_base_url"], "https://share.example.com/base")

                share_payload = run_command("load-workspace-share", workspace_root, {})
                self.assertEqual(
                    share_payload["share"]["active_session"]["session_id"],
                    created["created_share_session"]["session_id"],
                )
            finally:
                run_command("stop_share_server", workspace_root, {})

    def test_share_bridge_reuses_stable_share_url_when_regenerating_link(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"

            try:
                run_command("start_share_server", workspace_root, {})
                first = run_command(
                    "create_share_session",
                    workspace_root,
                    {
                        "created_by": "unit-test",
                        "bind_host": "0.0.0.0",
                        "public_base_url": "https://share.example.com/base",
                    },
                )
                second = run_command(
                    "create_share_session",
                    workspace_root,
                    {
                        "created_by": "unit-test",
                        "bind_host": "0.0.0.0",
                        "public_base_url": "https://share.example.com/base",
                    },
                )

                self.assertEqual(first["created_share_session"]["share_url"], second["created_share_session"]["share_url"])
                self.assertEqual(first["created_share_session"]["local_url"], second["created_share_session"]["local_url"])
                self.assertNotEqual(first["created_share_session"]["session_id"], second["created_share_session"]["session_id"])
                self.assertIn("?access=", first["created_share_session"]["share_url"])
            finally:
                run_command("stop_share_server", workspace_root, {})

    def test_share_bridge_restarts_stale_share_server_when_new_session_validation_fails(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"

            try:
                with mock.patch(
                    "jakal_flow.ui_bridge.start_share_server_process",
                    wraps=ui_bridge.start_share_server_process,
                ) as start_server, mock.patch(
                    "jakal_flow.ui_bridge.stop_share_server_process",
                    wraps=ui_bridge.stop_share_server_process,
                ) as stop_server, mock.patch(
                    "jakal_flow.ui_bridge_commands.share.verify_local_share_session_access",
                    side_effect=[RuntimeError("Unknown share session."), None],
                ) as verify_share:
                    created = run_command(
                        "create_share_session",
                        workspace_root,
                        {
                            "created_by": "unit-test",
                            "bind_host": "0.0.0.0",
                            "public_base_url": "https://share.example.com/base",
                        },
                    )

                self.assertTrue(created["created_share_session"]["share_url"].startswith("https://share.example.com/base/share/view?"))
                self.assertEqual(verify_share.call_count, 2)
                self.assertEqual(start_server.call_count, 2)
                self.assertGreaterEqual(stop_server.call_count, 1)
            finally:
                run_command("stop_share_server", workspace_root, {})

    def test_share_bridge_can_auto_start_quick_tunnel_for_public_phone_link(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Quick Tunnel Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m pytest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                run_command("save-project-setup", workspace_root, payload)

            def tunnel_payload(target_url: str) -> dict[str, object]:
                return {
                    "running": True,
                    "provider": "cloudflare-quick-tunnel",
                    "public_url": "https://demo.trycloudflare.com",
                    "target_url": target_url,
                    "pid": 4242,
                    "started_at": "2026-03-26T00:00:00+00:00",
                    "available": True,
                }

            def current_tunnel_status(_workspace_root: Path) -> dict[str, object]:
                share_state_path = workspace_root / "share_server.json"
                if not share_state_path.exists():
                    return {
                        "running": False,
                        "provider": "cloudflare-quick-tunnel",
                        "public_url": "",
                        "target_url": "",
                        "pid": None,
                        "started_at": None,
                        "available": True,
                    }
                state = json.loads(share_state_path.read_text(encoding="utf-8"))
                return tunnel_payload(f"http://{state['host']}:{state['port']}")

            try:
                with mock.patch(
                    "jakal_flow.ui_bridge.start_cloudflare_quick_tunnel",
                    side_effect=lambda actual_workspace_root, target_url: tunnel_payload(target_url),
                ) as start_tunnel, mock.patch(
                    "jakal_flow.public_tunnel.public_tunnel_status_payload",
                    side_effect=current_tunnel_status,
                ), mock.patch(
                    "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                    side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
                ):
                    created = run_command(
                        "create_share_session",
                        workspace_root,
                        {
                            "project_dir": str(repo_dir),
                            "created_by": "unit-test",
                            "bind_host": "0.0.0.0",
                            "public_base_url": "",
                        },
                    )

                start_tunnel.assert_called_once()
                self.assertEqual(created["share"]["server"]["share_base_url"], "https://demo.trycloudflare.com")
                self.assertEqual(created["share"]["server"]["share_base_url_source"], "quick_tunnel")
                self.assertTrue(created["created_share_session"]["share_url"].startswith("https://demo.trycloudflare.com/share/view?"))
            finally:
                run_command("stop_share_server", workspace_root, {})

    def test_share_bridge_rejects_local_only_share_session_when_quick_tunnel_fails(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Tunnel Fallback Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m pytest",
                    "max_blocks": 5,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                run_command("save-project-setup", workspace_root, payload)

            try:
                with mock.patch(
                    "jakal_flow.ui_bridge.start_cloudflare_quick_tunnel",
                    side_effect=RuntimeError("quick tunnel startup failed"),
                ), mock.patch(
                    "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                    side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
                ):
                    with self.assertRaisesRegex(RuntimeError, "Public share URL could not be created"):
                        run_command(
                            "create_share_session",
                            workspace_root,
                            {
                                "project_dir": str(repo_dir),
                                "created_by": "unit-test",
                                "bind_host": "0.0.0.0",
                                "public_base_url": "",
                            },
                        )

                status = share_server_status_payload(workspace_root)
                self.assertFalse(status["running"])
                with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: fake_codex_snapshot()):
                    loaded = run_command(
                        "load-project",
                        workspace_root,
                        {
                            "project_dir": str(repo_dir),
                            "refresh_codex_status": False,
                        },
                    )
                self.assertIsNone(loaded["share"]["active_session"])
            finally:
                run_command("stop_share_server", workspace_root, {})


if __name__ == "__main__":
    unittest.main()
