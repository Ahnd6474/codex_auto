from __future__ import annotations

import importlib
from types import SimpleNamespace
import unittest
from pathlib import Path
import shutil
import sys
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jakal_flow.environment import ensure_gitignore
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
from jakal_flow.models import CandidateTask, CodexRunResult, CommandResult, ExecutionPlanState, ExecutionStep, RuntimeOptions, TestRunResult
from jakal_flow.orchestrator import Orchestrator
from jakal_flow.planning import (
    DEBUGGER_PARALLEL_PROMPT_FILENAME,
    DEBUGGER_PROMPT_FILENAME,
    DEBUGGER_SERIAL_PROMPT_FILENAME,
    FINALIZATION_PROMPT_FILENAME,
    PLAN_GENERATION_PARALLEL_PROMPT_FILENAME,
    PLAN_GENERATION_PROMPT_FILENAME,
    PLAN_GENERATION_SERIAL_PROMPT_FILENAME,
    REFERENCE_GUIDE_FILENAME,
    SCOPE_GUARD_TEMPLATE_FILENAME,
    STEP_EXECUTION_PARALLEL_PROMPT_FILENAME,
    STEP_EXECUTION_PROMPT_FILENAME,
    STEP_EXECUTION_SERIAL_PROMPT_FILENAME,
    bootstrap_plan_prompt,
    execution_plan_svg,
    load_debugger_prompt_template,
    load_plan_generation_prompt_template,
    load_reference_guide_text,
    load_source_prompt_template,
    load_step_execution_prompt_template,
    parse_execution_plan_response,
    prompt_to_execution_plan_prompt,
    scan_repository_inputs,
    source_prompt_template_path,
)
from jakal_flow.reporting import Reporter
from jakal_flow.utils import append_jsonl, read_jsonl_tail, read_last_jsonl


class ExecutionPlanHelperTests(unittest.TestCase):
    def test_legacy_codex_auto_namespace_aliases_new_package(self) -> None:
        legacy_planning = importlib.import_module("codex_auto.planning")
        renamed_planning = importlib.import_module("jakal_flow.planning")

        self.assertEqual(legacy_planning.REFERENCE_GUIDE_DISPLAY_PATH, renamed_planning.REFERENCE_GUIDE_DISPLAY_PATH)

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

    def test_execution_plan_state_reads_closeout_fields(self) -> None:
        state = ExecutionPlanState.from_dict(
            {
                "plan_title": "demo",
                "execution_mode": "parallel",
                "closeout_status": "completed",
                "closeout_started_at": "2026-01-01T00:00:00+00:00",
                "closeout_completed_at": "2026-01-01T01:00:00+00:00",
                "closeout_commit_hash": "abc123",
                "closeout_notes": "final tests passed",
                "steps": [],
            }
        )

        self.assertEqual(state.execution_mode, "parallel")
        self.assertEqual(state.closeout_status, "completed")
        self.assertEqual(state.closeout_commit_hash, "abc123")
        self.assertEqual(state.closeout_notes, "final tests passed")

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

    def test_pending_execution_batches_splits_conflicting_owned_paths(self) -> None:
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

        self.assertEqual([[step.step_id for step in batch] for batch in batches], [["ST2"], ["ST3", "ST4"]])

    def test_save_execution_plan_state_clears_dag_fields_in_serial_mode(self) -> None:
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
                            )
                        ],
                    ),
                )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(context.runtime.execution_mode, "serial")
        self.assertEqual(plan_state.execution_mode, "serial")
        self.assertEqual(plan_state.steps[0].parallel_group, "")
        self.assertEqual(plan_state.steps[0].depends_on, [])
        self.assertEqual(plan_state.steps[0].owned_paths, [])

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

    def test_execute_pass_invokes_debugger_with_failure_logs_and_recovers(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_step_debugger_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", test_cmd="python -m pytest")

        try:
            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"):
                context, saved = orchestrator.update_execution_plan(
                    project_dir=repo_dir,
                    runtime=runtime,
                    plan_state=ExecutionPlanState(
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
            runner.run_pass.side_effect = [
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
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(commit_hash, "debug-commit")
        self.assertIsNotNone(test_result)
        self.assertEqual(test_result.returncode, 0)
        self.assertIn("after debugger recovery", test_result.summary)
        self.assertEqual(run_result.changed_files, ["src/app.py", "src/fix.py"])
        mocked_commit.assert_called_once()
        mocked_reset.assert_not_called()
        debugger_prompt_text = runner.run_pass.call_args_list[1].kwargs["prompt"]
        self.assertIn("Implement fix", debugger_prompt_text)
        self.assertIn("AssertionError: expected value", debugger_prompt_text)
        self.assertIn("Traceback: test failure details", debugger_prompt_text)
        self.assertIn("Do not modify tests unless", debugger_prompt_text)
        pass_entries = read_jsonl_tail(context.paths.pass_log_file, 5)
        self.assertEqual([item["pass_type"] for item in pass_entries], ["block-search-pass", "block-search-debug"])
        self.assertEqual(pass_entries[0]["rollback_status"], "debugger_invoked")
        self.assertEqual(pass_entries[1]["rollback_status"], "not_needed")

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

        try:
            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"):
                orchestrator.update_execution_plan(
                    project_dir=repo_dir,
                    runtime=runtime,
                    plan_state=ExecutionPlanState(
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
            ), mock.patch("jakal_flow.orchestrator.CodexRunner.run_pass") as mocked_run_pass:
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
                context, _plan_state, steps = orchestrator.run_parallel_execution_batch(
                    project_dir=repo_dir,
                    runtime=runtime,
                    step_ids=["ST1", "ST2"],
                )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual([step.status for step in steps], ["completed", "completed"])
        self.assertEqual(context.metadata.current_status, "plan_completed")
        self.assertEqual(context.metadata.current_safe_revision, "parallel-debug-commit")
        debug_prompt_text = mocked_run_pass.call_args.kwargs["prompt"]
        self.assertIn("Recover merged parallel batch ST1, ST2", debug_prompt_text)
        self.assertIn("integration assertion failed", debug_prompt_text)
        self.assertIn("parallel batch traceback", debug_prompt_text)
        self.assertIn("Do not modify tests unless", debug_prompt_text)

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
        serial_plan_template = load_source_prompt_template(PLAN_GENERATION_SERIAL_PROMPT_FILENAME)
        parallel_plan_template = load_source_prompt_template(PLAN_GENERATION_PARALLEL_PROMPT_FILENAME)
        serial_step_template = load_source_prompt_template(STEP_EXECUTION_SERIAL_PROMPT_FILENAME)
        parallel_step_template = load_source_prompt_template(STEP_EXECUTION_PARALLEL_PROMPT_FILENAME)
        serial_debugger_template = load_source_prompt_template(DEBUGGER_SERIAL_PROMPT_FILENAME)
        parallel_debugger_template = load_source_prompt_template(DEBUGGER_PARALLEL_PROMPT_FILENAME)
        final_template = load_source_prompt_template(FINALIZATION_PROMPT_FILENAME)
        scope_template = load_source_prompt_template(SCOPE_GUARD_TEMPLATE_FILENAME)

        self.assertTrue(source_prompt_template_path(PLAN_GENERATION_PROMPT_FILENAME).exists())
        self.assertTrue(source_prompt_template_path(PLAN_GENERATION_PARALLEL_PROMPT_FILENAME).exists())
        self.assertTrue(source_prompt_template_path(STEP_EXECUTION_PROMPT_FILENAME).exists())
        self.assertTrue(source_prompt_template_path(STEP_EXECUTION_PARALLEL_PROMPT_FILENAME).exists())
        self.assertTrue(source_prompt_template_path(DEBUGGER_PROMPT_FILENAME).exists())
        self.assertTrue(source_prompt_template_path(DEBUGGER_PARALLEL_PROMPT_FILENAME).exists())
        self.assertTrue(source_prompt_template_path(FINALIZATION_PROMPT_FILENAME).exists())
        self.assertTrue(source_prompt_template_path(SCOPE_GUARD_TEMPLATE_FILENAME).exists())
        self.assertTrue(source_prompt_template_path(REFERENCE_GUIDE_FILENAME).exists())
        self.assertIn("{repo_dir}", serial_plan_template)
        self.assertIn("{user_prompt}", serial_plan_template)
        self.assertIn("{max_steps}", serial_plan_template)
        self.assertIn("{execution_mode}", serial_plan_template)
        self.assertIn('"step_id": "stable id like ST1"', serial_plan_template)
        self.assertIn("strict sequential checkpoint list", serial_plan_template)
        self.assertIn('"step_id": "stable id like ST1"', parallel_plan_template)
        self.assertIn('"depends_on": ["step ids that must complete first"]', parallel_plan_template)
        self.assertIn('"owned_paths": ["repo-relative paths or directories this step primarily owns"]', parallel_plan_template)
        self.assertIn("DAG execution tree", parallel_plan_template)
        self.assertIn("{reference_notes}", parallel_plan_template)
        self.assertIn("src/jakal_flow/docs/REFERENCE_GUIDE.md", parallel_plan_template)
        self.assertIn("{task_title}", serial_step_template)
        self.assertIn("{display_description}", serial_step_template)
        self.assertIn("{codex_description}", serial_step_template)
        self.assertIn("{success_criteria}", serial_step_template)
        self.assertIn("{depends_on}", serial_step_template)
        self.assertIn("{owned_paths}", serial_step_template)
        self.assertIn("{plan_snapshot}", serial_step_template)
        self.assertIn("saved DAG execution tree", parallel_step_template)
        self.assertIn("primary write scope", parallel_step_template)
        self.assertIn("{failing_test_summary}", serial_debugger_template)
        self.assertIn("{failing_test_stdout}", serial_debugger_template)
        self.assertIn("Do not modify tests unless", serial_debugger_template)
        self.assertIn("{owned_paths}", parallel_debugger_template)
        self.assertIn("merged parallel batch", parallel_debugger_template)
        self.assertEqual(load_plan_generation_prompt_template("serial"), serial_plan_template)
        self.assertEqual(load_plan_generation_prompt_template("parallel"), parallel_plan_template)
        self.assertEqual(load_step_execution_prompt_template("serial"), serial_step_template)
        self.assertEqual(load_step_execution_prompt_template("parallel"), parallel_step_template)
        self.assertEqual(load_debugger_prompt_template("serial"), serial_debugger_template)
        self.assertEqual(load_debugger_prompt_template("parallel"), parallel_debugger_template)
        self.assertIn("{completed_steps}", final_template)
        self.assertIn("{closeout_report_file}", final_template)
        self.assertIn("{test_command}", final_template)
        self.assertIn("{repo_url}", scope_template)

    def test_scan_repository_inputs_and_source_reference_guide_feed_planning_prompts(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_reference_notes_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        repo_dir = temp_root / "repo"
        (repo_dir / "docs").mkdir(parents=True, exist_ok=True)
        (repo_dir / "README.md").write_text("README summary", encoding="utf-8")
        (repo_dir / "AGENTS.md").write_text("AGENTS summary", encoding="utf-8")
        (repo_dir / "docs" / "notes.md").write_text("docs summary", encoding="utf-8")

        try:
            repo_inputs = scan_repository_inputs(repo_dir)
            self.assertIn("notes.md", repo_inputs["docs"])
            reference_notes = load_reference_guide_text()
            self.assertIn("React + Tauri", reference_notes)

            context = SimpleNamespace(
                paths=SimpleNamespace(repo_dir=repo_dir, plan_file=temp_root / "managed-docs" / "PLAN.md"),
                metadata=SimpleNamespace(
                    repo_url="https://github.com/example/project.git",
                    branch="main",
                ),
            )
            plan_prompt = prompt_to_execution_plan_prompt(context, repo_inputs, "Build a desktop flow screen.", 4, "parallel")
            bootstrap_prompt = bootstrap_plan_prompt(context, repo_inputs, "Build a desktop flow screen.")
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertIn("Use the following priority order while planning:", plan_prompt)
        self.assertIn("Requested execution mode:", plan_prompt)
        self.assertIn("parallel", plan_prompt)
        self.assertIn("step_id", plan_prompt)
        self.assertIn("depends_on", plan_prompt)
        self.assertIn("owned_paths", plan_prompt)
        self.assertIn("src/jakal_flow/docs/REFERENCE_GUIDE.md", plan_prompt)
        self.assertIn("React + Tauri", plan_prompt)
        self.assertIn("1. Follow AGENTS.md and explicit repository constraints first.", bootstrap_prompt)
        self.assertIn("src/jakal_flow/docs/REFERENCE_GUIDE.md", bootstrap_prompt)
        self.assertIn("React + Tauri", bootstrap_prompt)

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


if __name__ == "__main__":
    unittest.main()
