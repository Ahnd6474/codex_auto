import shutil
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jakal_flow.models import ExecutionStep, RuntimeOptions
from jakal_flow.orchestrator import Orchestrator
from jakal_flow.step_models import GEMINI_DEFAULT_MODEL


class OrchestratorParallelTests(unittest.TestCase):
    def test_parallel_step_worker_fails_fast_when_gemini_auth_is_missing(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_parallel_worker_gemini_preflight_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", test_cmd="python -m pytest", execution_mode="parallel")

        try:
            context = orchestrator.workspace.initialize_local_project(project_dir=repo_dir, branch="main", runtime=runtime)
            with mock.patch(
                "jakal_flow.step_models._command_available",
                return_value=True,
            ), mock.patch(
                "jakal_flow.step_models._gemini_auth_env_configured",
                return_value=False,
            ), mock.patch(
                "jakal_flow.step_models._gemini_settings_file_configured",
                return_value=False,
            ), mock.patch.object(
                orchestrator,
                "_build_parallel_worker_context",
                side_effect=AssertionError("worker context should not be created before auth preflight passes"),
            ):
                result = orchestrator._run_parallel_step_worker(
                    context,
                    runtime,
                    ExecutionStep(
                        step_id="ST2",
                        title="Explicit Gemini slice",
                        model_provider="gemini",
                        model=GEMINI_DEFAULT_MODEL,
                        test_command="python -m pytest",
                    ),
                    "safe-revision",
                    "batch-token",
                    1,
                )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(result["status"], "failed")
        self.assertIn("Please set an Auth method", result["notes"])
        self.assertEqual(result["failure_type"], "ExecutionPreflightError")
        self.assertEqual(result["failure_reason_code"], "preflight_failed")

    def test_build_parallel_worker_paths_includes_lineage_state_file(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_parallel_worker_paths_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(
            model="gpt-5.4",
            effort="medium",
            execution_mode="parallel",
        )

        try:
            context = orchestrator.workspace.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=runtime,
            )
            worker_paths = orchestrator._build_parallel_worker_paths(
                context,
                batch_token="batch-demo",
                worker_slug="01-st1",
                worktree_dir=repo_dir,
            )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(worker_paths.lineage_state_file, worker_paths.state_dir / "LINEAGES.json")
        self.assertEqual(worker_paths.logs_dir, repo_dir.resolve() / "jakal-flow-logs")

    def test_copy_parallel_worker_support_files_skips_parent_state_caches(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_parallel_worker_support_files_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        worker_repo_dir = temp_root / "worker-repo"
        worker_repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", execution_mode="parallel")

        try:
            context = orchestrator.workspace.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=runtime,
            )
            (context.paths.docs_dir / "PLAN.md").write_text("parent plan\n", encoding="utf-8")
            (context.paths.memory_dir / "task_summaries.jsonl").write_text("{}\n", encoding="utf-8")
            context.paths.execution_plan_file.write_text('{"steps":[]}\n', encoding="utf-8")
            context.paths.checkpoint_state_file.write_text('{"checkpoints":[]}\n', encoding="utf-8")
            context.paths.lineage_state_file.write_text('{"lineages":[]}\n', encoding="utf-8")
            context.paths.spine_file.write_text('{"version":"1"}\n', encoding="utf-8")
            context.paths.common_requirements_file.write_text('{"files":[]}\n', encoding="utf-8")
            context.paths.contract_wave_audit_file.write_text("{}\n", encoding="utf-8")
            context.paths.ml_mode_state_file.write_text('{"mode":"off"}\n', encoding="utf-8")
            context.paths.ui_control_file.write_text('{"stop_requested":false}\n', encoding="utf-8")
            context.paths.planning_inputs_cache_file.write_text('{"cache":"large"}\n', encoding="utf-8")
            context.paths.planning_prompt_cache_file.write_text('{"prompt":"cached"}\n', encoding="utf-8")
            context.paths.block_plan_cache_file.write_text('{"blocks":[]}\n', encoding="utf-8")
            (context.paths.lineage_manifests_dir / "manifest.json").parent.mkdir(parents=True, exist_ok=True)
            (context.paths.lineage_manifests_dir / "manifest.json").write_text('{"lineage":"LN1"}\n', encoding="utf-8")

            worker_paths = orchestrator._build_parallel_worker_paths(
                context,
                batch_token="batch-demo",
                worker_slug="01-st1",
                worktree_dir=worker_repo_dir,
            )
            orchestrator._copy_parallel_worker_support_files(context, worker_paths)

            self.assertTrue((worker_paths.docs_dir / "PLAN.md").exists())
            self.assertTrue((worker_paths.memory_dir / "task_summaries.jsonl").exists())
            self.assertTrue(worker_paths.execution_plan_file.exists())
            self.assertTrue(worker_paths.checkpoint_state_file.exists())
            self.assertTrue(worker_paths.lineage_state_file.exists())
            self.assertTrue(worker_paths.spine_file.exists())
            self.assertTrue(worker_paths.common_requirements_file.exists())
            self.assertTrue(worker_paths.contract_wave_audit_file.exists())
            self.assertTrue(worker_paths.ml_mode_state_file.exists())
            self.assertTrue(worker_paths.ui_control_file.exists())
            self.assertTrue((worker_paths.lineage_manifests_dir / "manifest.json").exists())
            self.assertFalse(worker_paths.planning_inputs_cache_file.exists())
            self.assertFalse(worker_paths.planning_prompt_cache_file.exists())
            self.assertFalse(worker_paths.block_plan_cache_file.exists())
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

    def test_parallel_worker_summary_prefers_logged_failure_detail(self) -> None:
        orchestrator = Orchestrator(Path(__file__).resolve().parents[1] / ".tmp_parallel_worker_summary_test")
        summary = orchestrator._parallel_worker_summary(
            {"status": "failed", "test_summary": "", "rollback_status": "rolled_back_to_safe_revision"},
            {
                "rollback_status": "rolled_back_to_safe_revision",
                "codex_diagnostics": {
                    "attempts": [
                        {
                            "stderr_excerpt": (
                                "YOLO mode is enabled. All tool calls will be automatically approved.\n"
                                "Loaded cached credentials.\n"
                                "TerminalQuotaError: You have exhausted your capacity on this model."
                            )
                        }
                    ]
                },
            },
        )

        self.assertIn("Parallel worker failed. Cause:", summary)
        self.assertIn("TerminalQuotaError", summary)
        self.assertNotIn("Loaded cached credentials.", summary)
