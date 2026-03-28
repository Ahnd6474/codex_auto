from __future__ import annotations

import json
from types import SimpleNamespace
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jakal_flow.environment import ensure_gitignore
from jakal_flow.execution_control import ImmediateStopRequested
from jakal_flow.model_selection import (
    DEFAULT_MODEL_PRESET_ID,
    MODEL_MODE_CODEX,
    MODEL_MODE_SLUG,
    ModelSelection,
    model_preset_by_id,
    model_preset_from_runtime,
    model_selection_from_runtime,
    normalize_model_preset_id,
)
from jakal_flow.models import CandidateTask, CodexRunResult, CommandResult, ExecutionPlanState, ExecutionStep, LineageState, MLExperimentRecord, RuntimeOptions, TestRunResult
from jakal_flow.orchestrator import Orchestrator
from jakal_flow.parallel_resources import build_parallel_resource_plan
from jakal_flow.planning import (
    DEBUGGER_PARALLEL_PROMPT_FILENAME,
    DEBUGGER_PROMPT_FILENAME,
    FINALIZATION_PROMPT_FILENAME,
    MERGER_PARALLEL_PROMPT_FILENAME,
    ML_PLAN_DECOMPOSITION_PROMPT_FILENAME,
    OPTIMIZATION_PROMPT_FILENAME,
    ML_FINALIZATION_PROMPT_FILENAME,
    ML_PLAN_GENERATION_PROMPT_FILENAME,
    ML_STEP_EXECUTION_PROMPT_FILENAME,
    PLAN_DECOMPOSITION_PARALLEL_PROMPT_FILENAME,
    PLAN_GENERATION_PARALLEL_PROMPT_FILENAME,
    PLAN_GENERATION_PROMPT_FILENAME,
    REFERENCE_GUIDE_FILENAME,
    SCOPE_GUARD_TEMPLATE_FILENAME,
    STEP_EXECUTION_PARALLEL_PROMPT_FILENAME,
    STEP_EXECUTION_PROMPT_FILENAME,
    bootstrap_plan_prompt,
    execution_plan_svg,
    load_debugger_prompt_template,
    load_finalization_prompt_template,
    load_merger_prompt_template,
    load_optimization_prompt_template,
    load_plan_decomposition_prompt_template,
    load_plan_generation_prompt_template,
    load_reference_guide_text,
    load_source_prompt_template,
    load_step_execution_prompt_template,
    parse_execution_plan_response,
    prompt_to_plan_decomposition_prompt,
    prompt_to_execution_plan_prompt,
    scan_repository_inputs,
    source_prompt_template_path,
)
from jakal_flow.reporting import Reporter
from jakal_flow.step_models import GEMINI_DEFAULT_MODEL, resolve_step_model_choice
from jakal_flow.utils import append_jsonl, read_json, read_jsonl_tail, read_last_jsonl, write_json


class ExecutionPlanHelperTests(unittest.TestCase):
    def test_legacy_codex_auto_namespace_is_removed(self) -> None:
        with self.assertRaises(ModuleNotFoundError):
            __import__("codex_auto.planning")

    def test_parse_execution_plan_response_reads_json_tasks(self) -> None:
        response = """
        {
          "title": "CLI rollout",
          "summary": "Build the feature in small verified steps.",
          "tasks": [
            {
              "step_id": "ST1",
              "task_title": "Add the CLI flag",
              "display_description": "Expose the new flag to users.",
              "codex_description": "Inspect the CLI parser, add the flag, and cover it with tests.",
              "reasoning_effort": "medium",
              "depends_on": [],
              "owned_paths": ["src/cli.py", "tests/test_cli.py"],
              "success_criteria": "CLI parsing succeeds."
            },
            {
              "step_id": "ST2",
              "task_title": "Wire the backend",
              "display_description": "Connect the new option to execution.",
              "codex_description": "Review the execution path, add targeted tests, and wire the backend.",
              "reasoning_effort": "high",
              "depends_on": ["ST1"],
              "owned_paths": ["src/backend.py"],
              "success_criteria": "Backend path is covered."
            }
          ]
        }
        """
        plan_title, summary, steps = parse_execution_plan_response(response, "python -m unittest", "low", limit=4)

        self.assertEqual(plan_title, "CLI rollout")
        self.assertEqual(summary, "Build the feature in small verified steps.")
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0].step_id, "ST1")
        self.assertEqual(steps[0].display_description, "Expose the new flag to users.")
        self.assertIn("CLI parser", steps[0].codex_description)
        self.assertEqual(steps[0].test_command, "python -m unittest")
        self.assertEqual(steps[0].reasoning_effort, "medium")
        self.assertEqual(steps[0].depends_on, [])
        self.assertEqual(steps[0].owned_paths, ["src/cli.py", "tests/test_cli.py"])
        self.assertEqual(steps[1].step_id, "ST2")
        self.assertEqual(steps[1].test_command, "python -m unittest")
        self.assertEqual(steps[1].reasoning_effort, "high")
        self.assertEqual(steps[1].depends_on, ["ST1"])

    def test_parse_execution_plan_response_defaults_reasoning_effort(self) -> None:
        response = """
        {
          "tasks": [
            {
              "task_title": "Small fix",
              "display_description": "Keep the fallback effort.",
              "codex_description": "Apply the fix without an explicit effort."
            }
          ]
        }
        """

        _title, _summary, steps = parse_execution_plan_response(response, "python -m unittest", "xhigh", limit=2)

        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].reasoning_effort, "xhigh")

    def test_parse_execution_plan_response_preserves_metadata(self) -> None:
        response = """
        {
          "tasks": [
            {
              "task_title": "Run experiment",
              "display_description": "Evaluate one ML configuration.",
              "codex_description": "Use the existing training script and log one reproducible experiment.",
              "metadata": {
                "experiment_id": "EXP-1",
                "experiment_kind": "ml",
                "primary_metric": "f1",
                "feature_spec": "tfidf + stats",
                "model_spec": "lightgbm"
              }
            }
          ]
        }
        """

        _title, _summary, steps = parse_execution_plan_response(response, "python -m unittest", "high", limit=2)

        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].metadata["experiment_id"], "EXP-1")
        self.assertEqual(steps[0].metadata["model_spec"], "lightgbm")

    def test_parse_execution_plan_response_preserves_join_metadata(self) -> None:
        response = """
        {
          "tasks": [
            {
              "step_id": "ST3",
              "task_title": "Join frontend and backend",
              "display_description": "Integrate both branches.",
              "codex_description": "Reconcile the completed frontend and backend work on the current branch.",
              "depends_on": ["ST1", "ST2"],
              "success_criteria": "The integrated branch passes verification.",
              "metadata": {
                "step_kind": "join",
                "merge_from": ["ST1", "ST2"],
                "join_policy": "all",
                "join_reason": "The API and UI must be validated together before closeout."
              }
            }
          ]
        }
        """

        _title, _summary, steps = parse_execution_plan_response(response, "python -m unittest", "high", limit=3)

        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].metadata["step_kind"], "join")
        self.assertEqual(steps[0].metadata["merge_from"], ["ST1", "ST2"])
        self.assertEqual(steps[0].metadata["join_policy"], "all")

    def test_parse_execution_plan_response_recovers_json_from_noisy_text(self) -> None:
        response = """
        Here is the execution plan JSON.

        {
          "title": "Recovery rollout",
          "summary": "Recover the machine-readable plan.",
          "tasks": [
            {
              "task_title": "Retry the parser",
              "display_description": "Recover from prefixed prose.",
              "codex_description": "Read through the noisy response and keep the JSON payload.",
              "reasoning_effort": "medium"
            }
          ]
        }

        Keep the work incremental.
        """

        plan_title, summary, steps = parse_execution_plan_response(response, "python -m unittest", "high", limit=3)

        self.assertEqual(plan_title, "Recovery rollout")
        self.assertEqual(summary, "Recover the machine-readable plan.")
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].title, "Retry the parser")

    def test_execution_step_from_dict_accepts_legacy_description(self) -> None:
        step = ExecutionStep.from_dict(
            {
                "step_id": "ST1",
                "title": "Legacy task",
                "description": "Old UI description",
                "success_criteria": "Still works.",
            }
        )

        self.assertEqual(step.display_description, "Old UI description")
        self.assertEqual(step.codex_description, "Old UI description")
        self.assertEqual(step.success_criteria, "Still works.")

    def test_execution_step_from_dict_reads_reasoning_effort(self) -> None:
        step = ExecutionStep.from_dict(
            {
                "step_id": "ST1",
                "title": "Reasoning task",
                "reasoning_effort": "xhigh",
                "depends_on": "ST0, ST2",
                "owned_paths": "src/app.py,\nsrc/lib.py",
            }
        )

        self.assertEqual(step.reasoning_effort, "xhigh")
        self.assertEqual(step.depends_on, ["ST0", "ST2"])
        self.assertEqual(step.owned_paths, ["src/app.py", "src/lib.py"])

    def test_execution_step_from_dict_reads_model_fields(self) -> None:
        step = ExecutionStep.from_dict(
            {
                "step_id": "ST1",
                "title": "UI pass",
                "model_provider": "gemini",
                "model": "gemini-3-flash",
            }
        )

        self.assertEqual(step.model_provider, "gemini")
        self.assertEqual(step.model, "gemini-3-flash")

    def test_resolve_step_model_choice_prefers_gemini_for_ui_steps(self) -> None:
        runtime = RuntimeOptions(model="gpt-5.4", model_provider="openai")
        step = ExecutionStep(
            step_id="ST1",
            title="Refresh desktop settings panel",
            display_description="Update the UI layout for the settings screen.",
            owned_paths=["desktop/src/components/views/AppSettingsView.jsx"],
        )

        with mock.patch("jakal_flow.step_models.gemini_available_for_auto_selection", return_value=True):
            choice = resolve_step_model_choice(step, runtime)

        self.assertEqual(choice.provider, "gemini")
        self.assertEqual(choice.model, GEMINI_DEFAULT_MODEL)
        self.assertEqual(choice.source, "auto")

    def test_resolve_step_model_choice_falls_back_when_gemini_auth_is_unavailable(self) -> None:
        runtime = RuntimeOptions(model="gpt-5.4", model_provider="openai")
        step = ExecutionStep(
            step_id="ST1",
            title="Refresh desktop settings panel",
            display_description="Update the UI layout for the settings screen.",
            owned_paths=["desktop/src/components/views/AppSettingsView.jsx"],
        )

        with mock.patch("jakal_flow.step_models.gemini_available_for_auto_selection", return_value=False):
            choice = resolve_step_model_choice(step, runtime)

        self.assertEqual(choice.provider, "openai")
        self.assertEqual(choice.model, "gpt-5.4")
        self.assertEqual(choice.source, "auto")
        self.assertIn("Gemini auth is not configured", choice.reason)

    def test_resolve_step_model_choice_keeps_explicit_gemini_override(self) -> None:
        runtime = RuntimeOptions(model="gpt-5.4", model_provider="openai")
        step = ExecutionStep(
            step_id="ST1",
            title="Refresh desktop settings panel",
            model_provider="gemini",
            owned_paths=["desktop/src/components/views/AppSettingsView.jsx"],
        )

        with mock.patch("jakal_flow.step_models.gemini_available_for_auto_selection", return_value=False):
            choice = resolve_step_model_choice(step, runtime)

        self.assertEqual(choice.provider, "gemini")
        self.assertEqual(choice.model, GEMINI_DEFAULT_MODEL)
        self.assertEqual(choice.source, "manual")

    def test_resolve_step_model_choice_keeps_codex_for_non_ui_steps(self) -> None:
        runtime = RuntimeOptions(model="gpt-5.4", model_provider="openai")
        step = ExecutionStep(
            step_id="ST1",
            title="Refactor orchestrator runtime overlay",
            owned_paths=["src/jakal_flow/orchestrator.py"],
        )

        choice = resolve_step_model_choice(step, runtime)

        self.assertEqual(choice.provider, "openai")
        self.assertEqual(choice.model, "gpt-5.4")
        self.assertEqual(choice.source, "auto")

    def test_execution_plan_state_reads_closeout_fields(self) -> None:
        state = ExecutionPlanState.from_dict(
            {
                "plan_title": "demo",
                "workflow_mode": "ml",
                "execution_mode": "parallel",
                "closeout_status": "completed",
                "closeout_started_at": "2026-01-01T00:00:00+00:00",
                "closeout_completed_at": "2026-01-01T01:00:00+00:00",
                "closeout_commit_hash": "abc123",
                "closeout_notes": "final tests passed",
                "steps": [],
            }
        )

        self.assertEqual(state.workflow_mode, "ml")
        self.assertEqual(state.execution_mode, "parallel")
        self.assertEqual(state.closeout_status, "completed")
        self.assertEqual(state.closeout_commit_hash, "abc123")
        self.assertEqual(state.closeout_notes, "final tests passed")

    def test_lineage_state_from_dict_preserves_optional_null_fields(self) -> None:
        lineage = LineageState.from_dict(
            {
                "lineage_id": "LN1",
                "branch_name": "jakal-flow-lineage-ln1",
                "worktree_dir": "C:/tmp/ln1/repo",
                "project_root": "C:/tmp/ln1",
                "created_at": "2026-03-27T00:00:00+00:00",
                "updated_at": "2026-03-27T00:00:00+00:00",
                "merged_by_step_id": None,
                "parent_lineage_id": None,
            }
        )

        self.assertIsNone(lineage.merged_by_step_id)
        self.assertIsNone(lineage.parent_lineage_id)

    def test_create_lineage_state_uses_unique_branch_names_for_reused_lineage_ids(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_unique_lineage_branch_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", test_cmd="python -m pytest", execution_mode="parallel")

        try:
            context = orchestrator.workspace.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=runtime,
            )
            with mock.patch.object(orchestrator.git, "add_worktree") as mocked_add_worktree:
                first = orchestrator._create_lineage_state(context, {}, source_revision="safe-main")
                second = orchestrator._create_lineage_state(context, {}, source_revision="safe-main")
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertTrue(first.branch_name.startswith("jakal-flow-lineage-ln1-"))
        self.assertTrue(second.branch_name.startswith("jakal-flow-lineage-ln1-"))
        self.assertNotEqual(first.branch_name, second.branch_name)
        self.assertEqual(mocked_add_worktree.call_count, 2)
        self.assertNotEqual(mocked_add_worktree.call_args_list[0].args[2], mocked_add_worktree.call_args_list[1].args[2])

    def test_build_lineage_context_reattaches_existing_branch_when_worktree_is_missing(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_reattach_lineage_branch_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", test_cmd="python -m pytest", execution_mode="parallel")

        try:
            context = orchestrator.workspace.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=runtime,
            )
            lineage = LineageState(
                lineage_id="LN1",
                branch_name="jakal-flow-lineage-ln1",
                worktree_dir=temp_root / "lineages" / "ln1" / "repo",
                project_root=temp_root / "lineages" / "ln1",
                created_at="2026-03-28T00:00:00+00:00",
                updated_at="2026-03-28T00:00:00+00:00",
                head_commit="ln1-head",
                safe_revision="ln1-head",
            )
            step = ExecutionStep(step_id="ST1", title="Frontend slice", owned_paths=["desktop/src"])
            with mock.patch.object(orchestrator.git, "branch_exists", return_value=True) as mocked_branch_exists, mock.patch.object(
                orchestrator.git,
                "attach_worktree",
            ) as mocked_attach, mock.patch.object(
                orchestrator.git,
                "add_worktree",
            ) as mocked_add:
                lineage_context = orchestrator._build_lineage_context(context, runtime, step, lineage)
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        mocked_branch_exists.assert_called_once_with(context.paths.repo_dir, lineage.branch_name)
        mocked_attach.assert_called_once_with(context.paths.repo_dir, lineage.worktree_dir, lineage.branch_name)
        mocked_add.assert_not_called()
        self.assertEqual(lineage_context.metadata.branch, lineage.branch_name)

    def test_pending_execution_batches_uses_dependency_ready_waves(self) -> None:
        orchestrator = Orchestrator(Path.cwd() / ".tmp_pending_batches_workspace")
        plan_state = ExecutionPlanState(
            execution_mode="parallel",
            steps=[
                ExecutionStep(step_id="ST1", title="Root", status="completed"),
                ExecutionStep(step_id="ST2", title="Frontend", depends_on=["ST1"], owned_paths=["desktop/src"]),
                ExecutionStep(step_id="ST3", title="Backend", depends_on=["ST1"], owned_paths=["src/jakal_flow"]),
                ExecutionStep(step_id="ST4", title="Finalize", depends_on=["ST2", "ST3"], owned_paths=["docs"]),
            ],
        )

        batches = orchestrator.pending_execution_batches(plan_state)

        self.assertEqual([[step.step_id for step in batch] for batch in batches], [["ST2", "ST3"]])

    def test_parallel_resource_plan_auto_caps_workers_by_cpu_quarter(self) -> None:
        with mock.patch("jakal_flow.parallel_resources.os.cpu_count", return_value=16), mock.patch(
            "jakal_flow.parallel_resources._detect_memory_bytes",
            return_value=(64 * 1024**3, 32 * 1024**3),
        ):
            plan = build_parallel_resource_plan("auto", 0)

        self.assertEqual(plan.worker_mode, "auto")
        self.assertEqual(plan.cpu_logical_count, 16)
        self.assertEqual(plan.cpu_parallel_limit, 4)
        self.assertEqual(plan.recommended_workers, 4)

    def test_parallel_resource_plan_auto_uses_two_workers_on_four_core_machine(self) -> None:
        with mock.patch("jakal_flow.parallel_resources.os.cpu_count", return_value=4), mock.patch(
            "jakal_flow.parallel_resources._detect_memory_bytes",
            return_value=(16 * 1024**3, 12 * 1024**3),
        ):
            plan = build_parallel_resource_plan("auto", 0)

        self.assertEqual(plan.worker_mode, "auto")
        self.assertEqual(plan.cpu_logical_count, 4)
        self.assertEqual(plan.cpu_parallel_limit, 2)
        self.assertEqual(plan.memory_parallel_limit, 4)
        self.assertEqual(plan.recommended_workers, 2)

    def test_parallel_resource_plan_manual_respects_resource_cap(self) -> None:
        with mock.patch("jakal_flow.parallel_resources.os.cpu_count", return_value=12), mock.patch(
            "jakal_flow.parallel_resources._detect_memory_bytes",
            return_value=(64 * 1024**3, 32 * 1024**3),
        ):
            plan = build_parallel_resource_plan("manual", 6)

        self.assertEqual(plan.worker_mode, "manual")
        self.assertEqual(plan.cpu_parallel_limit, 3)
        self.assertEqual(plan.recommended_workers, 3)

    def test_parallel_resource_plan_uses_configured_memory_budget_per_worker(self) -> None:
        with mock.patch("jakal_flow.parallel_resources.os.cpu_count", return_value=16), mock.patch(
            "jakal_flow.parallel_resources._detect_memory_bytes",
            return_value=(64 * 1024**3, 10 * 1024**3),
        ):
            plan = build_parallel_resource_plan("auto", 0, 5)

        self.assertEqual(plan.memory_budget_per_worker_gib, 5)
        self.assertEqual(plan.memory_parallel_limit, 2)
        self.assertEqual(plan.recommended_workers, 2)

    def test_parallel_resource_plan_accepts_tenth_gib_memory_budget(self) -> None:
        with mock.patch("jakal_flow.parallel_resources.os.cpu_count", return_value=16), mock.patch(
            "jakal_flow.parallel_resources._detect_memory_bytes",
            return_value=(64 * 1024**3, 4 * 1024**3),
        ):
            plan = build_parallel_resource_plan("auto", 0, 1.5)

        self.assertAlmostEqual(plan.memory_budget_per_worker_gib, 1.5)
        self.assertEqual(plan.memory_parallel_limit, 2)
        self.assertEqual(plan.recommended_workers, 2)

    def test_pending_execution_batches_keeps_parent_child_owned_paths_together(self) -> None:
        orchestrator = Orchestrator(Path.cwd() / ".tmp_pending_batches_workspace")
        plan_state = ExecutionPlanState(
            execution_mode="parallel",
            steps=[
                ExecutionStep(step_id="ST1", title="Root", status="completed"),
                ExecutionStep(step_id="ST2", title="A", depends_on=["ST1"], owned_paths=["src/shared"]),
                ExecutionStep(step_id="ST3", title="B", depends_on=["ST1"], owned_paths=["src/shared/utils"]),
                ExecutionStep(step_id="ST4", title="C", depends_on=["ST1"], owned_paths=["tests"]),
            ],
        )

        batches = orchestrator.pending_execution_batches(plan_state)

        self.assertEqual([[step.step_id for step in batch] for batch in batches], [["ST2", "ST3", "ST4"]])

    def test_pending_execution_batches_splits_exact_owned_path_conflicts(self) -> None:
        orchestrator = Orchestrator(Path.cwd() / ".tmp_pending_batches_workspace")
        plan_state = ExecutionPlanState(
            execution_mode="parallel",
            steps=[
                ExecutionStep(step_id="ST1", title="Root", status="completed"),
                ExecutionStep(step_id="ST2", title="A", depends_on=["ST1"], owned_paths=["src/shared/utils.py"]),
                ExecutionStep(step_id="ST3", title="B", depends_on=["ST1"], owned_paths=["src/shared/utils.py"]),
                ExecutionStep(step_id="ST4", title="C", depends_on=["ST1"], owned_paths=["tests"]),
            ],
        )

        batches = orchestrator.pending_execution_batches(plan_state)

        self.assertEqual([[step.step_id for step in batch] for batch in batches], [["ST2"], ["ST3", "ST4"]])

    def test_pending_execution_batches_runs_join_nodes_as_singletons(self) -> None:
        orchestrator = Orchestrator(Path.cwd() / ".tmp_pending_batches_workspace")
        plan_state = ExecutionPlanState(
            execution_mode="parallel",
            steps=[
                ExecutionStep(step_id="ST1", title="Frontend slice", status="completed", owned_paths=["desktop/src"]),
                ExecutionStep(step_id="ST2", title="Backend slice", status="completed", owned_paths=["src/jakal_flow"]),
                ExecutionStep(
                    step_id="ST3",
                    title="Join frontend and backend",
                    depends_on=["ST1", "ST2"],
                    metadata={"step_kind": "join", "merge_from": ["ST1", "ST2"], "join_policy": "all"},
                ),
                ExecutionStep(step_id="ST4", title="Docs cleanup", depends_on=["ST2"], owned_paths=["docs"]),
            ],
        )

        batches = orchestrator.pending_execution_batches(plan_state)

        self.assertEqual([[step.step_id for step in batch] for batch in batches], [["ST3"], ["ST4"]])

    def test_pending_execution_batches_runs_root_barrier_nodes_as_singletons(self) -> None:
        orchestrator = Orchestrator(Path.cwd() / ".tmp_pending_batches_workspace")
        plan_state = ExecutionPlanState(
            execution_mode="parallel",
            steps=[
                ExecutionStep(step_id="ST1", title="Freeze shared contract", metadata={"step_kind": "barrier"}),
                ExecutionStep(step_id="ST2", title="Independent docs", owned_paths=["docs"]),
            ],
        )

        batches = orchestrator.pending_execution_batches(plan_state)

        self.assertEqual([[step.step_id for step in batch] for batch in batches], [["ST1"], ["ST2"]])

    def test_save_execution_plan_state_upgrades_legacy_serial_mode_to_parallel(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_serial_parallel_group_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", execution_mode="serial")

        try:
            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"):
                context, plan_state = orchestrator.update_execution_plan(
                    project_dir=repo_dir,
                    runtime=runtime,
                    plan_state=ExecutionPlanState(
                        execution_mode="",
                        default_test_command="python -m pytest",
                        steps=[
                            ExecutionStep(
                                step_id="custom-1",
                                title="Serialized step",
                                depends_on=["custom-2"],
                                owned_paths=["src/serial.py"],
                            ),
                            ExecutionStep(
                                step_id="custom-2",
                                title="Bootstrap step",
                                owned_paths=["src/bootstrap.py"],
                            ),
                        ],
                    ),
                )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(context.runtime.execution_mode, "parallel")
        self.assertEqual(plan_state.execution_mode, "parallel")
        self.assertEqual(plan_state.steps[0].parallel_group, "")
        self.assertEqual(plan_state.steps[0].depends_on, ["ST2"])
        self.assertEqual(plan_state.steps[0].owned_paths, ["src/serial.py"])

    def test_save_execution_plan_state_renormalizes_dag_dependency_ids(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_parallel_dag_plan_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", execution_mode="parallel")

        try:
            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"):
                _context, plan_state = orchestrator.update_execution_plan(
                    project_dir=repo_dir,
                    runtime=runtime,
                    plan_state=ExecutionPlanState(
                        execution_mode="parallel",
                        default_test_command="python -m pytest",
                        steps=[
                            ExecutionStep(step_id="NODE-B", title="Backend", depends_on=["NODE-A"], owned_paths=["src/backend"]),
                            ExecutionStep(step_id="NODE-A", title="API", depends_on=[], owned_paths=["src/api"]),
                        ],
                    ),
                )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual([step.step_id for step in plan_state.steps], ["ST1", "ST2"])
        self.assertEqual(plan_state.steps[0].depends_on, ["ST2"])
        self.assertEqual(plan_state.steps[1].depends_on, [])

    def test_save_execution_plan_state_normalizes_join_metadata(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_parallel_join_plan_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", execution_mode="parallel")

        try:
            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"):
                _context, plan_state = orchestrator.update_execution_plan(
                    project_dir=repo_dir,
                    runtime=runtime,
                    plan_state=ExecutionPlanState(
                        execution_mode="parallel",
                        default_test_command="python -m pytest",
                        steps=[
                            ExecutionStep(step_id="NODE-A", title="Frontend", owned_paths=["desktop/src"]),
                            ExecutionStep(step_id="NODE-B", title="Backend", owned_paths=["src/jakal_flow"]),
                            ExecutionStep(
                                step_id="NODE-C",
                                title="Join both branches",
                                depends_on=["NODE-A", "NODE-B"],
                                metadata={"step_kind": "join", "join_reason": "Validate the integrated application before closeout."},
                            ),
                        ],
                    ),
                )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        join_step = plan_state.steps[2]
        self.assertEqual(join_step.step_id, "ST3")
        self.assertEqual(join_step.metadata["step_kind"], "join")
        self.assertEqual(join_step.metadata["merge_from"], ["ST1", "ST2"])
        self.assertEqual(join_step.metadata["join_policy"], "all")
        self.assertEqual(join_step.metadata["join_reason"], "Validate the integrated application before closeout.")

    def test_save_execution_plan_state_allows_root_barrier_nodes(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_root_barrier_plan_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", execution_mode="parallel")

        try:
            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"):
                _context, plan_state = orchestrator.update_execution_plan(
                    project_dir=repo_dir,
                    runtime=runtime,
                    plan_state=ExecutionPlanState(
                        execution_mode="parallel",
                        default_test_command="python -m pytest",
                        steps=[
                            ExecutionStep(
                                step_id="NODE-A",
                                title="Freeze contract surface",
                                metadata={"step_kind": "barrier"},
                            ),
                            ExecutionStep(
                                step_id="NODE-B",
                                title="Implement feature slice",
                                depends_on=["NODE-A"],
                                owned_paths=["src/jakal_flow"],
                            ),
                        ],
                    ),
                )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        barrier_step = plan_state.steps[0]
        self.assertEqual(barrier_step.step_id, "ST1")
        self.assertEqual(barrier_step.depends_on, [])
        self.assertEqual(barrier_step.metadata["step_kind"], "barrier")

    def test_save_execution_plan_state_rejects_invalid_join_nodes(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_invalid_join_plan_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", execution_mode="parallel")

        try:
            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), self.assertRaises(ValueError):
                orchestrator.update_execution_plan(
                    project_dir=repo_dir,
                    runtime=runtime,
                    plan_state=ExecutionPlanState(
                        execution_mode="parallel",
                        default_test_command="python -m pytest",
                        steps=[
                            ExecutionStep(step_id="NODE-A", title="Frontend", owned_paths=["desktop/src"]),
                            ExecutionStep(
                                step_id="NODE-B",
                                title="Invalid join",
                                depends_on=["NODE-A"],
                                metadata={"step_kind": "join"},
                            ),
                        ],
                    ),
                )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

    def test_save_execution_plan_state_reports_dependency_cycle_path(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_parallel_cycle_plan_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", execution_mode="parallel")

        try:
            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), self.assertRaisesRegex(
                ValueError,
                r"Parallel execution plan contains a dependency cycle: ST1 -> ST2 -> ST1\.",
            ):
                orchestrator.update_execution_plan(
                    project_dir=repo_dir,
                    runtime=runtime,
                    plan_state=ExecutionPlanState(
                        execution_mode="parallel",
                        default_test_command="python -m pytest",
                        steps=[
                            ExecutionStep(step_id="NODE-A", title="Frontend", depends_on=["NODE-B"], owned_paths=["desktop/src"]),
                            ExecutionStep(step_id="NODE-B", title="Backend", depends_on=["NODE-A"], owned_paths=["src/jakal_flow"]),
                        ],
                    ),
                )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

    def test_run_parallel_execution_batch_persists_lineages_for_hybrid_tasks(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_hybrid_lineage_batch_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(
            model="gpt-5.4",
            effort="medium",
            test_cmd="python -m pytest",
            execution_mode="parallel",
            parallel_workers=1,
        )

        try:
            context = orchestrator.workspace.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=runtime,
            )
            context.metadata.current_safe_revision = "safe-main"
            context.loop_state.current_safe_revision = "safe-main"
            orchestrator.workspace.save_project(context)
            orchestrator.save_execution_plan_state(
                context,
                ExecutionPlanState(
                    plan_title="Hybrid Lineage Demo",
                    execution_mode="parallel",
                    default_test_command="python -m pytest",
                    steps=[
                        ExecutionStep(step_id="ST1", title="Frontend slice", owned_paths=["desktop/src"]),
                        ExecutionStep(step_id="ST2", title="Backend slice", owned_paths=["src/jakal_flow"]),
                        ExecutionStep(
                            step_id="ST3",
                            title="Join slices",
                            depends_on=["ST1", "ST2"],
                            metadata={"step_kind": "join", "merge_from": ["ST1", "ST2"], "join_policy": "all"},
                        ),
                    ],
                ),
            )
            worker_results = [
                {
                    "step_id": "ST1",
                    "status": "completed",
                    "notes": "frontend lineage ok",
                    "commit_hash": "ln1-step",
                    "changed_files": ["desktop/src/App.jsx"],
                    "pass_log": {"pass_type": "block-search-pass"},
                    "block_log": {"status": "completed"},
                    "test_summary": "frontend lineage ok",
                    "head_commit": "ln1-head",
                    "ml_report_payload": {},
                },
                {
                    "step_id": "ST2",
                    "status": "completed",
                    "notes": "backend lineage ok",
                    "commit_hash": "ln2-step",
                    "changed_files": ["src/jakal_flow/orchestrator.py"],
                    "pass_log": {"pass_type": "block-search-pass"},
                    "block_log": {"status": "completed"},
                    "test_summary": "backend lineage ok",
                    "head_commit": "ln2-head",
                    "ml_report_payload": {},
                },
            ]

            with mock.patch.object(orchestrator, "setup_local_project", return_value=context), mock.patch.object(
                orchestrator.git,
                "add_worktree",
            ) as mocked_add_worktree, mock.patch.object(
                orchestrator,
                "_parallel_worker_count",
                return_value=1,
            ), mock.patch.object(
                orchestrator,
                "_build_lineage_context",
                side_effect=[mock.Mock(name="lineage-1"), mock.Mock(name="lineage-2")],
            ), mock.patch.object(
                orchestrator,
                "_run_lineage_step_worker",
                side_effect=worker_results,
            ), mock.patch.object(
                orchestrator,
                "_push_if_ready",
                return_value=(True, "pushed"),
            ) as mocked_push:
                with mock.patch.object(
                    orchestrator,
                    "_maybe_open_pull_request",
                    return_value={"created": True, "html_url": "https://github.com/example/project/pull/1"},
                ) as mocked_pr:
                    context, plan_state, steps = orchestrator.run_parallel_execution_batch(
                        project_dir=repo_dir,
                        runtime=runtime,
                        step_ids=["ST1", "ST2"],
                    )
                    lineage_state = read_json(context.paths.lineage_state_file, default={})
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual([step.status for step in steps], ["completed", "completed"])
        self.assertEqual(context.metadata.current_safe_revision, "safe-main")
        mocked_add_worktree.assert_called()
        self.assertEqual(
            [step.metadata.get("lineage_id") for step in plan_state.steps[:2]],
            ["LN1", "LN2"],
        )
        self.assertEqual(
            {item["lineage_id"]: item["status"] for item in lineage_state["lineages"]},
            {"LN1": "active", "LN2": "active"},
        )
        self.assertEqual(
            {item["lineage_id"]: item["head_commit"] for item in lineage_state["lineages"]},
            {"LN1": "ln1-head", "LN2": "ln2-head"},
        )
        self.assertEqual(mocked_push.call_count, 2)
        self.assertEqual(mocked_pr.call_count, 2)

    def test_run_parallel_execution_batch_keeps_completed_lineages_when_one_worker_errors(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_hybrid_lineage_partial_failure_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(
            model="gpt-5.4",
            effort="medium",
            test_cmd="python -m pytest",
            execution_mode="parallel",
            parallel_workers=2,
        )

        try:
            context = orchestrator.workspace.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=runtime,
            )
            context.metadata.current_safe_revision = "safe-main"
            context.loop_state.current_safe_revision = "safe-main"
            orchestrator.workspace.save_project(context)
            orchestrator.save_execution_plan_state(
                context,
                ExecutionPlanState(
                    plan_title="Hybrid Lineage Partial Failure Demo",
                    execution_mode="parallel",
                    default_test_command="python -m pytest",
                    steps=[
                        ExecutionStep(step_id="ST1", title="Verification slice", owned_paths=["src/lit/verification.py"]),
                        ExecutionStep(step_id="ST2", title="Lineage slice", owned_paths=["src/lit/lineage.py"]),
                        ExecutionStep(
                            step_id="ST3",
                            title="Join slices",
                            depends_on=["ST1", "ST2"],
                            metadata={"step_kind": "join", "merge_from": ["ST1", "ST2"], "join_policy": "all"},
                        ),
                    ],
                ),
            )

            def fake_lineage_worker(_lineage_context, step):
                if step.step_id == "ST1":
                    return {
                        "step_id": "ST1",
                        "status": "completed",
                        "notes": "verification lineage ok",
                        "commit_hash": "ln1-step",
                        "changed_files": ["src/lit/verification.py"],
                        "pass_log": {"pass_type": "block-search-pass"},
                        "block_log": {"status": "completed"},
                        "test_summary": "verification lineage ok",
                        "head_commit": "ln1-head",
                        "ml_report_payload": {},
                    }
                raise FileNotFoundError(2, "missing lineage tool")

            with mock.patch.object(orchestrator, "setup_local_project", return_value=context), mock.patch.object(
                orchestrator.git,
                "add_worktree",
            ), mock.patch.object(
                orchestrator,
                "_parallel_worker_count",
                return_value=2,
            ), mock.patch.object(
                orchestrator,
                "_build_lineage_context",
                side_effect=[mock.Mock(name="lineage-1"), mock.Mock(name="lineage-2")],
            ), mock.patch.object(
                orchestrator,
                "_run_lineage_step_worker",
                side_effect=fake_lineage_worker,
            ), mock.patch.object(
                orchestrator,
                "_push_if_ready",
                return_value=(False, "already_up_to_date"),
            ):
                context, plan_state, steps = orchestrator.run_parallel_execution_batch(
                    project_dir=repo_dir,
                    runtime=runtime,
                    step_ids=["ST1", "ST2"],
                )
                lineage_state = read_json(context.paths.lineage_state_file, default={})
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual([step.step_id for step in steps], ["ST1", "ST2"])
        self.assertEqual([step.status for step in steps], ["completed", "failed"])
        self.assertEqual(steps[0].commit_hash, "ln1-step")
        self.assertIn("missing lineage tool", steps[1].notes)
        self.assertEqual(
            {item["lineage_id"]: item["status"] for item in lineage_state["lineages"]},
            {"LN1": "active", "LN2": "failed"},
        )
        self.assertEqual(
            {item["lineage_id"]: item["head_commit"] for item in lineage_state["lineages"]},
            {"LN1": "ln1-head", "LN2": "safe-main"},
        )

    def test_run_join_execution_step_selectively_merges_requested_lineages(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_selective_join_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(
            model="gpt-5.4",
            effort="medium",
            test_cmd="python -m pytest",
            execution_mode="parallel",
            allow_push=True,
        )

        try:
            context = orchestrator.workspace.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=runtime,
            )
            context.metadata.current_safe_revision = "safe-main"
            context.loop_state.current_safe_revision = "safe-main"
            orchestrator.workspace.save_project(context)
            orchestrator.save_execution_plan_state(
                context,
                ExecutionPlanState(
                    plan_title="Selective Join Demo",
                    execution_mode="parallel",
                    default_test_command="python -m pytest",
                    steps=[
                        ExecutionStep(step_id="ST1", title="Frontend", status="completed", metadata={"lineage_id": "LN1"}),
                        ExecutionStep(step_id="ST2", title="Backend", status="completed", metadata={"lineage_id": "LN2"}),
                        ExecutionStep(step_id="ST3", title="Docs", status="completed", metadata={"lineage_id": "LN3"}),
                        ExecutionStep(
                            step_id="ST4",
                            title="Join selected branches",
                            depends_on=["ST1", "ST2", "ST3"],
                            metadata={"step_kind": "join", "merge_from": ["ST1", "ST3"], "join_policy": "all"},
                        ),
                    ],
                ),
            )
            orchestrator._save_lineage_states(
                context,
                {
                    "LN1": LineageState(
                        lineage_id="LN1",
                        branch_name="jakal-flow-lineage-ln1",
                        worktree_dir=temp_root / "ln1" / "repo",
                        project_root=temp_root / "ln1",
                        created_at="2026-03-27T00:00:00+00:00",
                        updated_at="2026-03-27T00:00:00+00:00",
                        head_commit="ln1-head",
                        safe_revision="ln1-head",
                    ),
                    "LN2": LineageState(
                        lineage_id="LN2",
                        branch_name="jakal-flow-lineage-ln2",
                        worktree_dir=temp_root / "ln2" / "repo",
                        project_root=temp_root / "ln2",
                        created_at="2026-03-27T00:00:00+00:00",
                        updated_at="2026-03-27T00:00:00+00:00",
                        head_commit="ln2-head",
                        safe_revision="ln2-head",
                    ),
                    "LN3": LineageState(
                        lineage_id="LN3",
                        branch_name="jakal-flow-lineage-ln3",
                        worktree_dir=temp_root / "ln3" / "repo",
                        project_root=temp_root / "ln3",
                        created_at="2026-03-27T00:00:00+00:00",
                        updated_at="2026-03-27T00:00:00+00:00",
                        head_commit="ln3-head",
                        safe_revision="ln3-head",
                    ),
                },
            )

            with mock.patch.object(orchestrator.git, "add_worktree"), mock.patch.object(
                orchestrator.git,
                "current_revision",
                return_value="main-integrated",
            ), mock.patch.object(
                orchestrator,
                "_cleanup_lineage_worktree",
            ) as mocked_cleanup, mock.patch.object(
                orchestrator,
                "_cleanup_integration_worktree",
            ) as mocked_cleanup_integration:
                integration_info = orchestrator._build_integration_context(
                    context,
                    runtime,
                    ExecutionStep(step_id="ST4", title="Join selected branches"),
                    "safe-main",
                    "test-integration",
                )
                integration_context = integration_info["integration_context"]

                def fake_run_saved_execution_step_with_context(*args, **kwargs):
                    current = orchestrator.load_execution_plan_state(integration_context)
                    join_step = next(step for step in current.steps if step.step_id == "ST4")
                    join_step.status = "completed"
                    join_step.completed_at = "2026-03-27T01:00:00+00:00"
                    join_step.notes = "Integrated selected branches."
                    join_step.commit_hash = None
                    saved = orchestrator.save_execution_plan_state(integration_context, current)
                    integration_context.metadata.current_status = orchestrator._status_from_plan_state(saved)
                    orchestrator.workspace.save_project(integration_context)
                    return integration_context, saved, next(step for step in saved.steps if step.step_id == "ST4")

                with mock.patch.object(orchestrator, "setup_local_project", return_value=context), mock.patch.object(
                    orchestrator,
                    "_build_integration_context",
                    return_value=integration_info,
                ), mock.patch.object(
                    orchestrator.git,
                    "try_cherry_pick",
                    return_value=CommandResult(command=["git", "cherry-pick"], returncode=0, stdout="", stderr=""),
                ) as mocked_cherry_pick, mock.patch.object(
                    orchestrator,
                    "_run_saved_execution_step_with_context",
                    side_effect=fake_run_saved_execution_step_with_context,
                ), mock.patch.object(
                    orchestrator.git,
                    "merge_ff_only",
                ) as mocked_ff_merge, mock.patch.object(
                    orchestrator,
                    "_push_if_ready",
                    return_value=(True, "pushed"),
                ) as mocked_push_if_ready:
                    project, saved, step = orchestrator.run_join_execution_step(
                        project_dir=repo_dir,
                        runtime=runtime,
                        step_id="ST4",
                    )
                    lineage_state = read_json(project.paths.lineage_state_file, default={})
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(step.status, "completed")
        self.assertEqual(step.commit_hash, "main-integrated")
        self.assertEqual(project.metadata.current_safe_revision, "main-integrated")
        self.assertEqual([call.args[1] for call in mocked_cherry_pick.call_args_list], ["ln1-head", "ln3-head"])
        mocked_ff_merge.assert_called_once()
        mocked_push_if_ready.assert_called_once_with(
            project,
            project.paths.repo_dir,
            project.metadata.branch,
            commit_hash="main-integrated",
        )
        self.assertEqual(mocked_cleanup.call_count, 2)
        mocked_cleanup_integration.assert_called_once()
        self.assertEqual(
            {item["lineage_id"]: item["status"] for item in lineage_state["lineages"]},
            {"LN1": "merged", "LN2": "active", "LN3": "merged"},
        )
        self.assertEqual(
            {item["lineage_id"]: item["merged_by_step_id"] for item in lineage_state["lineages"]},
            {"LN1": "ST4", "LN2": None, "LN3": "ST4"},
        )

    def test_run_join_execution_step_rolls_back_main_when_selective_merge_fails(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_join_merge_failure_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(
            model="gpt-5.4",
            effort="medium",
            test_cmd="python -m pytest",
            execution_mode="parallel",
            regression_limit=1,
        )

        try:
            context = orchestrator.workspace.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=runtime,
            )
            context.metadata.current_safe_revision = "safe-main"
            context.loop_state.current_safe_revision = "safe-main"
            orchestrator.workspace.save_project(context)
            orchestrator.save_execution_plan_state(
                context,
                ExecutionPlanState(
                    plan_title="Join Failure Demo",
                    execution_mode="parallel",
                    default_test_command="python -m pytest",
                    steps=[
                        ExecutionStep(step_id="ST1", title="Frontend", status="completed", metadata={"lineage_id": "LN1"}),
                        ExecutionStep(step_id="ST2", title="Backend", status="completed", metadata={"lineage_id": "LN2"}),
                        ExecutionStep(
                            step_id="ST3",
                            title="Join branches",
                            depends_on=["ST1", "ST2"],
                            metadata={"step_kind": "join", "merge_from": ["ST1", "ST2"], "join_policy": "all"},
                        ),
                    ],
                ),
            )
            orchestrator._save_lineage_states(
                context,
                {
                    "LN1": LineageState(
                        lineage_id="LN1",
                        branch_name="jakal-flow-lineage-ln1",
                        worktree_dir=temp_root / "ln1" / "repo",
                        project_root=temp_root / "ln1",
                        created_at="2026-03-27T00:00:00+00:00",
                        updated_at="2026-03-27T00:00:00+00:00",
                        head_commit="ln1-head",
                        safe_revision="ln1-head",
                    ),
                    "LN2": LineageState(
                        lineage_id="LN2",
                        branch_name="jakal-flow-lineage-ln2",
                        worktree_dir=temp_root / "ln2" / "repo",
                        project_root=temp_root / "ln2",
                        created_at="2026-03-27T00:00:00+00:00",
                        updated_at="2026-03-27T00:00:00+00:00",
                        head_commit="ln2-head",
                        safe_revision="ln2-head",
                    ),
                },
            )

            with mock.patch.object(orchestrator.git, "add_worktree"), mock.patch.object(
                orchestrator,
                "_cleanup_integration_worktree",
            ) as mocked_cleanup_integration:
                integration_info = orchestrator._build_integration_context(
                    context,
                    runtime,
                    ExecutionStep(step_id="ST3", title="Join branches"),
                    "safe-main",
                    "test-integration",
                )
                integration_context = integration_info["integration_context"]
                with mock.patch.object(orchestrator, "setup_local_project", return_value=context), mock.patch.object(
                    orchestrator,
                    "_build_integration_context",
                    return_value=integration_info,
                ), mock.patch.object(
                    orchestrator.git,
                    "try_cherry_pick",
                    return_value=CommandResult(command=["git", "cherry-pick"], returncode=1, stdout="", stderr="merge conflict"),
                ), mock.patch.object(
                    orchestrator.git,
                    "conflicted_files",
                    return_value=["src/conflict.py"],
                ), mock.patch.object(
                    orchestrator.git,
                    "cherry_pick_in_progress",
                    return_value=False,
                ), mock.patch.object(
                    orchestrator.git,
                    "abort_cherry_pick",
                ) as mocked_abort, mock.patch.object(
                    orchestrator.git,
                    "hard_reset",
                ) as mocked_reset, mock.patch.object(
                    orchestrator,
                    "_run_saved_execution_step_with_context",
                ) as mocked_join_step:
                    project, saved, step = orchestrator.run_join_execution_step(
                        project_dir=repo_dir,
                        runtime=runtime,
                        step_id="ST3",
                    )
                    lineage_state = read_json(project.paths.lineage_state_file, default={})
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(step.status, "failed")
        self.assertIn("src/conflict.py", step.notes)
        mocked_abort.assert_called_once_with(integration_context.paths.repo_dir)
        mocked_reset.assert_any_call(integration_context.paths.repo_dir, "safe-main")
        mocked_reset.assert_any_call(repo_dir, "safe-main")
        self.assertEqual(mocked_reset.call_count, 2)
        mocked_join_step.assert_not_called()
        mocked_cleanup_integration.assert_called_once()
        self.assertEqual(project.metadata.current_status, "failed")
        self.assertEqual(
            {item["lineage_id"]: item["status"] for item in lineage_state["lineages"]},
            {"LN1": "active", "LN2": "active"},
        )

    def test_run_join_execution_step_skips_empty_cherry_pick_results(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_join_empty_cherry_pick_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(
            model="gpt-5.4",
            effort="medium",
            test_cmd="python -m pytest",
            execution_mode="parallel",
            allow_push=False,
        )

        try:
            context = orchestrator.workspace.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=runtime,
            )
            context.metadata.current_safe_revision = "safe-main"
            context.loop_state.current_safe_revision = "safe-main"
            orchestrator.workspace.save_project(context)
            orchestrator.save_execution_plan_state(
                context,
                ExecutionPlanState(
                    plan_title="Join Empty Cherry Pick Demo",
                    execution_mode="parallel",
                    default_test_command="python -m pytest",
                    steps=[
                        ExecutionStep(step_id="ST1", title="Artifact branch", status="completed", metadata={"lineage_id": "LN1"}),
                        ExecutionStep(step_id="ST2", title="Reference branch", status="completed", metadata={"lineage_id": "LN2"}),
                        ExecutionStep(
                            step_id="ST3",
                            title="Join artifacts",
                            depends_on=["ST1", "ST2"],
                            metadata={"step_kind": "join", "merge_from": ["ST1", "ST2"], "join_policy": "all"},
                        ),
                    ],
                ),
            )
            orchestrator._save_lineage_states(
                context,
                {
                    "LN1": LineageState(
                        lineage_id="LN1",
                        branch_name="jakal-flow-lineage-ln1",
                        worktree_dir=temp_root / "ln1" / "repo",
                        project_root=temp_root / "ln1",
                        created_at="2026-03-27T00:00:00+00:00",
                        updated_at="2026-03-27T00:00:00+00:00",
                        head_commit="ln1-head",
                        safe_revision="ln1-head",
                    ),
                    "LN2": LineageState(
                        lineage_id="LN2",
                        branch_name="jakal-flow-lineage-ln2",
                        worktree_dir=temp_root / "ln2" / "repo",
                        project_root=temp_root / "ln2",
                        created_at="2026-03-27T00:00:00+00:00",
                        updated_at="2026-03-27T00:00:00+00:00",
                        head_commit="ln2-head",
                        safe_revision="ln2-head",
                    ),
                },
            )

            with mock.patch.object(orchestrator.git, "add_worktree"), mock.patch.object(
                orchestrator.git,
                "current_revision",
                return_value="main-integrated",
            ), mock.patch.object(
                orchestrator,
                "_cleanup_lineage_worktree",
            ) as mocked_cleanup, mock.patch.object(
                orchestrator,
                "_cleanup_integration_worktree",
            ) as mocked_cleanup_integration:

                def fake_run_saved_execution_step_with_context(*args, **kwargs):
                    integration_context = kwargs["context"]
                    current = orchestrator.load_execution_plan_state(integration_context)
                    join_step = next(step for step in current.steps if step.step_id == "ST3")
                    join_step.status = "completed"
                    join_step.completed_at = "2026-03-27T01:00:00+00:00"
                    join_step.notes = "Integrated the already-applied lineage."
                    saved = orchestrator.save_execution_plan_state(integration_context, current)
                    return integration_context, saved, next(step for step in saved.steps if step.step_id == "ST3")

                with mock.patch.object(orchestrator, "setup_local_project", return_value=context), mock.patch.object(
                    orchestrator.git,
                    "try_cherry_pick",
                    side_effect=[
                        CommandResult(
                            command=["git", "cherry-pick"],
                            returncode=1,
                            stdout="",
                            stderr="The previous cherry-pick is now empty, possibly due to conflict resolution.",
                        ),
                        CommandResult(command=["git", "cherry-pick"], returncode=0, stdout="", stderr=""),
                    ],
                ), mock.patch.object(
                    orchestrator.git,
                    "cherry_pick_in_progress",
                    return_value=True,
                ), mock.patch.object(
                    orchestrator.git,
                    "skip_cherry_pick",
                ) as mocked_skip, mock.patch.object(
                    orchestrator,
                    "_run_saved_execution_step_with_context",
                    side_effect=fake_run_saved_execution_step_with_context,
                ), mock.patch.object(
                    orchestrator.git,
                    "merge_ff_only",
                ) as mocked_ff_merge, mock.patch.object(
                    orchestrator,
                    "_push_if_ready",
                    return_value=(False, "push_disabled"),
                ):
                    project, saved, step = orchestrator.run_join_execution_step(
                        project_dir=repo_dir,
                        runtime=runtime,
                        step_id="ST3",
                    )
                    lineage_state = read_json(project.paths.lineage_state_file, default={})
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(step.status, "completed")
        self.assertEqual(step.commit_hash, "main-integrated")
        self.assertEqual(project.metadata.current_status, "plan_completed")
        mocked_skip.assert_called_once()
        mocked_ff_merge.assert_called_once()
        self.assertEqual(mocked_cleanup.call_count, 2)
        mocked_cleanup_integration.assert_called_once()
        self.assertEqual(
            {item["lineage_id"]: item["status"] for item in lineage_state["lineages"]},
            {"LN1": "merged", "LN2": "merged"},
        )

    def test_run_join_execution_step_retries_failed_merges_and_persists_retry_status(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_join_retry_status_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(
            model="gpt-5.4",
            effort="medium",
            test_cmd="python -m pytest",
            execution_mode="parallel",
            regression_limit=2,
            allow_push=False,
        )
        observed_statuses: list[str] = []

        try:
            context = orchestrator.workspace.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=runtime,
            )
            context.metadata.current_safe_revision = "safe-main"
            context.loop_state.current_safe_revision = "safe-main"
            orchestrator.workspace.save_project(context)
            orchestrator.save_execution_plan_state(
                context,
                ExecutionPlanState(
                    plan_title="Join Retry Demo",
                    execution_mode="parallel",
                    default_test_command="python -m pytest",
                    steps=[
                        ExecutionStep(step_id="ST1", title="Verification branch", status="completed", metadata={"lineage_id": "LN1"}),
                        ExecutionStep(step_id="ST2", title="Reference branch", status="completed", metadata={"lineage_id": "LN2"}),
                        ExecutionStep(
                            step_id="ST3",
                            title="Join verification work",
                            depends_on=["ST1", "ST2"],
                            metadata={"step_kind": "join", "merge_from": ["ST1", "ST2"], "join_policy": "all"},
                        ),
                    ],
                ),
            )
            orchestrator._save_lineage_states(
                context,
                {
                    "LN1": LineageState(
                        lineage_id="LN1",
                        branch_name="jakal-flow-lineage-ln1",
                        worktree_dir=temp_root / "ln1" / "repo",
                        project_root=temp_root / "ln1",
                        created_at="2026-03-27T00:00:00+00:00",
                        updated_at="2026-03-27T00:00:00+00:00",
                        head_commit="ln1-head",
                        safe_revision="ln1-head",
                    ),
                    "LN2": LineageState(
                        lineage_id="LN2",
                        branch_name="jakal-flow-lineage-ln2",
                        worktree_dir=temp_root / "ln2" / "repo",
                        project_root=temp_root / "ln2",
                        created_at="2026-03-27T00:00:00+00:00",
                        updated_at="2026-03-27T00:00:00+00:00",
                        head_commit="ln2-head",
                        safe_revision="ln2-head",
                    ),
                },
            )

            def fake_try_cherry_pick(repo_path: Path, revision: str) -> CommandResult:
                observed_statuses.append(read_json(context.paths.metadata_file, default={}).get("current_status", ""))
                if len(observed_statuses) == 1:
                    return CommandResult(command=["git", "cherry-pick"], returncode=1, stdout="", stderr="merge conflict")
                return CommandResult(command=["git", "cherry-pick"], returncode=0, stdout="", stderr="")

            def fake_run_saved_execution_step_with_context(*args, **kwargs):
                integration_context = kwargs["context"]
                current = orchestrator.load_execution_plan_state(integration_context)
                join_step = next(step for step in current.steps if step.step_id == "ST3")
                join_step.status = "completed"
                join_step.completed_at = "2026-03-27T01:00:00+00:00"
                join_step.notes = "Integrated verification work after retry."
                saved = orchestrator.save_execution_plan_state(integration_context, current)
                return integration_context, saved, next(step for step in saved.steps if step.step_id == "ST3")

            with mock.patch.object(orchestrator.git, "add_worktree"), mock.patch.object(
                orchestrator.git,
                "current_revision",
                return_value="main-integrated",
            ), mock.patch.object(
                orchestrator,
                "_cleanup_lineage_worktree",
            ) as mocked_cleanup, mock.patch.object(
                orchestrator,
                "_cleanup_integration_worktree",
            ) as mocked_cleanup_integration, mock.patch.object(
                orchestrator, "setup_local_project", return_value=context
            ), mock.patch.object(
                orchestrator.git,
                "try_cherry_pick",
                side_effect=fake_try_cherry_pick,
            ) as mocked_cherry_pick, mock.patch.object(
                orchestrator.git,
                "conflicted_files",
                return_value=["src/conflict.py"],
            ), mock.patch.object(
                orchestrator.git,
                "cherry_pick_in_progress",
                return_value=False,
            ), mock.patch.object(
                orchestrator.git,
                "abort_cherry_pick",
            ) as mocked_abort, mock.patch.object(
                orchestrator.git,
                "hard_reset",
            ) as mocked_reset, mock.patch.object(
                orchestrator,
                "_run_saved_execution_step_with_context",
                side_effect=fake_run_saved_execution_step_with_context,
            ), mock.patch.object(
                orchestrator.git,
                "merge_ff_only",
            ) as mocked_ff_merge, mock.patch.object(
                orchestrator,
                "_push_if_ready",
                return_value=(False, "push_disabled"),
            ):
                project, saved, step = orchestrator.run_join_execution_step(
                    project_dir=repo_dir,
                    runtime=runtime,
                    step_id="ST3",
                )
                lineage_state = read_json(project.paths.lineage_state_file, default={})
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(observed_statuses[0], "running:st3")
        self.assertTrue(observed_statuses[1:])
        self.assertTrue(all(status == "running:retry-st3" for status in observed_statuses[1:]))
        self.assertEqual(mocked_cherry_pick.call_count, 3)
        self.assertEqual(step.status, "completed")
        self.assertEqual(step.commit_hash, "main-integrated")
        self.assertEqual(project.metadata.current_status, "plan_completed")
        mocked_abort.assert_called_once()
        self.assertGreaterEqual(mocked_reset.call_count, 2)
        mocked_ff_merge.assert_called_once()
        self.assertEqual(mocked_cleanup.call_count, 2)
        self.assertEqual(mocked_cleanup_integration.call_count, 2)
        self.assertEqual(
            {item["lineage_id"]: item["status"] for item in lineage_state["lineages"]},
            {"LN1": "merged", "LN2": "merged"},
        )

    def test_save_execution_plan_state_keeps_running_checkpoint_status_in_sync(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_running_checkpoint_sync_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", execution_mode="parallel")

        try:
            context = orchestrator.workspace.initialize_local_project(project_dir=repo_dir, branch="main", runtime=runtime)
            saved = orchestrator.save_execution_plan_state(
                context,
                ExecutionPlanState(
                    execution_mode="parallel",
                    default_test_command="python -m pytest",
                    steps=[
                        ExecutionStep(step_id="custom-1", title="Active node", status="running"),
                        ExecutionStep(step_id="custom-2", title="Queued node", status="pending"),
                    ],
                ),
            )
            checkpoint_state = read_json(context.paths.checkpoint_state_file, default={})
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(saved.steps[0].status, "running")
        self.assertEqual(checkpoint_state["checkpoints"][0]["status"], "running")
        self.assertEqual(checkpoint_state["checkpoints"][1]["status"], "pending")

    def test_run_saved_execution_step_uses_step_reasoning_effort(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_step_reasoning_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="low", test_cmd="python -m pytest")
        observed_efforts: list[str] = []

        def fake_run_single_block(*args, **kwargs) -> None:
            context = kwargs["context"]
            observed_efforts.append(context.runtime.effort)
            append_jsonl(
                context.paths.block_log_file,
                {
                    "block_index": 0,
                    "status": "completed",
                    "commit_hashes": ["abc123"],
                    "test_summary": "step passed",
                },
            )

        try:
            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch.object(
                orchestrator,
                "_run_single_block",
                side_effect=fake_run_single_block,
            ):
                orchestrator.update_execution_plan(
                    project_dir=repo_dir,
                    runtime=runtime,
                    plan_state=ExecutionPlanState(
                        plan_title="Reasoning Demo",
                        default_test_command="python -m pytest",
                        steps=[
                            ExecutionStep(
                                step_id="custom-1",
                                title="Hard checkpoint",
                                codex_description="Use deeper reasoning for this step.",
                                test_command="python -m pytest",
                                success_criteria="The step completes successfully.",
                                reasoning_effort="xhigh",
                            )
                        ],
                    ),
                )
                _context, _plan_state, step = orchestrator.run_saved_execution_step(
                    project_dir=repo_dir,
                    runtime=runtime,
                    step_id="ST1",
                )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(observed_efforts, ["xhigh"])
        self.assertEqual(step.status, "completed")
        self.assertEqual(step.reasoning_effort, "xhigh")
        self.assertEqual(step.commit_hash, "abc123")

    def test_collect_ml_step_report_updates_ml_state_and_outputs(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_ml_report_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(
            model="gpt-5.4",
            effort="high",
            test_cmd="python -m pytest",
            workflow_mode="ml",
            execution_mode="parallel",
            ml_max_cycles=4,
        )

        try:
            context = orchestrator.workspace.initialize_local_project(project_dir=repo_dir, branch="main", runtime=runtime)
            context.metadata.current_safe_revision = "safe-revision"
            context.loop_state.current_safe_revision = "safe-revision"
            orchestrator.workspace.save_project(context)
            plan_state = orchestrator.save_execution_plan_state(
                context,
                ExecutionPlanState(
                    plan_title="ML Demo",
                    project_prompt="Improve validation F1 with disciplined ML experiments.",
                    summary="Run one reproducible ML experiment.",
                    workflow_mode="ml",
                    execution_mode="parallel",
                    default_test_command="python -m pytest",
                    steps=[
                        ExecutionStep(
                            step_id="EXP-A",
                            title="Train a baseline classifier",
                            test_command="python -m pytest",
                            status="completed",
                            notes="validation f1 improved",
                            metadata={
                                "experiment_id": "EXP-BASELINE",
                                "experiment_kind": "ml",
                                "primary_metric": "f1",
                                "feature_spec": "tfidf + stats",
                                "model_spec": "lightgbm",
                                "resource_budget": "1 gpu-hour",
                            },
                        )
                    ],
                ),
            )
            orchestrator._initialize_ml_mode_state(context, plan_state, plan_state.project_prompt, cycle_index=1)
            write_json(
                context.paths.ml_step_report_file,
                {
                    "experiment_id": "EXP-BASELINE",
                    "experiment_kind": "ml",
                    "primary_metric": "f1",
                    "metric_direction": "maximize",
                    "metric_value": 0.913,
                    "feature_spec": "tfidf + stats",
                    "model_spec": "lightgbm",
                    "resource_budget": "1 gpu-hour",
                    "validation_summary": "Best validation f1 reached 0.913",
                    "notes": "No leakage detected during split audit.",
                },
            )

            record = orchestrator._collect_ml_step_report(context, plan_state.steps[0])
            ml_state = read_json(context.paths.ml_mode_state_file)
            report_text = context.paths.ml_experiment_report_file.read_text(encoding="utf-8")
            svg_text = context.paths.ml_experiment_results_svg_file.read_text(encoding="utf-8")
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertIsNotNone(record)
        self.assertEqual(record.experiment_id, "EXP-BASELINE")
        self.assertAlmostEqual(record.metric_value or 0.0, 0.913, places=3)
        self.assertEqual(ml_state["best_experiment_id"], "EXP-BASELINE")
        self.assertEqual(ml_state["best_metric_name"], "f1")
        self.assertIn("EXP-BASELINE", report_text)
        self.assertIn("0.913", report_text)
        self.assertIn("<svg", svg_text)

    def test_run_saved_execution_step_retries_rolled_back_attempts_until_success(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_step_retry_success_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", test_cmd="python -m pytest", regression_limit=3)
        attempt_indexes: list[int] = []
        suppression_flags: list[bool] = []

        def fake_run_single_block(*args, **kwargs) -> None:
            context = kwargs["context"]
            attempt_index = len(attempt_indexes) + 1
            attempt_indexes.append(attempt_index)
            suppression_flags.append(bool(kwargs.get("suppress_failure_reporting")))
            append_jsonl(
                context.paths.block_log_file,
                {
                    "block_index": attempt_index,
                    "status": "rolled_back" if attempt_index == 1 else "completed",
                    "commit_hashes": [] if attempt_index == 1 else ["retry-success-commit"],
                    "test_summary": "rolled back on the first attempt" if attempt_index == 1 else "step passed on retry",
                },
            )

        try:
            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch.object(
                orchestrator,
                "_run_single_block",
                side_effect=fake_run_single_block,
            ):
                orchestrator.update_execution_plan(
                    project_dir=repo_dir,
                    runtime=runtime,
                    plan_state=ExecutionPlanState(
                        plan_title="Retry Demo",
                        default_test_command="python -m pytest",
                        steps=[
                            ExecutionStep(
                                step_id="custom-1",
                                title="Retryable checkpoint",
                                codex_description="Retry after a rollback before giving up.",
                                test_command="python -m pytest",
                                success_criteria="The step completes after retrying.",
                            )
                        ],
                    ),
                )
                context, _plan_state, step = orchestrator.run_saved_execution_step(
                    project_dir=repo_dir,
                    runtime=runtime,
                    step_id="ST1",
                )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(attempt_indexes, [1, 2])
        self.assertEqual(suppression_flags, [True, True])
        self.assertEqual(step.status, "completed")
        self.assertEqual(step.commit_hash, "retry-success-commit")
        self.assertEqual(step.notes, "step passed on retry")
        self.assertEqual(context.metadata.current_status, "plan_completed")

    def test_run_saved_execution_step_marks_project_running_before_attempts_begin(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_step_running_status_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", test_cmd="python -m pytest")
        observed_statuses: list[str] = []

        def fake_run_single_block(*args, **kwargs) -> None:
            context = kwargs["context"]
            observed_statuses.append(context.metadata.current_status)
            append_jsonl(
                context.paths.block_log_file,
                {
                    "block_index": 1,
                    "status": "completed",
                    "commit_hashes": ["running-status-commit"],
                    "test_summary": "step passed",
                },
            )

        try:
            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch.object(
                orchestrator,
                "_run_single_block",
                side_effect=fake_run_single_block,
            ):
                orchestrator.update_execution_plan(
                    project_dir=repo_dir,
                    runtime=runtime,
                    plan_state=ExecutionPlanState(
                        plan_title="Running Status Demo",
                        default_test_command="python -m pytest",
                        steps=[ExecutionStep(step_id="custom-1", title="Start running", test_command="python -m pytest")],
                    ),
                )
                context, _plan_state, step = orchestrator.run_saved_execution_step(
                    project_dir=repo_dir,
                    runtime=runtime,
                    step_id="ST1",
                )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(observed_statuses, ["running:st1"])
        self.assertEqual(step.status, "completed")
        self.assertEqual(context.metadata.current_status, "plan_completed")

    def test_run_saved_execution_step_pauses_when_immediate_stop_is_requested(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_step_immediate_stop_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", test_cmd="python -m pytest")

        def fake_run_single_block(*args, **kwargs) -> None:
            raise ImmediateStopRequested("Immediate stop requested while running Codex demo-pass.")

        try:
            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch.object(
                orchestrator,
                "_run_single_block",
                side_effect=fake_run_single_block,
            ), mock.patch.object(
                orchestrator.git,
                "current_revision",
                return_value="safe-revision",
            ), mock.patch.object(
                orchestrator.git,
                "hard_reset",
            ) as mocked_hard_reset:
                orchestrator.update_execution_plan(
                    project_dir=repo_dir,
                    runtime=runtime,
                    plan_state=ExecutionPlanState(
                        plan_title="Immediate Stop Demo",
                        default_test_command="python -m pytest",
                        steps=[ExecutionStep(step_id="custom-1", title="Stop now", test_command="python -m pytest")],
                    ),
                )
                context, _plan_state, step = orchestrator.run_saved_execution_step(
                    project_dir=repo_dir,
                    runtime=runtime,
                    step_id="ST1",
                )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        mocked_hard_reset.assert_called_once_with(repo_dir, "safe-revision")
        self.assertEqual(step.status, "paused")
        self.assertEqual(step.commit_hash, None)
        self.assertIn("Immediate stop requested", step.notes)
        self.assertEqual(context.metadata.current_status, "plan_ready")

    def test_run_saved_execution_step_marks_failed_after_retry_limit(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_step_retry_failure_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", test_cmd="python -m pytest", regression_limit=2)
        attempt_indexes: list[int] = []
        suppression_flags: list[bool] = []

        def fake_run_single_block(*args, **kwargs) -> None:
            context = kwargs["context"]
            attempt_index = len(attempt_indexes) + 1
            attempt_indexes.append(attempt_index)
            suppression_flags.append(bool(kwargs.get("suppress_failure_reporting")))
            append_jsonl(
                context.paths.block_log_file,
                {
                    "block_index": attempt_index,
                    "status": "rolled_back",
                    "commit_hashes": [],
                    "test_summary": f"attempt {attempt_index} failed",
                },
            )

        try:
            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch.object(
                orchestrator,
                "_run_single_block",
                side_effect=fake_run_single_block,
            ):
                orchestrator.update_execution_plan(
                    project_dir=repo_dir,
                    runtime=runtime,
                    plan_state=ExecutionPlanState(
                        plan_title="Retry Failure Demo",
                        default_test_command="python -m pytest",
                        steps=[
                            ExecutionStep(
                                step_id="custom-1",
                                title="Eventually failing checkpoint",
                                codex_description="Stop after the retry budget is exhausted.",
                                test_command="python -m pytest",
                                success_criteria="The step eventually succeeds.",
                            )
                        ],
                    ),
                )
                context, _plan_state, step = orchestrator.run_saved_execution_step(
                    project_dir=repo_dir,
                    runtime=runtime,
                    step_id="ST1",
                )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(attempt_indexes, [1, 2])
        self.assertEqual(suppression_flags, [True, False])
        self.assertEqual(step.status, "failed")
        self.assertEqual(step.notes, "attempt 2 failed")
        self.assertEqual(context.metadata.current_status, "failed")

    def test_execute_verified_repo_pass_keeps_failure_reason_in_notes(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_verified_repo_pass_failure_reason_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", test_cmd="python -m pytest")

        try:
            context = orchestrator.workspace.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=runtime,
            )
            reporter = Reporter(context)
            runner = mock.Mock()
            runner.run_pass.return_value = CodexRunResult(
                pass_type="block-search-pass",
                prompt_file=context.paths.logs_dir / "initial.prompt.md",
                output_file=context.paths.logs_dir / "initial.last_message.txt",
                event_file=context.paths.logs_dir / "initial.events.jsonl",
                returncode=0,
                search_enabled=False,
                changed_files=[],
                usage={"input_tokens": 10},
                last_message="initial implementation pass",
            )

            block_dir = context.paths.logs_dir / "block_0001"
            block_dir.mkdir(parents=True, exist_ok=True)
            failing_stdout = block_dir / "block-search-pass.test.stdout.log"
            failing_stderr = block_dir / "block-search-pass.test.stderr.log"
            failing_stdout.write_text("", encoding="utf-8")
            failing_stderr.write_text("AssertionError: experiment2 failed\n", encoding="utf-8")
            failing_test = TestRunResult(
                command="python -m pytest",
                returncode=1,
                stdout_file=failing_stdout,
                stderr_file=failing_stderr,
                summary="python -m pytest exited with 1: AssertionError: experiment2 failed",
                failure_reason="AssertionError: experiment2 failed",
            )

            with mock.patch.object(orchestrator, "_run_test_command", return_value=failing_test), mock.patch.object(
                orchestrator.git,
                "changed_files",
                return_value=["src/app.py"],
            ), mock.patch.object(orchestrator.git, "hard_reset") as mocked_reset:
                pass_result = orchestrator._execute_verified_repo_pass(
                    context=context,
                    runner=runner,
                    reporter=reporter,
                    prompt="Implement the change safely.",
                    pass_type="block-search-pass",
                    block_index=1,
                    task_name="Experiment 2",
                    safe_revision="safe-revision",
                )

            logged_test = read_last_jsonl(context.paths.logs_dir / "test_runs.jsonl")
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertFalse(pass_result["success"])
        self.assertIn("AssertionError: experiment2 failed", str(pass_result["notes"]))
        self.assertIn("rolled back", str(pass_result["notes"]))
        self.assertIsInstance(pass_result["test_result"], TestRunResult)
        self.assertIsNotNone(logged_test)
        self.assertEqual(logged_test["failure_reason"], "AssertionError: experiment2 failed")
        mocked_reset.assert_called_once_with(repo_dir, "safe-revision")

    def test_execute_pass_invokes_debugger_with_failure_logs_and_recovers(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_step_debugger_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", test_cmd="python -m pytest")
        debugger_prompt_text = ""
        pass_entries: list[dict[str, object]] = []

        try:
            context = orchestrator.workspace.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=runtime,
            )
            context.metadata.current_safe_revision = "safe-revision"
            context.loop_state.current_safe_revision = "safe-revision"
            orchestrator.workspace.save_project(context)
            saved = orchestrator.save_execution_plan_state(
                context,
                ExecutionPlanState(
                    plan_title="Debugger Demo",
                    default_test_command="python -m pytest",
                    steps=[
                        ExecutionStep(
                            step_id="custom-1",
                            title="Implement fix",
                            display_description="Repair the broken behavior.",
                            codex_description="Update the implementation and keep tests passing.",
                            test_command="python -m pytest",
                            success_criteria="The verification command passes.",
                        )
                    ],
                ),
            )

            execution_step = saved.steps[0]
            candidate = CandidateTask(
                candidate_id=execution_step.step_id,
                title=execution_step.title,
                rationale="Fix the implementation without widening scope.",
                plan_refs=[execution_step.step_id],
                score=1.0,
            )
            reporter = Reporter(context)
            runner = mock.Mock()
            observed_statuses: list[str] = []
            run_results = [
                CodexRunResult(
                    pass_type="block-search-pass",
                    prompt_file=context.paths.logs_dir / "initial.prompt.md",
                    output_file=context.paths.logs_dir / "initial.last_message.txt",
                    event_file=context.paths.logs_dir / "initial.events.jsonl",
                    returncode=0,
                    search_enabled=True,
                    changed_files=[],
                    usage={"input_tokens": 10},
                    last_message="initial implementation pass",
                ),
                CodexRunResult(
                    pass_type="block-search-debug",
                    prompt_file=context.paths.logs_dir / "debug.prompt.md",
                    output_file=context.paths.logs_dir / "debug.last_message.txt",
                    event_file=context.paths.logs_dir / "debug.events.jsonl",
                    returncode=0,
                    search_enabled=False,
                    changed_files=[],
                    usage={"input_tokens": 8},
                    last_message="debugger recovery pass",
                ),
            ]

            def fake_run_pass(**kwargs):
                observed_statuses.append(context.metadata.current_status)
                return run_results.pop(0)

            runner.run_pass.side_effect = fake_run_pass

            block_dir = context.paths.logs_dir / "block_0001"
            block_dir.mkdir(parents=True, exist_ok=True)
            failing_stdout = block_dir / "block-search-pass.test.stdout.log"
            failing_stderr = block_dir / "block-search-pass.test.stderr.log"
            failing_stdout.write_text("AssertionError: expected value\n", encoding="utf-8")
            failing_stderr.write_text("Traceback: test failure details\n", encoding="utf-8")
            recovered_stdout = block_dir / "block-search-debug.test.stdout.log"
            recovered_stderr = block_dir / "block-search-debug.test.stderr.log"
            recovered_stdout.write_text("all green\n", encoding="utf-8")
            recovered_stderr.write_text("", encoding="utf-8")
            failing_test = TestRunResult(
                command="python -m pytest",
                returncode=1,
                stdout_file=failing_stdout,
                stderr_file=failing_stderr,
                summary="python -m pytest exited with 1",
            )
            recovered_test = TestRunResult(
                command="python -m pytest",
                returncode=0,
                stdout_file=recovered_stdout,
                stderr_file=recovered_stderr,
                summary="python -m pytest exited with 0",
            )

            with mock.patch.object(orchestrator, "_run_test_command", side_effect=[failing_test, recovered_test]), mock.patch.object(
                orchestrator.git,
                "changed_files",
                side_effect=[["src/app.py"], ["src/app.py", "src/fix.py"]],
            ), mock.patch.object(orchestrator.git, "has_changes", return_value=True), mock.patch.object(
                orchestrator.git,
                "commit_all",
                return_value="debug-commit",
            ) as mocked_commit, mock.patch.object(orchestrator.git, "hard_reset") as mocked_reset:
                run_result, test_result, commit_hash = orchestrator._execute_pass(
                    context=context,
                    runner=runner,
                    reporter=reporter,
                    block_index=1,
                    candidate=candidate,
                    pass_name="block-search-pass",
                    safe_revision="safe-revision",
                    search_enabled=True,
                    memory_context_override="Recent memory context",
                    execution_step=execution_step,
                )
                debugger_prompt_text = runner.run_pass.call_args_list[1].kwargs["prompt"]
                pass_entries = read_jsonl_tail(context.paths.pass_log_file, 5)
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(commit_hash, "debug-commit")
        self.assertIsNotNone(test_result)
        self.assertEqual(test_result.returncode, 0)
        self.assertIn("after debugger recovery", test_result.summary)
        self.assertEqual(run_result.changed_files, ["src/app.py", "src/fix.py"])
        mocked_commit.assert_called_once()
        self.assertEqual(mocked_commit.call_args.args[1], "Implement fix debugging")
        self.assertEqual(mocked_commit.call_args.kwargs["author_name"], "Jakal-Flow-debugger")
        mocked_reset.assert_not_called()
        self.assertIn("Implement fix", debugger_prompt_text)
        self.assertIn("AssertionError: expected value", debugger_prompt_text)
        self.assertIn("Traceback: test failure details", debugger_prompt_text)
        self.assertIn("Do not modify tests unless", debugger_prompt_text)
        self.assertEqual([item["pass_type"] for item in pass_entries], ["block-search-pass", "block-search-debug"])
        self.assertEqual(pass_entries[0]["rollback_status"], "debugger_invoked")
        self.assertEqual(pass_entries[1]["rollback_status"], "not_needed")
        self.assertEqual(observed_statuses, ["initialized", "running:debugging"])

    def test_parallel_batch_verification_failure_invokes_debugger(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_parallel_batch_debugger_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(
            model="gpt-5.4",
            effort="medium",
            test_cmd="python -m pytest",
            execution_mode="parallel",
            parallel_workers=2,
        )
        debug_prompt_text = ""

        try:
            context = orchestrator.workspace.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=runtime,
            )
            context.metadata.current_safe_revision = "safe-revision"
            context.loop_state.current_safe_revision = "safe-revision"
            orchestrator.workspace.save_project(context)
            orchestrator.save_execution_plan_state(
                context,
                ExecutionPlanState(
                    plan_title="Parallel Debugger Demo",
                    execution_mode="parallel",
                    default_test_command="python -m pytest",
                    steps=[
                        ExecutionStep(
                            step_id="node-a",
                            title="Desktop slice",
                            codex_description="Implement the desktop slice.",
                            test_command="python -m pytest",
                            success_criteria="The desktop slice passes verification.",
                            depends_on=[],
                            owned_paths=["desktop/src"],
                        ),
                        ExecutionStep(
                            step_id="node-b",
                            title="Backend slice",
                            codex_description="Implement the backend slice.",
                            test_command="python -m pytest",
                            success_criteria="The backend slice passes verification.",
                            depends_on=[],
                            owned_paths=["src/jakal_flow"],
                        ),
                    ],
                ),
            )

            failing_stdout = workspace_root / "parallel-batch-pass.stdout.log"
            failing_stderr = workspace_root / "parallel-batch-pass.stderr.log"
            failing_stdout.parent.mkdir(parents=True, exist_ok=True)
            failing_stdout.write_text("integration assertion failed\n", encoding="utf-8")
            failing_stderr.write_text("parallel batch traceback\n", encoding="utf-8")
            recovered_stdout = workspace_root / "parallel-batch-debug.stdout.log"
            recovered_stderr = workspace_root / "parallel-batch-debug.stderr.log"
            recovered_stdout.write_text("integration fixed\n", encoding="utf-8")
            recovered_stderr.write_text("", encoding="utf-8")
            failing_test = TestRunResult(
                command="python -m pytest",
                returncode=1,
                stdout_file=failing_stdout,
                stderr_file=failing_stderr,
                summary="python -m pytest exited with 1",
            )
            recovered_test = TestRunResult(
                command="python -m pytest",
                returncode=0,
                stdout_file=recovered_stdout,
                stderr_file=recovered_stderr,
                summary="python -m pytest exited with 0",
            )
            worker_results = [
                {
                    "step_id": "ST1",
                    "status": "completed",
                    "notes": "worker 1 ok",
                    "commit_hash": "worker-1-commit",
                    "changed_files": ["desktop/src/app.jsx"],
                    "pass_log": {"pass_type": "block-search-pass"},
                    "block_log": {"status": "completed"},
                    "test_summary": "worker 1 ok",
                },
                {
                    "step_id": "ST2",
                    "status": "completed",
                    "notes": "worker 2 ok",
                    "commit_hash": "worker-2-commit",
                    "changed_files": ["src/jakal_flow/orchestrator.py"],
                    "pass_log": {"pass_type": "block-search-pass"},
                    "block_log": {"status": "completed"},
                    "test_summary": "worker 2 ok",
                },
            ]

            with mock.patch.object(orchestrator, "_run_parallel_step_worker", side_effect=worker_results), mock.patch.object(
                orchestrator,
                "_run_test_command",
                side_effect=[failing_test, recovered_test],
            ), mock.patch.object(
                orchestrator.git,
                "try_cherry_pick",
                return_value=CommandResult(command=["git", "cherry-pick"], returncode=0, stdout="", stderr=""),
            ), mock.patch.object(orchestrator.git, "has_changes", return_value=True), mock.patch.object(
                orchestrator.git,
                "commit_all",
                return_value="parallel-debug-commit",
            ) as mocked_commit, mock.patch.object(
                orchestrator.git,
                "current_revision",
                side_effect=["merge-commit-1", "merge-commit-2"],
            ), mock.patch.object(
                orchestrator.git,
                "changed_files",
                return_value=["desktop/src/app.jsx", "src/jakal_flow/orchestrator.py"],
            ), mock.patch.object(
                orchestrator,
                "setup_local_project",
                return_value=context,
            ), mock.patch("jakal_flow.orchestrator.CodexRunner.run_pass") as mocked_run_pass, mock.patch(
                "jakal_flow.orchestrator.ensure_virtualenv",
                return_value=repo_dir / ".venv",
            ):
                mocked_run_pass.return_value = CodexRunResult(
                    pass_type="parallel-batch-debug",
                    prompt_file=workspace_root / "parallel-debug.prompt.md",
                    output_file=workspace_root / "parallel-debug.last_message.txt",
                    event_file=workspace_root / "parallel-debug.events.jsonl",
                    returncode=0,
                    search_enabled=False,
                    changed_files=[],
                    usage={"input_tokens": 12},
                    last_message="parallel debugger pass",
                )
                context, plan_state, steps = orchestrator.run_parallel_execution_batch(
                    project_dir=repo_dir,
                    runtime=runtime,
                    step_ids=["ST1", "ST2"],
                )
                debug_prompt_text = mocked_run_pass.call_args.kwargs["prompt"]
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual([step.status for step in steps], ["completed", "completed"])
        self.assertEqual([step.status for step in plan_state.steps], ["completed", "completed"])
        self.assertEqual(context.metadata.current_status, "plan_completed")
        self.assertEqual(context.metadata.current_safe_revision, "parallel-debug-commit")
        mocked_commit.assert_called_once()
        self.assertEqual(mocked_commit.call_args.args[1], "Desktop slice, Backend slice debugging")
        self.assertEqual(mocked_commit.call_args.kwargs["author_name"], "Jakal-Flow-debugger")
        self.assertIn("Recover merged parallel batch ST1, ST2", debug_prompt_text)
        self.assertIn("integration assertion failed", debug_prompt_text)
        self.assertIn("parallel batch traceback", debug_prompt_text)
        self.assertIn("Do not modify tests unless", debug_prompt_text)

    def test_parallel_batch_keeps_successful_steps_when_one_worker_fails(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_parallel_batch_partial_success_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(
            model="gpt-5.4",
            effort="medium",
            test_cmd="python -m pytest",
            execution_mode="parallel",
            parallel_workers=2,
        )

        try:
            context = orchestrator.workspace.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=runtime,
            )
            context.metadata.current_safe_revision = "safe-revision"
            context.loop_state.current_safe_revision = "safe-revision"
            orchestrator.workspace.save_project(context)
            orchestrator.save_execution_plan_state(
                context,
                ExecutionPlanState(
                    plan_title="Parallel Partial Success Demo",
                    execution_mode="parallel",
                    default_test_command="python -m pytest",
                    steps=[
                        ExecutionStep(
                            step_id="ST1",
                            title="Desktop slice",
                            codex_description="Implement the desktop slice.",
                            test_command="python -m pytest",
                            success_criteria="The desktop slice passes verification.",
                            depends_on=[],
                            owned_paths=["desktop/src"],
                        ),
                        ExecutionStep(
                            step_id="ST2",
                            title="Backend slice",
                            codex_description="Implement the backend slice.",
                            test_command="python -m pytest",
                            success_criteria="The backend slice passes verification.",
                            depends_on=[],
                            owned_paths=["src/jakal_flow"],
                        ),
                    ],
                ),
            )

            passing_stdout = workspace_root / "parallel-batch-pass.stdout.log"
            passing_stderr = workspace_root / "parallel-batch-pass.stderr.log"
            passing_stdout.parent.mkdir(parents=True, exist_ok=True)
            passing_stdout.write_text("batch green\n", encoding="utf-8")
            passing_stderr.write_text("", encoding="utf-8")
            passing_test = TestRunResult(
                command="python -m pytest",
                returncode=0,
                stdout_file=passing_stdout,
                stderr_file=passing_stderr,
                summary="python -m pytest exited with 0",
            )
            worker_results = [
                {
                    "step_id": "ST1",
                    "status": "completed",
                    "notes": "worker 1 ok",
                    "commit_hash": "worker-1-commit",
                    "changed_files": ["desktop/src/app.jsx"],
                    "pass_log": {"pass_type": "block-search-pass"},
                    "block_log": {"status": "completed"},
                    "test_summary": "worker 1 ok",
                },
                {
                    "step_id": "ST2",
                    "status": "failed",
                    "notes": "worker 2 failed badly",
                    "commit_hash": None,
                    "changed_files": ["src/jakal_flow/orchestrator.py"],
                    "pass_log": {"pass_type": "block-search-pass"},
                    "block_log": {"status": "failed"},
                    "test_summary": "",
                },
            ]

            with mock.patch.object(orchestrator, "_run_parallel_step_worker", side_effect=worker_results), mock.patch.object(
                orchestrator,
                "_run_test_command",
                return_value=passing_test,
            ) as mocked_test, mock.patch.object(
                orchestrator.git,
                "try_cherry_pick",
                return_value=CommandResult(command=["git", "cherry-pick"], returncode=0, stdout="", stderr=""),
            ) as mocked_pick, mock.patch.object(
                orchestrator.git,
                "current_revision",
                return_value="merge-commit-1",
            ), mock.patch.object(
                orchestrator,
                "_push_if_ready",
                return_value=(False, "already_up_to_date"),
            ) as mocked_push, mock.patch.object(
                orchestrator,
                "_report_failure",
            ) as mocked_report, mock.patch.object(
                orchestrator,
                "setup_local_project",
                return_value=context,
            ):
                context, plan_state, steps = orchestrator.run_parallel_execution_batch(
                    project_dir=repo_dir,
                    runtime=runtime,
                    step_ids=["ST1", "ST2"],
                )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual([step.status for step in steps], ["completed", "failed"])
        self.assertEqual([step.status for step in plan_state.steps], ["completed", "failed"])
        self.assertEqual(steps[0].commit_hash, "merge-commit-1")
        self.assertIsNone(steps[1].commit_hash)
        self.assertEqual(context.metadata.current_safe_revision, "merge-commit-1")
        self.assertEqual(context.metadata.current_status, "plan_ready")
        mocked_test.assert_called_once()
        mocked_push.assert_called_once()
        self.assertEqual(mocked_pick.call_count, 1)
        self.assertEqual(mocked_pick.call_args.args[1], "worker-1-commit")
        mocked_report.assert_called_once()
        self.assertIn("Completed and kept: ST1", mocked_report.call_args.kwargs["summary"])
        self.assertEqual(mocked_report.call_args.kwargs["extra"]["completed_steps"], ["ST1"])
        self.assertEqual(
            [item["step_id"] for item in mocked_report.call_args.kwargs["extra"]["failed_steps"]],
            ["ST2"],
        )
        self.assertIn("worker 2 failed badly", steps[1].notes)

    def test_parallel_batch_persists_worker_sync_before_last_worker_finishes(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_parallel_batch_sync_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(
            model="gpt-5.4",
            effort="medium",
            test_cmd="python -m pytest",
            execution_mode="parallel",
            parallel_workers=2,
        )

        first_worker_finished = threading.Event()
        release_second_worker = threading.Event()
        background_error: list[BaseException] = []

        try:
            context = orchestrator.workspace.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=runtime,
            )
            context.metadata.current_safe_revision = "safe-revision"
            context.loop_state.current_safe_revision = "safe-revision"
            orchestrator.workspace.save_project(context)
            orchestrator.save_execution_plan_state(
                context,
                ExecutionPlanState(
                    plan_title="Parallel Sync Demo",
                    execution_mode="parallel",
                    default_test_command="python -m pytest",
                    steps=[
                        ExecutionStep(step_id="ST1", title="Frontend", owned_paths=["desktop/src"]),
                        ExecutionStep(step_id="ST2", title="Backend", owned_paths=["src/jakal_flow"]),
                    ],
                ),
            )

            passing_stdout = workspace_root / "parallel-batch-pass.stdout.log"
            passing_stderr = workspace_root / "parallel-batch-pass.stderr.log"
            passing_stdout.parent.mkdir(parents=True, exist_ok=True)
            passing_stdout.write_text("batch green\n", encoding="utf-8")
            passing_stderr.write_text("", encoding="utf-8")
            passing_test = TestRunResult(
                command="python -m pytest",
                returncode=0,
                stdout_file=passing_stdout,
                stderr_file=passing_stderr,
                summary="python -m pytest exited with 0",
            )

            def fake_parallel_worker(_context, _runtime, step, _base_revision, _batch_token, _worker_index):
                if step.step_id == "ST1":
                    first_worker_finished.set()
                    return {
                        "step_id": "ST1",
                        "status": "completed",
                        "notes": "frontend worker ok",
                        "commit_hash": "worker-1-commit",
                        "changed_files": ["desktop/src/App.jsx"],
                        "pass_log": {"pass_type": "block-search-pass"},
                        "block_log": {"status": "completed"},
                        "test_summary": "frontend worker ok",
                    }
                release_second_worker.wait(timeout=5)
                return {
                    "step_id": "ST2",
                    "status": "completed",
                    "notes": "backend worker ok",
                    "commit_hash": "worker-2-commit",
                    "changed_files": ["src/jakal_flow/orchestrator.py"],
                    "pass_log": {"pass_type": "block-search-pass"},
                    "block_log": {"status": "completed"},
                    "test_summary": "backend worker ok",
                }

            def run_batch() -> None:
                try:
                    orchestrator.run_parallel_execution_batch(
                        project_dir=repo_dir,
                        runtime=runtime,
                        step_ids=["ST1", "ST2"],
                    )
                except BaseException as exc:  # pragma: no cover - surfaced by assertion below
                    background_error.append(exc)

            with mock.patch.object(orchestrator, "_run_parallel_step_worker", side_effect=fake_parallel_worker), mock.patch.object(
                orchestrator,
                "_run_test_command",
                return_value=passing_test,
            ), mock.patch.object(
                orchestrator.git,
                "try_cherry_pick",
                return_value=CommandResult(command=["git", "cherry-pick"], returncode=0, stdout="", stderr=""),
            ), mock.patch.object(
                orchestrator.git,
                "current_revision",
                side_effect=["merge-commit-1", "merge-commit-2"],
            ), mock.patch.object(
                orchestrator.git,
                "remote_url",
                return_value=None,
            ), mock.patch.object(
                orchestrator,
                "setup_local_project",
                return_value=context,
            ):
                thread = threading.Thread(target=run_batch, daemon=True)
                thread.start()

                self.assertTrue(first_worker_finished.wait(timeout=2))

                synced_statuses: list[str] = []
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    try:
                        current_plan = read_json(context.paths.execution_plan_file, default={})
                    except json.JSONDecodeError:
                        time.sleep(0.05)
                        continue
                    steps = current_plan.get("steps", []) if isinstance(current_plan, dict) else []
                    synced_statuses = [str(item.get("status", "")) for item in steps[:2]]
                    if synced_statuses == ["integrating", "running"]:
                        break
                    time.sleep(0.05)

                release_second_worker.set()
                thread.join(timeout=5)

        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertFalse(background_error, str(background_error[0]) if background_error else "")
        self.assertEqual(synced_statuses, ["integrating", "running"])

    def test_parallel_batch_merge_conflict_invokes_merger_and_continues(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_parallel_merge_debugger_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(
            model="gpt-5.4",
            effort="medium",
            test_cmd="python -m pytest",
            execution_mode="parallel",
            parallel_workers=2,
        )
        merge_prompt_text = ""

        try:
            context = orchestrator.workspace.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=runtime,
            )
            context.metadata.current_safe_revision = "safe-revision"
            context.loop_state.current_safe_revision = "safe-revision"
            orchestrator.workspace.save_project(context)
            orchestrator.save_execution_plan_state(
                context,
                ExecutionPlanState(
                    plan_title="Parallel Merge Recovery Demo",
                    execution_mode="parallel",
                    default_test_command="python -m pytest",
                    steps=[
                        ExecutionStep(
                            step_id="node-a",
                            title="Desktop slice",
                            codex_description="Implement the desktop slice.",
                            test_command="python -m pytest",
                            success_criteria="The desktop slice passes verification.",
                            depends_on=[],
                            owned_paths=["desktop/src"],
                        ),
                        ExecutionStep(
                            step_id="node-b",
                            title="Backend slice",
                            codex_description="Implement the backend slice.",
                            test_command="python -m pytest",
                            success_criteria="The backend slice passes verification.",
                            depends_on=[],
                            owned_paths=["src/jakal_flow"],
                        ),
                    ],
                ),
            )

            recovered_stdout = workspace_root / "parallel-batch-merge.stdout.log"
            recovered_stderr = workspace_root / "parallel-batch-merge.stderr.log"
            recovered_stdout.write_text("merge conflict resolved\n", encoding="utf-8")
            recovered_stderr.write_text("", encoding="utf-8")
            passing_stdout = workspace_root / "parallel-batch-pass.stdout.log"
            passing_stderr = workspace_root / "parallel-batch-pass.stderr.log"
            passing_stdout.write_text("batch green\n", encoding="utf-8")
            passing_stderr.write_text("", encoding="utf-8")
            recovered_test = TestRunResult(
                command="python -m pytest",
                returncode=0,
                stdout_file=recovered_stdout,
                stderr_file=recovered_stderr,
                summary="python -m pytest exited with 0",
            )
            passing_test = TestRunResult(
                command="python -m pytest",
                returncode=0,
                stdout_file=passing_stdout,
                stderr_file=passing_stderr,
                summary="python -m pytest exited with 0",
            )
            worker_results = [
                {
                    "step_id": "ST1",
                    "status": "completed",
                    "notes": "worker 1 ok",
                    "commit_hash": "worker-1-commit",
                    "changed_files": ["desktop/src/app.jsx"],
                    "pass_log": {"pass_type": "block-search-pass"},
                    "block_log": {"status": "completed"},
                    "test_summary": "worker 1 ok",
                },
                {
                    "step_id": "ST2",
                    "status": "completed",
                    "notes": "worker 2 ok",
                    "commit_hash": "worker-2-commit",
                    "changed_files": ["src/jakal_flow/orchestrator.py"],
                    "pass_log": {"pass_type": "block-search-pass"},
                    "block_log": {"status": "completed"},
                    "test_summary": "worker 2 ok",
                },
            ]

            with mock.patch.object(orchestrator, "_run_parallel_step_worker", side_effect=worker_results), mock.patch.object(
                orchestrator,
                "_run_test_command",
                side_effect=[recovered_test, passing_test],
            ), mock.patch.object(
                orchestrator.git,
                "try_cherry_pick",
                side_effect=[
                    CommandResult(command=["git", "cherry-pick"], returncode=0, stdout="", stderr=""),
                    CommandResult(
                        command=["git", "cherry-pick"],
                        returncode=1,
                        stdout="Auto-merging src/jakal_flow/orchestrator.py\n",
                        stderr="CONFLICT (content): Merge conflict in src/jakal_flow/orchestrator.py\n",
                    ),
                ],
            ), mock.patch.object(
                orchestrator.git,
                "conflicted_files",
                side_effect=[["src/jakal_flow/orchestrator.py"], []],
            ), mock.patch.object(
                orchestrator.git,
                "cherry_pick_in_progress",
                return_value=True,
            ), mock.patch.object(orchestrator.git, "add_all") as mocked_add_all, mock.patch.object(
                orchestrator.git,
                "commit_staged",
                return_value="merge-recovery-commit",
            ) as mocked_commit, mock.patch.object(
                orchestrator.git,
                "current_revision",
                side_effect=["merge-commit-1", "merge-recovery-commit"],
            ), mock.patch.object(
                orchestrator.git,
                "changed_files",
                return_value=["desktop/src/app.jsx", "src/jakal_flow/orchestrator.py"],
            ), mock.patch.object(
                orchestrator.git,
                "remote_url",
                return_value=None,
            ), mock.patch.object(
                orchestrator.git,
                "abort_cherry_pick",
            ) as mocked_abort, mock.patch.object(
                orchestrator.git,
                "hard_reset",
            ) as mocked_reset, mock.patch.object(
                orchestrator,
                "setup_local_project",
                return_value=context,
            ), mock.patch("jakal_flow.orchestrator.CodexRunner.run_pass") as mocked_run_pass, mock.patch(
                "jakal_flow.orchestrator.ensure_virtualenv",
                return_value=repo_dir / ".venv",
            ):
                mocked_run_pass.return_value = CodexRunResult(
                    pass_type="parallel-batch-merger",
                    prompt_file=workspace_root / "parallel-merge-merger.prompt.md",
                    output_file=workspace_root / "parallel-merge-merger.last_message.txt",
                    event_file=workspace_root / "parallel-merge-merger.events.jsonl",
                    returncode=0,
                    search_enabled=False,
                    changed_files=[],
                    usage={"input_tokens": 15},
                    last_message="parallel merge merger pass",
                )
                context, plan_state, steps = orchestrator.run_parallel_execution_batch(
                    project_dir=repo_dir,
                    runtime=runtime,
                    step_ids=["ST1", "ST2"],
                )
                merge_prompt_text = mocked_run_pass.call_args.kwargs["prompt"]
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual([step.status for step in steps], ["completed", "completed"])
        self.assertEqual([step.commit_hash for step in steps], ["merge-commit-1", "merge-recovery-commit"])
        self.assertEqual([step.status for step in plan_state.steps], ["completed", "completed"])
        self.assertEqual(context.metadata.current_status, "plan_completed")
        self.assertEqual(context.metadata.current_safe_revision, "merge-recovery-commit")
        mocked_add_all.assert_called_once_with(context.paths.repo_dir)
        mocked_commit.assert_called_once()
        self.assertEqual(mocked_commit.call_args.args[1], "Desktop slice, Backend slice conflict resolution")
        self.assertEqual(mocked_commit.call_args.kwargs["author_name"], "Jakal-Flow-merge-resolver")
        mocked_abort.assert_not_called()
        mocked_reset.assert_not_called()
        self.assertIn("git cherry-pick worker-2-commit conflicted", merge_prompt_text)
        self.assertIn("CONFLICT (content): Merge conflict in src/jakal_flow/orchestrator.py", merge_prompt_text)
        self.assertIn("Merge targets", merge_prompt_text)

    def test_execution_plan_svg_includes_step_statuses(self) -> None:
        svg = execution_plan_svg(
            "demo flow",
            [
                ExecutionStep(step_id="ST1", title="First", test_command="pytest a", status="completed"),
                ExecutionStep(step_id="ST2", title="Second", test_command="pytest b", status="pending"),
            ],
        )

        self.assertIn("<svg", svg)
        self.assertIn("demo flow", svg)
        self.assertIn("ST1", svg)
        self.assertIn("ST2", svg)
        self.assertIn("#0f766e", svg)
        self.assertIn("#cbd5e1", svg)

    def test_execution_plan_svg_wraps_long_text_inside_boxes(self) -> None:
        svg = execution_plan_svg(
            "demo flow with a very long title that should wrap instead of overflowing the card boundary",
            [
                ExecutionStep(
                    step_id="ST1",
                    title="A deliberately long execution step title that should wrap across multiple lines",
                    display_description="A deliberately long description that should stay inside the SVG card instead of spilling outside the box boundary.",
                    status="running",
                )
            ],
        )

        self.assertIn("<tspan", svg)
        self.assertIn("execution step title", svg)
        self.assertIn("description that should s...", svg)

    def test_execution_plan_svg_routes_merge_edges_through_shared_junctions(self) -> None:
        svg = execution_plan_svg(
            "merge flow",
            [
                ExecutionStep(step_id="ST1", title="Frontend", status="completed"),
                ExecutionStep(step_id="ST2", title="Backend", status="completed"),
                ExecutionStep(step_id="ST3", title="Integrate", depends_on=["ST1", "ST2"], status="pending"),
                ExecutionStep(step_id="ST4", title="Verify", depends_on=["ST3"], status="pending"),
            ],
            execution_mode="parallel",
        )

        self.assertIn('marker id="flow-arrow"', svg)
        self.assertIn("<circle", svg)
        self.assertEqual(svg.count('marker-end="url(#flow-arrow)"'), 2)

    def test_ml_results_svg_wraps_long_labels(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_ml_results_svg_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        temp_root.mkdir(parents=True, exist_ok=True)

        try:
            svg = Orchestrator(temp_root)._ml_results_svg(
                [
                    MLExperimentRecord(
                        experiment_id="EXP-1",
                        step_id="STEP-WITH-A-LONG-ID",
                        primary_metric="very_long_metric_name_that_should_wrap_inside_the_chart_label",
                        metric_value=0.9132,
                    )
                ]
            )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertIn("<tspan", svg)
        self.assertIn("STEP-WITH-A-LONG-ID", svg)

    def test_model_selection_resolves_direct_slug_without_builder(self) -> None:
        selection = ModelSelection(mode=MODEL_MODE_SLUG, direct_slug="gpt-5.4", effort="high")

        self.assertEqual(selection.resolved_slug(), "gpt-5.4")
        self.assertEqual(selection.summary(), "Model gpt-5.4 | Direct slug | reasoning high")

    def test_model_selection_resolves_codex_slug_from_slug_parts(self) -> None:
        selection = ModelSelection(
            mode=MODEL_MODE_CODEX,
            direct_slug="ignored",
            codex_base_slug="gpt-5.4",
            codex_variant_slug="codex",
            effort="medium",
        )

        self.assertEqual(selection.resolved_slug(), "gpt-5.4-codex")

    def test_model_selection_from_runtime_infers_codex_builder_inputs(self) -> None:
        runtime = RuntimeOptions(model="gpt-5.4-codex", effort="low")

        selection = model_selection_from_runtime(runtime)

        self.assertEqual(selection.mode, MODEL_MODE_CODEX)
        self.assertEqual(selection.codex_base_slug, "gpt-5.4")
        self.assertEqual(selection.codex_variant_slug, "codex")
        self.assertEqual(selection.direct_slug, "gpt-5.4-codex")

    def test_model_selection_from_runtime_keeps_oss_models_in_direct_slug_mode(self) -> None:
        runtime = RuntimeOptions(
            model_provider="oss",
            local_model_provider="ollama",
            model="qwen2.5-coder:0.5b",
            effort="medium",
        )

        selection = model_selection_from_runtime(runtime)

        self.assertEqual(selection.mode, MODEL_MODE_SLUG)
        self.assertEqual(selection.direct_slug, "qwen2.5-coder:0.5b")

    def test_model_preset_helpers_match_runtime(self) -> None:
        preset = model_preset_by_id(DEFAULT_MODEL_PRESET_ID)
        runtime = RuntimeOptions(model=preset.model, model_preset=preset.preset_id, effort=preset.effort)

        resolved = model_preset_from_runtime(runtime)

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.preset_id, preset.preset_id)
        self.assertEqual(resolved.model, "auto")

    def test_model_preset_helpers_return_none_for_custom_runtime(self) -> None:
        runtime = RuntimeOptions(model="custom-preview-model", model_preset="", effort="medium")

        self.assertIsNone(model_preset_from_runtime(runtime))

    def test_model_preset_helpers_accept_legacy_auto_preset_ids(self) -> None:
        self.assertEqual(normalize_model_preset_id("auto-high"), "high")
        preset = model_preset_by_id("auto-medium")

        self.assertEqual(preset.preset_id, "medium")
        self.assertEqual(preset.label, "Medium Only")
        self.assertEqual(preset.effort, "medium")

    def test_source_prompt_templates_exist_and_keep_expected_placeholders(self) -> None:
        parallel_decomposition_template = load_source_prompt_template(PLAN_DECOMPOSITION_PARALLEL_PROMPT_FILENAME)
        ml_decomposition_template = load_source_prompt_template(ML_PLAN_DECOMPOSITION_PROMPT_FILENAME)
        parallel_plan_template = load_source_prompt_template(PLAN_GENERATION_PARALLEL_PROMPT_FILENAME)
        ml_plan_template = load_source_prompt_template(ML_PLAN_GENERATION_PROMPT_FILENAME)
        parallel_step_template = load_source_prompt_template(STEP_EXECUTION_PARALLEL_PROMPT_FILENAME)
        ml_step_template = load_source_prompt_template(ML_STEP_EXECUTION_PROMPT_FILENAME)
        parallel_debugger_template = load_source_prompt_template(DEBUGGER_PARALLEL_PROMPT_FILENAME)
        parallel_merger_template = load_source_prompt_template(MERGER_PARALLEL_PROMPT_FILENAME)
        final_template = load_source_prompt_template(FINALIZATION_PROMPT_FILENAME)
        optimization_template = load_source_prompt_template(OPTIMIZATION_PROMPT_FILENAME)
        ml_final_template = load_source_prompt_template(ML_FINALIZATION_PROMPT_FILENAME)
        scope_template = load_source_prompt_template(SCOPE_GUARD_TEMPLATE_FILENAME)

        self.assertTrue(source_prompt_template_path(PLAN_DECOMPOSITION_PARALLEL_PROMPT_FILENAME).exists())
        self.assertTrue(source_prompt_template_path(PLAN_GENERATION_PROMPT_FILENAME).exists())
        self.assertTrue(source_prompt_template_path(PLAN_GENERATION_PARALLEL_PROMPT_FILENAME).exists())
        self.assertTrue(source_prompt_template_path(STEP_EXECUTION_PROMPT_FILENAME).exists())
        self.assertTrue(source_prompt_template_path(STEP_EXECUTION_PARALLEL_PROMPT_FILENAME).exists())
        self.assertTrue(source_prompt_template_path(DEBUGGER_PROMPT_FILENAME).exists())
        self.assertTrue(source_prompt_template_path(DEBUGGER_PARALLEL_PROMPT_FILENAME).exists())
        self.assertTrue(source_prompt_template_path(MERGER_PARALLEL_PROMPT_FILENAME).exists())
        self.assertTrue(source_prompt_template_path(FINALIZATION_PROMPT_FILENAME).exists())
        self.assertTrue(source_prompt_template_path(ML_PLAN_DECOMPOSITION_PROMPT_FILENAME).exists())
        self.assertTrue(source_prompt_template_path(ML_PLAN_GENERATION_PROMPT_FILENAME).exists())
        self.assertTrue(source_prompt_template_path(ML_STEP_EXECUTION_PROMPT_FILENAME).exists())
        self.assertTrue(source_prompt_template_path(ML_FINALIZATION_PROMPT_FILENAME).exists())
        self.assertTrue(source_prompt_template_path(SCOPE_GUARD_TEMPLATE_FILENAME).exists())
        self.assertTrue(source_prompt_template_path(REFERENCE_GUIDE_FILENAME).exists())
        self.assertIn("Planner Agent A", parallel_decomposition_template)
        self.assertIn('"candidate_blocks": [', parallel_decomposition_template)
        self.assertIn('"contract_docstring"', parallel_decomposition_template)
        self.assertIn("candidate_experiments", ml_decomposition_template)
        self.assertIn('"contract_docstring"', ml_decomposition_template)
        self.assertEqual(PLAN_GENERATION_PROMPT_FILENAME, PLAN_GENERATION_PARALLEL_PROMPT_FILENAME)
        self.assertIn("{planner_outline}", parallel_plan_template)
        self.assertIn('"step_id": "stable id like ST1"', parallel_plan_template)
        self.assertIn('"depends_on": ["step ids that must complete first"]', parallel_plan_template)
        self.assertIn('"owned_paths": ["repo-relative paths or directories this step primarily owns"]', parallel_plan_template)
        self.assertIn('"implementation_notes"', parallel_plan_template)
        self.assertIn('"skeleton_contract_docstring"', parallel_plan_template)
        self.assertIn("DAG execution tree", parallel_plan_template)
        self.assertIn("Maximize safe frontier width", parallel_plan_template)
        self.assertIn("contract-freezing or coordination step", parallel_plan_template)
        self.assertIn("explicit join node", parallel_plan_template)
        self.assertIn('"step_kind": "task unless this is an explicit join or barrier node"', parallel_plan_template)
        self.assertIn('"join_policy": "use `all` for join nodes and leave empty for normal task nodes"', parallel_plan_template)
        self.assertIn("finished, handoff-quality result", parallel_plan_template)
        self.assertIn("{reference_notes}", parallel_plan_template)
        self.assertIn("src/jakal_flow/docs/REFERENCE_GUIDE.md", parallel_plan_template)
        self.assertIn('"metadata": {', ml_plan_template)
        self.assertIn('"implementation_notes"', ml_plan_template)
        self.assertIn('"skeleton_contract_docstring"', ml_plan_template)
        self.assertIn("Prevent data leakage", ml_plan_template)
        self.assertIn("Maximize safe experiment frontier width", ml_plan_template)
        self.assertIn("small coordination node", ml_plan_template)
        self.assertIn("{planner_outline}", ml_plan_template)
        self.assertIn("{workflow_mode}", ml_plan_template)
        self.assertEqual(STEP_EXECUTION_PROMPT_FILENAME, STEP_EXECUTION_PARALLEL_PROMPT_FILENAME)
        self.assertIn("{step_metadata}", parallel_step_template)
        self.assertIn("step_metadata.step_kind", parallel_step_template)
        self.assertIn("saved DAG execution tree", parallel_step_template)
        self.assertIn("primary write scope", parallel_step_template)
        self.assertIn("Do not edit README.md during normal execution steps.", parallel_step_template)
        self.assertIn("{ml_step_report_file}", ml_step_template)
        self.assertIn("Step metadata", ml_step_template)
        self.assertIn("Do not edit README.md during normal execution steps.", ml_step_template)
        self.assertEqual(DEBUGGER_PROMPT_FILENAME, DEBUGGER_PARALLEL_PROMPT_FILENAME)
        self.assertIn("{step_metadata}", parallel_debugger_template)
        self.assertIn("step_metadata.step_kind", parallel_debugger_template)
        self.assertIn("{owned_paths}", parallel_debugger_template)
        self.assertIn("merged parallel batch", parallel_debugger_template)
        self.assertIn("cherry-pick conflict", parallel_debugger_template)
        self.assertIn("Do not edit README.md during debugger recovery.", parallel_debugger_template)
        self.assertIn("{merge_targets}", parallel_merger_template)
        self.assertIn("integration worktree", parallel_merger_template)
        self.assertIn("Failing merge context", parallel_merger_template)
        self.assertIn("adjacent compatibility breakage", parallel_merger_template)
        self.assertIn("adjacent integration touchpoints", parallel_merger_template)
        self.assertIn("Do not edit README.md during merge recovery.", parallel_merger_template)
        self.assertEqual(load_plan_decomposition_prompt_template("serial"), parallel_decomposition_template)
        self.assertEqual(load_plan_decomposition_prompt_template("parallel"), parallel_decomposition_template)
        self.assertEqual(load_plan_decomposition_prompt_template("parallel", "ml"), ml_decomposition_template)
        self.assertEqual(load_plan_generation_prompt_template("serial"), parallel_plan_template)
        self.assertEqual(load_plan_generation_prompt_template("parallel"), parallel_plan_template)
        self.assertEqual(load_plan_generation_prompt_template("parallel", "ml"), ml_plan_template)
        self.assertEqual(load_step_execution_prompt_template("serial"), parallel_step_template)
        self.assertEqual(load_step_execution_prompt_template("parallel"), parallel_step_template)
        self.assertEqual(load_step_execution_prompt_template("parallel", "ml"), ml_step_template)
        self.assertEqual(load_debugger_prompt_template("serial"), parallel_debugger_template)
        self.assertEqual(load_debugger_prompt_template("parallel"), parallel_debugger_template)
        self.assertEqual(load_merger_prompt_template("serial"), parallel_merger_template)
        self.assertEqual(load_merger_prompt_template("parallel"), parallel_merger_template)
        self.assertIn("{completed_steps}", final_template)
        self.assertIn("{closeout_report_file}", final_template)
        self.assertIn("{test_command}", final_template)
        self.assertIn("README.md as a first-class closeout deliverable", final_template)
        self.assertIn("{optimization_mode}", optimization_template)
        self.assertIn("{candidate_files}", optimization_template)
        self.assertIn("{optimization_candidates}", optimization_template)
        self.assertEqual(load_optimization_prompt_template(), optimization_template)
        self.assertIn("{ml_mode_state_file}", ml_final_template)
        self.assertIn("{ml_experiment_reports_dir}", ml_final_template)
        self.assertIn("audit README.md and related repository docs", ml_final_template)
        self.assertEqual(load_finalization_prompt_template("ml"), ml_final_template)
        self.assertIn("{repo_url}", scope_template)
        self.assertIn("reserve README.md edits for planning-time alignment or the final closeout pass", scope_template)

    def test_scan_repository_inputs_and_source_reference_guide_feed_planning_prompts(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_reference_notes_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        repo_dir = temp_root / "repo"
        (repo_dir / "docs").mkdir(parents=True, exist_ok=True)
        (repo_dir / "src").mkdir(parents=True, exist_ok=True)
        (repo_dir / "README.md").write_text("README summary", encoding="utf-8")
        (repo_dir / "AGENTS.md").write_text("AGENTS summary", encoding="utf-8")
        (repo_dir / "docs" / "notes.md").write_text("docs summary", encoding="utf-8")
        (repo_dir / "src" / "main.py").write_text("def run() -> None:\n    pass\n", encoding="utf-8")

        try:
            repo_inputs = scan_repository_inputs(repo_dir)
            self.assertIn("notes.md", repo_inputs["docs"])
            self.assertIn("Existing implementation files detected.", repo_inputs["source"])
            self.assertIn("src/main.py", repo_inputs["source"])
            reference_notes = load_reference_guide_text()
            self.assertIn("React + Tauri", reference_notes)

            context = SimpleNamespace(
                paths=SimpleNamespace(repo_dir=repo_dir, plan_file=temp_root / "managed-docs" / "PLAN.md"),
                metadata=SimpleNamespace(
                    repo_url="https://github.com/example/project.git",
                    branch="main",
                ),
                runtime=SimpleNamespace(workflow_mode="standard"),
            )
            decomposition_prompt = prompt_to_plan_decomposition_prompt(context, repo_inputs, "Build a desktop flow screen.", 4, "parallel")
            plan_prompt = prompt_to_execution_plan_prompt(context, repo_inputs, "Build a desktop flow screen.", 4, "parallel")
            packed_plan_prompt = prompt_to_execution_plan_prompt(
                context,
                repo_inputs,
                "Build a desktop flow screen.",
                4,
                "parallel",
                planner_outline='{"candidate_blocks":[{"block_id":"B1","goal":"demo"}]}',
            )
            bootstrap_prompt = bootstrap_plan_prompt(context, repo_inputs, "Build a desktop flow screen.")
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertIn("Planner Agent A", decomposition_prompt)
        self.assertIn("candidate_blocks", decomposition_prompt)
        self.assertIn("Source inventory:", decomposition_prompt)
        self.assertIn("prefer editing or extending that code", decomposition_prompt)
        self.assertIn("Use the following priority order while planning:", plan_prompt)
        self.assertIn("Requested execution mode:", plan_prompt)
        self.assertIn("parallel", plan_prompt)
        self.assertIn("Planner Agent A decomposition artifact:", plan_prompt)
        self.assertIn("Planner Agent A output unavailable.", plan_prompt)
        self.assertIn("Source inventory:", plan_prompt)
        self.assertIn("fold scaffold-only bootstrap work into the concrete implementation step", plan_prompt)
        self.assertIn('"block_id":"B1"', packed_plan_prompt)
        self.assertIn("step_id", plan_prompt)
        self.assertIn("depends_on", plan_prompt)
        self.assertIn("owned_paths", plan_prompt)
        self.assertIn("src/jakal_flow/docs/REFERENCE_GUIDE.md", plan_prompt)
        self.assertIn("React + Tauri", plan_prompt)
        self.assertIn("well-known algorithm", plan_prompt)
        self.assertIn("1. Follow AGENTS.md and explicit repository constraints first.", bootstrap_prompt)
        self.assertIn("src/jakal_flow/docs/REFERENCE_GUIDE.md", bootstrap_prompt)
        self.assertIn("React + Tauri", bootstrap_prompt)
        self.assertIn("well-known algorithm", bootstrap_prompt)
        self.assertIn("finished, handoff-quality result", plan_prompt)
        self.assertIn("finished, handoff-quality implementation", bootstrap_prompt)

    def test_scan_repository_inputs_compacts_large_docs_inventory(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_large_docs_summary_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        repo_dir = temp_root / "repo"
        docs_dir = repo_dir / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / "README.md").write_text("README summary", encoding="utf-8")
        (repo_dir / "AGENTS.md").write_text("AGENTS summary", encoding="utf-8")

        for index in range(1, 11):
            (docs_dir / f"note_{index}.md").write_text(f"doc {index} " + ("detail " * 120), encoding="utf-8")

        try:
            repo_inputs = scan_repository_inputs(repo_dir)
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertLessEqual(len(repo_inputs["docs"]), 2600)
        self.assertIn("omitted to keep planning context compact", repo_inputs["docs"])
        self.assertIn("note_1.md", repo_inputs["docs"])

    def test_generate_execution_plan_runs_planner_agent_a_then_agent_b(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_dual_planner_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / "README.md").write_text("README summary", encoding="utf-8")
        (repo_dir / "AGENTS.md").write_text("AGENTS summary", encoding="utf-8")
        (repo_dir / "src").mkdir(parents=True, exist_ok=True)
        (repo_dir / "src" / "contracts.py").write_text("class StepSchema:\n    pass\n", encoding="utf-8")
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(
            model="gpt-5.4",
            effort="high",
            planning_effort="low",
            execution_mode="parallel",
            test_cmd="python -m pytest",
        )

        try:
            context = orchestrator.workspace.initialize_local_project(project_dir=repo_dir, branch="main", runtime=runtime)
            planning_events: list[tuple[str, str, dict[str, object] | None]] = []
            outline_json = """
            {
              "title": "Dual planner demo",
              "strategy_summary": "Freeze a contract, then fan out.",
              "shared_contracts": ["step schema"],
              "skeleton_step": {
                "needed": true,
                "task_title": "Freeze the contract",
                "purpose": "Unblock safe downstream fan-out.",
                "contract_docstring": "Keep the shared step schema stable for downstream executors.",
                "candidate_owned_paths": ["src/contracts.py"],
                "success_criteria": "The shared contract exists."
              },
              "candidate_blocks": [
                {
                  "block_id": "B1",
                  "goal": "Implement UI work",
                  "work_items": ["Build the UI slice"],
                  "testable_boundary": "UI path is wired.",
                  "candidate_owned_paths": ["desktop/src"],
                  "parallelizable_after": ["step schema"],
                  "parallel_notes": "Independent after contract freeze."
                }
              ],
              "packing_notes": ["Prefer one bootstrap then one ready wave."]
            }
            """
            final_plan_json = """
            {
              "title": "Dual planner demo",
              "summary": "Freeze the contract first, then execute parallel implementation slices.",
              "tasks": [
                {
                  "step_id": "ST1",
                  "task_title": "Freeze the contract",
                  "display_description": "Add the shared contract.",
                  "codex_description": "Create the contract module that later slices will share.",
                  "reasoning_effort": "medium",
                  "depends_on": [],
                  "owned_paths": ["src/contracts.py"],
                  "success_criteria": "The shared contract exists."
                },
                {
                  "step_id": "ST2",
                  "task_title": "Implement the UI slice",
                  "display_description": "Build the UI work.",
                  "codex_description": "Implement the UI slice against the frozen contract.",
                  "reasoning_effort": "high",
                  "depends_on": ["ST1"],
                  "owned_paths": ["desktop/src"],
                  "success_criteria": "The UI slice is wired."
                }
              ]
            }
            """
            run_results = [
                CodexRunResult(
                    pass_type="plan-agent-a-decomposition",
                    prompt_file=context.paths.logs_dir / "a.prompt.md",
                    output_file=context.paths.logs_dir / "a.last_message.txt",
                    event_file=context.paths.logs_dir / "a.events.jsonl",
                    returncode=0,
                    search_enabled=False,
                    changed_files=[],
                    usage={"input_tokens": 10},
                    last_message=outline_json,
                ),
                CodexRunResult(
                    pass_type="plan-agent-b-packing",
                    prompt_file=context.paths.logs_dir / "b.prompt.md",
                    output_file=context.paths.logs_dir / "b.last_message.txt",
                    event_file=context.paths.logs_dir / "b.events.jsonl",
                    returncode=0,
                    search_enabled=False,
                    changed_files=[],
                    usage={"input_tokens": 12},
                    last_message=final_plan_json,
                ),
            ]

            with mock.patch.object(orchestrator, "setup_local_project", return_value=context), mock.patch(
                "jakal_flow.orchestrator.CodexRunner.run_pass",
                side_effect=run_results,
            ) as mocked_run_pass:
                _context, plan_state = orchestrator.generate_execution_plan(
                    project_dir=repo_dir,
                    runtime=runtime,
                    project_prompt="Build a dual planner demo.",
                    max_steps=4,
                    progress_callback=lambda _context, event_type, message, details=None: planning_events.append(
                        (event_type, message, details)
                    ),
                )
                first_prompt = mocked_run_pass.call_args_list[0].kwargs["prompt"]
                second_prompt = mocked_run_pass.call_args_list[1].kwargs["prompt"]
                outline_text = (context.paths.docs_dir / "PLAN_AGENT_A_OUTLINE.md").read_text(encoding="utf-8")
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual([call.kwargs["pass_type"] for call in mocked_run_pass.call_args_list], ["plan-agent-a-decomposition", "plan-agent-b-packing"])
        self.assertEqual([call.kwargs["reasoning_effort"] for call in mocked_run_pass.call_args_list], ["low", "low"])
        self.assertEqual(
            [item[0] for item in planning_events],
            [
                "plan-started",
                "planner-agent-started",
                "planner-agent-finished",
                "planner-agent-started",
                "planner-agent-finished",
                "plan-finalizing",
            ],
        )
        self.assertEqual(planning_events[1][2]["stage_key"], "planner_a")
        self.assertEqual(planning_events[3][2]["stage_key"], "planner_b")
        self.assertEqual(planning_events[-1][2]["stage_key"], "finalize")
        self.assertIn("Planner Agent A", first_prompt)
        self.assertIn("Freeze the contract", outline_text)
        self.assertIn("Planner Agent A decomposition artifact:", second_prompt)
        self.assertIn('"block_id": "B1"', second_prompt)
        self.assertEqual(plan_state.plan_title, "Dual planner demo")
        self.assertEqual([step.step_id for step in plan_state.steps], ["ST1", "ST2"])
        self.assertIn("If the relevant module, class, or function already exists, update it in place", plan_state.steps[0].codex_description)

    def test_generate_execution_plan_skips_planner_agent_a_in_fast_mode(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_fast_planner_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / "README.md").write_text("README summary " + ("context " * 200), encoding="utf-8")
        (repo_dir / "AGENTS.md").write_text("AGENTS summary " + ("guardrails " * 160), encoding="utf-8")
        (repo_dir / "src").mkdir(parents=True, exist_ok=True)
        (repo_dir / "src" / "planner.py").write_text("def run() -> None:\n    pass\n", encoding="utf-8")
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(
            model="gpt-5.4",
            effort="medium",
            planning_effort="medium",
            execution_mode="parallel",
            use_fast_mode=True,
            test_cmd="python -m pytest",
        )

        try:
            context = orchestrator.workspace.initialize_local_project(project_dir=repo_dir, branch="main", runtime=runtime)
            planning_events: list[tuple[str, str, dict[str, object] | None]] = []
            final_plan_json = """
            {
              "title": "Fast planner demo",
              "summary": "Use the compact outline and emit the final DAG directly.",
              "tasks": [
                {
                  "step_id": "ST1",
                  "task_title": "Implement the planner update",
                  "display_description": "Update the planning path.",
                  "codex_description": "Tighten the planning path while preserving traceability artifacts.",
                  "reasoning_effort": "medium",
                  "depends_on": [],
                  "owned_paths": ["src/planner.py"],
                  "success_criteria": "The planner change is implemented safely."
                }
              ]
            }
            """
            run_result = CodexRunResult(
                pass_type="plan-agent-b-packing",
                prompt_file=context.paths.logs_dir / "b.prompt.md",
                output_file=context.paths.logs_dir / "b.last_message.txt",
                event_file=context.paths.logs_dir / "b.events.jsonl",
                returncode=0,
                search_enabled=False,
                changed_files=[],
                usage={"input_tokens": 12},
                last_message=final_plan_json,
            )

            with mock.patch.object(orchestrator, "setup_local_project", return_value=context), mock.patch(
                "jakal_flow.orchestrator.CodexRunner.run_pass",
                return_value=run_result,
            ) as mocked_run_pass:
                _context, plan_state = orchestrator.generate_execution_plan(
                    project_dir=repo_dir,
                    runtime=runtime,
                    project_prompt="Speed up the planning stage without losing traceability.",
                    max_steps=4,
                    progress_callback=lambda _context, event_type, message, details=None: planning_events.append(
                        (event_type, message, details)
                    ),
                )
                prompt = mocked_run_pass.call_args.kwargs["prompt"]
                outline_text = (context.paths.docs_dir / "PLAN_AGENT_A_OUTLINE.md").read_text(encoding="utf-8")
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(mocked_run_pass.call_count, 1)
        self.assertEqual(mocked_run_pass.call_args.kwargs["pass_type"], "plan-agent-b-packing")
        self.assertIn("Fast planning mode", outline_text)
        self.assertIn('"block_id": "B1"', outline_text)
        self.assertIn("Planner Agent A decomposition artifact:", prompt)
        self.assertIn('"block_id": "B1"', prompt)
        self.assertEqual(
            [item[0] for item in planning_events],
            [
                "plan-started",
                "planner-agent-started",
                "planner-agent-finished",
                "planner-agent-started",
                "planner-agent-finished",
                "plan-finalizing",
            ],
        )
        self.assertTrue(planning_events[2][2]["skipped"])
        self.assertEqual(plan_state.plan_title, "Fast planner demo")
        self.assertEqual([step.step_id for step in plan_state.steps], ["ST1"])

    def test_ensure_gitignore_adds_missing_entries_once(self) -> None:
        project_dir = Path(__file__).resolve().parents[1] / ".tmp_gitignore_test"
        shutil.rmtree(project_dir, ignore_errors=True)
        project_dir.mkdir(parents=True, exist_ok=True)
        gitignore = project_dir / ".gitignore"
        gitignore.write_text("node_modules/\n", encoding="utf-8")

        changed_first = ensure_gitignore(project_dir, entries=[".venv/", "__pycache__/"])
        changed_second = ensure_gitignore(project_dir, entries=[".venv/", "__pycache__/"])
        content = gitignore.read_text(encoding="utf-8")
        shutil.rmtree(project_dir, ignore_errors=True)

        self.assertTrue(changed_first)
        self.assertFalse(changed_second)
        self.assertIn(".venv/", content)
        self.assertIn("__pycache__/", content)

    def test_jsonl_tail_helpers_only_return_recent_entries(self) -> None:
        temp_dir = Path(__file__).resolve().parents[1] / ".tmp_jsonl_tail_test"
        shutil.rmtree(temp_dir, ignore_errors=True)
        temp_dir.mkdir(parents=True, exist_ok=True)
        log_file = temp_dir / "events.jsonl"

        for index in range(1, 6):
            append_jsonl(log_file, {"index": index})

        tail = read_jsonl_tail(log_file, 2)
        last = read_last_jsonl(log_file)
        shutil.rmtree(temp_dir, ignore_errors=True)

        self.assertEqual([item["index"] for item in tail], [4, 5])
        self.assertEqual(last, {"index": 5})

    def test_jsonl_tail_helpers_skip_malformed_lines(self) -> None:
        temp_dir = Path(__file__).resolve().parents[1] / ".tmp_jsonl_tail_test_invalid"
        shutil.rmtree(temp_dir, ignore_errors=True)
        temp_dir.mkdir(parents=True, exist_ok=True)
        log_file = temp_dir / "events.jsonl"
        log_file.write_text('{"index": 1}\nUnexpected token < in JSON\n{"index": 2}\n', encoding="utf-8")

        tail = read_jsonl_tail(log_file, 5)
        last = read_last_jsonl(log_file)
        shutil.rmtree(temp_dir, ignore_errors=True)

        self.assertEqual([item["index"] for item in tail], [1, 2])
        self.assertEqual(last, {"index": 2})

    def test_jsonl_tail_helpers_handle_missing_trailing_newline_and_large_utf8_lines(self) -> None:
        temp_dir = Path(__file__).resolve().parents[1] / ".tmp_jsonl_tail_test_utf8"
        shutil.rmtree(temp_dir, ignore_errors=True)
        temp_dir.mkdir(parents=True, exist_ok=True)
        log_file = temp_dir / "events.jsonl"
        long_message = "가나다라" * 3000
        log_file.write_text(
            "\n".join(
                [
                    json.dumps({"index": 1, "message": "first"}, ensure_ascii=False),
                    json.dumps({"index": 2, "message": long_message}, ensure_ascii=False),
                    json.dumps({"index": 3, "message": "last"}, ensure_ascii=False),
                ]
            ),
            encoding="utf-8",
        )

        tail = read_jsonl_tail(log_file, 2)
        last = read_last_jsonl(log_file)
        shutil.rmtree(temp_dir, ignore_errors=True)

        self.assertEqual([item["index"] for item in tail], [2, 3])
        self.assertEqual(tail[0]["message"], long_message)
        self.assertEqual(last, {"index": 3, "message": "last"})

    def test_jsonl_tail_helpers_skip_malformed_trailing_line_without_scanning_from_start(self) -> None:
        temp_dir = Path(__file__).resolve().parents[1] / ".tmp_jsonl_tail_test_trailing_invalid"
        shutil.rmtree(temp_dir, ignore_errors=True)
        temp_dir.mkdir(parents=True, exist_ok=True)
        log_file = temp_dir / "events.jsonl"
        log_file.write_text('{"index": 1}\n{"index": 2}\n{"index":', encoding="utf-8")

        tail = read_jsonl_tail(log_file, 2)
        last = read_last_jsonl(log_file)
        shutil.rmtree(temp_dir, ignore_errors=True)

        self.assertEqual([item["index"] for item in tail], [1, 2])
        self.assertEqual(last, {"index": 2})


if __name__ == "__main__":
    unittest.main()
