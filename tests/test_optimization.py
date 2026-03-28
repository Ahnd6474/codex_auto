from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import sys
import unittest
from unittest import mock
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jakal_flow.models import CodexRunResult, ExecutionPlanState, ExecutionStep, RuntimeOptions, TestRunResult
from jakal_flow.optimization import scan_optimization_candidates
from jakal_flow.orchestrator import Orchestrator
from jakal_flow.utils import read_jsonl_tail

UTC = getattr(datetime, "UTC", timezone.utc)


def _local_temp_root() -> Path:
    root = Path(__file__).resolve().parents[1] / ".tmp_optimization_tests"
    root.mkdir(parents=True, exist_ok=True)
    return root


class _TemporaryTestDir:
    def __enter__(self) -> Path:
        self.path = _local_temp_root() / f"case_{uuid.uuid4().hex}"
        self.path.mkdir(parents=True, exist_ok=True)
        return self.path

    def __exit__(self, exc_type, exc, tb) -> None:
        shutil.rmtree(self.path, ignore_errors=True)


def _long_python_function() -> str:
    body = "\n".join(f"    total += {index}" for index in range(90))
    return f"def oversized_handler():\n    total = 0\n{body}\n    return total\n"


def _test_result(root: Path, label: str, returncode: int = 0) -> TestRunResult:
    stdout_file = root / f"{label}.stdout.log"
    stderr_file = root / f"{label}.stderr.log"
    stdout_file.write_text("ok\n", encoding="utf-8")
    stderr_file.write_text("" if returncode == 0 else "failed\n", encoding="utf-8")
    return TestRunResult(
        command="python -m pytest",
        returncode=returncode,
        stdout_file=stdout_file,
        stderr_file=stderr_file,
        summary=f"python -m pytest exited with {returncode}",
    )


def _run_result(root: Path, pass_type: str, returncode: int = 0) -> CodexRunResult:
    prompt_file = root / f"{pass_type}.prompt.md"
    output_file = root / f"{pass_type}.last_message.txt"
    event_file = root / f"{pass_type}.events.jsonl"
    prompt_file.write_text("prompt\n", encoding="utf-8")
    output_file.write_text("message\n", encoding="utf-8")
    event_file.write_text("{}\n", encoding="utf-8")
    return CodexRunResult(
        pass_type=pass_type,
        prompt_file=prompt_file,
        output_file=output_file,
        event_file=event_file,
        returncode=returncode,
        search_enabled=False,
        changed_files=[],
        usage={"input_tokens": 1},
        last_message="done",
    )


class OptimizationTests(unittest.TestCase):
    def test_scan_optimization_candidates_flags_large_file_and_long_function(self) -> None:
        with _TemporaryTestDir() as temp_root:
            repo_dir = temp_root / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            (repo_dir / "src").mkdir(parents=True, exist_ok=True)
            (repo_dir / "src" / "demo.py").write_text(_long_python_function(), encoding="utf-8")
            runtime = RuntimeOptions(
                optimization_mode="light",
                optimization_large_file_lines=20,
                optimization_long_function_lines=20,
                optimization_duplicate_block_lines=4,
                optimization_max_files=2,
            )

            result = scan_optimization_candidates(repo_dir, runtime)

        categories = {item.category for item in result.candidates}
        self.assertEqual(result.mode, "light")
        self.assertGreaterEqual(result.scanned_file_count, 1)
        self.assertIn("large_file", categories)
        self.assertIn("multi_responsibility", categories)
        self.assertIn("src/demo.py", result.candidate_files)

    def test_run_execution_closeout_runs_optimization_before_closeout(self) -> None:
        with _TemporaryTestDir() as temp_root:
            workspace_root = temp_root / "workspace"
            repo_dir = temp_root / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            (repo_dir / "README.md").write_text("demo\n", encoding="utf-8")
            (repo_dir / "AGENTS.md").write_text("follow the rules\n", encoding="utf-8")
            (repo_dir / "src").mkdir(parents=True, exist_ok=True)
            (repo_dir / "src" / "demo.py").write_text(_long_python_function(), encoding="utf-8")
            orchestrator = Orchestrator(workspace_root)
            runtime = RuntimeOptions(
                model="gpt-5.4",
                effort="medium",
                test_cmd="python -m pytest",
                optimization_mode="light",
                optimization_large_file_lines=20,
                optimization_long_function_lines=20,
                optimization_max_files=2,
            )
            context = orchestrator.workspace.initialize_local_project(project_dir=repo_dir, branch="main", runtime=runtime)
            context.metadata.current_safe_revision = "safe-revision"
            context.loop_state.current_safe_revision = "safe-revision"
            orchestrator.workspace.save_project(context)
            orchestrator.save_execution_plan_state(
                context,
                ExecutionPlanState(
                    plan_title="Optimization demo",
                    project_prompt="Make the program lighter.",
                    summary="Implementation is complete and ready for cleanup.",
                    default_test_command="python -m pytest",
                    steps=[
                        ExecutionStep(
                            step_id="ST1",
                            title="Finish implementation",
                            status="completed",
                        )
                    ],
                ),
            )

            with mock.patch.object(orchestrator, "setup_local_project", return_value=context), mock.patch(
                "jakal_flow.orchestrator.CodexRunner.run_pass",
                side_effect=[
                    _run_result(workspace_root, "project-optimization-pass"),
                    _run_result(workspace_root, "project-closeout-pass"),
                ],
            ) as mocked_run_pass, mock.patch.object(
                orchestrator,
                "_run_test_command",
                side_effect=[
                    _test_result(workspace_root, "project-optimization-pass"),
                    _test_result(workspace_root, "project-closeout-pass"),
                ],
            ), mock.patch.object(
                orchestrator.git,
                "changed_files",
                side_effect=[["src/demo.py"], []],
            ), mock.patch.object(
                orchestrator.git,
                "has_changes",
                side_effect=[True, False],
            ), mock.patch.object(
                orchestrator.git,
                "commit_all",
                return_value="opt-commit",
            ), mock.patch.object(
                orchestrator.git,
                "remote_url",
                return_value=None,
            ):
                _, plan_state = orchestrator.run_execution_closeout(repo_dir, runtime)

            block_entries = read_jsonl_tail(context.paths.block_log_file, 5)

        self.assertEqual(plan_state.closeout_status, "completed")
        self.assertEqual(context.metadata.current_safe_revision, "opt-commit")
        self.assertEqual([call.kwargs["pass_type"] for call in mocked_run_pass.call_args_list], ["project-optimization-pass", "project-closeout-pass"])
        self.assertEqual([item["status"] for item in block_entries], ["optimization_completed", "closeout_completed"])

    def test_run_execution_closeout_continues_after_failed_optimization_pass(self) -> None:
        with _TemporaryTestDir() as temp_root:
            workspace_root = temp_root / "workspace"
            repo_dir = temp_root / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            (repo_dir / "README.md").write_text("demo\n", encoding="utf-8")
            (repo_dir / "AGENTS.md").write_text("follow the rules\n", encoding="utf-8")
            (repo_dir / "src").mkdir(parents=True, exist_ok=True)
            (repo_dir / "src" / "demo.py").write_text(_long_python_function(), encoding="utf-8")
            orchestrator = Orchestrator(workspace_root)
            runtime = RuntimeOptions(
                model="gpt-5.4",
                effort="medium",
                test_cmd="python -m pytest",
                optimization_mode="light",
                optimization_large_file_lines=20,
                optimization_long_function_lines=20,
                optimization_max_files=2,
            )
            context = orchestrator.workspace.initialize_local_project(project_dir=repo_dir, branch="main", runtime=runtime)
            context.metadata.current_safe_revision = "safe-revision"
            context.loop_state.current_safe_revision = "safe-revision"
            orchestrator.workspace.save_project(context)
            orchestrator.save_execution_plan_state(
                context,
                ExecutionPlanState(
                    plan_title="Optimization demo",
                    project_prompt="Make the program lighter.",
                    summary="Implementation is complete and ready for cleanup.",
                    default_test_command="python -m pytest",
                    steps=[
                        ExecutionStep(
                            step_id="ST1",
                            title="Finish implementation",
                            status="completed",
                        )
                    ],
                ),
            )

            with mock.patch.object(orchestrator, "setup_local_project", return_value=context), mock.patch(
                "jakal_flow.orchestrator.CodexRunner.run_pass",
                side_effect=[
                    _run_result(workspace_root, "project-optimization-pass", returncode=1),
                    _run_result(workspace_root, "project-closeout-pass"),
                ],
            ), mock.patch.object(
                orchestrator,
                "_run_test_command",
                side_effect=[_test_result(workspace_root, "project-closeout-pass")],
            ), mock.patch.object(
                orchestrator.git,
                "changed_files",
                side_effect=[["src/demo.py"], []],
            ), mock.patch.object(
                orchestrator.git,
                "has_changes",
                return_value=False,
            ), mock.patch.object(
                orchestrator.git,
                "remote_url",
                return_value=None,
            ), mock.patch.object(
                orchestrator.git,
                "hard_reset",
            ) as mocked_reset:
                _, plan_state = orchestrator.run_execution_closeout(repo_dir, runtime)

            pass_entries = read_jsonl_tail(context.paths.pass_log_file, 5)

        self.assertEqual(plan_state.closeout_status, "completed")
        self.assertGreaterEqual(mocked_reset.call_count, 1)
        self.assertEqual(pass_entries[0]["pass_type"], "project-optimization-pass")
        self.assertEqual(pass_entries[0]["rollback_status"], "rolled_back_to_safe_revision")
        self.assertEqual(pass_entries[1]["pass_type"], "project-closeout-pass")

    def test_run_execution_closeout_recovers_stale_running_state(self) -> None:
        with _TemporaryTestDir() as temp_root:
            workspace_root = temp_root / "workspace"
            repo_dir = temp_root / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            (repo_dir / "README.md").write_text("demo\n", encoding="utf-8")
            orchestrator = Orchestrator(workspace_root)
            runtime = RuntimeOptions(
                model="gpt-5.4",
                effort="medium",
                test_cmd="python -m pytest",
            )
            context = orchestrator.workspace.initialize_local_project(project_dir=repo_dir, branch="main", runtime=runtime)
            stale_time = (datetime.now(tz=UTC) - timedelta(hours=7)).replace(microsecond=0).isoformat()
            context.metadata.current_status = "running:closeout"
            context.metadata.last_run_at = stale_time
            context.metadata.current_safe_revision = "safe-revision"
            context.loop_state.current_safe_revision = "safe-revision"
            orchestrator.workspace.save_project(context)
            orchestrator.save_execution_plan_state(
                context,
                ExecutionPlanState(
                    plan_title="Closeout recovery demo",
                    project_prompt="Ship the repo safely.",
                    summary="Implementation is complete.",
                    default_test_command="python -m pytest",
                    closeout_status="running",
                    closeout_started_at=stale_time,
                    closeout_notes="Original closeout never finished.",
                    steps=[ExecutionStep(step_id="ST1", title="Finish implementation", status="completed")],
                ),
            )

            with mock.patch.object(orchestrator, "setup_local_project", return_value=context), mock.patch(
                "jakal_flow.orchestrator.CodexRunner.run_pass",
                return_value=_run_result(workspace_root, "project-closeout-pass"),
            ), mock.patch.object(
                orchestrator,
                "_run_test_command",
                return_value=_test_result(workspace_root, "project-closeout-pass"),
            ), mock.patch.object(
                orchestrator.git,
                "changed_files",
                return_value=[],
            ), mock.patch.object(
                orchestrator.git,
                "has_changes",
                return_value=False,
            ), mock.patch.object(
                orchestrator.git,
                "remote_url",
                return_value=None,
            ):
                _, plan_state = orchestrator.run_execution_closeout(repo_dir, runtime)

        self.assertEqual(plan_state.closeout_status, "completed")
        self.assertNotEqual(plan_state.closeout_started_at, stale_time)
        self.assertEqual(context.metadata.current_status, "closed_out")

    def test_run_execution_closeout_rejects_recent_running_state(self) -> None:
        with _TemporaryTestDir() as temp_root:
            workspace_root = temp_root / "workspace"
            repo_dir = temp_root / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            (repo_dir / "README.md").write_text("demo\n", encoding="utf-8")
            orchestrator = Orchestrator(workspace_root)
            runtime = RuntimeOptions(
                model="gpt-5.4",
                effort="medium",
                test_cmd="python -m pytest",
            )
            context = orchestrator.workspace.initialize_local_project(project_dir=repo_dir, branch="main", runtime=runtime)
            recent_time = datetime.now(tz=UTC).replace(microsecond=0).isoformat()
            context.metadata.current_status = "running:closeout"
            context.metadata.last_run_at = recent_time
            orchestrator.workspace.save_project(context)
            orchestrator.save_execution_plan_state(
                context,
                ExecutionPlanState(
                    plan_title="Closeout recovery demo",
                    project_prompt="Ship the repo safely.",
                    summary="Implementation is complete.",
                    default_test_command="python -m pytest",
                    closeout_status="running",
                    closeout_started_at=recent_time,
                    steps=[ExecutionStep(step_id="ST1", title="Finish implementation", status="completed")],
                ),
            )

            with mock.patch.object(orchestrator, "setup_local_project", return_value=context):
                with self.assertRaisesRegex(RuntimeError, "Closeout is already running."):
                    orchestrator.run_execution_closeout(repo_dir, runtime)
            saved_state = orchestrator.load_execution_plan_state(context)
            self.assertEqual(saved_state.closeout_status, "running")

    def test_load_execution_plan_state_recovers_stale_closeout_before_retry(self) -> None:
        with _TemporaryTestDir() as temp_root:
            workspace_root = temp_root / "workspace"
            repo_dir = temp_root / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            orchestrator = Orchestrator(workspace_root)
            runtime = RuntimeOptions(
                model="gpt-5.4",
                effort="medium",
                test_cmd="python -m pytest",
            )
            context = orchestrator.workspace.initialize_local_project(project_dir=repo_dir, branch="main", runtime=runtime)
            stale_time = (datetime.now(tz=UTC) - timedelta(hours=7)).replace(microsecond=0).isoformat()
            context.metadata.current_status = "running:closeout"
            context.metadata.last_run_at = stale_time
            orchestrator.workspace.save_project(context)
            report_path = context.paths.reports_dir / "20260328000000_closeout_failed.prfail.md"
            report_path.write_text("closeout failure details\n", encoding="utf-8")
            (context.paths.reports_dir / "latest_pr_failure_status.json").write_text(
                (
                    "{"
                    f"\"generated_at\": \"{stale_time}\", "
                    "\"failure_type\": \"closeout_failed\", "
                    f"\"report_markdown_file\": \"{str(report_path).replace('\\', '\\\\')}\""
                    "}"
                ),
                encoding="utf-8",
            )
            orchestrator.save_execution_plan_state(
                context,
                ExecutionPlanState(
                    plan_title="Closeout recovery demo",
                    project_prompt="Ship the repo safely.",
                    summary="Implementation is complete.",
                    default_test_command="python -m pytest",
                    closeout_status="running",
                    closeout_started_at=stale_time,
                    steps=[ExecutionStep(step_id="ST1", title="Finish implementation", status="completed")],
                ),
            )

            saved_state = orchestrator.load_execution_plan_state(context)

        self.assertEqual(saved_state.closeout_status, "failed")
        self.assertIn("Closeout appears to have stopped before it finished", saved_state.closeout_notes)
        self.assertIn(str(report_path), saved_state.closeout_notes)
        self.assertEqual(context.metadata.current_status, "closeout_failed")


if __name__ == "__main__":
    unittest.main()
