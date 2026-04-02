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
import jakal_flow.chat_sessions as chat_sessions
import jakal_flow.orchestrator as orchestrator_module
import jakal_flow.share as share_module
import jakal_flow.ui_bridge as ui_bridge
import jakal_flow.ui_bridge_payloads as ui_bridge_payloads
from jakal_flow.ui_bridge_commands.read_models import build_read_model_handlers
from jakal_flow.ui_bridge_commands.runs import _effective_parallel_worker_count
import jakal_flow.workspace as workspace_module
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
        planning_metrics_file=logs_dir / "planning_metrics.jsonl",
        checkpoint_state_file=state_dir / "CHECKPOINTS.json",
        execution_plan_file=state_dir / "EXECUTION_PLAN.json",
        planning_inputs_cache_file=state_dir / "PLANNING_INPUTS_CACHE.json",
        planning_prompt_cache_file=state_dir / "PLANNING_PROMPT_CACHE.json",
        block_plan_cache_file=state_dir / "BLOCK_PLAN_CACHE.json",
        lineage_state_file=state_dir / "LINEAGES.json",
        spine_file=state_dir / "SPINE.json",
        common_requirements_file=state_dir / "COMMON_REQUIREMENTS.json",
        contract_wave_audit_file=state_dir / "CONTRACT_WAVE_AUDIT.jsonl",
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
            context.loop_state.current_checkpoint_id = "CP2"

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
            self.assertEqual(payload["event"]["details"]["current_checkpoint_id"], "CP2")
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

    def test_project_detail_payload_can_bypass_detail_cache_for_manual_refresh(self) -> None:
        with TemporaryTestDir() as temp_dir:
            project = build_test_project_context(temp_dir)
            base_payload = {"project": {"repo_id": project.metadata.repo_id}, "detail_level": "core"}
            captured_kwargs: dict[str, object] = {}

            def fake_cached_project_detail_base_payload(
                orchestrator,
                project_arg,
                normalized_detail_level,
                load_run_control,
                *,
                bypass_cache=False,
                execution_processes=None,
            ):
                captured_kwargs["bypass_cache"] = bypass_cache
                captured_kwargs["detail_level"] = normalized_detail_level
                captured_kwargs["project_repo_id"] = project_arg.metadata.repo_id
                captured_kwargs["execution_processes"] = execution_processes
                return base_payload, "sig-123", False, {"detail_level": normalized_detail_level}

            with mock.patch.object(
                ui_bridge_payloads,
                "_cached_project_detail_base_payload",
                side_effect=fake_cached_project_detail_base_payload,
            ), mock.patch.object(
                ui_bridge_payloads,
                "_finalize_project_detail_payload",
                side_effect=lambda payload, **_kwargs: payload,
            ):
                result = ui_bridge_payloads.project_detail_payload(
                    mock.Mock(),
                    project,
                    load_run_control=lambda _project: {},
                    refresh_codex_status=False,
                    detail_level="core",
                    bypass_detail_cache=True,
                )

            self.assertEqual(result, base_payload)
            self.assertEqual(captured_kwargs["bypass_cache"], True)
            self.assertEqual(captured_kwargs["detail_level"], "core")
            self.assertEqual(captured_kwargs["project_repo_id"], project.metadata.repo_id)

    def test_project_detail_payload_includes_explicit_snapshot_sources(self) -> None:
        with TemporaryTestDir() as temp_dir:
            project = build_test_project_context(temp_dir)
            orchestrator = mock.Mock()
            orchestrator.load_execution_plan_state.return_value = ExecutionPlanState(default_test_command=project.runtime.test_cmd)
            with mock.patch.object(ui_bridge_payloads, "_provider_statuses_for_detail", return_value={}), mock.patch.object(
                ui_bridge_payloads,
                "project_share_payload",
                return_value={"share": "full"},
            ):
                result = ui_bridge_payloads.project_detail_payload(
                    orchestrator,
                    project,
                    load_run_control=lambda _project: {},
                    refresh_codex_status=False,
                    detail_level="full",
                    bypass_detail_cache=True,
                )

            self.assertEqual(result["snapshot"]["snapshot_kind"], "cache_view")
            self.assertEqual(result["snapshot"]["state_origin"], "cache_view")
            self.assertIn("snapshot_sources", result)
            self.assertIn("persisted_state", result["snapshot_sources"])
            self.assertIn("event_derived", result["snapshot_sources"])
            self.assertIn("live_runtime", result["snapshot_sources"])
            self.assertIn("cache_view", result["snapshot_sources"])
            self.assertEqual(result["snapshot_sources"]["persisted_state"]["snapshot_kind"], "persisted_state")
            self.assertEqual(result["snapshot_sources"]["event_derived"]["snapshot_kind"], "event_derived")
            self.assertEqual(result["snapshot_sources"]["live_runtime"]["snapshot_kind"], "live_runtime")
            self.assertEqual(result["snapshot_sources"]["cache_view"]["snapshot_kind"], "cache_view")

    def test_project_detail_payload_includes_execution_processes(self) -> None:
        with TemporaryTestDir() as temp_dir:
            project = build_test_project_context(temp_dir)
            orchestrator = mock.Mock()
            orchestrator.load_execution_plan_state.return_value = ExecutionPlanState(default_test_command=project.runtime.test_cmd)
            execution_processes = [{"scope_id": "repo-1", "label": "Block 1", "pid": 4321}]
            with mock.patch.object(ui_bridge_payloads, "_provider_statuses_for_detail", return_value={}), mock.patch.object(
                ui_bridge_payloads,
                "project_share_payload",
                return_value={"share": "full"},
            ):
                result = ui_bridge_payloads.project_detail_payload(
                    orchestrator,
                    project,
                    load_run_control=lambda _project: {},
                    refresh_codex_status=False,
                    detail_level="full",
                    execution_processes=execution_processes,
                    bypass_detail_cache=True,
                )

            self.assertEqual(result["execution_processes"], execution_processes)

    def test_load_visible_project_state_passes_bypass_detail_cache_to_detail_payload(self) -> None:
        with TemporaryTestDir() as temp_dir:
            project = build_test_project_context(temp_dir)
            captured_kwargs: dict[str, object] = {}

            def fake_detail_payload(_project, **kwargs):
                captured_kwargs.update(kwargs)
                return {"project": {"repo_id": project.metadata.repo_id}}

            handlers = build_read_model_handlers(
                bootstrap_payload=lambda _workspace_root: {"workspace_root": str(temp_dir / "workspace")},
                resolve_project=lambda _orchestrator, _payload: project,
                resolve_history_project=lambda _orchestrator, _payload: project,
                coerce_bool=lambda value, default=False: bool(value) if value is not None else default,
                codex_snapshot_service=mock.Mock(invalidate=mock.Mock()),
            )
            ctx = mock.Mock(
                orchestrator=mock.Mock(),
                payload={
                    "repo_id": project.metadata.repo_id,
                    "refresh_codex_status": False,
                    "detail_level": "core",
                    "include_listing": False,
                    "bypass_detail_cache": True,
                },
                detail_payload=fake_detail_payload,
                workspace_root=project.paths.workspace_root,
            )

            result = handlers["load-visible-project-state"](ctx)

            self.assertEqual(result["detail"]["project"]["repo_id"], project.metadata.repo_id)
            self.assertTrue(captured_kwargs["bypass_detail_cache"])
            self.assertEqual(captured_kwargs["detail_level"], "core")
            self.assertFalse(captured_kwargs["refresh_codex_status"])

    def test_load_project_passes_bypass_detail_cache_to_detail_payload(self) -> None:
        with TemporaryTestDir() as temp_dir:
            project = build_test_project_context(temp_dir)
            captured_kwargs: dict[str, object] = {}

            def fake_detail_payload(_project, **kwargs):
                captured_kwargs.update(kwargs)
                return {"project": {"repo_id": project.metadata.repo_id}}

            handlers = build_read_model_handlers(
                bootstrap_payload=lambda _workspace_root: {"workspace_root": str(temp_dir / "workspace")},
                resolve_project=lambda _orchestrator, _payload: project,
                resolve_history_project=lambda _orchestrator, _payload: project,
                coerce_bool=lambda value, default=False: bool(value) if value is not None else default,
                codex_snapshot_service=mock.Mock(invalidate=mock.Mock()),
            )
            ctx = mock.Mock(
                orchestrator=mock.Mock(),
                payload={
                    "repo_id": project.metadata.repo_id,
                    "refresh_codex_status": False,
                    "detail_level": "core",
                    "bypass_detail_cache": True,
                },
                detail_payload=fake_detail_payload,
                workspace_root=project.paths.workspace_root,
            )

            result = handlers["load-project"](ctx)

            self.assertEqual(result["project"]["repo_id"], project.metadata.repo_id)
            self.assertTrue(captured_kwargs["bypass_detail_cache"])
            self.assertEqual(captured_kwargs["detail_level"], "core")
            self.assertFalse(captured_kwargs["refresh_codex_status"])

    def test_load_visible_project_state_passes_bypass_listing_cache_to_listing_payload(self) -> None:
        with TemporaryTestDir() as temp_dir:
            project = build_test_project_context(temp_dir)
            captured_kwargs: dict[str, object] = {}

            def fake_list_projects_payload(_orchestrator, *, bypass_cache=False):
                captured_kwargs["bypass_cache"] = bypass_cache
                return {"projects": [{"repo_id": project.metadata.repo_id}], "history": []}

            def fake_detail_payload(_project, **kwargs):
                return {"project": {"repo_id": project.metadata.repo_id}}

            handlers = build_read_model_handlers(
                bootstrap_payload=lambda _workspace_root: {"workspace_root": str(temp_dir / "workspace")},
                resolve_project=lambda _orchestrator, _payload: project,
                resolve_history_project=lambda _orchestrator, _payload: project,
                coerce_bool=lambda value, default=False: bool(value) if value is not None else default,
                codex_snapshot_service=mock.Mock(invalidate=mock.Mock()),
            )
            ctx = mock.Mock(
                orchestrator=mock.Mock(),
                payload={
                    "repo_id": project.metadata.repo_id,
                    "refresh_codex_status": False,
                    "detail_level": "core",
                    "include_listing": True,
                    "bypass_detail_cache": False,
                    "bypass_listing_cache": True,
                },
                detail_payload=fake_detail_payload,
                workspace_root=project.paths.workspace_root,
            )

            with mock.patch("jakal_flow.ui_bridge_commands.read_models.list_projects_payload", side_effect=fake_list_projects_payload):
                result = handlers["load-visible-project-state"](ctx)

            self.assertEqual(result["listing"]["projects"][0]["repo_id"], project.metadata.repo_id)
            self.assertTrue(captured_kwargs["bypass_cache"])

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

    def test_default_workspace_root_prefers_repo_workspace_over_cwd(self) -> None:
        with TemporaryTestDir() as temp_dir:
            repo_dir = temp_dir / "repo"
            repo_workspace = repo_dir / ".jakal-flow-workspace"
            cwd_dir = temp_dir / "cwd"
            cwd_workspace = cwd_dir / ".jakal-flow-workspace"
            home_dir = temp_dir / "home"
            repo_workspace.mkdir(parents=True, exist_ok=True)
            cwd_workspace.mkdir(parents=True, exist_ok=True)
            home_dir.mkdir(parents=True, exist_ok=True)
            with mock.patch.dict(os.environ, {}, clear=True), mock.patch(
                "jakal_flow.ui_bridge.repo_root",
                return_value=repo_dir,
            ), mock.patch(
                "jakal_flow.ui_bridge.Path.cwd",
                return_value=cwd_dir,
            ), mock.patch(
                "jakal_flow.ui_bridge.Path.home",
                return_value=home_dir,
            ):
                resolved = default_workspace_root()

        self.assertEqual(resolved, repo_workspace.resolve())

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

        self.assertEqual(caption, "Completed 1/4 steps, pending: ST2, ST3")

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

    def test_effective_parallel_worker_count_uses_multiple_workers_for_multi_step_batches(self) -> None:
        self.assertEqual(_effective_parallel_worker_count(1, 1), 1)
        self.assertEqual(_effective_parallel_worker_count(1, 2), 2)
        self.assertEqual(_effective_parallel_worker_count(3, 2), 2)
        self.assertEqual(_effective_parallel_worker_count(4, 5), 4)

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

    def test_effective_project_status_promotes_running_planning_progress_over_ready_like_state(self) -> None:
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
            planning_progress={"current_stage_status": "running"},
        )

        self.assertEqual(status, "running:generate-plan")

    def test_history_payload_refreshes_flow_svg_when_step_status_changes(self) -> None:
        with TemporaryTestDir() as temp_dir:
            context = build_test_project_context(
                temp_dir,
                repo_id="repo-flow",
                slug="repo-flow",
                display_name="Flow Demo",
            )
            ui_bridge_payloads._SECTION_PAYLOAD_MEMORY_CACHE.clear()

            initial_plan = ExecutionPlanState(
                execution_mode="parallel",
                steps=[ExecutionStep(step_id="ST1", title="Plan work", status="pending")],
            )
            context.paths.execution_plan_file.write_text(
                json.dumps(initial_plan.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            first_history = ui_bridge_payloads.history_payload(context)

            updated_plan = ExecutionPlanState(
                execution_mode="parallel",
                steps=[ExecutionStep(step_id="ST1", title="Plan work", status="running")],
            )
            context.paths.execution_plan_file.write_text(
                json.dumps(updated_plan.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            second_history = ui_bridge_payloads.history_payload(context)

            self.assertIn(">pending<", first_history["flow_svg_text"])
            self.assertIn(">running<", second_history["flow_svg_text"])
            self.assertNotEqual(first_history["flow_svg_text"], second_history["flow_svg_text"])

    def test_history_payload_refreshes_flow_svg_from_lineage_block_logs(self) -> None:
        with TemporaryTestDir() as temp_dir:
            context = build_test_project_context(
                temp_dir,
                repo_id="repo-flow-lineage",
                slug="repo-flow-lineage",
                display_name="Flow Lineage Demo",
            )
            ui_bridge_payloads._SECTION_PAYLOAD_MEMORY_CACHE.clear()

            plan = ExecutionPlanState(
                execution_mode="parallel",
                steps=[
                    ExecutionStep(step_id="ST1", title="Frontend", status="pending", metadata={"lineage_id": "LN1"}),
                    ExecutionStep(step_id="ST2", title="Backend", status="pending", metadata={"lineage_id": "LN2"}),
                ],
            )
            context.paths.execution_plan_file.write_text(
                json.dumps(plan.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            context.paths.block_log_file.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "block_index": 7,
                                "lineage_id": "LN2",
                                "status": "failed",
                                "selected_task": "Backend",
                                "test_summary": "backend failed",
                            },
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            {
                                "block_index": 7,
                                "lineage_id": "LN1",
                                "status": "completed",
                                "selected_task": "Frontend",
                                "test_summary": "frontend done",
                            },
                            ensure_ascii=False,
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            if context.paths.execution_flow_svg_file.exists():
                context.paths.execution_flow_svg_file.unlink()

            history = ui_bridge_payloads.history_payload(context)

            self.assertTrue(context.paths.execution_flow_svg_file.exists())
            self.assertIn("execution-flow-signature:", history["flow_svg_text"])
            self.assertIn(">completed<", history["flow_svg_text"])
            self.assertIn(">failed<", history["flow_svg_text"])

    def test_history_payload_refreshes_flow_svg_when_block_log_changes(self) -> None:
        with TemporaryTestDir() as temp_dir:
            context = build_test_project_context(
                temp_dir,
                repo_id="repo-flow-refresh",
                slug="repo-flow-refresh",
                display_name="Flow Refresh Demo",
            )
            ui_bridge_payloads._SECTION_PAYLOAD_MEMORY_CACHE.clear()

            plan = ExecutionPlanState(
                execution_mode="parallel",
                steps=[
                    ExecutionStep(step_id="ST1", title="Frontend", status="pending", metadata={"lineage_id": "LN1"}),
                ],
            )
            context.paths.execution_plan_file.write_text(
                json.dumps(plan.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            context.paths.block_log_file.write_text(
                json.dumps(
                    {
                        "block_index": 1,
                        "lineage_id": "LN1",
                        "status": "running",
                        "selected_task": "Frontend",
                        "test_summary": "still running",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            first_history = ui_bridge_payloads.history_payload(context)

            context.paths.block_log_file.write_text(
                json.dumps(
                    {
                        "block_index": 1,
                        "lineage_id": "LN1",
                        "status": "completed",
                        "selected_task": "Frontend",
                        "test_summary": "frontend done",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            second_history = ui_bridge_payloads.history_payload(context)

            self.assertNotEqual(first_history["flow_svg_text"], second_history["flow_svg_text"])
            self.assertIn(">running<", first_history["flow_svg_text"])
            self.assertIn(">completed<", second_history["flow_svg_text"])

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
        self.assertEqual(runtime.optimization_mode, "off")
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

    def test_runtime_from_payload_defaults_fast_mode_for_desktop(self) -> None:
        runtime = runtime_from_payload(
            {
                "model": "gpt-5.4",
            }
        )

        self.assertTrue(runtime.use_fast_mode)

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

    def test_provider_execution_preflight_error_blocks_known_invalid_gemini_model(self) -> None:
        fake_snapshot = mock.Mock(
            to_dict=mock.Mock(
                return_value={
                    "available": True,
                    "model_catalog": [
                        {"provider": "gemini", "model": "gemini-3-flash-preview"},
                        {"provider": "gemini", "model": "gemini-2.5-pro"},
                    ],
                    "account": {},
                    "rate_limits": {"default_limit_id": "", "items": []},
                    "error": "",
                }
            )
        )
        with mock.patch("jakal_flow.step_models._command_available", return_value=True), mock.patch(
            "jakal_flow.step_models._gemini_runtime_auth_configured",
            return_value=True,
        ), mock.patch(
            "jakal_flow.step_models.fetch_codex_backend_snapshot",
            return_value=fake_snapshot,
        ):
            error = provider_execution_preflight_error(
                "gemini",
                codex_path="gemini-invalid-model.cmd",
                repo_dir=Path.cwd(),
                provider_api_key_env="GEMINI_API_KEY",
                model="gemini-not-real",
            )

        self.assertIn("not available", error)
        self.assertIn("gemini-not-real", error)

    def test_bootstrap_payload_includes_provider_statuses(self) -> None:
        with TemporaryTestDir() as temp_dir, mock.patch(
            "jakal_flow.ui_bridge.tooling_snapshot_payload",
            return_value={
                "codex_status": {
                    **fake_codex_snapshot().to_dict(),
                    "provider_statuses": {"openai": {"available": True}},
                },
                "model_catalog": fake_codex_snapshot().model_catalog,
                "tooling_statuses": {"codex": {"installed": True}},
            },
        ):
            payload = ui_bridge.bootstrap_payload(temp_dir / "workspace")

        self.assertIn("provider_statuses", payload["codex_status"])
        self.assertEqual(payload["codex_status"]["provider_statuses"]["openai"]["available"], True)
        self.assertIn("tooling_statuses", payload)

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

    def test_runtime_from_payload_preserves_explicit_fast_mode_disable(self) -> None:
        runtime = runtime_from_payload(
            {
                "model": "gpt-5.4",
                "use_fast_mode": "false",
            }
        )

        self.assertEqual(runtime.model, "gpt-5.4")
        self.assertFalse(runtime.use_fast_mode)

    def test_runtime_from_payload_accepts_compact_planning_alias(self) -> None:
        runtime = runtime_from_payload(
            {
                "model": "gpt-5.4",
                "use_compact_planning": "true",
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

    def test_runtime_from_payload_normalizes_chat_oss_overrides(self) -> None:
        runtime = runtime_from_payload(
            {
                "model_provider": "openai",
                "chat_model_provider": "oss",
                "chat_local_model_provider": "LMStudio",
                "chat_model": "AUTO",
            }
        )

        self.assertEqual(runtime.model_provider, "openai")
        self.assertEqual(runtime.chat_model_provider, "oss")
        self.assertEqual(runtime.chat_local_model_provider, "lmstudio")
        self.assertEqual(runtime.chat_model, "")

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

    def test_runtime_from_payload_syncs_stale_model_to_execution_model(self) -> None:
        runtime = runtime_from_payload(
            {
                "model_provider": "gemini",
                "model": "gemini-3-flash-preview",
                "model_slug_input": "gemini-3-flash-preview",
                "execution_model": "gemini-2.5-flash",
            }
        )

        self.assertEqual(runtime.execution_model, "gemini-2.5-flash")
        self.assertEqual(runtime.model, "gemini-2.5-flash")
        self.assertEqual(runtime.model_slug_input, "gemini-2.5-flash")

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
        self.assertFalse(payload["default_runtime"]["generate_word_report"])
        self.assertFalse(payload["default_runtime"]["save_project_logs"])
        self.assertEqual(payload["default_runtime"]["sandbox_mode"], "danger-full-access")
        self.assertEqual(payload["default_runtime"]["optimization_mode"], "off")

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
            (repo_dir / "README.md").write_text("# Demo\n", encoding="utf-8")
            (repo_dir / "src").mkdir(parents=True, exist_ok=True)
            (repo_dir / "src" / "main.py").write_text("print('demo')\n", encoding="utf-8")

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
            self.assertIn("provider_statuses", detail["codex_status"])
            self.assertNotIn("account", detail["codex_status"])
            self.assertIn("runtime_insights", detail)
            self.assertIn("runtime_insights", detail["bottom_panels"])
            self.assertIn("parallel", detail["runtime_insights"])
            self.assertEqual(len(detail["workspace_tree"]), 1)
            self.assertEqual(detail["workspace_tree"][0]["label"], "repo")
            self.assertEqual(detail["workspace_tree"][0]["path"], str(repo_dir))
            tree_labels = [item["label"] for item in detail["workspace_tree"][0]["children"]]
            self.assertIn("src", tree_labels)
            self.assertIn("README.md", tree_labels)
            self.assertNotIn(".git", tree_labels)
            self.assertNotIn("jakal-flow-logs", tree_labels)

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

    def test_load_project_hides_stale_word_report_when_generation_disabled(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Report Disabled Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "effort": "medium",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                    "generate_word_report": False,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            word_report_path = Path(detail["files"]["project_root"]) / "reports" / "CLOSEOUT_REPORT.docx"
            word_report_path.parent.mkdir(parents=True, exist_ok=True)
            word_report_path.write_bytes(b"stale-demo")

            with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: fake_codex_snapshot()):
                loaded = run_command(
                    "load-project",
                    workspace_root,
                    {
                        "repo_id": detail["project"]["repo_id"],
                    },
                )

            self.assertEqual(loaded["reports"]["word_report_path"], "")
            self.assertNotIn(str(word_report_path), loaded["summary"])

    def test_report_payload_includes_contract_wave_artifacts(self) -> None:
        with TemporaryTestDir() as temp_dir:
            context = build_test_project_context(temp_dir, display_name="Contract Wave Demo")
            context.paths.planning_metrics_file.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "generated_at": "2026-03-29T00:40:00+00:00",
                                "flow": "planning",
                                "stage": "context_scan",
                                "duration_ms": 42.5,
                                "block_index": 0,
                            }
                        ),
                        json.dumps(
                            {
                                "generated_at": "2026-03-29T00:41:00+00:00",
                                "flow": "planning",
                                "stage": "planner_b",
                                "duration_ms": 128.0,
                                "block_index": 0,
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            context.paths.spine_file.write_text(
                json.dumps(
                    {
                        "current_version": "spine-v3",
                        "updated_at": "2026-03-29T01:00:00+00:00",
                        "history": [
                            {
                                "version": "spine-v3",
                                "created_at": "2026-03-29T01:00:00+00:00",
                                "step_id": "ST-CONTRACT",
                                "lineage_id": "LN1",
                                "shared_contracts": ["api/payments"],
                                "notes": "Advanced the shared payments contract.",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            context.paths.common_requirements_file.write_text(
                json.dumps(
                    {
                        "updated_at": "2026-03-29T01:30:00+00:00",
                        "open_requirements": [
                            {
                                "request_id": "CRR1",
                                "status": "open",
                                "created_at": "2026-03-29T01:15:00+00:00",
                                "title": "Payments schema review",
                                "reason": "Touches a shared reviewed adapter.",
                                "promotion_class": "yellow",
                                "step_id": "ST2",
                                "lineage_id": "LN2",
                                "spine_version": "spine-v3",
                                "affected_paths": ["src/payments/adapter.py"],
                                "shared_contracts": ["api/payments"],
                            }
                        ],
                        "resolved_requirements": [
                            {
                                "request_id": "CRR0",
                                "status": "resolved",
                                "created_at": "2026-03-29T00:30:00+00:00",
                                "resolved_at": "2026-03-29T01:10:00+00:00",
                                "title": "Initial contract freeze",
                                "reason": "Shared contract advanced cleanly.",
                                "promotion_class": "yellow",
                                "step_id": "ST-CONTRACT",
                                "lineage_id": "LN1",
                                "spine_version": "spine-v3",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            context.paths.shared_contracts_file.write_text(
                "# Shared Contracts\n\n- Current spine version: spine-v3\n- Shared contracts: api/payments\n",
                encoding="utf-8",
            )
            context.paths.contract_wave_audit_file.write_text(
                '{"timestamp":"2026-03-29T02:10:00+00:00","action":"update","entity_type":"common_requirement","entity_id":"CRR1","note":"edited"}\n',
                encoding="utf-8",
            )
            (context.paths.lineage_manifests_dir / "20260329020000_ln2_st2.json").write_text(
                json.dumps(
                    {
                        "manifest_id": "MAN-1",
                        "lineage_id": "LN2",
                        "step_id": "ST2",
                        "step_title": "Adapt the shared payments adapter",
                        "created_at": "2026-03-29T02:00:00+00:00",
                        "step_type": "feature",
                        "scope_class": "shared_reviewed",
                        "spine_version": "spine-v3",
                        "touched_files": ["src/payments/adapter.py"],
                        "verification_commands": ["python -m pytest tests/test_payments.py"],
                        "verification_summary": "payments tests passed",
                        "verification_status": "passed",
                        "shared_contracts_used": ["api/payments"],
                        "promotion_class": "yellow",
                        "promotion_reason": "Touches shared-reviewed adapter paths.",
                        "common_requirement_request_id": "CRR1",
                    }
                ),
                encoding="utf-8",
            )

            reports = ui_bridge_payloads.report_payload(context)

            self.assertEqual(reports["spine"]["current_version"], "spine-v3")
            self.assertEqual(reports["spine"]["history_count"], 1)
            self.assertEqual(reports["common_requirements"]["open_count"], 1)
            self.assertEqual(reports["common_requirements"]["resolved_count"], 1)
            self.assertEqual(reports["lineage_manifest_summary"]["yellow_count"], 1)
            self.assertEqual(reports["lineage_manifest_summary"]["total"], 1)
            self.assertEqual(reports["lineage_manifests"][0]["manifest_id"], "MAN-1")
            self.assertEqual(reports["lineage_manifests"][0]["common_requirement_request_id"], "CRR1")
            self.assertEqual(reports["planning_metrics"]["entry_count"], 2)
            self.assertEqual(reports["planning_metrics"]["slowest_item"]["stage"], "planner_b")
            self.assertEqual(reports["planning_metrics"]["stage_summary"][0]["stage"], "planner_b")
            self.assertIn("api/payments", reports["shared_contracts_text"])
            self.assertEqual(reports["contract_wave_audit"]["recent_items"][0]["entity_type"], "common_requirement")

    def test_history_payload_renders_execution_flow_svg_lazily(self) -> None:
        with TemporaryTestDir() as temp_dir:
            context = build_test_project_context(temp_dir, display_name="Flow Demo")
            context.paths.execution_plan_file.write_text(
                json.dumps(
                    ExecutionPlanState(
                        plan_title="Flow Demo",
                        execution_mode="parallel",
                        steps=[
                            ExecutionStep(
                                step_id="ST1",
                                title="First step",
                                display_description="Do the first thing.",
                                codex_description="Implement the first change.",
                                owned_paths=["src/app.py"],
                            ),
                            ExecutionStep(
                                step_id="ST2",
                                title="Join step",
                                display_description="Integrate the work.",
                                codex_description="Merge the work carefully.",
                                depends_on=["ST1"],
                                metadata={"step_kind": "join"},
                            ),
                        ],
                    ).to_dict(),
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            if context.paths.execution_flow_svg_file.exists():
                context.paths.execution_flow_svg_file.unlink()

            history = ui_bridge_payloads.history_payload(context)

            self.assertTrue(context.paths.execution_flow_svg_file.exists())
            self.assertEqual(history["flow_svg_path"], str(context.paths.execution_flow_svg_file))
            self.assertIn("execution-flow-signature:", history["flow_svg_text"])
            self.assertIn("<svg", history["flow_svg_text"])

    def test_contract_wave_bridge_commands_update_crr_and_spine_state(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            workspace = WorkspaceManager(workspace_root)
            context = workspace.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=runtime_from_payload(
                    {
                        "model": "gpt-5.4",
                        "effort": "medium",
                        "test_cmd": "python -m unittest",
                        "max_blocks": 5,
                    }
                ),
                display_name="Contract Ops Demo",
            )
            context.paths.spine_file.write_text(
                json.dumps(
                    {
                        "current_version": "spine-v3",
                        "updated_at": "2026-03-29T01:00:00+00:00",
                        "history": [],
                    }
                ),
                encoding="utf-8",
            )
            context.paths.common_requirements_file.write_text(
                json.dumps(
                    {
                        "updated_at": "2026-03-29T01:30:00+00:00",
                        "open_requirements": [
                            {
                                "request_id": "CRR1",
                                "status": "open",
                                "created_at": "2026-03-29T01:15:00+00:00",
                                "title": "Payments schema review",
                                "reason": "Touches a shared reviewed adapter.",
                                "promotion_class": "yellow",
                                "step_id": "ST2",
                                "lineage_id": "LN2",
                                "spine_version": "spine-v3",
                                "affected_paths": ["src/payments/adapter.py"],
                                "shared_contracts": ["api/payments"],
                            }
                        ],
                        "resolved_requirements": [],
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: fake_codex_snapshot()):
                resolved = run_command(
                    "resolve-common-requirement",
                    workspace_root,
                    {
                        "repo_id": context.metadata.repo_id,
                        "request_id": "CRR1",
                        "note": "operator approved for integration",
                    },
                )
                reopened = run_command(
                    "reopen-common-requirement",
                    workspace_root,
                    {
                        "repo_id": context.metadata.repo_id,
                        "request_id": "CRR1",
                        "note": "reopened after follow-up review",
                    },
                )
                checkpointed = run_command(
                    "record-spine-checkpoint",
                    workspace_root,
                    {
                        "repo_id": context.metadata.repo_id,
                        "version": "spine-v4",
                        "notes": "operator checkpoint before integration",
                        "shared_contracts": ["api/payments", "schema/invoice"],
                        "step_id": "ST-OPS",
                        "lineage_id": "LN-OPS",
                    },
                )

            self.assertEqual(resolved["reports"]["common_requirements"]["open_count"], 0)
            self.assertEqual(resolved["reports"]["common_requirements"]["resolved_count"], 1)
            self.assertEqual(resolved["reports"]["common_requirements"]["resolved_items"][0]["request_id"], "CRR1")
            self.assertIn(
                "operator approved for integration",
                resolved["reports"]["common_requirements"]["resolved_items"][0]["notes"],
            )
            self.assertEqual(reopened["reports"]["common_requirements"]["open_count"], 1)
            self.assertEqual(reopened["reports"]["common_requirements"]["resolved_count"], 0)
            self.assertEqual(checkpointed["reports"]["spine"]["current_version"], "spine-v4")
            self.assertEqual(checkpointed["reports"]["spine"]["latest_checkpoint"]["lineage_id"], "LN-OPS")
            self.assertIn("schema/invoice", checkpointed["reports"]["shared_contracts_text"])

    def test_contract_wave_bridge_commands_edit_and_delete_with_audit(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            workspace = WorkspaceManager(workspace_root)
            context = workspace.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=runtime_from_payload(
                    {
                        "model": "gpt-5.4",
                        "effort": "medium",
                        "test_cmd": "python -m unittest",
                        "max_blocks": 5,
                    }
                ),
                display_name="Contract Edit Demo",
            )
            context.paths.spine_file.write_text(
                json.dumps(
                    {
                        "current_version": "spine-v2",
                        "updated_at": "2026-03-29T00:50:00+00:00",
                        "history": [
                            {
                                "version": "spine-v2",
                                "created_at": "2026-03-29T00:40:00+00:00",
                                "step_id": "ST0",
                                "lineage_id": "LN0",
                                "shared_contracts": ["api/legacy"],
                                "touched_files": ["src/legacy.py"],
                                "notes": "legacy checkpoint"
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            context.paths.common_requirements_file.write_text(
                json.dumps(
                    {
                        "updated_at": "2026-03-29T01:30:00+00:00",
                        "open_requirements": [
                            {
                                "request_id": "CRR9",
                                "status": "open",
                                "created_at": "2026-03-29T01:15:00+00:00",
                                "title": "Old title",
                                "reason": "Old reason",
                                "promotion_class": "yellow",
                                "step_id": "ST9",
                                "lineage_id": "LN9",
                                "spine_version": "spine-v2",
                                "affected_paths": ["src/legacy.py"],
                                "shared_contracts": ["api/legacy"],
                            }
                        ],
                        "resolved_requirements": [],
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: fake_codex_snapshot()):
                baseline = run_command(
                    "load-project",
                    workspace_root,
                    {
                        "repo_id": context.metadata.repo_id,
                    },
                )
                checkpoint_id = baseline["reports"]["spine"]["latest_checkpoint"]["checkpoint_id"]
                updated_requirement = run_command(
                    "update-common-requirement",
                    workspace_root,
                    {
                        "repo_id": context.metadata.repo_id,
                        "request_id": "CRR9",
                        "title": "Payments review",
                        "reason": "Updated adapter scope",
                        "notes": "operator edited",
                        "affected_paths": ["src/payments/adapter.py"],
                        "shared_contracts": ["api/payments"],
                        "promotion_class": "red",
                        "step_id": "ST10",
                        "lineage_id": "LN10",
                        "spine_version": "spine-v4",
                    },
                )
                updated_checkpoint = run_command(
                    "update-spine-checkpoint",
                    workspace_root,
                    {
                        "repo_id": context.metadata.repo_id,
                        "checkpoint_id": checkpoint_id,
                        "version": "spine-v3",
                        "notes": "operator updated checkpoint",
                        "shared_contracts": ["api/payments", "schema/invoice"],
                        "touched_files": ["src/payments/adapter.py"],
                        "step_id": "ST11",
                        "lineage_id": "LN11",
                        "commit_hash": "ops-head",
                    },
                )
                deleted_requirement = run_command(
                    "delete-common-requirement",
                    workspace_root,
                    {
                        "repo_id": context.metadata.repo_id,
                        "request_id": "CRR9",
                        "note": "duplicate request",
                    },
                )
                deleted_checkpoint = run_command(
                    "delete-spine-checkpoint",
                    workspace_root,
                    {
                        "repo_id": context.metadata.repo_id,
                        "checkpoint_id": checkpoint_id,
                        "note": "superseded",
                    },
                )

            self.assertEqual(updated_requirement["reports"]["common_requirements"]["open_items"][0]["title"], "Payments review")
            self.assertEqual(updated_requirement["reports"]["common_requirements"]["open_items"][0]["promotion_class"], "red")
            self.assertEqual(updated_checkpoint["reports"]["spine"]["latest_checkpoint"]["version"], "spine-v3")
            self.assertEqual(updated_checkpoint["reports"]["spine"]["latest_checkpoint"]["lineage_id"], "LN11")
            self.assertEqual(deleted_requirement["reports"]["common_requirements"]["open_count"], 0)
            self.assertEqual(deleted_checkpoint["reports"]["spine"]["history_count"], 0)
            self.assertTrue(deleted_checkpoint["reports"]["contract_wave_audit"]["recent_items"])
            self.assertTrue(
                any(
                    str(item.get("entity_type", "")).strip() == "spine_checkpoint"
                    for item in deleted_checkpoint["reports"]["contract_wave_audit"]["recent_items"]
                )
            )
            self.assertTrue(deleted_checkpoint["files"]["contract_wave_audit_file"].endswith("CONTRACT_WAVE_AUDIT.jsonl"))

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

    def test_request_stop_forwards_process_pids(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"):
                workspace = WorkspaceManager(workspace_root)
                workspace.initialize_local_project(repo_dir, "main", runtime_from_payload({}), display_name="Plan Demo")

            with mock.patch.object(
                ui_bridge.EXECUTION_STOP_REGISTRY,
                "request_stop",
                wraps=ui_bridge.EXECUTION_STOP_REGISTRY.request_stop,
            ) as request_stop_mock:
                run_command(
                    "request-stop",
                    workspace_root,
                    {
                        "project_dir": str(repo_dir),
                        "process_pids": [4321, 4322],
                        "source": "unit-test",
                    },
                )

            self.assertEqual(request_stop_mock.call_count, 1)
            self.assertEqual(request_stop_mock.call_args.kwargs["process_pids"], [4321, 4322])

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
            stopped_at = "2026-03-27T09:59:00+00:00"
            orchestrator = orchestrator_module.Orchestrator(workspace_root)
            project = orchestrator.local_project(repo_dir)
            self.assertIsNotNone(project)
            assert project is not None
            project.metadata.current_status = "running:generate-plan"
            project.metadata.last_run_at = stopped_at
            orchestrator.workspace.save_project(project)

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
            reloaded = orchestrator.workspace.load_project_by_id(stopped["project"]["repo_id"])
            self.assertEqual(reloaded.metadata.current_status, "setup_ready")
            self.assertNotEqual(reloaded.metadata.last_run_at, stopped_at)
            listing = run_command("list-projects", workspace_root, {})
            listing_project = next(item for item in listing["projects"] if item["repo_id"] == stopped["project"]["repo_id"])
            self.assertEqual(listing_project["status"], "setup_ready")

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

    def test_checkpoint_payload_reconciles_status_from_block_log(self) -> None:
        with TemporaryTestDir() as temp_dir:
            context = build_test_project_context(temp_dir)
            context.loop_state.current_checkpoint_id = "CP1"
            context.loop_state.current_checkpoint_lineage_id = "LN-1"
            context.loop_state.pending_checkpoint_approval = True

            context.paths.checkpoint_state_file.write_text(
                json.dumps(
                    {
                        "checkpoints": [
                            {
                                "checkpoint_id": "CP1",
                                "title": "Review me",
                                "target_block": 1,
                                "status": "pending",
                                "lineage_id": "LN-1",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            context.paths.block_log_file.write_text(
                json.dumps(
                    {
                        "block_index": 1,
                        "lineage_id": "LN-1",
                        "status": "completed",
                        "selected_task": "Review me",
                        "test_summary": "Checkpoint ready.",
                        "commit_hashes": ["abc123"],
                        "completed_at": "2026-03-29T10:00:00+00:00",
                        "started_at": "2026-03-29T09:59:00+00:00",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            payload = ui_bridge_payloads.checkpoint_payload(context)

            self.assertEqual(payload["items"][0]["status"], "awaiting_review")
            self.assertEqual(payload["items"][0]["commit_hashes"], ["abc123"])
            self.assertIsNotNone(payload["pending"])
            self.assertEqual(payload["pending"]["checkpoint_id"], "CP1")
            self.assertEqual(payload["pending"]["status"], "awaiting_review")
            self.assertIn("Status: awaiting_review", payload["timeline_markdown"])
            self.assertIn("Lineage: LN-1", payload["timeline_markdown"])

    def test_checkpoint_payload_normalizes_active_running_checkpoint_to_awaiting_review(self) -> None:
        with TemporaryTestDir() as temp_dir:
            context = build_test_project_context(temp_dir)
            context.loop_state.current_checkpoint_id = "CP1"
            context.loop_state.current_checkpoint_lineage_id = "LN-1"
            context.loop_state.pending_checkpoint_approval = True

            context.paths.checkpoint_state_file.write_text(
                json.dumps(
                    {
                        "checkpoints": [
                            {
                                "checkpoint_id": "CP1",
                                "title": "Review me",
                                "target_block": 1,
                                "status": "running",
                                "lineage_id": "LN-1",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            context.paths.block_log_file.write_text(
                json.dumps(
                    {
                        "block_index": 1,
                        "lineage_id": "LN-1",
                        "status": "completed",
                        "selected_task": "Review me",
                        "test_summary": "Checkpoint ready.",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            payload = ui_bridge_payloads.checkpoint_payload(context)

            self.assertEqual(payload["items"][0]["status"], "awaiting_review")
            self.assertEqual(payload["pending"]["status"], "awaiting_review")
            self.assertIn("Status: awaiting_review", payload["timeline_markdown"])

    def test_checkpoint_and_flowchart_payloads_share_block_log_lineage_state(self) -> None:
        with TemporaryTestDir() as temp_dir:
            context = build_test_project_context(temp_dir)
            ui_bridge_payloads._SECTION_PAYLOAD_MEMORY_CACHE.clear()
            context.loop_state.current_checkpoint_id = "CP1"
            context.loop_state.current_checkpoint_lineage_id = "LN-1"
            context.loop_state.pending_checkpoint_approval = True

            plan = ExecutionPlanState(
                execution_mode="parallel",
                closeout_status="not_started",
                steps=[
                    ExecutionStep(
                        step_id="ST1",
                        title="Frontend",
                        status="pending",
                        metadata={"lineage_id": "LN-1"},
                    )
                ],
            )
            context.paths.execution_plan_file.write_text(
                json.dumps(plan.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            context.paths.checkpoint_state_file.write_text(
                json.dumps(
                    {
                        "checkpoints": [
                            {
                                "checkpoint_id": "CP1",
                                "title": "Review me",
                                "target_block": 1,
                                "status": "pending",
                                "lineage_id": "LN-1",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            context.paths.block_log_file.write_text(
                json.dumps(
                    {
                        "block_index": 1,
                        "lineage_id": "LN-1",
                        "status": "completed",
                        "selected_task": "Review me",
                        "test_summary": "Checkpoint ready.",
                        "commit_hashes": ["abc123"],
                        "completed_at": "2026-03-29T10:00:00+00:00",
                        "started_at": "2026-03-29T09:59:00+00:00",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            checkpoint_payload = ui_bridge_payloads.checkpoint_payload(context)
            history_payload = ui_bridge_payloads.history_payload(context)

            self.assertEqual(checkpoint_payload["items"][0]["status"], "awaiting_review")
            self.assertEqual(checkpoint_payload["items"][0]["lineage_id"], "LN-1")
            self.assertEqual(checkpoint_payload["pending"]["status"], "awaiting_review")
            self.assertEqual(checkpoint_payload["current_checkpoint_lineage_id"], "LN-1")
            self.assertIn("Status: awaiting_review", checkpoint_payload["timeline_markdown"])
            self.assertIn("Lineage: LN-1", checkpoint_payload["timeline_markdown"])
            self.assertIn("execution-flow-signature:", history_payload["flow_svg_text"])
            self.assertIn(">completed<", history_payload["flow_svg_text"])

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

    def test_run_closeout_hides_stale_word_report_path_when_generation_disabled(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Closeout Report Disabled Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "model_preset": "high",
                    "effort": "high",
                    "test_cmd": "python -m unittest",
                    "max_blocks": 5,
                    "generate_word_report": False,
                },
            }
            completed_plan = {
                "plan_title": "Closeout Report Disabled Demo",
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
                context.paths.closeout_report_docx_file.parent.mkdir(parents=True, exist_ok=True)
                context.paths.closeout_report_docx_file.write_bytes(b"stale-demo")
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
                    "run-closeout",
                    workspace_root,
                    {
                        **payload,
                        "plan": completed_plan,
                    },
                )

            stale_path = str(Path(result["files"]["project_root"]) / "reports" / "CLOSEOUT_REPORT.docx")
            self.assertEqual(result["reports"]["word_report_path"], "")
            self.assertFalse(any(stale_path in line for line in result["activity"]))

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

    def test_run_plan_marks_started_step_failed_when_step_execution_raises(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Raised Step Failure Demo",
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
            plan = {
                "plan_title": "Raised Step Failure Demo",
                "project_prompt": "Run the first step",
                "summary": "The first step should fail cleanly.",
                "workflow_mode": "standard",
                "execution_mode": "parallel",
                "default_test_command": "python -m unittest",
                "steps": [
                    {
                        "step_id": "ST1",
                        "title": "Freeze Shared Harness Contract",
                        "display_description": "Start the shared harness work",
                        "codex_description": "Start the shared harness work",
                        "success_criteria": "Tests pass",
                        "test_command": "python -m unittest",
                        "reasoning_effort": "high",
                        "status": "pending",
                    }
                ],
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            ui_event_log_file = Path(detail["files"]["ui_event_log_file"])

            with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: fake_codex_snapshot()), mock.patch(
                "jakal_flow.orchestrator.Orchestrator.run_saved_execution_step",
                side_effect=RuntimeError("Injected ST1 failure"),
            ):
                with self.assertRaisesRegex(RuntimeError, "Injected ST1 failure"):
                    run_command(
                        "run-plan",
                        workspace_root,
                        {
                            **payload,
                            "plan": plan,
                        },
                    )

            events = read_jsonl(ui_event_log_file)
            self.assertEqual(
                [event.get("event_type") for event in events[-3:]],
                ["run-started", "step-started", "step-finished"],
            )
            self.assertEqual(events[-1]["details"]["step_id"], "ST1")
            self.assertEqual(events[-1]["details"]["status"], "failed")

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

    def test_run_manual_debugger_command_handles_immediate_stop_as_pause(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Debugger Stop Demo",
                "runtime": {
                    "model": "gpt-5.4",
                    "effort": "medium",
                    "test_cmd": "python -m pytest",
                },
            }
            plan_payload = {
                "plan_title": "Manual debugger stop",
                "project_prompt": "Pause debugger recovery on stop.",
                "steps": [],
            }

            with mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                run_command("save-project-setup", workspace_root, payload)

            with mock.patch(
                "jakal_flow.orchestrator.Orchestrator.run_manual_debugger_recovery",
                side_effect=ImmediateStopRequested("Manual debugger stopped by user."),
            ), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command(
                    "run-manual-debugger",
                    workspace_root,
                    {
                        **payload,
                        "plan": plan_payload,
                    },
                )

            self.assertTrue(any("manual-debugger-finished" in line for line in detail["activity"]))
            self.assertTrue(any("Manual debugger stopped by user." in line for line in detail["activity"]))

    def test_send_chat_message_debugger_records_cancelled_message_when_stopped(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Chat Debugger Stop Demo",
                "runtime": {
                    "model": "gpt-5.4",
                    "effort": "medium",
                    "test_cmd": "python -m pytest",
                },
            }
            plan_payload = {
                "plan_title": "Chat debugger stop",
                "project_prompt": "Stop chat debugger recovery.",
                "steps": [],
            }

            with mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            with mock.patch(
                "jakal_flow.orchestrator.Orchestrator.run_manual_debugger_recovery",
                side_effect=ImmediateStopRequested("Manual debugger stopped by user."),
            ), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                result = run_command(
                    "send-chat-message",
                    workspace_root,
                    {
                        **payload,
                        "repo_id": detail["project"]["repo_id"],
                        "plan": plan_payload,
                        "message": "Stop the debugger run.",
                        "chat_mode": "debugger",
                    },
                )

            self.assertEqual(result["error"], "")
            self.assertEqual(result["chat"]["messages"][-1]["status"], "cancelled")
            self.assertTrue(result["chat"]["messages"][-1]["metadata"]["interrupted"])
            self.assertEqual(result["chat"]["messages"][-1]["text"], "Manual debugger stopped by user.")

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

    def test_execute_conversation_turn_sanitizes_markdown_heavy_reply(self) -> None:
        with TemporaryTestDir() as temp_dir:
            chat_home = temp_dir / "jakal-flow-chat"
            context = build_test_project_context(
                temp_dir,
                repo_id="chat-format-demo",
                slug="chat-format-demo",
                display_name="Chat Format Demo",
            )
            plan_state = ExecutionPlanState(
                plan_title="Chat Format Demo",
                project_prompt="Explain the repository state plainly.",
                summary="Chat formatting test plan.",
            )
            raw_reply = (
                "**판단** lit는 이미 정리되어 있습니다.\n\n"
                "- 핵심 문서는 [README.md](/tmp/README.md#L3) 를 보세요.\n"
                "- 구현은 [backend_api.py](/tmp/backend_api.py#L10) 에 있습니다."
            )

            with mock.patch.dict(os.environ, {CHAT_HOME_ENV_VAR: str(chat_home)}), mock.patch(
                "jakal_flow.chat_sessions._run_conversation_reply",
                return_value=(0, raw_reply),
            ):
                result = execute_conversation_turn(
                    context,
                    plan_state=plan_state,
                    user_message="현재 상태를 읽기 쉽게 설명해줘",
                )

            assistant_text = result["chat"]["messages"][-1]["text"]
            self.assertIn("판단", assistant_text)
            self.assertIn("README.md", assistant_text)
            self.assertIn("backend_api.py", assistant_text)
            self.assertNotIn("[README.md](", assistant_text)
            self.assertNotIn("**판단**", assistant_text)

    def test_execute_conversation_turn_records_interrupted_chat_without_failing(self) -> None:
        with TemporaryTestDir() as temp_dir:
            chat_home = temp_dir / "jakal-flow-chat"
            context = build_test_project_context(
                temp_dir,
                repo_id="chat-stop-demo",
                slug="chat-stop-demo",
                display_name="Chat Stop Demo",
            )
            plan_state = ExecutionPlanState(
                plan_title="Chat Stop Demo",
                project_prompt="Stop the current reply when requested.",
                summary="Chat interruption test plan.",
            )

            with mock.patch.dict(os.environ, {CHAT_HOME_ENV_VAR: str(chat_home)}), mock.patch(
                "jakal_flow.chat_sessions._run_conversation_reply",
                side_effect=ImmediateStopRequested("Immediate stop requested while running OpenAI chat."),
            ):
                result = execute_conversation_turn(
                    context,
                    plan_state=plan_state,
                    user_message="Stop this response.",
                )

            self.assertEqual(result["error"], "")
            self.assertTrue(result["interrupted"])
            self.assertEqual([item["role"] for item in result["chat"]["messages"]], ["user", "system"])
            self.assertEqual(result["chat"]["messages"][-1]["status"], "cancelled")
            self.assertEqual(result["chat"]["messages"][-1]["text"], "Response stopped.")
            self.assertTrue(result["chat"]["messages"][-1]["metadata"]["interrupted"])

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

    def test_execute_conversation_turn_review_mode_wraps_the_user_request(self) -> None:
        with TemporaryTestDir() as temp_dir:
            chat_home = temp_dir / "jakal-flow-chat"
            context = build_test_project_context(
                temp_dir,
                repo_id="chat-review-demo",
                slug="chat-review-demo",
                display_name="Chat Review Demo",
            )
            plan_state = ExecutionPlanState(
                plan_title="Chat Review Demo",
                project_prompt="Review the latest desktop changes.",
                summary="Chat review test plan.",
            )

            with mock.patch.dict(os.environ, {CHAT_HOME_ENV_VAR: str(chat_home)}), mock.patch(
                "jakal_flow.chat_sessions._run_conversation_reply",
                return_value=(0, "Review reply."),
            ) as run_reply:
                result = execute_conversation_turn(
                    context,
                    plan_state=plan_state,
                    user_message="desktop/src/App.jsx changes",
                    mode="review",
                )

            prompt_text = run_reply.call_args.kwargs["prompt"]
            self.assertIn("Review the following code, diff, or implementation request.", prompt_text)
            self.assertIn("desktop/src/App.jsx changes", prompt_text)
            self.assertEqual(result["chat"]["messages"][0]["mode"], "review")
            self.assertEqual(result["chat"]["messages"][1]["mode"], "review")

    def test_send_chat_message_conversation_uses_chat_model_override(self) -> None:
        context = mock.Mock(
            metadata=mock.sentinel.metadata,
            paths=mock.sentinel.paths,
            loop_state=mock.sentinel.loop_state,
            runtime=RuntimeOptions(
                model_provider="openai",
                model="gpt-5.4",
                model_slug_input="gpt-5.4",
                chat_model_provider="gemini",
                chat_model="gemini-2.5-pro",
            ),
        )

        conversation_context = chat_sessions._conversation_context(context)

        self.assertEqual(conversation_context.metadata, mock.sentinel.metadata)
        self.assertEqual(conversation_context.paths, mock.sentinel.paths)
        self.assertEqual(conversation_context.loop_state, mock.sentinel.loop_state)
        self.assertEqual(conversation_context.runtime.model_provider, "gemini")
        self.assertEqual(conversation_context.runtime.model, "gemini-2.5-pro")
        self.assertIn("gemini", conversation_context.runtime.codex_path)

    def test_send_chat_message_conversation_context_resets_provider_overrides_when_switching_to_local_oss(self) -> None:
        with TemporaryTestDir() as temp_dir:
            base_context = build_test_project_context(temp_dir)
            context = ProjectContext(
                metadata=base_context.metadata,
                paths=base_context.paths,
                loop_state=base_context.loop_state,
                runtime=RuntimeOptions(
                    model_provider="openrouter",
                    model="openai/gpt-4.1-mini",
                    model_slug_input="openai/gpt-4.1-mini",
                    provider_base_url="https://openrouter.ai/api/v1",
                    provider_api_key_env="OPENROUTER_API_KEY",
                    codex_path="codex-custom",
                    chat_model_provider="oss",
                    chat_local_model_provider="lmstudio",
                    chat_model="qwen2.5-coder:14b",
                ),
            )

            conversation_context = chat_sessions._conversation_context(context)

        self.assertEqual(conversation_context.runtime.model_provider, "oss")
        self.assertEqual(conversation_context.runtime.local_model_provider, "lmstudio")
        self.assertEqual(conversation_context.runtime.model, "qwen2.5-coder:14b")
        self.assertEqual(conversation_context.runtime.model_slug_input, "qwen2.5-coder:14b")
        self.assertEqual(conversation_context.runtime.provider_base_url, "")
        self.assertEqual(conversation_context.runtime.provider_api_key_env, "")

    def test_send_chat_message_conversation_route_returns_non_project_changing_payload(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Chat Conversation Route Demo",
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

            session_payload = {
                "chat": {
                    "active_session_id": "chat-1",
                    "active_session": {
                        "session_id": "chat-1",
                        "title": "Chat route",
                    },
                    "messages": [
                        {
                            "message_id": "msg-1",
                            "role": "assistant",
                            "text": "Conversation reply.",
                        }
                    ],
                },
                "error": "",
            }

            with mock.patch(
                "jakal_flow.ui_bridge_commands.runs.execute_conversation_turn",
                return_value=session_payload,
            ) as execute_turn:
                result = run_command(
                    "send-chat-message",
                    workspace_root,
                    {
                        **payload,
                        "repo_id": detail["project"]["repo_id"],
                        "message": "Summarize the saved state.",
                        "chat_mode": "conversation",
                        "session_id": "chat-1",
                    },
                )

            execute_turn.assert_called_once()
            _project, = execute_turn.call_args.args
            self.assertEqual(_project.metadata.repo_id, detail["project"]["repo_id"])
            self.assertEqual(execute_turn.call_args.kwargs["user_message"], "Summarize the saved state.")
            self.assertEqual(execute_turn.call_args.kwargs["session_id"], "chat-1")
            self.assertFalse(execute_turn.call_args.kwargs["create_new_session"])
            self.assertEqual(result["chat_mode"], "conversation")
            self.assertFalse(result["emit_project_changed"])
            self.assertEqual(result["project"]["repo_id"], detail["project"]["repo_id"])
            self.assertEqual(result["chat"]["active_session_id"], "chat-1")
            self.assertNotIn("detail", result)

    def test_send_chat_message_review_route_uses_conversation_execution(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Chat Review Route Demo",
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

            session_payload = {
                "chat": {
                    "active_session_id": "chat-review-1",
                    "active_session": {
                        "session_id": "chat-review-1",
                        "title": "Chat review route",
                    },
                    "messages": [
                        {
                            "message_id": "msg-1",
                            "role": "assistant",
                            "text": "Review reply.",
                            "mode": "review",
                        }
                    ],
                },
                "error": "",
            }

            with mock.patch(
                "jakal_flow.ui_bridge_commands.runs.execute_conversation_turn",
                return_value=session_payload,
            ) as execute_turn:
                result = run_command(
                    "send-chat-message",
                    workspace_root,
                    {
                        **payload,
                        "repo_id": detail["project"]["repo_id"],
                        "message": "Please review these desktop changes.",
                        "chat_mode": "review",
                        "session_id": "chat-review-1",
                    },
                )

            execute_turn.assert_called_once()
            self.assertEqual(execute_turn.call_args.kwargs["mode"], "review")
            self.assertEqual(execute_turn.call_args.kwargs["user_message"], "Please review these desktop changes.")
            self.assertEqual(result["chat_mode"], "review")
            self.assertFalse(result["emit_project_changed"])

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

    def test_load_project_normalizes_active_running_checkpoint_to_awaiting_review(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Active Checkpoint Demo",
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
                                "status": "running",
                                "lineage_id": "LN-1",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            loop_state_path = project_root / "state" / "LOOP_STATE.json"
            loop_state = json.loads(loop_state_path.read_text(encoding="utf-8"))
            loop_state["current_checkpoint_id"] = "CP1"
            loop_state["current_checkpoint_lineage_id"] = "LN-1"
            loop_state["pending_checkpoint_approval"] = True
            loop_state_path.write_text(json.dumps(loop_state), encoding="utf-8")

            with mock.patch("jakal_flow.ui_bridge.fetch_codex_backend_snapshot", side_effect=lambda *args, **kwargs: fake_codex_snapshot()):
                loaded = run_command(
                    "load-project",
                    workspace_root,
                    {
                        "project_dir": str(repo_dir),
                        "refresh_codex_status": False,
                        "detail_level": "full",
                        "bypass_detail_cache": True,
                    },
                )

            self.assertEqual(loaded["checkpoints"]["items"][0]["status"], "awaiting_review")
            self.assertEqual(loaded["checkpoints"]["pending"]["status"], "awaiting_review")
            self.assertEqual(loaded["project"]["current_status"], "awaiting_checkpoint_approval")

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

    def test_save_project_setup_skips_codex_refresh_without_shrinking_detail(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Lean Save Demo",
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
                side_effect=AssertionError("save-project-setup should not force a Codex status refresh"),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            self.assertEqual(detail["detail_level"], "full")
            self.assertEqual(detail["project"]["display_name"], "Lean Save Demo")
            self.assertIn("provider_statuses", detail["codex_status"])
            self.assertFalse(detail["codex_status"].get("model_catalog"))
            self.assertIn("powerpoint_report_target_path", detail["reports"])
            self.assertTrue(detail["workspace_tree"])
            self.assertTrue(detail["activity"])

    def test_save_project_setup_persists_runtime_fields_from_desktop_payload(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Runtime Persistence Demo",
                "branch": "main",
                "origin_url": "",
                "runtime": {
                    "model": "gpt-5.4",
                    "execution_model": "gpt-5.4-mini",
                    "allow_background_queue": False,
                    "require_checkpoint_approval": False,
                    "checkpoint_interval_blocks": 3,
                    "parallel_worker_mode": "manual",
                    "parallel_workers": 2,
                    "parallel_memory_per_worker_gib": 4.5,
                    "local_model_provider": "lmstudio",
                    "chat_model_provider": "oss",
                    "chat_local_model_provider": "ollama",
                    "chat_model": "llama3.2",
                    "generate_word_report": True,
                },
            }

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            self.assertEqual(detail["runtime"]["execution_model"], "gpt-5.4-mini")
            self.assertFalse(detail["runtime"]["allow_background_queue"])
            self.assertFalse(detail["runtime"]["require_checkpoint_approval"])
            self.assertEqual(detail["runtime"]["checkpoint_interval_blocks"], 3)
            self.assertEqual(detail["runtime"]["parallel_worker_mode"], "manual")
            self.assertEqual(detail["runtime"]["parallel_workers"], 2)
            self.assertAlmostEqual(detail["runtime"]["parallel_memory_per_worker_gib"], 4.5)
            self.assertEqual(detail["runtime"]["chat_model_provider"], "oss")
            self.assertEqual(detail["runtime"]["chat_local_model_provider"], "ollama")
            self.assertEqual(detail["runtime"]["chat_model"], "llama3.2")
            self.assertTrue(detail["runtime"]["generate_word_report"])

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
            self.assertEqual(loaded["project"]["current_status"], "running:generate-plan")
            self.assertEqual(loaded["snapshot"]["project"]["current_status"], "running:generate-plan")
            self.assertEqual(loaded["bottom_panels"]["git_status"]["current_status"], "running:generate-plan")
            self.assertEqual(planning_progress["current_stage_key"], "planner_a")
            self.assertEqual(planning_progress["current_stage_index"], 2)
            self.assertEqual(planning_progress["current_stage_label"], "Planner Agent A")
            self.assertEqual(planning_progress["current_agent_label"], "Planner Agent A")
            self.assertEqual(planning_progress["percent"], 38)
            self.assertEqual(
                [item["status"] for item in planning_progress["stages"]],
                ["completed", "running", "pending", "pending"],
            )

    def test_load_project_clears_planning_progress_after_stop_event(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Planning Stop Progress Demo",
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
                    {
                        "timestamp": "2026-03-27T10:00:08Z",
                        "event_type": "plan-stopped",
                        "message": "Planning stopped by user.",
                        "details": {
                            "flow": "planning",
                            "status": "stopped",
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

            self.assertEqual(loaded["planning_progress"], {})
            self.assertEqual(loaded["project"]["current_status"], "setup_ready")
            self.assertEqual(loaded["snapshot"]["project"]["current_status"], "setup_ready")
            self.assertEqual(loaded["bottom_panels"]["git_status"]["current_status"], "setup_ready")

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

    def test_load_project_core_detail_skips_chat_message_and_summary_reads(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Core Chat Demo",
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

            project = WorkspaceManager(workspace_root).list_projects()[0]
            session = chat_sessions.create_chat_session(project, title_hint="Core Chat Demo")
            chat_sessions.save_chat_message(
                project,
                session.session_id,
                role="user",
                text="Summarize the latest run.",
                mode="conversation",
            )

            summary_file = Path(session.summary_file)
            original_read_text = chat_sessions.read_text

            def guarded_read_text(path, *args, **kwargs):
                if Path(path) == summary_file:
                    raise AssertionError("core detail should not read the chat summary file")
                return original_read_text(path, *args, **kwargs)

            with mock.patch(
                "jakal_flow.chat_sessions.load_chat_messages",
                side_effect=AssertionError("core detail should not load chat messages"),
            ), mock.patch(
                "jakal_flow.chat_sessions.read_text",
                side_effect=guarded_read_text,
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

            self.assertEqual(loaded["detail_level"], "core")
            self.assertEqual(loaded["chat"]["active_session_id"], session.session_id)
            self.assertEqual(loaded["chat"]["messages"], [])
            self.assertEqual(loaded["chat"]["summary_text"], "")

    def test_list_projects_reuses_cached_list_item_payload_when_state_is_unchanged(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "List Cache Demo",
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

            cache_file = Path(detail["project"]["project_root"]) / "state" / "PROJECT_LIST_ITEM_CACHE_ACTIVE.json"
            if cache_file.exists():
                cache_file.unlink()

            first = run_command("list-projects", workspace_root)

            self.assertTrue(cache_file.exists())
            self.assertEqual(first["projects"][0]["repo_id"], detail["project"]["repo_id"])

            with mock.patch(
                "jakal_flow.ui_bridge_payloads._build_project_list_item_payload",
                side_effect=AssertionError("the cached list item payload should be reused"),
            ):
                second = run_command("list-projects", workspace_root)

            self.assertEqual(second["projects"][0]["repo_id"], detail["project"]["repo_id"])
            self.assertEqual(second["projects"][0]["summary"], first["projects"][0]["summary"])
            self.assertEqual(second["workspace"], first["workspace"])

    def test_list_projects_reuses_cached_workspace_listing_when_state_is_unchanged(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Workspace Listing Cache Demo",
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

            ui_bridge._orchestrator_cache.clear()
            ui_bridge_payloads._WORKSPACE_LISTING_MEMORY_CACHE.clear()

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            first = run_command("list-projects", workspace_root)

            with mock.patch(
                "jakal_flow.workspace.WorkspaceManager.list_projects",
                side_effect=AssertionError("workspace listing cache should bypass list_projects"),
            ), mock.patch(
                "jakal_flow.workspace.WorkspaceManager.list_history_projects",
                side_effect=AssertionError("workspace listing cache should bypass list_history_projects"),
            ):
                second = run_command("list-projects", workspace_root)

            self.assertEqual(first["projects"][0]["repo_id"], detail["project"]["repo_id"])
            self.assertEqual(second["projects"], first["projects"])
            self.assertEqual(second["workspace"], first["workspace"])

    def test_list_projects_bypass_cache_forces_workspace_refresh(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Workspace Listing Bypass Demo",
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

            ui_bridge._orchestrator_cache.clear()
            ui_bridge_payloads._WORKSPACE_LISTING_MEMORY_CACHE.clear()

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            orchestrator = ui_bridge.orchestrator_for(workspace_root)
            first = ui_bridge_payloads.list_projects_payload(orchestrator)

            original_list_projects = workspace_module.WorkspaceManager.list_projects
            original_list_history_projects = workspace_module.WorkspaceManager.list_history_projects
            call_counts = {"projects": 0, "history": 0}

            def counting_list_projects(self):
                call_counts["projects"] += 1
                return original_list_projects(self)

            def counting_list_history_projects(self):
                call_counts["history"] += 1
                return original_list_history_projects(self)

            with mock.patch.object(
                workspace_module.WorkspaceManager,
                "list_projects",
                counting_list_projects,
            ), mock.patch.object(
                workspace_module.WorkspaceManager,
                "list_history_projects",
                counting_list_history_projects,
            ):
                second = ui_bridge_payloads.list_projects_payload(orchestrator, bypass_cache=True)

            self.assertEqual(first["projects"][0]["repo_id"], detail["project"]["repo_id"])
            self.assertEqual(second["projects"][0]["repo_id"], detail["project"]["repo_id"])
            self.assertGreater(call_counts["projects"], 0)
            self.assertGreater(call_counts["history"], 0)

    def test_list_projects_workspace_listing_cache_invalidates_when_metadata_changes(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Workspace Listing Invalidation Demo",
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

            ui_bridge._orchestrator_cache.clear()
            ui_bridge_payloads._WORKSPACE_LISTING_MEMORY_CACHE.clear()

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            first = run_command("list-projects", workspace_root)
            metadata_path = Path(detail["project"]["project_root"]) / "metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["display_name"] = "Workspace Listing Invalidation Updated"
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

            second = run_command("list-projects", workspace_root)

            self.assertEqual(first["projects"][0]["display_name"], "Workspace Listing Invalidation Demo")
            self.assertEqual(second["projects"][0]["display_name"], "Workspace Listing Invalidation Updated")

    def test_list_projects_reuses_persisted_workspace_listing_cache_after_memory_reset(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Workspace Listing File Cache Demo",
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

            ui_bridge._orchestrator_cache.clear()
            ui_bridge_payloads._WORKSPACE_LISTING_MEMORY_CACHE.clear()

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            cache_file = workspace_root / "WORKSPACE_LISTING_CACHE.json"
            if cache_file.exists():
                cache_file.unlink()

            first = run_command("list-projects", workspace_root)

            self.assertTrue(cache_file.exists())

            ui_bridge._orchestrator_cache.clear()
            ui_bridge_payloads._WORKSPACE_LISTING_MEMORY_CACHE.clear()

            with mock.patch(
                "jakal_flow.workspace.WorkspaceManager.list_projects",
                side_effect=AssertionError("persisted workspace listing cache should bypass list_projects"),
            ), mock.patch(
                "jakal_flow.workspace.WorkspaceManager.list_history_projects",
                side_effect=AssertionError("persisted workspace listing cache should bypass list_history_projects"),
            ):
                second = run_command("list-projects", workspace_root)

            self.assertEqual(first["projects"][0]["repo_id"], detail["project"]["repo_id"])
            self.assertEqual(second["projects"], first["projects"])
            self.assertEqual(second["workspace"], first["workspace"])

    def test_list_projects_cached_payload_isolated_from_result_mutation(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Workspace Listing Isolation Demo",
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

            ui_bridge._orchestrator_cache.clear()
            ui_bridge_payloads._WORKSPACE_LISTING_MEMORY_CACHE.clear()

            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                run_command("save-project-setup", workspace_root, payload)

            first = run_command("list-projects", workspace_root)
            first["projects"][0]["display_name"] = "mutated"
            first["workspace"]["project_count"] = 999

            second = run_command("list-projects", workspace_root)

            self.assertEqual(second["projects"][0]["display_name"], "Workspace Listing Isolation Demo")
            self.assertNotEqual(second["workspace"]["project_count"], 999)

    def test_load_project_cached_payload_isolated_from_result_mutation(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Detail Isolation Demo",
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
                first = run_command(
                    "load-project",
                    workspace_root,
                    {
                        "repo_id": detail["project"]["repo_id"],
                        "refresh_codex_status": False,
                        "detail_level": "core",
                    },
                )

            first["summary"] = "mutated"
            first["project"]["display_name"] = "mutated"
            first["snapshot"]["project"]["display_name"] = "mutated"

            second = run_command(
                "load-project",
                workspace_root,
                {
                    "repo_id": detail["project"]["repo_id"],
                    "refresh_codex_status": False,
                    "detail_level": "core",
                },
            )

            self.assertEqual(second["project"]["display_name"], "Detail Isolation Demo")
            self.assertEqual(second["snapshot"]["project"]["display_name"], "Detail Isolation Demo")
            self.assertNotEqual(second["summary"], "mutated")

    def test_load_project_reuses_cached_provider_statuses_during_refresh_window(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Provider Status Cache Demo",
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

            ui_bridge_payloads._PROVIDER_STATUSES_FETCH_CACHE = None
            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)

            provider_status_calls: list[bool] = []

            def fake_provider_statuses_payload(*, fetch_snapshot=None):
                provider_status_calls.append(callable(fetch_snapshot))
                return {"openai": {"available": True, "usable": True}}

            ui_bridge_payloads._PROVIDER_STATUSES_FETCH_CACHE = None
            with mock.patch(
                "jakal_flow.ui_bridge_payloads.provider_statuses_payload",
                side_effect=fake_provider_statuses_payload,
            ), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                run_command(
                    "load-project",
                    workspace_root,
                    {
                        "repo_id": detail["project"]["repo_id"],
                        "refresh_codex_status": True,
                        "detail_level": "core",
                    },
                )
                run_command(
                    "load-project",
                    workspace_root,
                    {
                        "repo_id": detail["project"]["repo_id"],
                        "refresh_codex_status": True,
                        "detail_level": "core",
                    },
                )

            self.assertEqual(provider_status_calls, [True])

    def test_load_project_full_reuses_recent_content_signature_without_rescanning(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            (repo_dir / "README.md").write_text("demo", encoding="utf-8")

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Full Detail Signature Cache Demo",
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

            ui_bridge_payloads._DETAIL_CONTENT_SIGNATURE_MEMORY_CACHE.clear()
            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
                "jakal_flow.ui_bridge.fetch_codex_backend_snapshot",
                side_effect=lambda *args, **kwargs: fake_codex_snapshot(),
            ):
                detail = run_command("save-project-setup", workspace_root, payload)
                first = run_command(
                    "load-project",
                    workspace_root,
                    {
                        "repo_id": detail["project"]["repo_id"],
                        "refresh_codex_status": False,
                        "detail_level": "full",
                    },
                )

                with mock.patch(
                    "jakal_flow.ui_bridge_payloads._preview_tree_structure_token",
                    side_effect=AssertionError("recent content signature cache should bypass preview tree structure rescans"),
                ), mock.patch(
                    "jakal_flow.ui_bridge_payloads._preview_tree_signature",
                    side_effect=AssertionError("recent content signature cache should bypass preview tree rescans"),
                ):
                    second = run_command(
                        "load-project",
                        workspace_root,
                        {
                            "repo_id": detail["project"]["repo_id"],
                            "refresh_codex_status": False,
                            "detail_level": "full",
                        },
                    )

            self.assertEqual(second["detail_signature"], first["detail_signature"])

    def test_bridge_payload_size_estimator_handles_large_nested_payload_without_json_dumps(self) -> None:
        large_payload = {
            "detail_signature": "sig",
            "history": [{"index": index, "message": "x" * 256} for index in range(200)],
            "workspace_tree": [{"path": f"src/file-{index}.py", "kind": "file"} for index in range(200)],
        }

        with mock.patch("jakal_flow.ui_bridge.json.dumps", side_effect=AssertionError("json.dumps should not be used")):
            size = ui_bridge._payload_size_bytes(large_payload)

        self.assertGreater(size, 0)

    def test_bridge_perf_log_aggregates_fast_cached_read_commands(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            workspace_root.mkdir(parents=True, exist_ok=True)
            bridge_perf_file = workspace_root / "bridge_perf.jsonl"
            if bridge_perf_file.exists():
                bridge_perf_file.unlink()

            ui_bridge._bridge_perf_aggregate_cache.clear()
            result = {
                "payload_cache_hit": True,
                "content_signature": "content",
                "detail_signature": "detail",
                "project": {"repo_id": "repo-1"},
            }
            payload = {
                "repo_id": "repo-1",
                "detail_level": "core",
                "refresh_codex_status": False,
            }

            for _ in range(10):
                ui_bridge._bridge_perf_log(workspace_root, "load-project", payload, result, 4.0)

            entries = read_jsonl(bridge_perf_file)

            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["command"], "load-project")
            self.assertEqual(entries[0]["sample_count"], 10)
            self.assertEqual(entries[0]["payload_cache_hit"], True)

    def test_load_project_chat_reuses_cached_payload_and_isolates_result_mutation(self) -> None:
        with TemporaryTestDir() as temp_dir, mock.patch.dict(
            os.environ,
            {CHAT_HOME_ENV_VAR: str(temp_dir / "chat-home")},
            clear=False,
        ):
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Chat Cache Demo",
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

            project = ui_bridge.orchestrator_for(workspace_root).workspace.load_project_by_id(detail["project"]["repo_id"])
            session = chat_sessions.create_chat_session(project, title_hint="Release follow-up")
            chat_sessions.save_chat_message(
                project,
                session.session_id,
                role="user",
                text="status update",
                mode="conversation",
            )
            chat_sessions.save_chat_message(
                project,
                session.session_id,
                role="assistant",
                text="working on it",
                mode="conversation",
            )
            chat_sessions.rebuild_chat_session_files(project, session.session_id)

            chat_sessions._CHAT_REGISTRY_MEMORY_CACHE.clear()
            chat_sessions._CHAT_ACTIVE_SESSION_MEMORY_CACHE.clear()
            chat_sessions._CHAT_MESSAGES_MEMORY_CACHE.clear()
            chat_sessions._CHAT_TEXT_MEMORY_CACHE.clear()
            chat_sessions._CHAT_PAYLOAD_MEMORY_CACHE.clear()

            first = run_command(
                "load-project-chat",
                workspace_root,
                {
                    "repo_id": detail["project"]["repo_id"],
                    "session_id": session.session_id,
                },
            )

            first["chat"]["summary_text"] = "mutated"
            first["chat"]["messages"][0]["text"] = "mutated"
            first["chat"]["sessions"][0]["title"] = "mutated"

            with mock.patch(
                "jakal_flow.chat_sessions._read_jsonl_txt",
                side_effect=AssertionError("chat registry cache should avoid reparsing jsonl text"),
            ), mock.patch(
                "jakal_flow.chat_sessions._read_jsonl_txt_tail",
                side_effect=AssertionError("chat payload cache should avoid rereading message tails"),
            ):
                second = run_command(
                    "load-project-chat",
                    workspace_root,
                    {
                        "repo_id": detail["project"]["repo_id"],
                        "session_id": session.session_id,
                    },
                )

            self.assertEqual(second["chat"]["messages"][0]["text"], "status update")
            self.assertNotEqual(second["chat"]["summary_text"], "mutated")
            self.assertNotEqual(second["chat"]["sessions"][0]["title"], "mutated")

    def test_load_workspace_share_reuses_cached_payload_and_isolates_result_mutation(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            workspace_root.mkdir(parents=True, exist_ok=True)

            share_module._SHARE_STATUS_MEMORY_CACHE.clear()
            share_module._WORKSPACE_SHARE_PAYLOAD_MEMORY_CACHE.clear()
            share_module.save_share_server_config(
                workspace_root,
                share_module.ShareServerConfig(public_base_url="https://share.example.com/base"),
            )
            (workspace_root / "share_server.json").write_text(
                json.dumps(
                    {
                        "host": "0.0.0.0",
                        "port": 43123,
                        "pid": 4242,
                        "started_at": "2026-03-30T00:00:00+00:00",
                        "viewer_path": "/share/view",
                    }
                ),
                encoding="utf-8",
            )
            share_module.create_workspace_share_session(workspace_root, expires_in_minutes=60)

            fake_tunnel = {
                "running": False,
                "provider": None,
                "public_url": "",
                "target_url": "",
                "pid": None,
                "started_at": None,
                "available": True,
            }

            with mock.patch("jakal_flow.share.process_is_running", return_value=True), mock.patch(
                "jakal_flow.public_tunnel.public_tunnel_status_payload",
                return_value=fake_tunnel,
            ):
                first = run_command("load-workspace-share", workspace_root, {})

            first["share"]["server"]["config"]["public_base_url"] = "mutated"
            first["share"]["sessions"][0]["share_url"] = "mutated"

            with mock.patch(
                "jakal_flow.share.process_is_running",
                side_effect=AssertionError("workspace share cache should avoid repeated process checks"),
            ), mock.patch(
                "jakal_flow.public_tunnel.public_tunnel_status_payload",
                side_effect=AssertionError("workspace share cache should avoid repeated tunnel refreshes"),
            ):
                second = run_command("load-workspace-share", workspace_root, {})

            self.assertEqual(second["share"]["server"]["config"]["public_base_url"], "https://share.example.com/base")
            self.assertNotEqual(second["share"]["sessions"][0]["share_url"], "mutated")

    def test_load_project_share_reuses_cached_payload_and_isolates_result_mutation(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Project Share Cache Demo",
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

            share_module._SHARE_STATUS_MEMORY_CACHE.clear()
            share_module._WORKSPACE_SHARE_PAYLOAD_MEMORY_CACHE.clear()
            share_module.save_share_server_config(
                workspace_root,
                share_module.ShareServerConfig(public_base_url="https://share.example.com/project"),
            )
            (workspace_root / "share_server.json").write_text(
                json.dumps(
                    {
                        "host": "0.0.0.0",
                        "port": 43124,
                        "pid": 4343,
                        "started_at": "2026-03-30T00:00:00+00:00",
                        "viewer_path": "/share/view",
                    }
                ),
                encoding="utf-8",
            )
            project = ui_bridge.orchestrator_for(workspace_root).workspace.load_project_by_id(detail["project"]["repo_id"])
            share_module.create_workspace_share_session(workspace_root, context=project, expires_in_minutes=60)

            fake_tunnel = {
                "running": False,
                "provider": None,
                "public_url": "",
                "target_url": "",
                "pid": None,
                "started_at": None,
                "available": True,
            }

            with mock.patch("jakal_flow.share.process_is_running", return_value=True), mock.patch(
                "jakal_flow.public_tunnel.public_tunnel_status_payload",
                return_value=fake_tunnel,
            ):
                first = run_command(
                    "load-project-share",
                    workspace_root,
                    {
                        "repo_id": detail["project"]["repo_id"],
                    },
                )

            first["share"]["server"]["config"]["public_base_url"] = "mutated"

            with mock.patch(
                "jakal_flow.share.process_is_running",
                side_effect=AssertionError("project share cache should avoid repeated process checks"),
            ), mock.patch(
                "jakal_flow.public_tunnel.public_tunnel_status_payload",
                side_effect=AssertionError("project share cache should avoid repeated tunnel refreshes"),
            ):
                second = run_command(
                    "load-project-share",
                    workspace_root,
                    {
                        "repo_id": detail["project"]["repo_id"],
                    },
                )

            self.assertEqual(second["share"]["server"]["config"]["public_base_url"], "https://share.example.com/project")

    def test_load_project_reports_reuses_cached_payload_and_isolates_result_mutation(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Reports Cache Demo",
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

            project = ui_bridge.orchestrator_for(workspace_root).workspace.load_project_by_id(detail["project"]["repo_id"])
            project.paths.closeout_report_file.write_text("# Closeout Report\n\nDone.\n", encoding="utf-8")
            project.paths.attempt_history_file.write_text("attempt 1", encoding="utf-8")
            ui_bridge_payloads._SECTION_PAYLOAD_MEMORY_CACHE.clear()

            first = run_command(
                "load-project-reports",
                workspace_root,
                {
                    "repo_id": detail["project"]["repo_id"],
                },
            )

            first["closeout_report_text"] = "mutated"
            first["spine"]["current_version"] = "mutated"

            with mock.patch(
                "jakal_flow.ui_bridge_payloads.preview_text",
                side_effect=AssertionError("report payload cache should avoid preview text rebuilds"),
            ), mock.patch(
                "jakal_flow.ui_bridge_payloads._contract_wave_report_payload",
                side_effect=AssertionError("report payload cache should avoid contract wave rebuilds"),
            ), mock.patch(
                "jakal_flow.ui_bridge_payloads._latest_failure_details",
                side_effect=AssertionError("report payload cache should avoid latest failure rebuilds"),
            ):
                second = run_command(
                    "load-project-reports",
                    workspace_root,
                    {
                        "repo_id": detail["project"]["repo_id"],
                    },
                )

            self.assertNotEqual(second["closeout_report_text"], "mutated")
            self.assertNotEqual(second["spine"]["current_version"], "mutated")

    def test_workspace_manager_reuses_cached_project_context_when_files_are_unchanged(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Project Context Cache Demo",
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

            workspace = WorkspaceManager(workspace_root)
            project = workspace.load_project_by_id(detail["project"]["repo_id"])
            blocked_paths = {
                workspace.registry_file.resolve(),
                project.paths.metadata_file.resolve(),
                project.paths.project_config_file.resolve(),
                project.paths.loop_state_file.resolve(),
            }
            original_read_json = workspace_module.read_json

            def guarded_read_json(path, *args, **kwargs):
                if Path(path).resolve() in blocked_paths:
                    raise AssertionError("cached workspace project context should be reused")
                return original_read_json(path, *args, **kwargs)

            with mock.patch("jakal_flow.workspace.read_json", side_effect=guarded_read_json):
                cached = workspace.load_project_by_id(detail["project"]["repo_id"])

            self.assertEqual(cached.metadata.repo_id, project.metadata.repo_id)
            self.assertEqual(cached.runtime.model, project.runtime.model)
            self.assertEqual(cached.loop_state.repo_id, project.loop_state.repo_id)

    def test_orchestrator_reuses_cached_execution_plan_state_when_file_is_unchanged(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            payload = {
                "project_dir": str(repo_dir),
                "display_name": "Plan Cache Demo",
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

            workspace = WorkspaceManager(workspace_root)
            project = workspace.load_project_by_id(detail["project"]["repo_id"])
            orchestrator = orchestrator_module.Orchestrator(workspace_root)
            saved_state = orchestrator.load_execution_plan_state(project)
            execution_plan_file = project.paths.execution_plan_file.resolve()
            original_read_json = orchestrator_module.read_json

            def guarded_read_json(path, *args, **kwargs):
                if Path(path).resolve() == execution_plan_file:
                    raise AssertionError("cached execution plan state should be reused")
                return original_read_json(path, *args, **kwargs)

            with mock.patch("jakal_flow.orchestrator.read_json", side_effect=guarded_read_json):
                cached_state = orchestrator.load_execution_plan_state(project)

            self.assertEqual(cached_state.to_dict(), saved_state.to_dict())

    def test_workspace_recovers_project_root_from_stale_registry_entry(self) -> None:
        with TemporaryTestDir() as temp_dir:
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)

            workspace = WorkspaceManager(workspace_root)
            context = workspace.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=RuntimeOptions(),
                origin_url="",
                display_name="Lit Project",
            )

            actual_root = context.paths.project_root
            stale_root = workspace.projects_root / "c-users-ahnd6-onedrive-github-lit-main-679f7c0bcc"
            stale_root.mkdir(parents=True, exist_ok=True)
            stale_metadata = json.loads((actual_root / "metadata.json").read_text(encoding="utf-8"))
            stale_metadata["project_root"] = str(stale_root)
            stale_metadata["repo_path"] = r"C:\Users\ahnd6\OneDrive\Documents\GitHub\lit"
            stale_metadata["slug"] = "c-users-ahnd6-onedrive-github-lit-main-679f7c0bcc"
            (stale_root / "metadata.json").write_text(json.dumps(stale_metadata, indent=2, sort_keys=True), encoding="utf-8")

            registry = json.loads(workspace.registry_file.read_text(encoding="utf-8"))
            registry["projects"][context.metadata.repo_id]["project_root"] = str(stale_root)
            registry["projects"][context.metadata.repo_id]["slug"] = "c-users-ahnd6-onedrive-github-lit-main-679f7c0bcc"
            registry["projects"][context.metadata.repo_id]["repo_path"] = r"C:\Users\ahnd6\OneDrive\Documents\GitHub\lit"
            workspace.registry_file.write_text(json.dumps(registry, indent=2, sort_keys=True), encoding="utf-8")

            projects = workspace.list_projects()

            self.assertEqual(len(projects), 1)
            self.assertEqual(projects[0].metadata.repo_id, context.metadata.repo_id)
            self.assertEqual(projects[0].paths.project_root.resolve(), actual_root.resolve())

            refreshed_registry = json.loads(workspace.registry_file.read_text(encoding="utf-8"))
            self.assertEqual(
                refreshed_registry["projects"][context.metadata.repo_id]["project_root"],
                str(actual_root),
            )
            self.assertEqual(
                refreshed_registry["projects"][context.metadata.repo_id]["repo_path"],
                str(repo_dir.resolve()),
            )

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
