from __future__ import annotations

from pathlib import Path
import shutil
import sys
import unittest
from unittest import mock
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jakal_flow.models import ExecutionPlanState, ExecutionStep, RuntimeOptions
from jakal_flow.orchestrator import Orchestrator


def _local_temp_root() -> Path:
    root = Path(__file__).resolve().parents[1] / ".tmp_reviewer_flow_tests"
    root.mkdir(parents=True, exist_ok=True)
    return root


class _TemporaryTestDir:
    def __enter__(self) -> Path:
        self.path = _local_temp_root() / f"case_{uuid.uuid4().hex}"
        self.path.mkdir(parents=True, exist_ok=True)
        return self.path

    def __exit__(self, exc_type, exc, tb) -> None:
        shutil.rmtree(self.path, ignore_errors=True)


def _runtime() -> RuntimeOptions:
    return RuntimeOptions(
        model="gpt-5.4",
        effort="medium",
        test_cmd="python -m pytest",
        max_blocks=4,
    )


def _seed_repo(repo_dir: Path) -> None:
    repo_dir.mkdir(parents=True, exist_ok=True)
    (repo_dir / "README.md").write_text("demo\n", encoding="utf-8")
    (repo_dir / "AGENTS.md").write_text("follow the rules\n", encoding="utf-8")


class ReviewerFlowTests(unittest.TestCase):
    def test_run_execution_closeout_backfills_reviewer_a_for_completed_legacy_plan(self) -> None:
        with _TemporaryTestDir() as temp_root:
            workspace_root = temp_root / "workspace"
            repo_dir = temp_root / "repo"
            _seed_repo(repo_dir)
            orchestrator = Orchestrator(workspace_root)
            runtime = _runtime()
            context = orchestrator.workspace.initialize_local_project(project_dir=repo_dir, branch="main", runtime=runtime)
            saved = orchestrator.save_execution_plan_state(
                context,
                ExecutionPlanState(
                    plan_title="Legacy completed plan",
                    project_prompt="Ship the repo.",
                    summary="All implementation steps finished before Reviewer A existed.",
                    default_test_command="python -m pytest",
                    steps=[ExecutionStep(step_id="ST1", title="Done", status="completed")],
                ),
            )

            def fake_run_pre_execution_review(*args, **kwargs):
                review_context = orchestrator.setup_local_project(project_dir=repo_dir, runtime=runtime, branch="main", origin_url="")
                review_state = orchestrator.load_execution_plan_state(review_context)
                review_state.reviewer_a_status = "completed"
                review_state.reviewer_a_verdict = "READY_TO_EXECUTE"
                review_state.reviewer_a_plan_signature = orchestrator._plan_review_signature(review_state)
                review_state.reviewer_a_notes = "Legacy plan backfilled."
                review_state = orchestrator.save_execution_plan_state(review_context, review_state)
                return review_context, review_state

            with mock.patch.object(orchestrator, "run_pre_execution_review", side_effect=fake_run_pre_execution_review) as mocked_review, mock.patch.object(
                orchestrator.git,
                "current_revision",
                return_value="safe-revision",
            ), mock.patch.object(
                orchestrator,
                "_reusable_closeout_result",
                return_value=None,
            ), mock.patch.object(
                orchestrator,
                "_run_optional_closeout_optimization",
                side_effect=lambda **kwargs: (kwargs["safe_revision"], kwargs["block_index"]),
            ), mock.patch.object(
                orchestrator,
                "_execute_verified_repo_pass",
                return_value={
                    "success": True,
                    "notes": "closeout ok",
                    "run_result": None,
                    "test_result": None,
                    "commit_hash": "closeout-commit",
                    "changed_files": [],
                    "rollback_status": "not_needed",
                    "safe_revision": "closeout-commit",
                },
            ), mock.patch.object(
                orchestrator,
                "_execute_workspace_gate_pass",
                return_value={
                    "success": True,
                    "notes": "ship",
                    "run_result": None,
                    "test_result": None,
                    "commit_hash": None,
                    "changed_files": [],
                    "rollback_status": "not_needed",
                    "safe_revision": "closeout-commit",
                    "reviewer_b_decision": "SHIP",
                    "next_cycle_prompt": "",
                },
            ), mock.patch.object(
                orchestrator,
                "_record_repo_pass",
            ), mock.patch.object(
                orchestrator,
                "_record_reviewer_pass",
            ), mock.patch.object(
                orchestrator,
                "_publish_closeout_pull_request",
                return_value={"created": False},
            ):
                _, result = orchestrator.run_execution_closeout(repo_dir, runtime)

        self.assertEqual(saved.reviewer_a_status, "not_started")
        self.assertTrue(mocked_review.called)
        self.assertEqual(result.reviewer_a_status, "completed")
        self.assertEqual(result.closeout_status, "completed")
        self.assertEqual(result.reviewer_b_decision, "SHIP")

    def test_prepare_pre_execution_cycle_consumes_persisted_reviewer_a_replan(self) -> None:
        with _TemporaryTestDir() as temp_root:
            workspace_root = temp_root / "workspace"
            repo_dir = temp_root / "repo"
            _seed_repo(repo_dir)
            orchestrator = Orchestrator(workspace_root)
            runtime = _runtime()
            context = orchestrator.workspace.initialize_local_project(project_dir=repo_dir, branch="main", runtime=runtime)
            base_state = orchestrator.save_execution_plan_state(
                context,
                ExecutionPlanState(
                    plan_title="Needs replanning",
                    project_prompt="Refine the execution DAG.",
                    summary="Reviewer A should request a tighter plan.",
                    default_test_command="python -m pytest",
                    steps=[ExecutionStep(step_id="ST1", title="Pending", status="pending")],
                ),
            )
            base_state.reviewer_a_status = "replan_required"
            base_state.reviewer_a_verdict = "REPLAN"
            base_state.reviewer_a_plan_signature = orchestrator._plan_review_signature(base_state)
            base_state.replan_required = True
            base_state.next_cycle_prompt = "Replan around the tighter requirement."
            orchestrator.save_execution_plan_state(context, base_state)

            replanned_state = ExecutionPlanState(
                plan_title="Replanned",
                project_prompt="Replan around the tighter requirement.",
                summary="New DAG",
                default_test_command="python -m pytest",
                steps=[ExecutionStep(step_id="ST1", title="New step", status="pending")],
            )

            with mock.patch.object(
                orchestrator,
                "generate_execution_plan",
                return_value=(context, replanned_state),
            ) as mocked_generate, mock.patch.object(
                orchestrator,
                "run_pre_execution_review",
                side_effect=AssertionError("Reviewer A should not rerun when a persisted replan is present."),
            ):
                next_context, next_plan, continued, reason = orchestrator.prepare_pre_execution_cycle(
                    project_dir=repo_dir,
                    runtime=runtime,
                )

        self.assertTrue(continued)
        self.assertEqual(reason, "")
        self.assertIs(next_context, context)
        self.assertIs(next_plan, replanned_state)
        mocked_generate.assert_called_once()

    def test_prepare_post_closeout_cycle_consumes_persisted_reviewer_b_replan(self) -> None:
        with _TemporaryTestDir() as temp_root:
            workspace_root = temp_root / "workspace"
            repo_dir = temp_root / "repo"
            _seed_repo(repo_dir)
            orchestrator = Orchestrator(workspace_root)
            runtime = _runtime()
            context = orchestrator.workspace.initialize_local_project(project_dir=repo_dir, branch="main", runtime=runtime)
            base_state = orchestrator.save_execution_plan_state(
                context,
                ExecutionPlanState(
                    plan_title="Closeout replan",
                    project_prompt="Ship safely.",
                    summary="Reviewer B should request another cycle.",
                    default_test_command="python -m pytest",
                    steps=[ExecutionStep(step_id="ST1", title="Done", status="completed")],
                ),
            )
            plan_signature = orchestrator._plan_review_signature(base_state)
            base_state.reviewer_a_status = "completed"
            base_state.reviewer_a_verdict = "READY_TO_EXECUTE"
            base_state.reviewer_a_plan_signature = plan_signature
            base_state.closeout_status = "replan_required"
            base_state.reviewer_b_status = "replan_required"
            base_state.reviewer_b_decision = "REPLAN"
            base_state.reviewer_b_plan_signature = plan_signature
            base_state.replan_required = True
            base_state.next_cycle_prompt = "Generate a narrower follow-up cycle."
            orchestrator.save_execution_plan_state(context, base_state)

            replanned_state = ExecutionPlanState(
                plan_title="Cycle 2",
                project_prompt="Generate a narrower follow-up cycle.",
                summary="Follow-up DAG",
                default_test_command="python -m pytest",
                steps=[ExecutionStep(step_id="ST1", title="Follow-up", status="pending")],
            )

            with mock.patch.object(
                orchestrator,
                "generate_execution_plan",
                return_value=(context, replanned_state),
            ) as mocked_generate:
                next_context, next_plan, continued, reason = orchestrator.prepare_post_closeout_cycle(
                    project_dir=repo_dir,
                    runtime=runtime,
                )

        self.assertTrue(continued)
        self.assertEqual(reason, "")
        self.assertIs(next_context, context)
        self.assertIs(next_plan, replanned_state)
        mocked_generate.assert_called_once()

    def test_update_execution_plan_invalidates_reviewer_state_when_structure_changes(self) -> None:
        with _TemporaryTestDir() as temp_root:
            workspace_root = temp_root / "workspace"
            repo_dir = temp_root / "repo"
            _seed_repo(repo_dir)
            orchestrator = Orchestrator(workspace_root)
            runtime = _runtime()
            context = orchestrator.workspace.initialize_local_project(project_dir=repo_dir, branch="main", runtime=runtime)
            initial_state = orchestrator.save_execution_plan_state(
                context,
                ExecutionPlanState(
                    plan_title="Original plan",
                    project_prompt="Implement the feature.",
                    summary="Original DAG",
                    default_test_command="python -m pytest",
                    closeout_status="completed",
                    steps=[ExecutionStep(step_id="ST1", title="Done", success_criteria="Old criteria", status="completed")],
                ),
            )
            plan_signature = orchestrator._plan_review_signature(initial_state)
            initial_state.reviewer_a_status = "completed"
            initial_state.reviewer_a_verdict = "READY_TO_EXECUTE"
            initial_state.reviewer_a_plan_signature = plan_signature
            initial_state.reviewer_b_status = "completed"
            initial_state.reviewer_b_decision = "SHIP"
            initial_state.reviewer_b_plan_signature = plan_signature
            initial_state.replan_required = True
            initial_state.next_cycle_prompt = "stale prompt"
            initial_state.closeout_status = "completed"
            orchestrator.save_execution_plan_state(context, initial_state)

            for path in (
                context.paths.requirements_matrix_file,
                context.paths.global_test_plan_file,
                context.paths.test_strength_report_file,
                context.paths.reviewer_a_verdict_file,
                context.paths.reviewer_b_decision_file,
                context.paths.replan_packet_file,
            ):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}", encoding="utf-8")

            modified_state = orchestrator.load_execution_plan_state(context)
            modified_state.steps[0].success_criteria = "New criteria"
            _updated_context, updated_state = orchestrator.update_execution_plan(
                project_dir=repo_dir,
                runtime=runtime,
                plan_state=modified_state,
            )
            requirements_matrix_exists = context.paths.requirements_matrix_file.exists()
            reviewer_b_decision_exists = context.paths.reviewer_b_decision_file.exists()

        self.assertEqual(updated_state.reviewer_a_status, "not_started")
        self.assertEqual(updated_state.reviewer_a_verdict, "")
        self.assertEqual(updated_state.reviewer_b_status, "not_started")
        self.assertEqual(updated_state.reviewer_b_decision, "")
        self.assertEqual(updated_state.closeout_status, "not_started")
        self.assertFalse(updated_state.replan_required)
        self.assertEqual(updated_state.next_cycle_prompt, "")
        self.assertFalse(requirements_matrix_exists)
        self.assertFalse(reviewer_b_decision_exists)


if __name__ == "__main__":
    unittest.main()
