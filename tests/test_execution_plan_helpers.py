from __future__ import annotations

import json
import os
import subprocess
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

import jakal_flow.planning as planning_module
from jakal_flow.environment import ensure_gitignore
from jakal_flow.errors import (
    AgentPassExecutionError,
    ExecutionPreflightError,
    MergeConflictStateError,
    MissingRecoveryArtifactsError,
    ParallelExecutionFailure,
    ParallelMergeConflictError,
    VerificationTestFailure,
    execution_failure_from_reason,
)
from jakal_flow.execution_control import ImmediateStopRequested
from jakal_flow.git_ops import GitOps
from jakal_flow.memory import MemoryStore
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
    PlanItem,
    REFERENCE_GUIDE_FILENAME,
    SCOPE_GUARD_TEMPLATE_FILENAME,
    STEP_EXECUTION_PARALLEL_PROMPT_FILENAME,
    STEP_EXECUTION_PROMPT_FILENAME,
    bootstrap_plan_prompt,
    build_fast_planner_outline,
    execution_plan_markdown,
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
    debugger_prompt,
    implementation_prompt,
    merger_prompt,
    parse_execution_plan_response,
    prompt_to_plan_decomposition_prompt,
    prompt_to_execution_plan_prompt,
    scan_repository_inputs,
    source_prompt_template_path,
)
from jakal_flow.reporting import Reporter
from jakal_flow.step_models import CLAUDE_DEFAULT_MODEL, GEMINI_DEFAULT_MODEL, resolve_step_model_choice
import jakal_flow.ui_bridge_payloads as ui_bridge_payloads
from jakal_flow.utils import append_jsonl, read_json, read_jsonl_tail, read_last_jsonl, write_json
from jakal_flow.verification import VerificationRunner


class ExecutionPlanHelperTests(unittest.TestCase):
    def test_git_ops_caches_current_revision_and_local_identity(self) -> None:
        git = GitOps()
        repo_dir = Path(__file__).resolve().parents[1]
        run_calls: list[list[str]] = []

        def fake_run(args, cwd, check=True, env=None):
            run_calls.append(list(args))
            if args[:2] == ["config", "user.name"] or args[:2] == ["config", "user.email"]:
                return CommandResult(command=["git", *args], returncode=0, stdout="", stderr="")
            if args[:2] == ["rev-parse", "HEAD"]:
                return CommandResult(command=["git", *args], returncode=0, stdout="abc123\n", stderr="")
            if args[:2] == ["reset", "--hard"] or args[:1] == ["clean"]:
                return CommandResult(command=["git", *args], returncode=0, stdout="", stderr="")
            raise AssertionError(f"unexpected git args: {args}")

        with mock.patch.object(git, "_current_revision_from_head", return_value=""), mock.patch.object(
            git,
            "run",
            side_effect=fake_run,
        ):
            git.configure_local_identity(repo_dir, "Jakal Flow", "jakal@example.com")
            git.configure_local_identity(repo_dir, "Jakal Flow", "jakal@example.com")
            self.assertEqual(git.current_revision(repo_dir), "abc123")
            self.assertEqual(git.current_revision(repo_dir), "abc123")
            git.hard_reset(repo_dir, "safe-revision")
            self.assertEqual(git.current_revision(repo_dir), "safe-revision")

        self.assertEqual(run_calls.count(["config", "user.name", "Jakal Flow"]), 1)
        self.assertEqual(run_calls.count(["config", "user.email", "jakal@example.com"]), 1)
        self.assertEqual(run_calls.count(["rev-parse", "HEAD"]), 1)

    def test_git_ops_uses_feature_specific_timeouts(self) -> None:
        git = GitOps()
        repo_dir = Path(__file__).resolve().parents[1]
        observed_timeouts: list[tuple[list[str], float | None]] = []

        def fake_run_subprocess(command, cwd, capture_output, check, env, timeout_seconds):
            filtered_args = [part for part in command if not str(part).startswith("safe.directory=") and part != "-c" and part != "git"]
            observed_timeouts.append((filtered_args, timeout_seconds))
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

        with mock.patch("jakal_flow.git_ops.run_subprocess", side_effect=fake_run_subprocess):
            git.run(["branch", "--show-current"], cwd=repo_dir, check=False)
            git.run(["remote"], cwd=repo_dir, check=False)
            git.run(["status", "--porcelain"], cwd=repo_dir, check=False)
            git.run(["fetch", "origin", "main"], cwd=repo_dir, check=False)
            git.run(["cherry-pick", "abc123"], cwd=repo_dir, check=False)
            git.run(["clone", "--branch", "main", "demo", "target"], cwd=repo_dir, check=False)

        timeout_map = {tuple(args[:2] if len(args) > 1 else args): timeout for args, timeout in observed_timeouts}
        self.assertEqual(timeout_map[("branch", "--show-current")], 10.0)
        self.assertEqual(timeout_map[("remote",)], 60.0)
        self.assertEqual(timeout_map[("status", "--porcelain")], 60.0)
        self.assertEqual(timeout_map[("fetch", "origin")], 180.0)
        self.assertEqual(timeout_map[("cherry-pick", "abc123")], 180.0)
        self.assertEqual(timeout_map[("clone", "--branch")], 300.0)

    def test_verification_runner_uses_explicit_state_fingerprint(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_verification_state_fingerprint_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", test_cmd="python -m pytest")
        context = orchestrator.workspace.initialize_local_project(project_dir=repo_dir, branch="main", runtime=runtime)

        try:
            with mock.patch.object(
                orchestrator.verification,
                "_compute_state_fingerprint",
                side_effect=AssertionError("should not recompute state fingerprint"),
            ), mock.patch(
                "jakal_flow.verification.run_subprocess_capture",
                return_value=SimpleNamespace(returncode=0, stdout=b"ok\n", stderr=b""),
            ):
                result = orchestrator.verification.run(
                    context=context,
                    block_index=1,
                    label="demo",
                    state_fingerprint="precomputed-fingerprint",
                )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(result.state_fingerprint, "precomputed-fingerprint")

    def test_execution_failure_from_reason_maps_known_failure_codes(self) -> None:
        cases = {
            "preflight_failed": ExecutionPreflightError,
            "agent_pass_failed": AgentPassExecutionError,
            "verification_test_failed": VerificationTestFailure,
            "parallel_execution_failed": ParallelExecutionFailure,
            "parallel_merge_conflict": ParallelMergeConflictError,
            "recovery_artifacts_missing": MissingRecoveryArtifactsError,
            "merge_conflict_state_invalid": MergeConflictStateError,
        }

        for reason_code, failure_type in cases.items():
            with self.subTest(reason_code=reason_code):
                failure = execution_failure_from_reason(reason_code, "demo failure")
                self.assertIsInstance(failure, failure_type)
                self.assertEqual(failure.reason_code, reason_code)

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

    def test_execution_plan_markdown_explicitly_marks_pending_steps(self) -> None:
        context = SimpleNamespace(
            metadata=SimpleNamespace(
                display_name="Demo Repo",
                slug="demo-repo",
                repo_url="https://example.invalid/demo.git",
                branch="main",
            ),
            paths=SimpleNamespace(repo_dir=Path("C:/tmp/demo-repo")),
            runtime=SimpleNamespace(effort="medium"),
        )

        markdown = execution_plan_markdown(
            context,
            "Demo Plan",
            "Prompt",
            "Summary",
            "standard",
            "parallel",
            [ExecutionStep(step_id="ST1", title="Start here", status="pending")],
        )

        self.assertIn("  - Status: pending", markdown)

    def test_checkpoints_reconcile_from_block_log(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            temp_dir = Path(temp_root)
            workspace_root = temp_dir / "workspace"
            repo_dir = temp_dir / "repo"
            repo_dir.mkdir(parents=True, exist_ok=True)
            orchestrator = Orchestrator(workspace_root)
            runtime = RuntimeOptions(test_cmd="python -m unittest", require_checkpoint_approval=True)
            context = orchestrator.workspace.initialize_local_project(repo_dir, "main", runtime, display_name="Demo")

            write_json(
                context.paths.checkpoint_state_file,
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
                },
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

            data = orchestrator.checkpoints(context.metadata.repo_url, context.metadata.branch)
            stored = read_json(context.paths.checkpoint_state_file, default={})
            timeline = context.paths.checkpoint_timeline_file.read_text(encoding="utf-8")

        self.assertEqual(data["checkpoints"][0]["status"], "awaiting_review")
        self.assertEqual(stored["checkpoints"][0]["status"], "awaiting_review")
        self.assertEqual(stored["checkpoints"][0]["commit_hashes"], ["abc123"])
        self.assertIn("Status: awaiting_review", timeline)

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

    def test_parse_execution_plan_response_accepts_string_policy_lists(self) -> None:
        response = """
        {
          "tasks": [
            {
              "step_id": "ST2",
              "task_title": "Harden the shared adapter",
              "display_description": "Update the shared adapter carefully.",
              "codex_description": "Change the adapter in place and keep compatibility intact.",
              "depends_on": "ST1",
              "owned_paths": "src/payments/adapter.py",
              "step_type": "feature",
              "scope_class": "shared_reviewed",
              "spine_version": "spine-v5",
              "shared_contracts": "api/payments, config/runtime",
              "verification_profile": "adapter",
              "primary_scope_paths": "src/payments/adapter.py",
              "shared_reviewed_paths": "src/contracts/payments.py\\nsrc/config/runtime.py",
              "forbidden_core_paths": "src/core/schema.py",
              "success_criteria": "The adapter remains backward compatible."
            }
          ]
        }
        """

        _title, _summary, steps = parse_execution_plan_response(response, "python -m unittest", "high", limit=3)

        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].depends_on, ["ST1"])
        self.assertEqual(steps[0].shared_contracts, ["api/payments", "config/runtime"])
        self.assertEqual(steps[0].primary_scope_paths, ["src/payments/adapter.py"])
        self.assertEqual(
            steps[0].shared_reviewed_paths,
            ["src/contracts/payments.py", "src/config/runtime.py"],
        )
        self.assertEqual(steps[0].forbidden_core_paths, ["src/core/schema.py"])
        self.assertEqual(steps[0].spine_version, "spine-v5")
        self.assertEqual(steps[0].verification_profile, "adapter")

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
                "model": GEMINI_DEFAULT_MODEL,
            }
        )

        self.assertEqual(step.model_provider, "gemini")
        self.assertEqual(step.model, GEMINI_DEFAULT_MODEL)

    def test_build_fast_planner_outline_emits_contract_wave_hints(self) -> None:
        outline = json.loads(
            build_fast_planner_outline(
                {"source": "Existing implementation files detected. src/main.py"},
                "Add a contract-aware payments flow.",
                current_spine_version="spine-v9",
            )
        )

        candidate = outline["candidate_blocks"][0]
        self.assertEqual(candidate["step_type_hint"], "feature")
        self.assertEqual(candidate["scope_class_hint"], "free_owned")
        self.assertEqual(candidate["spine_version_hint"], "spine-v9")
        self.assertIn("primary_scope_candidates", candidate)
        self.assertIn("shared_reviewed_candidates", candidate)
        self.assertIn("forbidden_core_candidates", candidate)

    def test_execution_step_from_dict_drops_plain_codex_model_for_openai_steps(self) -> None:
        step = ExecutionStep.from_dict(
            {
                "step_id": "ST1",
                "title": "Backend pass",
                "model_provider": "openai",
                "model": "codex",
            }
        )

        self.assertEqual(step.model_provider, "openai")
        self.assertEqual(step.model, "")

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

    def test_resolve_step_model_choice_prefers_execution_model_for_general_steps(self) -> None:
        runtime = RuntimeOptions(model="gpt-5.4", execution_model="gpt-5.5", model_provider="openai")
        step = ExecutionStep(
            step_id="ST1",
            title="Refactor orchestrator runtime overlay",
            owned_paths=["src/jakal_flow/orchestrator.py"],
        )

        choice = resolve_step_model_choice(step, runtime)

        self.assertEqual(choice.provider, "openai")
        self.assertEqual(choice.model, "gpt-5.5")
        self.assertEqual(choice.source, "auto")

    def test_resolve_step_model_choice_prefers_claude_for_ensemble_ui_steps(self) -> None:
        runtime = RuntimeOptions(model="gpt-5.4", model_provider="ensemble")
        step = ExecutionStep(
            step_id="ST1",
            title="Refresh desktop settings panel",
            display_description="Update the UI layout for the settings screen.",
            owned_paths=["desktop/src/components/views/AppSettingsView.jsx"],
        )

        with mock.patch("jakal_flow.step_models.claude_available_for_auto_selection", return_value=True), mock.patch(
            "jakal_flow.step_models.gemini_available_for_auto_selection",
            return_value=False,
        ):
            choice = resolve_step_model_choice(step, runtime)

        self.assertEqual(choice.provider, "claude")
        self.assertEqual(choice.model, CLAUDE_DEFAULT_MODEL)
        self.assertEqual(choice.source, "auto")
        self.assertIn("Ensemble UI preference", choice.reason)

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

    def test_build_lineage_context_sanitizes_parent_active_plan_state(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_lineage_plan_sync_sanitization_test"
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
            orchestrator.save_execution_plan_state(
                context,
                ExecutionPlanState(
                    execution_mode="parallel",
                    default_test_command="python -m pytest",
                    closeout_status="failed",
                    closeout_started_at="2026-03-30T00:30:00+00:00",
                    closeout_completed_at="2026-03-30T00:45:00+00:00",
                    closeout_commit_hash="closeout-head",
                    closeout_notes="closeout failed",
                    steps=[
                        ExecutionStep(
                            step_id="ST1",
                            title="Parent active step",
                            status="running",
                            started_at="2026-03-30T00:00:00+00:00",
                            commit_hash="parent-running",
                            notes="still running",
                            metadata={"failure_type": "should-clear", "failure_reason_code": "running"},
                        ),
                        ExecutionStep(
                            step_id="ST2",
                            title="Sibling failed step",
                            status="failed",
                            started_at="2026-03-29T12:00:00+00:00",
                            completed_at="2026-03-29T12:30:00+00:00",
                            commit_hash="failed-head",
                            notes="failed previously",
                            metadata={"failure_type": "test_failure", "failure_reason_code": "tests_failed"},
                        ),
                        ExecutionStep(
                            step_id="ST3",
                            title="Sibling paused step",
                            status="paused",
                            started_at="2026-03-29T13:00:00+00:00",
                            notes="paused previously",
                        ),
                        ExecutionStep(step_id="ST4", title="Sibling already done", status="completed", completed_at="2026-03-29T00:00:00+00:00"),
                    ],
                ),
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
            step = ExecutionStep(step_id="ST1", title="Parent active step", owned_paths=["desktop/src"])
            with mock.patch.object(orchestrator.git, "branch_exists", return_value=True), mock.patch.object(
                orchestrator.git,
                "attach_worktree",
            ), mock.patch.object(
                orchestrator.git,
                "add_worktree",
            ):
                lineage_context = orchestrator._build_lineage_context(context, runtime, step, lineage)
                lineage_plan = orchestrator.load_execution_plan_state(lineage_context)
                checkpoint_state = read_json(lineage_context.paths.checkpoint_state_file, default={})
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual([item.status for item in lineage_plan.steps], ["pending", "pending", "pending", "completed"])
        self.assertIsNone(lineage_plan.steps[0].started_at)
        self.assertIsNone(lineage_plan.steps[0].completed_at)
        self.assertIsNone(lineage_plan.steps[0].commit_hash)
        self.assertEqual(lineage_plan.steps[0].notes, "")
        self.assertNotIn("failure_type", lineage_plan.steps[0].metadata)
        self.assertNotIn("failure_reason_code", lineage_plan.steps[0].metadata)
        self.assertIsNone(lineage_plan.steps[1].started_at)
        self.assertIsNone(lineage_plan.steps[1].completed_at)
        self.assertIsNone(lineage_plan.steps[1].commit_hash)
        self.assertEqual(lineage_plan.steps[1].notes, "")
        self.assertNotIn("failure_type", lineage_plan.steps[1].metadata)
        self.assertNotIn("failure_reason_code", lineage_plan.steps[1].metadata)
        self.assertIsNone(lineage_plan.steps[2].started_at)
        self.assertIsNone(lineage_plan.steps[2].completed_at)
        self.assertEqual(lineage_plan.steps[2].notes, "")
        self.assertEqual(lineage_plan.closeout_status, "not_started")
        self.assertIsNone(lineage_plan.closeout_started_at)
        self.assertIsNone(lineage_plan.closeout_completed_at)
        self.assertIsNone(lineage_plan.closeout_commit_hash)
        self.assertEqual(lineage_plan.closeout_notes, "")
        self.assertEqual(checkpoint_state["checkpoints"][0]["status"], "pending")
        self.assertEqual(checkpoint_state["checkpoints"][1]["status"], "pending")
        self.assertEqual(checkpoint_state["checkpoints"][2]["status"], "pending")
        self.assertEqual(checkpoint_state["checkpoints"][3]["status"], "approved")
        self.assertEqual(lineage_context.metadata.current_status, "lineage_ready")

    def test_cleanup_lineage_worktree_unregisters_missing_worktree_path(self) -> None:
        orchestrator = Orchestrator(Path.cwd() / ".tmp_cleanup_lineage_worktree_test")
        repo_dir = Path.cwd() / ".tmp_cleanup_lineage_worktree_test" / "repo"
        lineage = LineageState(
            lineage_id="LN1",
            branch_name="jakal-flow-lineage-ln1",
            worktree_dir=repo_dir / ".lineages" / "ln1" / "repo",
            project_root=repo_dir / ".lineages" / "ln1",
            created_at="2026-03-28T00:00:00+00:00",
            updated_at="2026-03-28T00:00:00+00:00",
        )

        with mock.patch.object(orchestrator.git, "remove_worktree") as mocked_remove, mock.patch.object(
            orchestrator.git,
            "delete_branch",
        ) as mocked_delete:
            orchestrator._cleanup_lineage_worktree(repo_dir, lineage)

        mocked_remove.assert_called_once_with(repo_dir, lineage.worktree_dir, force=True)
        mocked_delete.assert_called_once_with(repo_dir, lineage.branch_name, force=True)

    def test_cleanup_integration_worktree_unregisters_missing_worktree_path(self) -> None:
        orchestrator = Orchestrator(Path.cwd() / ".tmp_cleanup_integration_worktree_test")
        repo_dir = Path.cwd() / ".tmp_cleanup_integration_worktree_test" / "repo"
        worktree_dir = repo_dir / ".integration" / "repo"

        with mock.patch.object(orchestrator.git, "remove_worktree") as mocked_remove, mock.patch.object(
            orchestrator.git,
            "delete_branch",
        ) as mocked_delete:
            orchestrator._cleanup_integration_worktree(
                repo_dir,
                {"worktree_dir": worktree_dir, "branch_name": "jakal-flow-integration"},
            )

        mocked_remove.assert_called_once_with(repo_dir, worktree_dir, force=True)
        mocked_delete.assert_called_once_with(repo_dir, "jakal-flow-integration", force=True)

    def test_build_lineage_paths_writes_logs_under_worktree_repo_root_and_migrates_legacy_logs(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_lineage_repo_logs_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        worktree_dir = temp_root / "lineage-worktree"
        repo_dir.mkdir(parents=True, exist_ok=True)
        worktree_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium")

        try:
            context = orchestrator.workspace.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=runtime,
            )
            legacy_logs_dir = context.paths.project_root / ".lineages" / "ln1" / "logs"
            legacy_logs_dir.mkdir(parents=True, exist_ok=True)
            (legacy_logs_dir / "passes.jsonl").write_text('{"event":"legacy"}\n', encoding="utf-8")
            (legacy_logs_dir / "block_0001").mkdir(parents=True, exist_ok=True)
            (legacy_logs_dir / "block_0001" / "debug.txt").write_text("legacy-lineage", encoding="utf-8")

            repo_logs_dir = worktree_dir / "jakal-flow-logs"
            repo_logs_dir.mkdir(parents=True, exist_ok=True)
            (repo_logs_dir / "passes.jsonl").write_text('{"event":"current"}\n', encoding="utf-8")

            lineage_paths = orchestrator._build_lineage_paths(context, "LN1", worktree_dir)
            self.assertEqual(lineage_paths.logs_dir, repo_logs_dir.resolve())
            self.assertFalse(legacy_logs_dir.exists())
            self.assertEqual(
                read_jsonl_tail(lineage_paths.pass_log_file, 10),
                [{"event": "legacy"}, {"event": "current"}],
            )
            self.assertEqual((lineage_paths.logs_dir / "block_0001" / "debug.txt").read_text(encoding="utf-8"), "legacy-lineage")
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

    def test_build_integration_paths_writes_logs_under_worktree_repo_root(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_integration_repo_logs_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        worktree_dir = temp_root / "integration-worktree"
        repo_dir.mkdir(parents=True, exist_ok=True)
        worktree_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium")

        try:
            context = orchestrator.workspace.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=runtime,
            )
            integration_paths = orchestrator._build_integration_paths(context, "token-demo", worktree_dir)
            self.assertEqual(integration_paths.logs_dir, worktree_dir.resolve() / "jakal-flow-logs")
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

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

    def test_save_execution_plan_state_prunes_transitive_dag_dependencies(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_parallel_transitive_dependency_plan_test"
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
                            ExecutionStep(step_id="NODE-A", title="Bootstrap", owned_paths=["src/bootstrap"]),
                            ExecutionStep(step_id="NODE-B", title="Backend", depends_on=["NODE-A"], owned_paths=["src/backend"]),
                            ExecutionStep(step_id="NODE-C", title="API", depends_on=["NODE-B"], owned_paths=["src/api"]),
                            ExecutionStep(
                                step_id="NODE-D",
                                title="Docs",
                                depends_on=["NODE-A", "NODE-C"],
                                owned_paths=["docs"],
                            ),
                        ],
                    ),
                )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(plan_state.steps[3].step_id, "ST4")
        self.assertEqual(plan_state.steps[3].depends_on, ["ST3"])

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
                    block_entries = read_jsonl_tail(context.paths.block_log_file, 10)
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
        self.assertEqual(
            sorted(
                str(item.get("lineage_id", "")).strip()
                for item in block_entries
                if item.get("selected_task") in {"Frontend slice", "Backend slice"}
            ),
            ["LN1", "LN2"],
        )
        self.assertEqual(mocked_push.call_count, 2)
        self.assertEqual(mocked_pr.call_count, 2)

    def test_latest_logged_block_for_lineage_ignores_other_lineage_blocks(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_latest_lineage_block_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        temp_root.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(temp_root / "workspace")
        block_log_file = temp_root / "blocks.jsonl"

        try:
            append_jsonl(
                block_log_file,
                {
                    "block_index": 7,
                    "lineage_id": "LN2",
                    "status": "completed",
                    "selected_task": "Backend slice",
                    "test_summary": "lineage 2",
                },
            )
            append_jsonl(
                block_log_file,
                {
                    "block_index": 7,
                    "lineage_id": "LN1",
                    "status": "completed",
                    "selected_task": "Frontend slice",
                    "test_summary": "lineage 1",
                },
            )
            selected = orchestrator._latest_logged_block_for_lineage(block_log_file, "LN2")
            fallback = orchestrator._latest_logged_block_for_lineage(block_log_file, "")
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertIsNotNone(selected)
        self.assertIsNotNone(fallback)
        self.assertEqual(selected["lineage_id"], "LN2")
        self.assertEqual(selected["test_summary"], "lineage 2")
        self.assertEqual(fallback["lineage_id"], "LN1")

    def test_run_parallel_execution_batch_promotes_single_leaf_lineage_immediately(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_hybrid_lineage_single_promote_test"
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
                    plan_title="Hybrid Singleton Promotion Demo",
                    execution_mode="parallel",
                    default_test_command="python -m pytest",
                    steps=[
                        ExecutionStep(step_id="ST1", title="Frontend slice", owned_paths=["desktop/src"]),
                        ExecutionStep(step_id="ST2", title="Backend slice", status="completed", metadata={"lineage_id": "LN2"}),
                        ExecutionStep(
                            step_id="ST3",
                            title="Join slices",
                            depends_on=["ST1", "ST2"],
                            metadata={"step_kind": "join", "merge_from": ["ST1", "ST2"], "join_policy": "all"},
                        ),
                    ],
                ),
            )
            orchestrator._save_lineage_states(
                context,
                {
                    "LN2": LineageState(
                        lineage_id="LN2",
                        branch_name="jakal-flow-lineage-ln2",
                        worktree_dir=temp_root / "ln2" / "repo",
                        project_root=temp_root / "ln2",
                        created_at="2026-03-27T00:00:00+00:00",
                        updated_at="2026-03-27T00:00:00+00:00",
                        head_commit="ln2-head",
                        safe_revision="ln2-head",
                        status="merged",
                        merged_by_step_id="ST0",
                    ),
                },
            )
            worker_result = {
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
            }

            def fake_promote(promotion_context, lineage):
                promotion_context.metadata.current_safe_revision = "main-promoted"
                promotion_context.loop_state.current_safe_revision = "main-promoted"
                promotion_context.loop_state.last_commit_hash = "main-promoted"
                return True, "pushed", "main-promoted"

            with mock.patch.object(orchestrator, "setup_local_project", return_value=context), mock.patch.object(
                orchestrator.git,
                "add_worktree",
            ), mock.patch.object(
                orchestrator,
                "_parallel_worker_count",
                return_value=1,
            ), mock.patch.object(
                orchestrator,
                "_build_lineage_context",
                return_value=mock.Mock(name="lineage-1"),
            ), mock.patch.object(
                orchestrator,
                "_run_lineage_step_worker",
                return_value=worker_result,
            ), mock.patch.object(
                orchestrator,
                "_promote_lineage_to_target_branch",
                side_effect=fake_promote,
            ) as mocked_promote, mock.patch.object(
                orchestrator,
                "_push_if_ready",
            ) as mocked_push, mock.patch.object(
                orchestrator,
                "_maybe_open_pull_request",
            ) as mocked_pr, mock.patch.object(
                orchestrator,
                "_cleanup_lineage_worktree",
            ) as mocked_cleanup:
                context, plan_state, steps = orchestrator.run_parallel_execution_batch(
                    project_dir=repo_dir,
                    runtime=runtime,
                    step_ids=["ST1"],
                )
                lineage_state = read_json(context.paths.lineage_state_file, default={})
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual([step.step_id for step in steps], ["ST1"])
        self.assertEqual([step.status for step in steps], ["completed"])
        self.assertEqual(steps[0].commit_hash, "main-promoted")
        self.assertEqual(context.metadata.current_safe_revision, "main-promoted")
        mocked_promote.assert_called_once()
        mocked_push.assert_not_called()
        mocked_pr.assert_not_called()
        mocked_cleanup.assert_called_once()
        self.assertEqual(
            {item["lineage_id"]: item["status"] for item in lineage_state["lineages"]},
            {"LN2": "merged", "LN3": "merged"},
        )
        self.assertEqual(
            {item["lineage_id"]: item["merged_by_step_id"] for item in lineage_state["lineages"]},
            {"LN2": "ST0", "LN3": "ST1"},
        )

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
                ) as mocked_push_if_ready, mock.patch.object(
                    orchestrator,
                    "_delete_remote_branch_if_present",
                    return_value=(True, "deleted"),
                ) as mocked_delete_remote:
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
        self.assertEqual(mocked_delete_remote.call_count, 3)
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

    def test_lineages_for_join_step_skips_already_merged_lineages(self) -> None:
        orchestrator = Orchestrator(Path.cwd() / ".tmp_join_lineage_filter_workspace")
        plan_state = ExecutionPlanState(
            execution_mode="parallel",
            steps=[
                ExecutionStep(step_id="ST1", title="Frontend", status="completed", metadata={"lineage_id": "LN1"}),
                ExecutionStep(step_id="ST2", title="Backend", status="completed", metadata={"lineage_id": "LN2"}),
                ExecutionStep(
                    step_id="ST3",
                    title="Join frontend and backend",
                    status="completed",
                    depends_on=["ST1", "ST2"],
                    metadata={"step_kind": "join", "merge_from": ["ST1", "ST2"], "join_policy": "all"},
                ),
                ExecutionStep(step_id="ST4", title="Docs", status="completed", metadata={"lineage_id": "LN4"}),
                ExecutionStep(
                    step_id="ST5",
                    title="Reconcile final flow",
                    depends_on=["ST1", "ST3", "ST4"],
                    metadata={"step_kind": "join", "merge_from": ["ST1", "ST3", "ST4"], "join_policy": "all"},
                ),
            ],
        )
        lineages = {
            "LN1": LineageState(
                lineage_id="LN1",
                branch_name="jakal-flow-lineage-ln1",
                worktree_dir=Path.cwd() / ".tmp_join_lineage_filter_workspace" / "ln1",
                project_root=Path.cwd() / ".tmp_join_lineage_filter_workspace" / "ln1-project",
                created_at="2026-03-27T00:00:00+00:00",
                updated_at="2026-03-27T00:00:00+00:00",
                head_commit="ln1-head",
                safe_revision="ln1-head",
                status="merged",
                merged_by_step_id="ST3",
            ),
            "LN2": LineageState(
                lineage_id="LN2",
                branch_name="jakal-flow-lineage-ln2",
                worktree_dir=Path.cwd() / ".tmp_join_lineage_filter_workspace" / "ln2",
                project_root=Path.cwd() / ".tmp_join_lineage_filter_workspace" / "ln2-project",
                created_at="2026-03-27T00:00:00+00:00",
                updated_at="2026-03-27T00:00:00+00:00",
                head_commit="ln2-head",
                safe_revision="ln2-head",
            ),
            "LN4": LineageState(
                lineage_id="LN4",
                branch_name="jakal-flow-lineage-ln4",
                worktree_dir=Path.cwd() / ".tmp_join_lineage_filter_workspace" / "ln4",
                project_root=Path.cwd() / ".tmp_join_lineage_filter_workspace" / "ln4-project",
                created_at="2026-03-27T00:00:00+00:00",
                updated_at="2026-03-27T00:00:00+00:00",
                head_commit="ln4-head",
                safe_revision="ln4-head",
            ),
        }

        selected = orchestrator._lineages_for_join_step(plan_state, plan_state.steps[4], lineages)

        self.assertEqual([lineage.lineage_id for lineage in selected], ["LN4"])

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

    def test_validate_hybrid_execution_steps_includes_candidate_block_id_in_join_errors(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_join_block_id_error_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        orchestrator = Orchestrator(temp_root)

        try:
            with self.assertRaisesRegex(
                ValueError,
                r"ST4 \(block B3\) must depend on at least two prior steps to act as a join node\.",
            ):
                orchestrator._validate_hybrid_execution_steps(
                    [
                        ExecutionStep(
                            step_id="ST4",
                            title="Document Harness Workflow",
                            depends_on=["ST2"],
                            metadata={
                                "step_kind": "join",
                                "candidate_block_id": "B3",
                                "merge_from": ["ST2"],
                                "join_policy": "all",
                            },
                        )
                    ]
                )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

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

    def test_mark_checkpoint_if_due_records_lineage_id(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_checkpoint_lineage_id_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", execution_mode="parallel")

        try:
            context = orchestrator.workspace.initialize_local_project(project_dir=repo_dir, branch="main", runtime=runtime)
            write_json(
                context.paths.checkpoint_state_file,
                {
                    "checkpoints": [
                        {
                            "checkpoint_id": "CP1",
                            "title": "Initial stabilization checkpoint",
                            "plan_refs": ["ST1"],
                            "target_block": 1,
                            "status": "pending",
                        }
                    ]
                },
            )
            orchestrator._mark_checkpoint_if_due(context, 1, ["abc123"], lineage_id="LN9")
            checkpoint_state = read_json(context.paths.checkpoint_state_file, default={})
            checkpoint_view = ui_bridge_payloads.checkpoint_payload(context)
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(checkpoint_state["checkpoints"][0]["status"], "awaiting_review")
        self.assertEqual(checkpoint_state["checkpoints"][0]["lineage_id"], "LN9")
        self.assertEqual(checkpoint_state["checkpoints"][0]["commit_hashes"], ["abc123"])
        self.assertEqual(context.loop_state.current_checkpoint_lineage_id, "LN9")
        self.assertEqual(checkpoint_view["current_checkpoint_lineage_id"], "LN9")

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

    def test_run_saved_execution_step_fails_fast_when_gemini_auth_is_missing(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_step_gemini_preflight_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", test_cmd="python -m pytest")

        try:
            with mock.patch("jakal_flow.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch(
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
                "_run_single_block",
                side_effect=AssertionError("step execution should stop before launching Codex"),
            ):
                orchestrator.update_execution_plan(
                    project_dir=repo_dir,
                    runtime=runtime,
                    plan_state=ExecutionPlanState(
                        plan_title="Gemini Preflight Demo",
                        default_test_command="python -m pytest",
                        steps=[
                            ExecutionStep(
                                step_id="custom-1",
                                title="Explicit Gemini task",
                                model_provider="gemini",
                                model=GEMINI_DEFAULT_MODEL,
                                test_command="python -m pytest",
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

        self.assertEqual(step.status, "failed")
        self.assertIn("Please set an Auth method", step.notes)
        self.assertEqual(step.metadata["failure_type"], "ExecutionPreflightError")
        self.assertEqual(step.metadata["failure_reason_code"], "preflight_failed")
        self.assertEqual(context.metadata.current_status, "failed")

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
                    "failure_type": "AgentPassExecutionError",
                    "failure_reason_code": "agent_pass_failed",
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
        self.assertEqual(step.metadata["failure_type"], "AgentPassExecutionError")
        self.assertEqual(step.metadata["failure_reason_code"], "agent_pass_failed")
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
        self.assertEqual(pass_result["failure_type"], "VerificationTestFailure")
        self.assertEqual(pass_result["failure_reason_code"], "verification_test_failed")
        self.assertIsNotNone(logged_test)
        self.assertEqual(logged_test["failure_reason"], "AssertionError: experiment2 failed")
        mocked_reset.assert_called_once_with(repo_dir, "safe-revision")

    def test_run_single_block_records_search_execution_failures_without_regression_label(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_search_execution_failure_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", test_cmd="python -m pytest", regression_limit=3)

        try:
            context = orchestrator.workspace.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=runtime,
            )
            context.metadata.current_safe_revision = "safe-revision"
            context.loop_state.current_safe_revision = "safe-revision"
            orchestrator.workspace.save_project(context)
            reporter = Reporter(context)
            memory = MemoryStore(context.paths)
            runner = mock.Mock()
            candidate = CandidateTask(
                candidate_id="ST1",
                title="Canonicalize root layout",
                rationale="Normalize the root layout safely.",
                plan_refs=["ST1"],
                score=1.0,
            )
            search_run_result = CodexRunResult(
                pass_type="block-search-pass",
                prompt_file=context.paths.logs_dir / "search.prompt.md",
                output_file=context.paths.logs_dir / "search.last_message.txt",
                event_file=context.paths.logs_dir / "search.events.jsonl",
                returncode=41,
                search_enabled=True,
                changed_files=[],
                usage={},
                last_message="",
                diagnostics={
                    "attempts": [
                        {
                            "attempt": 1,
                            "returncode": 41,
                            "stderr_excerpt": "Please set an Auth method in C:/Users/alber/.gemini/settings.json before running.",
                        }
                    ]
                },
            )

            with mock.patch.object(
                orchestrator,
                "_execute_pass",
                return_value=(search_run_result, None, None),
            ), mock.patch.object(orchestrator, "_report_failure") as mocked_report_failure:
                orchestrator._run_single_block(
                    context=context,
                    runner=runner,
                    memory=memory,
                    reporter=reporter,
                    candidate_override=candidate,
                    suppress_failure_reporting=False,
                )

            block_entry = read_last_jsonl(context.paths.block_log_file)
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertIsNotNone(block_entry)
        self.assertEqual(context.loop_state.counters.regression_failures, 0)
        self.assertEqual(block_entry["status"], "rolled_back")
        self.assertIn("Codex pass failed and changes were rolled back", block_entry["test_summary"])
        self.assertIn("Please set an Auth method", block_entry["test_summary"])
        self.assertEqual(block_entry["failure_type"], "AgentPassExecutionError")
        self.assertEqual(block_entry["failure_reason_code"], "agent_pass_failed")
        mocked_report_failure.assert_called_once()
        self.assertIn("Please set an Auth method", mocked_report_failure.call_args.kwargs["summary"])

    def test_run_manual_debugger_recovery_raises_missing_recovery_artifacts_error(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_manual_debugger_missing_artifacts_test"
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
            orchestrator.save_execution_plan_state(
                context,
                ExecutionPlanState(
                    plan_title="Manual debugger missing artifacts",
                    default_test_command="python -m pytest",
                    steps=[],
                ),
            )

            with self.assertRaises(MissingRecoveryArtifactsError):
                orchestrator.run_manual_debugger_recovery(
                    project_dir=repo_dir,
                    runtime=runtime,
                )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

    def test_run_manual_merger_recovery_raises_merge_conflict_state_error(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_manual_merger_missing_conflict_test"
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
            orchestrator.save_execution_plan_state(
                context,
                ExecutionPlanState(
                    plan_title="Manual merger missing conflict",
                    default_test_command="python -m pytest",
                    steps=[],
                ),
            )

            with self.assertRaises(MergeConflictStateError):
                orchestrator.run_manual_merger_recovery(
                    project_dir=repo_dir,
                    runtime=runtime,
                )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

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

    def test_execute_pass_skips_debugger_when_verification_fails_without_changed_files(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_step_debugger_skip_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", test_cmd="python -m pytest")

        try:
            context = orchestrator.workspace.initialize_local_project(project_dir=repo_dir, branch="main", runtime=runtime)
            candidate = CandidateTask(candidate_id="task-1", title="Implement fix", rationale="demo", plan_refs=["PL1"], score=1.0)
            runner = mock.Mock()
            reporter = Reporter(context)
            failing_stdout = workspace_root / "no-change.stdout.log"
            failing_stderr = workspace_root / "no-change.stderr.log"
            failing_stdout.parent.mkdir(parents=True, exist_ok=True)
            failing_stdout.write_text("no tests ran\n", encoding="utf-8")
            failing_stderr.write_text("ERROR: file or directory not found: tests/missing.py\n", encoding="utf-8")
            failing_test = TestRunResult(
                command="python -m pytest",
                returncode=1,
                stdout_file=failing_stdout,
                stderr_file=failing_stderr,
                summary="python -m pytest exited with 1",
            )

            with mock.patch.object(
                orchestrator,
                "_run_pass_with_provider_fallback",
                return_value=CodexRunResult(
                    pass_type="block-search-pass",
                    prompt_file=workspace_root / "pass.prompt.md",
                    output_file=workspace_root / "pass.last_message.txt",
                    event_file=workspace_root / "pass.events.jsonl",
                    returncode=0,
                    search_enabled=True,
                    changed_files=[],
                    usage={},
                    last_message="pass completed",
                ),
            ), mock.patch.object(
                orchestrator.git,
                "changed_files",
                return_value=[],
            ), mock.patch.object(
                orchestrator,
                "_run_test_command",
                return_value=failing_test,
            ), mock.patch.object(
                orchestrator,
                "_run_debugger_pass",
            ) as mocked_debugger, mock.patch.object(
                orchestrator.git,
                "hard_reset",
            ) as mocked_reset:
                run_result, test_result, commit_hash = orchestrator._execute_pass(
                    context=context,
                    runner=runner,
                    reporter=reporter,
                    block_index=1,
                    candidate=candidate,
                    pass_name="block-search-pass",
                    safe_revision="safe-revision",
                    search_enabled=True,
                )
                pass_entries = read_jsonl_tail(context.paths.pass_log_file, 2)
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(run_result.returncode, 0)
        self.assertIsNone(test_result)
        self.assertIsNone(commit_hash)
        mocked_debugger.assert_not_called()
        mocked_reset.assert_called_once_with(repo_dir, "safe-revision")
        self.assertEqual(pass_entries[-1]["rollback_status"], "debugger_skipped_no_changed_files")

    def test_execute_pass_falls_back_to_openai_after_auto_gemini_runtime_failure(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_step_provider_fallback_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", test_cmd="python -m pytest")
        observed_providers: list[str] = []

        try:
            context = orchestrator.workspace.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=runtime,
            )
            context.metadata.current_safe_revision = "safe-revision"
            context.loop_state.current_safe_revision = "safe-revision"
            execution_step = ExecutionStep(
                step_id="ST1",
                title="Refresh desktop settings panel",
                display_description="Update the UI layout for the settings screen.",
                owned_paths=["desktop/src/components/views/AppSettingsView.jsx"],
                test_command="python -m pytest",
            )
            with mock.patch("jakal_flow.step_models.gemini_available_for_auto_selection", return_value=True):
                context.runtime = orchestrator._build_execution_step_runtime(
                    runtime,
                    execution_step,
                    execution_mode="parallel",
                    max_blocks=1,
                    allow_push=False,
                    require_checkpoint_approval=False,
                    checkpoint_interval_blocks=1,
                )
            orchestrator.workspace.save_project(context)

            candidate = CandidateTask(
                candidate_id=execution_step.step_id,
                title=execution_step.title,
                rationale="Refresh the UI layout safely.",
                plan_refs=[execution_step.step_id],
                score=1.0,
            )
            reporter = Reporter(context)
            runner = mock.Mock()
            failing_result = CodexRunResult(
                pass_type="block-search-pass",
                prompt_file=context.paths.logs_dir / "initial.prompt.md",
                output_file=context.paths.logs_dir / "initial.last_message.txt",
                event_file=context.paths.logs_dir / "initial.events.jsonl",
                returncode=1,
                search_enabled=True,
                changed_files=[],
                usage={},
                last_message="",
                diagnostics={
                    "attempts": [
                        {
                            "attempt": 1,
                            "returncode": 1,
                            "stderr_excerpt": "Attempt 1 failed: You have exhausted your capacity on this model. Your quota will reset after 5s.",
                        }
                    ]
                },
            )
            recovered_result = CodexRunResult(
                pass_type="block-search-pass-fallback-openai",
                prompt_file=context.paths.logs_dir / "fallback.prompt.md",
                output_file=context.paths.logs_dir / "fallback.last_message.txt",
                event_file=context.paths.logs_dir / "fallback.events.jsonl",
                returncode=0,
                search_enabled=True,
                changed_files=[],
                usage={"input_tokens": 9},
                last_message="fallback implementation pass",
            )
            successful_test = TestRunResult(
                command="python -m pytest",
                returncode=0,
                stdout_file=context.paths.logs_dir / "fallback.test.stdout.log",
                stderr_file=context.paths.logs_dir / "fallback.test.stderr.log",
                summary="python -m pytest exited with 0",
            )

            def fake_primary_run_pass(**kwargs):
                observed_providers.append(str(kwargs["context"].runtime.model_provider))
                return failing_result

            def fake_fallback_run_pass(*args, **kwargs):
                observed_providers.append(str(kwargs["context"].runtime.model_provider))
                return recovered_result

            runner.run_pass.side_effect = fake_primary_run_pass

            with mock.patch("jakal_flow.orchestrator.CodexRunner.run_pass", side_effect=fake_fallback_run_pass) as mocked_fallback_run, mock.patch.object(
                orchestrator,
                "_run_test_command",
                return_value=successful_test,
            ), mock.patch.object(
                orchestrator.git,
                "changed_files",
                return_value=["desktop/src/components/views/AppSettingsView.jsx"],
            ), mock.patch.object(orchestrator.git, "has_changes", return_value=True), mock.patch.object(
                orchestrator.git,
                "commit_all",
                return_value="fallback-commit",
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

        self.assertEqual(observed_providers, ["gemini", "openai"])
        self.assertEqual(context.runtime.model_provider, "openai")
        self.assertEqual(commit_hash, "fallback-commit")
        self.assertIsNotNone(test_result)
        self.assertEqual(test_result.returncode, 0)
        self.assertEqual(run_result.attempt_count, 2)
        self.assertEqual(run_result.changed_files, ["desktop/src/components/views/AppSettingsView.jsx"])
        self.assertEqual(run_result.diagnostics["provider_fallback"]["from_provider"], "gemini")
        self.assertEqual(run_result.diagnostics["provider_fallback"]["to_provider"], "openai")
        self.assertIn("exhausted your capacity", run_result.diagnostics["provider_fallback"]["trigger_detail"])
        mocked_fallback_run.assert_called_once()
        mocked_reset.assert_called_once_with(repo_dir, "safe-revision")
        mocked_commit.assert_called_once()

    def test_execute_verified_repo_pass_falls_back_to_openai_after_gemini_quota_failure(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_verified_repo_provider_fallback_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(
            model_provider="gemini",
            provider_api_key_env="GEMINI_API_KEY",
            codex_path="gemini.cmd",
            model="gemini-2.5-flash",
            effort="medium",
            test_cmd="python -m pytest",
        )
        observed_providers: list[str] = []

        try:
            context = orchestrator.workspace.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=runtime,
            )
            context.metadata.current_safe_revision = "safe-revision"
            context.loop_state.current_safe_revision = "safe-revision"
            orchestrator.workspace.save_project(context)

            reporter = Reporter(context)
            runner = mock.Mock()
            failing_result = CodexRunResult(
                pass_type="project-closeout-pass",
                prompt_file=context.paths.logs_dir / "initial.prompt.md",
                output_file=context.paths.logs_dir / "initial.last_message.txt",
                event_file=context.paths.logs_dir / "initial.events.jsonl",
                returncode=1,
                search_enabled=False,
                changed_files=[],
                usage={},
                last_message="",
                diagnostics={
                    "attempts": [
                        {
                            "attempt": 1,
                            "returncode": 1,
                            "stderr_excerpt": "Gemini failed: You have exhausted your capacity on this model. Your quota will reset after 5s.",
                        }
                    ]
                },
            )
            recovered_result = CodexRunResult(
                pass_type="project-closeout-pass-fallback-openai",
                prompt_file=context.paths.logs_dir / "fallback.prompt.md",
                output_file=context.paths.logs_dir / "fallback.last_message.txt",
                event_file=context.paths.logs_dir / "fallback.events.jsonl",
                returncode=0,
                search_enabled=False,
                changed_files=[],
                usage={"input_tokens": 11},
                last_message="fallback closeout pass",
            )
            successful_test = TestRunResult(
                command="python -m pytest",
                returncode=0,
                stdout_file=context.paths.logs_dir / "fallback.test.stdout.log",
                stderr_file=context.paths.logs_dir / "fallback.test.stderr.log",
                summary="python -m pytest exited with 0",
            )

            def fake_primary_run_pass(**kwargs):
                observed_providers.append(str(kwargs["context"].runtime.model_provider))
                return failing_result

            def fake_fallback_run_pass(*args, **kwargs):
                observed_providers.append(str(kwargs["context"].runtime.model_provider))
                return recovered_result

            runner.run_pass.side_effect = fake_primary_run_pass

            with mock.patch("jakal_flow.orchestrator.CodexRunner.run_pass", side_effect=fake_fallback_run_pass) as mocked_fallback_run, mock.patch.object(
                orchestrator,
                "_run_test_command",
                return_value=successful_test,
            ), mock.patch.object(
                orchestrator.git,
                "changed_files",
                return_value=["README.md"],
            ), mock.patch.object(orchestrator.git, "has_changes", return_value=True), mock.patch.object(
                orchestrator.git,
                "commit_all",
                return_value="fallback-closeout-commit",
            ) as mocked_commit, mock.patch.object(orchestrator.git, "hard_reset") as mocked_reset:
                result = orchestrator._execute_verified_repo_pass(
                    context=context,
                    runner=runner,
                    reporter=reporter,
                    prompt="Summarize the release closeout.",
                    pass_type="project-closeout-pass",
                    block_index=1,
                    task_name="Release closeout",
                    safe_revision="safe-revision",
                )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(observed_providers, ["gemini", "openai"])
        self.assertEqual(context.runtime.model_provider, "openai")
        self.assertTrue(result["success"])
        self.assertEqual(result["commit_hash"], "fallback-closeout-commit")
        self.assertEqual(result["run_result"].attempt_count, 2)
        self.assertEqual(result["run_result"].diagnostics["provider_fallback"]["from_provider"], "gemini")
        self.assertEqual(result["run_result"].diagnostics["provider_fallback"]["to_provider"], "openai")
        self.assertIn("exhausted your capacity", result["run_result"].diagnostics["provider_fallback"]["trigger_detail"])
        mocked_fallback_run.assert_called_once()
        mocked_reset.assert_called_once_with(repo_dir, "safe-revision")
        mocked_commit.assert_called_once()

    def test_execute_pass_falls_back_to_openai_after_gemini_model_not_found_error(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_execute_pass_model_not_found_fallback_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(
            model_provider="gemini",
            provider_api_key_env="GEMINI_API_KEY",
            codex_path="gemini.cmd",
            model="gemini-2.5-flash",
            effort="medium",
            test_cmd="python -m pytest",
        )
        observed_providers: list[str] = []
        ui_events: list[dict[str, object]] = []

        try:
            context = orchestrator.workspace.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=runtime,
            )
            context.metadata.current_safe_revision = "safe-revision"
            context.loop_state.current_safe_revision = "safe-revision"
            orchestrator.workspace.save_project(context)

            reporter = Reporter(context)
            runner = mock.Mock()
            candidate = CandidateTask(
                candidate_id="ST7",
                title="Ship Release Surfaces",
                rationale="Finish the release surface step.",
                plan_refs=["ST7"],
                score=1.0,
            )
            execution_step = ExecutionStep(
                step_id="ST7",
                title="Ship Release Surfaces",
                test_command="python -m pytest",
            )
            failing_result = CodexRunResult(
                pass_type="block-search-pass",
                prompt_file=context.paths.logs_dir / "initial.prompt.md",
                output_file=context.paths.logs_dir / "initial.last_message.txt",
                event_file=context.paths.logs_dir / "initial.events.jsonl",
                returncode=1,
                search_enabled=True,
                changed_files=[],
                usage={},
                last_message="",
                diagnostics={
                    "attempts": [
                        {
                            "attempt": 1,
                            "returncode": 1,
                            "stderr_excerpt": (
                                "YOLO mode is enabled. All tool calls will be automatically approved.\n"
                                "Loaded cached credentials.\n"
                                "Error when talking to Gemini API\n"
                                "ModelNotFoundError: Requested entity was not found."
                            ),
                        }
                    ]
                },
            )
            recovered_result = CodexRunResult(
                pass_type="block-search-pass-fallback-openai",
                prompt_file=context.paths.logs_dir / "fallback.prompt.md",
                output_file=context.paths.logs_dir / "fallback.last_message.txt",
                event_file=context.paths.logs_dir / "fallback.events.jsonl",
                returncode=0,
                search_enabled=True,
                changed_files=[],
                usage={"input_tokens": 17},
                last_message="fallback implementation pass",
            )
            successful_test = TestRunResult(
                command="python -m pytest",
                returncode=0,
                stdout_file=context.paths.logs_dir / "fallback.test.stdout.log",
                stderr_file=context.paths.logs_dir / "fallback.test.stderr.log",
                summary="59 passed in 40.65s",
            )

            def fake_primary_run_pass(**kwargs):
                observed_providers.append(str(kwargs["context"].runtime.model_provider))
                return failing_result

            def fake_fallback_run_pass(*args, **kwargs):
                observed_providers.append(str(kwargs["context"].runtime.model_provider))
                return recovered_result

            runner.run_pass.side_effect = fake_primary_run_pass

            with mock.patch("jakal_flow.orchestrator.CodexRunner.run_pass", side_effect=fake_fallback_run_pass) as mocked_fallback_run, mock.patch.object(
                orchestrator,
                "_run_test_command",
                return_value=successful_test,
            ), mock.patch.object(
                orchestrator.git,
                "changed_files",
                return_value=["src/lit/cli.py", "desktop/src/components/layout/SidebarPane.jsx"],
            ), mock.patch.object(orchestrator.git, "has_changes", return_value=True), mock.patch.object(
                orchestrator.git,
                "commit_all",
                return_value="release-surfaces-commit",
            ) as mocked_commit, mock.patch.object(orchestrator.git, "hard_reset") as mocked_reset:
                run_result, test_result, commit_hash = orchestrator._execute_pass(
                    context=context,
                    runner=runner,
                    reporter=reporter,
                    block_index=2,
                    candidate=candidate,
                    pass_name="block-search-pass",
                    safe_revision="safe-revision",
                    search_enabled=True,
                    memory_context_override="Recent memory context",
                    execution_step=execution_step,
                )
                ui_events = read_jsonl_tail(context.paths.ui_event_log_file, 4)
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(observed_providers, ["gemini", "openai"])
        self.assertEqual(context.runtime.model_provider, "openai")
        self.assertEqual(commit_hash, "release-surfaces-commit")
        self.assertIsNotNone(test_result)
        self.assertEqual(test_result.returncode, 0)
        self.assertEqual(test_result.summary, "59 passed in 40.65s")
        self.assertEqual(run_result.attempt_count, 2)
        self.assertEqual(run_result.changed_files, ["src/lit/cli.py", "desktop/src/components/layout/SidebarPane.jsx"])
        self.assertEqual(run_result.diagnostics["provider_fallback"]["from_provider"], "gemini")
        self.assertEqual(run_result.diagnostics["provider_fallback"]["to_provider"], "openai")
        self.assertIn("ModelNotFoundError", run_result.diagnostics["provider_fallback"]["trigger_detail"])
        self.assertEqual([event.get("event_type") for event in ui_events[-2:]], ["provider-fallback-started", "provider-fallback-finished"])
        self.assertIn("Retrying block-search-pass on openai", str(ui_events[-2].get("message", "")))
        self.assertEqual(ui_events[-1].get("details", {}).get("succeeded"), True)
        mocked_fallback_run.assert_called_once()
        mocked_reset.assert_called_once_with(repo_dir, "safe-revision")
        mocked_commit.assert_called_once()

    def test_write_json_retries_transient_windows_replace_denied(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_atomic_write_retry_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        temp_root.mkdir(parents=True, exist_ok=True)
        target = temp_root / "LOOP_STATE.json"

        replace_attempts: list[tuple[str, str]] = []
        saved_payload: dict[str, object] = {}
        real_replace = os.replace

        def flaky_replace(src, dst):
            replace_attempts.append((str(src), str(dst)))
            if len(replace_attempts) < 3:
                raise PermissionError(13, "Access is denied", str(dst))
            return real_replace(src, dst)

        try:
            with mock.patch("jakal_flow.utils.os.replace", side_effect=flaky_replace), mock.patch(
                "jakal_flow.utils.time.sleep"
            ) as mocked_sleep:
                write_json(target, {"current_task": "ST7", "pending_checkpoint_approval": False})
                saved_payload = read_json(target, default={})
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(len(replace_attempts), 3)
        self.assertEqual(mocked_sleep.call_count, 2)
        self.assertEqual(saved_payload, {"current_task": "ST7", "pending_checkpoint_approval": False})

    def test_execute_verified_repo_pass_falls_back_to_local_oss_after_remote_quota_failures(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_verified_repo_local_provider_fallback_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(
            model_provider="openai",
            model="gpt-5.4",
            effort="medium",
            test_cmd="python -m pytest",
        )
        observed_providers: list[str] = []

        try:
            context = orchestrator.workspace.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=runtime,
            )
            context.metadata.current_safe_revision = "safe-revision"
            context.loop_state.current_safe_revision = "safe-revision"
            orchestrator.workspace.save_project(context)

            reporter = Reporter(context)
            runner = mock.Mock()
            failing_result = CodexRunResult(
                pass_type="project-closeout-pass",
                prompt_file=context.paths.logs_dir / "initial.prompt.md",
                output_file=context.paths.logs_dir / "initial.last_message.txt",
                event_file=context.paths.logs_dir / "initial.events.jsonl",
                returncode=1,
                search_enabled=False,
                changed_files=[],
                usage={},
                last_message="",
                diagnostics={
                    "attempts": [
                        {
                            "attempt": 1,
                            "returncode": 1,
                            "stderr_excerpt": "OpenAI failed: You have exhausted your capacity on this model. Your quota will reset after 5s.",
                        }
                    ]
                },
            )
            remote_failing_result = CodexRunResult(
                pass_type="project-closeout-pass-fallback-claude",
                prompt_file=context.paths.logs_dir / "claude.prompt.md",
                output_file=context.paths.logs_dir / "claude.last_message.txt",
                event_file=context.paths.logs_dir / "claude.events.jsonl",
                returncode=1,
                search_enabled=False,
                changed_files=[],
                usage={},
                last_message="",
                diagnostics={
                    "attempts": [
                        {
                            "attempt": 1,
                            "returncode": 1,
                            "stderr_excerpt": "Claude failed: rate limit exceeded for the current workspace.",
                        }
                    ]
                },
            )
            local_success_result = CodexRunResult(
                pass_type="project-closeout-pass-fallback-oss",
                prompt_file=context.paths.logs_dir / "oss.prompt.md",
                output_file=context.paths.logs_dir / "oss.last_message.txt",
                event_file=context.paths.logs_dir / "oss.events.jsonl",
                returncode=0,
                search_enabled=False,
                changed_files=[],
                usage={"input_tokens": 13},
                last_message="local fallback closeout pass",
            )
            successful_test = TestRunResult(
                command="python -m pytest",
                returncode=0,
                stdout_file=context.paths.logs_dir / "fallback.test.stdout.log",
                stderr_file=context.paths.logs_dir / "fallback.test.stderr.log",
                summary="python -m pytest exited with 0",
            )

            def fake_primary_run_pass(**kwargs):
                observed_providers.append(str(kwargs["context"].runtime.model_provider))
                return failing_result

            def fake_fallback_run_pass(*args, **kwargs):
                provider = str(kwargs["context"].runtime.model_provider)
                observed_providers.append(provider)
                if provider == "claude":
                    return remote_failing_result
                if provider == "oss":
                    return local_success_result
                raise AssertionError(f"unexpected fallback provider: {provider}")

            fallback_runtimes = [
                RuntimeOptions(
                    model_provider="claude",
                    provider_api_key_env="ANTHROPIC_API_KEY",
                    codex_path="claude.cmd",
                    model=CLAUDE_DEFAULT_MODEL,
                    effort="medium",
                    test_cmd="python -m pytest",
                ),
                RuntimeOptions(
                    model_provider="oss",
                    local_model_provider="ollama",
                    codex_path="codex.cmd",
                    model="qwen2.5-coder:7b",
                    effort="medium",
                    test_cmd="python -m pytest",
                ),
            ]
            runner.run_pass.side_effect = fake_primary_run_pass

            with mock.patch(
                "jakal_flow.orchestrator.build_provider_fallback_runtimes",
                return_value=fallback_runtimes,
            ), mock.patch(
                "jakal_flow.orchestrator.CodexRunner.run_pass",
                side_effect=fake_fallback_run_pass,
            ) as mocked_fallback_run, mock.patch.object(
                orchestrator,
                "_run_test_command",
                return_value=successful_test,
            ), mock.patch.object(
                orchestrator.git,
                "changed_files",
                return_value=["README.md"],
            ), mock.patch.object(orchestrator.git, "has_changes", return_value=True), mock.patch.object(
                orchestrator.git,
                "commit_all",
                return_value="local-fallback-closeout-commit",
            ) as mocked_commit, mock.patch.object(orchestrator.git, "hard_reset") as mocked_reset:
                result = orchestrator._execute_verified_repo_pass(
                    context=context,
                    runner=runner,
                    reporter=reporter,
                    prompt="Summarize the release closeout.",
                    pass_type="project-closeout-pass",
                    block_index=1,
                    task_name="Release closeout",
                    safe_revision="safe-revision",
                )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(observed_providers, ["openai", "claude", "oss"])
        self.assertEqual(context.runtime.model_provider, "oss")
        self.assertEqual(context.runtime.local_model_provider, "ollama")
        self.assertTrue(result["success"])
        self.assertEqual(result["commit_hash"], "local-fallback-closeout-commit")
        self.assertEqual(result["run_result"].attempt_count, 3)
        self.assertEqual(result["run_result"].diagnostics["provider_fallback"]["from_provider"], "openai")
        self.assertEqual(result["run_result"].diagnostics["provider_fallback"]["to_provider"], "oss")
        self.assertEqual(
            [item["provider"] for item in result["run_result"].diagnostics["provider_fallback"]["chain"]],
            ["claude", "oss"],
        )
        mocked_fallback_run.assert_called()
        self.assertGreaterEqual(mocked_reset.call_count, 2)
        mocked_commit.assert_called_once()

    def test_execute_verified_repo_pass_skips_preflight_invalid_fallback_candidates(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_verified_repo_skip_invalid_fallback_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(
            model_provider="openai",
            model="gpt-5.4",
            effort="medium",
            test_cmd="python -m pytest",
        )
        observed_providers: list[str] = []

        try:
            context = orchestrator.workspace.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=runtime,
            )
            context.metadata.current_safe_revision = "safe-revision"
            context.loop_state.current_safe_revision = "safe-revision"
            orchestrator.workspace.save_project(context)

            reporter = Reporter(context)
            runner = mock.Mock()
            failing_result = CodexRunResult(
                pass_type="project-closeout-pass",
                prompt_file=context.paths.logs_dir / "initial.prompt.md",
                output_file=context.paths.logs_dir / "initial.last_message.txt",
                event_file=context.paths.logs_dir / "initial.events.jsonl",
                returncode=1,
                search_enabled=False,
                changed_files=[],
                usage={},
                last_message="",
                diagnostics={
                    "attempts": [
                        {
                            "attempt": 1,
                            "returncode": 1,
                            "stderr_excerpt": "OpenAI failed: You have exhausted your capacity on this model. Your quota will reset after 5s.",
                        }
                    ]
                },
            )
            local_success_result = CodexRunResult(
                pass_type="project-closeout-pass-fallback-oss",
                prompt_file=context.paths.logs_dir / "oss.prompt.md",
                output_file=context.paths.logs_dir / "oss.last_message.txt",
                event_file=context.paths.logs_dir / "oss.events.jsonl",
                returncode=0,
                search_enabled=False,
                changed_files=[],
                usage={"input_tokens": 13},
                last_message="local fallback closeout pass",
            )
            successful_test = TestRunResult(
                command="python -m pytest",
                returncode=0,
                stdout_file=context.paths.logs_dir / "fallback.test.stdout.log",
                stderr_file=context.paths.logs_dir / "fallback.test.stderr.log",
                summary="python -m pytest exited with 0",
            )

            def fake_primary_run_pass(**kwargs):
                observed_providers.append(str(kwargs["context"].runtime.model_provider))
                return failing_result

            def fake_fallback_run_pass(*args, **kwargs):
                provider = str(kwargs["context"].runtime.model_provider)
                observed_providers.append(provider)
                if provider == "oss":
                    return local_success_result
                raise AssertionError(f"unexpected fallback provider: {provider}")

            fallback_runtimes = [
                RuntimeOptions(
                    model_provider="gemini",
                    provider_api_key_env="GEMINI_API_KEY",
                    codex_path="gemini.cmd",
                    model="gemini-not-real",
                    effort="medium",
                    test_cmd="python -m pytest",
                ),
                RuntimeOptions(
                    model_provider="oss",
                    local_model_provider="ollama",
                    codex_path="codex.cmd",
                    model="qwen2.5-coder:7b",
                    effort="medium",
                    test_cmd="python -m pytest",
                ),
            ]
            runner.run_pass.side_effect = fake_primary_run_pass

            with mock.patch(
                "jakal_flow.orchestrator.build_provider_fallback_runtimes",
                return_value=fallback_runtimes,
            ), mock.patch(
                "jakal_flow.orchestrator.CodexRunner.run_pass",
                side_effect=fake_fallback_run_pass,
            ) as mocked_fallback_run, mock.patch.object(
                orchestrator,
                "_execution_runtime_preflight_error",
                side_effect=lambda _context, candidate_runtime: (
                    "Model 'gemini-not-real' is not available for provider 'gemini' on this machine."
                    if str(candidate_runtime.model_provider) == "gemini"
                    else ""
                ),
            ), mock.patch.object(
                orchestrator,
                "_run_test_command",
                return_value=successful_test,
            ), mock.patch.object(
                orchestrator.git,
                "changed_files",
                return_value=["README.md"],
            ), mock.patch.object(orchestrator.git, "has_changes", return_value=True), mock.patch.object(
                orchestrator.git,
                "commit_all",
                return_value="local-fallback-closeout-commit",
            ) as mocked_commit, mock.patch.object(orchestrator.git, "hard_reset") as mocked_reset:
                result = orchestrator._execute_verified_repo_pass(
                    context=context,
                    runner=runner,
                    reporter=reporter,
                    prompt="Summarize the release closeout.",
                    pass_type="project-closeout-pass",
                    block_index=1,
                    task_name="Release closeout",
                    safe_revision="safe-revision",
                )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(observed_providers, ["openai", "oss"])
        self.assertEqual(context.runtime.model_provider, "oss")
        self.assertTrue(result["success"])
        self.assertEqual(result["run_result"].attempt_count, 2)
        self.assertEqual(result["run_result"].diagnostics["provider_fallback"]["to_provider"], "oss")
        self.assertEqual(
            [item["provider"] for item in result["run_result"].diagnostics["provider_fallback"]["chain"]],
            ["gemini", "oss"],
        )
        self.assertEqual(result["run_result"].diagnostics["provider_fallback"]["chain"][0]["skipped"], True)
        mocked_fallback_run.assert_called_once()
        self.assertEqual(mocked_reset.call_count, 1)
        mocked_commit.assert_called_once()

    def test_run_execution_closeout_reuses_successful_logged_closeout_pass(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_reuse_closeout_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", test_cmd="python -m pytest")

        try:
            context = orchestrator.workspace.initialize_local_project(project_dir=repo_dir, branch="main", runtime=runtime)
            context.metadata.current_safe_revision = "closeout-commit"
            context.loop_state.current_safe_revision = "closeout-commit"
            orchestrator.workspace.save_project(context)
            plan_state = orchestrator.save_execution_plan_state(
                context,
                ExecutionPlanState(
                    plan_title="Reuse closeout demo",
                    summary="All work is already finished.",
                    default_test_command="python -m pytest",
                    steps=[
                        ExecutionStep(
                            step_id="ST1",
                            title="Ship it",
                            status="completed",
                            completed_at="2026-03-30T00:00:00+00:00",
                            commit_hash="closeout-commit",
                            owned_paths=["src"],
                        )
                    ],
                ),
            )
            append_jsonl(
                context.paths.pass_log_file,
                {
                    "block_index": 7,
                    "pass_type": "project-closeout-pass",
                    "selected_task": "Project closeout",
                    "changed_files": ["README.md"],
                    "test_results": {
                        "command": "python -m pytest",
                        "returncode": 0,
                        "summary": "python -m pytest exited with 0",
                    },
                    "codex_return_code": 0,
                    "commit_hash": "closeout-commit",
                    "rollback_status": "not_needed",
                },
            )
            with mock.patch.object(
                orchestrator.git,
                "current_revision",
                return_value="closeout-commit",
            ), mock.patch.object(
                orchestrator,
                "_execute_verified_repo_pass",
            ) as mocked_execute_closeout, mock.patch.object(
                orchestrator,
                "_publish_closeout_pull_request",
            ) as mocked_publish:
                _context, saved = orchestrator.run_execution_closeout(
                    project_dir=repo_dir,
                    runtime=runtime,
                )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        mocked_execute_closeout.assert_not_called()
        mocked_publish.assert_called_once()
        self.assertEqual(saved.closeout_status, "completed")
        self.assertEqual(saved.closeout_commit_hash, "closeout-commit")
        self.assertIn("python -m pytest exited with 0", saved.closeout_notes)

    def test_run_result_failure_detail_prefers_event_error_over_empty_output_warning(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_run_result_failure_detail_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        temp_root.mkdir(parents=True, exist_ok=True)
        try:
            orchestrator = Orchestrator(temp_root / "workspace")
            event_file = temp_root / "block-search-pass.events.jsonl"
            event_file.write_text(
                "\n".join(
                    [
                        '{"type":"thread.started","thread_id":"demo"}',
                        '{"type":"turn.started"}',
                        '{"type":"error","message":"{\\"type\\":\\"error\\",\\"status\\":400,\\"error\\":{\\"type\\":\\"invalid_request_error\\",\\"message\\":\\"The \'codex\' model is not supported when using Codex with a ChatGPT account.\\"}}"}',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            run_result = CodexRunResult(
                pass_type="block-search-pass",
                prompt_file=temp_root / "block-search-pass.prompt.md",
                output_file=temp_root / "block-search-pass.last_message.txt",
                event_file=event_file,
                returncode=1,
                search_enabled=True,
                changed_files=[],
                usage={},
                last_message="",
                diagnostics={
                    "attempts": [
                        {
                            "attempt": 1,
                            "returncode": 1,
                            "stderr_excerpt": "Warning: no last agent message; wrote empty content to C:/Temp/out.txt",
                            "stdout_excerpt": '{"type":"turn.started"}',
                        }
                    ]
                },
            )

            detail = orchestrator._run_result_failure_detail(run_result)
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(detail, "The 'codex' model is not supported when using Codex with a ChatGPT account.")

    def test_run_manual_debugger_recovery_uses_failed_pass_diagnostics_without_test_log(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_manual_debugger_pass_fallback_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", test_cmd="python -m pytest")
        captured: dict[str, str] = {}

        try:
            context = orchestrator.workspace.initialize_local_project(
                project_dir=repo_dir,
                branch="main",
                runtime=runtime,
            )
            plan_state = ExecutionPlanState(
                plan_title="Manual debugger fallback",
                default_test_command="python -m pytest",
                steps=[
                    ExecutionStep(
                        step_id="ST1",
                        title="Freeze Shared Sync Boundary",
                        display_description="Add the shared integration boundary.",
                        codex_description="Repair the shared integration boundary safely.",
                        model_provider="openai",
                        model="codex",
                        test_command="python -m pytest",
                        status="failed",
                    )
                ],
            )
            orchestrator.save_execution_plan_state(context, plan_state)
            block_dir = context.paths.logs_dir / "block_0001"
            block_dir.mkdir(parents=True, exist_ok=True)
            event_file = block_dir / "block-search-pass.events.jsonl"
            event_file.write_text(
                "\n".join(
                    [
                        '{"type":"thread.started","thread_id":"demo"}',
                        '{"type":"turn.started"}',
                        '{"type":"error","message":"{\\"type\\":\\"error\\",\\"status\\":400,\\"error\\":{\\"type\\":\\"invalid_request_error\\",\\"message\\":\\"The \'codex\' model is not supported when using Codex with a ChatGPT account.\\"}}"}',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (block_dir / "block-search-pass.stderr.log").write_text(
                "Warning: no last agent message; wrote empty content to C:/Temp/out.txt\n",
                encoding="utf-8",
            )
            bundle_json = {
                "block_index": 1,
                "selected_task": "Freeze Shared Sync Boundary",
                "summary": "Freeze Shared Sync Boundary Codex pass failed and changes were rolled back.",
                "recent_passes": [
                    {
                        "block_index": 1,
                        "pass_type": "block-search-pass",
                        "selected_task": "Freeze Shared Sync Boundary",
                        "codex_return_code": 1,
                        "search_enabled": True,
                        "duration_seconds": 2.0,
                        "codex_diagnostics": {
                            "attempts": [
                                {
                                    "attempt": 1,
                                    "returncode": 1,
                                    "stderr_excerpt": "Warning: no last agent message; wrote empty content to C:/Temp/out.txt",
                                    "stdout_excerpt": '{"type":"error","message":"The \'codex\' model is not supported when using Codex with a ChatGPT account."}',
                                }
                            ]
                        },
                    }
                ],
            }
            report_json = context.paths.reports_dir / "20260329060315_lineage_batch_failed.prfail.json"
            report_json.write_text(json.dumps(bundle_json), encoding="utf-8")
            (context.paths.reports_dir / "latest_pr_failure_status.json").write_text(
                json.dumps(
                    {
                        "generated_at": "2026-03-29T06:03:15+00:00",
                        "failure_type": "lineage_batch_failed",
                        "report_json_file": str(report_json),
                        "report_markdown_file": str(context.paths.reports_dir / "20260329060315_lineage_batch_failed.prfail.md"),
                    }
                ),
                encoding="utf-8",
            )

            def fake_run_debugger_pass(**kwargs):
                execution_step = kwargs["execution_step"]
                failing_test_result = kwargs["failing_test_result"]
                captured["step_model"] = execution_step.model if execution_step is not None else ""
                captured["pass_name"] = kwargs["failing_pass_name"]
                captured["summary"] = failing_test_result.summary
                captured["stdout"] = failing_test_result.stdout_file.read_text(encoding="utf-8")
                captured["stderr"] = failing_test_result.stderr_file.read_text(encoding="utf-8")
                return (
                    "block-search-debug",
                    CodexRunResult(
                        pass_type="block-search-debug",
                        prompt_file=block_dir / "block-search-debug.prompt.md",
                        output_file=block_dir / "block-search-debug.last_message.txt",
                        event_file=block_dir / "block-search-debug.events.jsonl",
                        returncode=0,
                        search_enabled=False,
                        changed_files=[],
                        usage={},
                        last_message="Debugger repair applied",
                    ),
                    TestRunResult(
                        command="python -m pytest",
                        returncode=0,
                        stdout_file=block_dir / "block-search-debug.test.stdout.log",
                        stderr_file=block_dir / "block-search-debug.test.stderr.log",
                        summary="python -m pytest exited with 0",
                    ),
                    "debug-commit",
                )

            with mock.patch.object(orchestrator, "_run_debugger_pass", side_effect=fake_run_debugger_pass):
                _context, _saved, result = orchestrator.run_manual_debugger_recovery(
                    project_dir=repo_dir,
                    runtime=runtime,
                )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(captured["step_model"], "")
        self.assertEqual(captured["pass_name"], "block-search-pass")
        self.assertIn("The 'codex' model is not supported when using Codex with a ChatGPT account.", captured["summary"])
        self.assertIn("The 'codex' model is not supported when using Codex with a ChatGPT account.", captured["stdout"])
        self.assertIn("Warning: no last agent message", captured["stderr"])
        self.assertEqual(result["commit_hash"], "debug-commit")

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

    def test_parallel_batch_recovers_failed_worker_serially(self) -> None:
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

            def fake_serial_recovery(*args, **kwargs):
                recovery_context = kwargs["context"]
                self.assertFalse(kwargs["allow_push"])
                self.assertFalse(kwargs["final_failure_reports"])
                current = orchestrator.load_execution_plan_state(recovery_context)
                target = next(step for step in current.steps if step.step_id == "ST2")
                target.status = "completed"
                target.completed_at = "2026-03-29T00:00:00+00:00"
                target.commit_hash = "serial-recovery-commit"
                target.notes = "worker 2 recovered serially"
                recovery_context.metadata.current_safe_revision = "serial-recovery-commit"
                recovery_context.loop_state.current_safe_revision = "serial-recovery-commit"
                recovery_context.loop_state.last_commit_hash = "serial-recovery-commit"
                saved = orchestrator.save_execution_plan_state(recovery_context, current)
                return recovery_context, saved, next(step for step in saved.steps if step.step_id == "ST2")

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
                "_run_saved_execution_step_with_context",
                side_effect=fake_serial_recovery,
            ) as mocked_serial_recovery, mock.patch.object(
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

        self.assertEqual([step.status for step in steps], ["completed", "completed"])
        self.assertEqual([step.status for step in plan_state.steps], ["completed", "completed"])
        self.assertEqual(steps[0].commit_hash, "merge-commit-1")
        self.assertEqual(steps[1].commit_hash, "serial-recovery-commit")
        self.assertEqual(context.metadata.current_safe_revision, "serial-recovery-commit")
        self.assertEqual(context.metadata.current_status, "plan_completed")
        mocked_test.assert_called_once()
        self.assertEqual(mocked_push.call_count, 2)
        self.assertEqual(mocked_pick.call_count, 1)
        self.assertEqual(mocked_pick.call_args.args[1], "worker-1-commit")
        mocked_serial_recovery.assert_called_once()
        mocked_report.assert_not_called()
        self.assertEqual(steps[0].notes, "worker 1 ok")
        self.assertEqual(steps[1].notes, "worker 2 recovered serially")

    def test_parallel_batch_partial_failure_skips_batch_debugger(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_parallel_batch_skip_debugger_test"
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
                    plan_title="Parallel Skip Debugger Demo",
                    execution_mode="parallel",
                    default_test_command="python -m pytest",
                    steps=[
                        ExecutionStep(step_id="ST1", title="Desktop slice", test_command="python -m pytest", owned_paths=["desktop/src"]),
                        ExecutionStep(step_id="ST2", title="Backend slice", test_command="python -m pytest", owned_paths=["src/jakal_flow"]),
                    ],
                ),
            )

            failing_stdout = workspace_root / "parallel-batch-pass.stdout.log"
            failing_stderr = workspace_root / "parallel-batch-pass.stderr.log"
            failing_stdout.parent.mkdir(parents=True, exist_ok=True)
            failing_stdout.write_text("integration assertion failed\n", encoding="utf-8")
            failing_stderr.write_text("parallel batch traceback\n", encoding="utf-8")
            failing_test = TestRunResult(
                command="python -m pytest",
                returncode=1,
                stdout_file=failing_stdout,
                stderr_file=failing_stderr,
                summary="python -m pytest exited with 1",
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

            def fake_serial_recovery(*args, **kwargs):
                recovery_context = kwargs["context"]
                current = orchestrator.load_execution_plan_state(recovery_context)
                target = next(step for step in current.steps if step.step_id == "ST2")
                target.status = "completed"
                target.completed_at = "2026-03-30T00:00:00+00:00"
                target.commit_hash = "serial-recovery-commit"
                target.notes = "worker 2 recovered serially"
                recovery_context.metadata.current_safe_revision = "serial-recovery-commit"
                recovery_context.loop_state.current_safe_revision = "serial-recovery-commit"
                recovery_context.loop_state.last_commit_hash = "serial-recovery-commit"
                saved = orchestrator.save_execution_plan_state(recovery_context, current)
                return recovery_context, saved, next(step for step in saved.steps if step.step_id == "ST2")

            with mock.patch.object(orchestrator, "_run_parallel_step_worker", side_effect=worker_results), mock.patch.object(
                orchestrator,
                "_run_test_command",
                return_value=failing_test,
            ), mock.patch.object(
                orchestrator.git,
                "try_cherry_pick",
                return_value=CommandResult(command=["git", "cherry-pick"], returncode=0, stdout="", stderr=""),
            ), mock.patch.object(
                orchestrator.git,
                "current_revision",
                return_value="merge-commit-1",
            ), mock.patch.object(
                orchestrator,
                "_push_if_ready",
                return_value=(False, "already_up_to_date"),
            ), mock.patch.object(
                orchestrator,
                "_run_saved_execution_step_with_context",
                side_effect=fake_serial_recovery,
            ), mock.patch.object(
                orchestrator.git,
                "hard_reset",
            ), mock.patch.object(
                orchestrator,
                "_run_debugger_pass",
            ) as mocked_debugger, mock.patch.object(
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

        mocked_debugger.assert_not_called()
        self.assertEqual(context.metadata.current_safe_revision, "serial-recovery-commit")
        recovered_step = next(step for step in plan_state.steps if step.step_id == "ST2")
        self.assertEqual(recovered_step.status, "completed")
        self.assertIn("worker 2 recovered serially", recovered_step.notes)

    def test_parallel_batch_defers_step_when_serial_recovery_still_fails(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_parallel_batch_deferred_recovery_test"
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
                    plan_title="Parallel Deferred Recovery Demo",
                    execution_mode="parallel",
                    default_test_command="python -m pytest",
                    steps=[
                        ExecutionStep(step_id="ST1", title="Desktop slice", test_command="python -m pytest", owned_paths=["desktop/src"]),
                        ExecutionStep(step_id="ST2", title="Backend slice", test_command="python -m pytest", owned_paths=["src/jakal_flow"]),
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

            def fake_failed_serial_recovery(*args, **kwargs):
                recovery_context = kwargs["context"]
                current = orchestrator.load_execution_plan_state(recovery_context)
                target = next(step for step in current.steps if step.step_id == "ST2")
                target.status = "failed"
                target.notes = "serial recovery still failed"
                saved = orchestrator.save_execution_plan_state(recovery_context, current)
                return recovery_context, saved, next(step for step in saved.steps if step.step_id == "ST2")

            with mock.patch.object(orchestrator, "_run_parallel_step_worker", side_effect=worker_results), mock.patch.object(
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
                return_value="merge-commit-1",
            ), mock.patch.object(
                orchestrator,
                "_push_if_ready",
                return_value=(False, "already_up_to_date"),
            ) as mocked_push, mock.patch.object(
                orchestrator,
                "_run_saved_execution_step_with_context",
                side_effect=fake_failed_serial_recovery,
            ) as mocked_serial_recovery, mock.patch.object(
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

        self.assertEqual([step.status for step in steps], ["completed", "pending"])
        self.assertEqual([step.status for step in plan_state.steps], ["completed", "pending"])
        self.assertEqual(steps[0].commit_hash, "merge-commit-1")
        self.assertIsNone(steps[1].commit_hash)
        self.assertEqual(context.metadata.current_safe_revision, "merge-commit-1")
        self.assertEqual(context.metadata.current_status, "plan_ready")
        self.assertEqual(mocked_push.call_count, 1)
        mocked_serial_recovery.assert_called_once()
        mocked_report.assert_not_called()
        self.assertIn("Automatic recovery deferred", steps[1].notes)

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
        self.assertIn("{agents_summary}", parallel_step_template)
        self.assertIn("{step_metadata}", parallel_step_template)
        self.assertIn("step_metadata.step_kind", parallel_step_template)
        self.assertIn("saved DAG execution tree", parallel_step_template)
        self.assertIn("primary write scope", parallel_step_template)
        self.assertIn("do not emit bash heredocs", parallel_step_template.lower())
        self.assertIn("Do not edit README.md during normal execution steps.", parallel_step_template)
        self.assertIn("{agents_summary}", ml_step_template)
        self.assertIn("{ml_step_report_file}", ml_step_template)
        self.assertIn("Step metadata", ml_step_template)
        self.assertIn("do not emit bash heredocs", ml_step_template.lower())
        self.assertIn("Do not edit README.md during normal execution steps.", ml_step_template)
        self.assertEqual(DEBUGGER_PROMPT_FILENAME, DEBUGGER_PARALLEL_PROMPT_FILENAME)
        self.assertIn("{agents_summary}", parallel_debugger_template)
        self.assertIn("{step_metadata}", parallel_debugger_template)
        self.assertIn("step_metadata.step_kind", parallel_debugger_template)
        self.assertIn("{owned_paths}", parallel_debugger_template)
        self.assertIn("merged parallel batch", parallel_debugger_template)
        self.assertIn("cherry-pick conflict", parallel_debugger_template)
        self.assertIn("do not emit bash heredocs", parallel_debugger_template.lower())
        self.assertIn("If a repo-relative path is missing", parallel_debugger_template)
        self.assertIn("Do not edit README.md during debugger recovery.", parallel_debugger_template)
        self.assertIn("{agents_summary}", parallel_merger_template)
        self.assertIn("{merge_targets}", parallel_merger_template)
        self.assertIn("integration worktree", parallel_merger_template)
        self.assertIn("git worktree list", parallel_merger_template)
        self.assertIn("multiple branches or lineages", parallel_merger_template)
        self.assertIn("Failing merge context", parallel_merger_template)
        self.assertIn("adjacent compatibility breakage", parallel_merger_template)
        self.assertIn("adjacent integration touchpoints", parallel_merger_template)
        self.assertIn("do not emit bash heredocs", parallel_merger_template.lower())
        self.assertIn("If a repo-relative path is missing", parallel_merger_template)
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
        managed_docs = temp_root / "managed-docs"
        managed_docs.mkdir(parents=True, exist_ok=True)
        (repo_dir / "README.md").write_text("README summary", encoding="utf-8")
        (repo_dir / "AGENTS.md").write_text("AGENTS summary", encoding="utf-8")
        (repo_dir / "docs" / "notes.md").write_text("docs summary", encoding="utf-8")
        (repo_dir / "src" / "main.py").write_text("def run() -> None:\n    pass\n", encoding="utf-8")
        (managed_docs / "SPINE.json").write_text(
            json.dumps({"current_version": "spine-v7", "history": []}),
            encoding="utf-8",
        )
        (managed_docs / "SHARED_CONTRACTS.md").write_text(
            "# Shared Contracts\n\n- Current spine version: spine-v7\n- Shared contracts: api/ui-shell\n",
            encoding="utf-8",
        )

        try:
            repo_inputs = scan_repository_inputs(repo_dir)
            self.assertIn("notes.md", repo_inputs["docs"])
            self.assertIn("Existing implementation files detected.", repo_inputs["source"])
            self.assertIn("src/main.py", repo_inputs["source"])
            reference_notes = load_reference_guide_text()
            self.assertIn("React + Tauri", reference_notes)

            context = SimpleNamespace(
                paths=SimpleNamespace(
                    repo_dir=repo_dir,
                    plan_file=managed_docs / "PLAN.md",
                    spine_file=managed_docs / "SPINE.json",
                    shared_contracts_file=managed_docs / "SHARED_CONTRACTS.md",
                ),
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
        self.assertIn("Model routing guidance for this run:", plan_prompt)
        self.assertIn("Default routing for this run:", plan_prompt)
        self.assertIn("Current spine version:", plan_prompt)
        self.assertIn("spine-v7", plan_prompt)
        self.assertIn("Current shared contract snapshot:", plan_prompt)
        self.assertIn("api/ui-shell", plan_prompt)
        self.assertIn("parallel", plan_prompt)
        self.assertIn("Planner Agent A decomposition artifact:", plan_prompt)
        self.assertIn("Planner Agent A output unavailable.", plan_prompt)
        self.assertIn("Source inventory:", plan_prompt)
        self.assertIn("fold scaffold-only bootstrap work into the concrete implementation step", plan_prompt)
        self.assertIn('"block_id":"B1"', packed_plan_prompt)
        self.assertIn("step_id", plan_prompt)
        self.assertIn("model_provider", plan_prompt)
        self.assertIn('"model"', plan_prompt)
        self.assertIn("depends_on", plan_prompt)
        self.assertIn("owned_paths", plan_prompt)
        self.assertIn("step_type", plan_prompt)
        self.assertIn("scope_class", plan_prompt)
        self.assertIn("shared_contracts", plan_prompt)
        self.assertIn("primary_scope_paths", plan_prompt)
        self.assertIn("shared_reviewed_paths", plan_prompt)
        self.assertIn("forbidden_core_paths", plan_prompt)
        self.assertIn("src/jakal_flow/docs/REFERENCE_GUIDE.md", plan_prompt)
        self.assertIn("React + Tauri", plan_prompt)
        self.assertIn("well-known algorithm", plan_prompt)
        self.assertIn("step_type_hint", decomposition_prompt)
        self.assertIn("scope_class_hint", decomposition_prompt)
        self.assertIn("spine_version_hint", decomposition_prompt)
        self.assertIn("primary_scope_candidates", decomposition_prompt)
        self.assertIn("shared_reviewed_candidates", decomposition_prompt)
        self.assertIn("forbidden_core_candidates", decomposition_prompt)
        self.assertIn("1. Follow AGENTS.md and explicit repository constraints first.", bootstrap_prompt)
        self.assertIn("src/jakal_flow/docs/REFERENCE_GUIDE.md", bootstrap_prompt)
        self.assertIn("React + Tauri", bootstrap_prompt)
        self.assertIn("well-known algorithm", bootstrap_prompt)
        self.assertIn("finished, handoff-quality result", plan_prompt)
        self.assertIn("finished, handoff-quality implementation", bootstrap_prompt)

    def test_implementation_prompt_embeds_agents_summary_and_shell_guidance(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_step_prompt_guidance_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        repo_dir = temp_root / "repo"
        managed_docs = temp_root / "managed-docs"
        repo_dir.mkdir(parents=True, exist_ok=True)
        managed_docs.mkdir(parents=True, exist_ok=True)
        (repo_dir / "AGENTS.md").write_text("Keep changes scoped to src only.", encoding="utf-8")
        (managed_docs / "PLAN.md").write_text("Plan snapshot", encoding="utf-8")
        (managed_docs / "MID_TERM_PLAN.md").write_text("Mid term", encoding="utf-8")
        (managed_docs / "SCOPE_GUARD.md").write_text("Scope guard", encoding="utf-8")
        (managed_docs / "RESEARCH_NOTES.md").write_text("Research notes", encoding="utf-8")

        context = SimpleNamespace(
            paths=SimpleNamespace(
                repo_dir=repo_dir,
                docs_dir=managed_docs,
                plan_file=managed_docs / "PLAN.md",
                mid_term_plan_file=managed_docs / "MID_TERM_PLAN.md",
                scope_guard_file=managed_docs / "SCOPE_GUARD.md",
                research_notes_file=managed_docs / "RESEARCH_NOTES.md",
                ml_step_report_file=managed_docs / "ML_STEP_REPORT.json",
                ml_experiment_report_file=managed_docs / "ML_EXPERIMENT_REPORT.md",
            ),
            runtime=SimpleNamespace(
                workflow_mode="standard",
                execution_mode="parallel",
                test_cmd="python -m pytest",
                extra_prompt="",
            ),
        )
        candidate = CandidateTask(
            candidate_id="cand-1",
            title="Harden shell guidance",
            rationale="Keep shell usage compatible with the runtime.",
            plan_refs=[],
            score=1.0,
        )
        step = ExecutionStep(
            step_id="ST1",
            title="Harden shell guidance",
            display_description="Add runtime-safe execution instructions.",
            codex_description="Update the prompt to keep shell commands compatible with the active environment.",
            test_command="python -m pytest",
            owned_paths=["src/jakal_flow/docs"],
        )

        try:
            prompt = implementation_prompt(
                context,
                candidate,
                memory_context="None.",
                pass_name="block-search-pass",
                execution_step=step,
            )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertIn("Keep changes scoped to src only.", prompt)
        self.assertIn("do not emit bash heredocs", prompt.lower())
        self.assertIn("Do not probe parent directories outside the managed repo", prompt)

    def test_debugger_and_merger_prompts_embed_agents_summary_and_path_guards(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_recovery_prompt_guidance_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        repo_dir = temp_root / "repo"
        managed_docs = temp_root / "managed-docs"
        repo_dir.mkdir(parents=True, exist_ok=True)
        managed_docs.mkdir(parents=True, exist_ok=True)
        (repo_dir / "AGENTS.md").write_text("Keep recovery edits inside owned paths.", encoding="utf-8")
        (managed_docs / "PLAN.md").write_text("Plan snapshot", encoding="utf-8")
        (managed_docs / "MID_TERM_PLAN.md").write_text("Mid term", encoding="utf-8")
        (managed_docs / "SCOPE_GUARD.md").write_text("Scope guard", encoding="utf-8")
        (managed_docs / "RESEARCH_NOTES.md").write_text("Research notes", encoding="utf-8")

        context = SimpleNamespace(
            paths=SimpleNamespace(
                repo_dir=repo_dir,
                docs_dir=managed_docs,
                plan_file=managed_docs / "PLAN.md",
                mid_term_plan_file=managed_docs / "MID_TERM_PLAN.md",
                scope_guard_file=managed_docs / "SCOPE_GUARD.md",
                research_notes_file=managed_docs / "RESEARCH_NOTES.md",
                ml_step_report_file=managed_docs / "ML_STEP_REPORT.json",
                ml_experiment_report_file=managed_docs / "ML_EXPERIMENT_REPORT.md",
            ),
            runtime=SimpleNamespace(
                workflow_mode="standard",
                execution_mode="parallel",
                test_cmd="python -m pytest",
                extra_prompt="",
            ),
        )
        candidate = CandidateTask(
            candidate_id="cand-1",
            title="Recover integration flow",
            rationale="Diagnose the concrete failure before editing.",
            plan_refs=[],
            score=1.0,
        )
        step = ExecutionStep(
            step_id="ST2",
            title="Recover integration flow",
            display_description="Repair the failing integration slice.",
            codex_description="Inspect the failing paths and repair the narrow integration issue.",
            test_command="python -m pytest",
            owned_paths=["src/jakal_flow"],
        )

        try:
            debug_prompt = debugger_prompt(
                context,
                candidate,
                memory_context="None.",
                failing_pass_name="parallel-batch-merge-debug",
                failing_test_summary="Missing file",
                failing_test_stdout="",
                failing_test_stderr="Cannot find path",
                execution_step=step,
            )
            merge_prompt = merger_prompt(
                context,
                candidate,
                memory_context="None.",
                failing_command="git cherry-pick --continue",
                failing_summary="Merge conflict",
                failing_stdout="",
                failing_stderr="Cannot find path",
                merge_targets=["ST1", "ST2"],
                execution_step=step,
            )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertIn("Keep recovery edits inside owned paths.", debug_prompt)
        self.assertIn("do not emit bash heredocs", debug_prompt.lower())
        self.assertIn("If a repo-relative path is missing", debug_prompt)
        self.assertIn("Do not probe parent directories outside the managed repo", debug_prompt)
        self.assertIn("Keep recovery edits inside owned paths.", merge_prompt)
        self.assertIn("do not emit bash heredocs", merge_prompt.lower())
        self.assertIn("If a repo-relative path is missing", merge_prompt)
        self.assertIn("Do not probe parent directories outside the managed repo", merge_prompt)

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

    def test_scan_repository_inputs_reuses_disk_cache(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_repo_inputs_disk_cache_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        repo_dir = temp_root / "repo"
        cache_file = temp_root / "workspace" / "state" / "PLANNING_INPUTS_CACHE.json"
        (repo_dir / "docs").mkdir(parents=True, exist_ok=True)
        (repo_dir / "src").mkdir(parents=True, exist_ok=True)
        (repo_dir / "README.md").write_text("README summary", encoding="utf-8")
        (repo_dir / "AGENTS.md").write_text("AGENTS summary", encoding="utf-8")
        (repo_dir / "docs" / "note_1.md").write_text("docs summary", encoding="utf-8")
        (repo_dir / "src" / "main.py").write_text("def run() -> None:\n    pass\n", encoding="utf-8")

        try:
            payload = scan_repository_inputs(repo_dir, cache_file=cache_file)
            with mock.patch("jakal_flow.planning._build_repository_inputs", side_effect=AssertionError("disk cache should satisfy the second call.")):
                cached = scan_repository_inputs(repo_dir, cache_file=cache_file)
            cache_exists = cache_file.exists()
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertTrue(cache_exists)
        self.assertEqual(payload, cached)

    def test_scan_repository_inputs_invalidates_cache_when_git_tracks_content_change(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_repo_inputs_git_invalidation_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        repo_dir = temp_root / "repo"
        cache_file = temp_root / "workspace" / "state" / "PLANNING_INPUTS_CACHE.json"
        (repo_dir / "src").mkdir(parents=True, exist_ok=True)
        (repo_dir / "README.md").write_text("README summary", encoding="utf-8")
        (repo_dir / "AGENTS.md").write_text("AGENTS summary", encoding="utf-8")
        tracked_file = repo_dir / "src" / "main.py"
        tracked_file.write_text("def run() -> None:\n    pass\n", encoding="utf-8")
        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True, text=True)
        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True, text=True)
        subprocess.run(
            ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "init"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
            text=True,
        )

        try:
            scan_repository_inputs(repo_dir, cache_file=cache_file)
            tracked_file.write_text("def run() -> None:\n    print('updated')\n", encoding="utf-8")
            with mock.patch("jakal_flow.planning._build_repository_inputs", wraps=planning_module._build_repository_inputs) as mocked_build:
                scan_repository_inputs(repo_dir, cache_file=cache_file)
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertGreaterEqual(mocked_build.call_count, 1)

    def test_scan_repository_inputs_invalidates_cache_for_ignored_docs_changes(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_repo_inputs_ignored_docs_invalidation_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        repo_dir = temp_root / "repo"
        cache_file = temp_root / "workspace" / "state" / "PLANNING_INPUTS_CACHE.json"
        docs_dir = repo_dir / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / "README.md").write_text("README summary", encoding="utf-8")
        (repo_dir / "AGENTS.md").write_text("AGENTS summary", encoding="utf-8")
        (repo_dir / ".gitignore").write_text("docs/generated.md\n", encoding="utf-8")
        ignored_doc = docs_dir / "generated.md"
        ignored_doc.write_text("doc v1", encoding="utf-8")
        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True, text=True)
        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True, text=True)
        subprocess.run(
            ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "init"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
            text=True,
        )

        try:
            first = scan_repository_inputs(repo_dir, cache_file=cache_file)
            ignored_doc.write_text("doc v2", encoding="utf-8")
            second = scan_repository_inputs(repo_dir, cache_file=cache_file)
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertIn("doc v1", first["docs"])
        self.assertIn("doc v2", second["docs"])

    def test_source_inventory_uses_git_index_fast_path_before_scandir_fallback(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_source_inventory_git_fast_path_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        repo_dir = temp_root / "repo"
        (repo_dir / "src").mkdir(parents=True, exist_ok=True)
        (repo_dir / "src" / "main.py").write_text("def run() -> None:\n    pass\n", encoding="utf-8")
        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True, text=True)
        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True, text=True)
        subprocess.run(
            ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "init"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
            text=True,
        )

        try:
            with mock.patch("jakal_flow.planning._sorted_scandir", side_effect=AssertionError("git fast path should avoid the filesystem fallback for tracked source inventory.")):
                summary = planning_module._summarize_source_inventory(repo_dir)
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertIn("src/main.py", summary)
        self.assertIn("Existing implementation files detected.", summary)

    def test_prompt_to_execution_plan_prompt_reuses_prompt_bundle_cache(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_prompt_bundle_cache_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        repo_dir = temp_root / "repo"
        managed_docs = temp_root / "managed-docs"
        managed_state = temp_root / "managed-state"
        repo_dir.mkdir(parents=True, exist_ok=True)
        managed_docs.mkdir(parents=True, exist_ok=True)
        managed_state.mkdir(parents=True, exist_ok=True)
        (repo_dir / "README.md").write_text("README summary", encoding="utf-8")
        (repo_dir / "AGENTS.md").write_text("AGENTS summary", encoding="utf-8")
        (managed_state / "SPINE.json").write_text(json.dumps({"current_version": "spine-v9", "history": []}), encoding="utf-8")
        (managed_docs / "SHARED_CONTRACTS.md").write_text("# Shared Contracts\n\n- api/root\n", encoding="utf-8")
        repo_inputs = {
            "readme": "README summary",
            "agents": "AGENTS summary",
            "docs": "No markdown files under repo/docs.",
            "source": "Existing implementation files detected. src/main.py",
        }
        context = SimpleNamespace(
            paths=SimpleNamespace(
                repo_dir=repo_dir,
                plan_file=managed_docs / "PLAN.md",
                spine_file=managed_state / "SPINE.json",
                shared_contracts_file=managed_docs / "SHARED_CONTRACTS.md",
                planning_prompt_cache_file=managed_state / "PLANNING_PROMPT_CACHE.json",
            ),
            metadata=SimpleNamespace(
                repo_url="https://github.com/example/project.git",
                branch="main",
            ),
            runtime=SimpleNamespace(workflow_mode="standard"),
        )

        try:
            first = prompt_to_execution_plan_prompt(context, repo_inputs, "Build a desktop flow screen.", 4, "parallel")
            with mock.patch("jakal_flow.planning.followup_planning_repository_inputs", side_effect=AssertionError("prompt bundle cache should be reused.")), mock.patch(
                "jakal_flow.planning._planning_spine_version",
                side_effect=AssertionError("spine snapshot should come from the prompt bundle cache."),
            ), mock.patch(
                "jakal_flow.planning._planning_shared_contracts_snapshot",
                side_effect=AssertionError("shared contract snapshot should come from the prompt bundle cache."),
            ):
                second = prompt_to_execution_plan_prompt(context, repo_inputs, "Build a desktop flow screen.", 4, "parallel")
            cache_exists = (managed_state / "PLANNING_PROMPT_CACHE.json").exists()
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertTrue(cache_exists)
        self.assertEqual(first, second)

    def test_plan_work_reuses_existing_plan_without_re_scanning_resolution_inputs(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_plan_work_existing_plan_scan_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / "README.md").write_text("README summary", encoding="utf-8")
        (repo_dir / "AGENTS.md").write_text("AGENTS summary", encoding="utf-8")
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", test_cmd="python -m pytest")
        context = orchestrator.workspace.initialize_project(
            repo_url="https://github.com/example/project.git",
            branch="main",
            runtime=runtime,
        )
        context.paths.repo_dir.mkdir(parents=True, exist_ok=True)
        context.paths.plan_file.write_text("# Existing Plan\n\n- [ ] PL1: Keep the current plan.\n", encoding="utf-8")
        orchestrator.workspace.save_project(context)

        try:
            with mock.patch.object(orchestrator.workspace, "find_project", return_value=context), mock.patch.object(
                orchestrator.git,
                "clone_or_update",
            ), mock.patch.object(
                orchestrator.git,
                "configure_local_identity",
            ), mock.patch.object(
                orchestrator,
                "_plan_block_items",
                return_value=([], "# Mid-Term Plan\n"),
            ), mock.patch(
                "jakal_flow.orchestrator.scan_repository_inputs",
                side_effect=AssertionError("plan_work should not rescan repository inputs when the saved plan is reused."),
            ):
                result = orchestrator.plan_work(
                    repo_url="https://github.com/example/project.git",
                    branch="main",
                    runtime=runtime,
                )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(result["current_status"], context.metadata.current_status)

    def test_plan_block_items_reuses_cached_breakdown(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_block_plan_cache_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", test_cmd="python -m pytest")
        context = orchestrator.workspace.initialize_local_project(project_dir=repo_dir, branch="main", runtime=runtime)
        plan_text = "# Project Plan\n\n- [ ] PL1: Narrow task\n"
        planned_items = [PlanItem(item_id="PL1", text="Narrow task")]

        try:
            with mock.patch.object(orchestrator, "_generate_codex_work_items", return_value=planned_items):
                first_items, first_text = orchestrator._plan_block_items(
                    context=context,
                    runner=mock.Mock(),
                    plan_text=plan_text,
                    work_items=None,
                    max_items=3,
                    repo_inputs={"readme": "r", "agents": "a", "docs": "d", "source": "s"},
                )
            with mock.patch.object(
                orchestrator,
                "_generate_codex_work_items",
                side_effect=AssertionError("cached block plan should avoid another breakdown pass."),
            ):
                second_items, second_text = orchestrator._plan_block_items(
                    context=context,
                    runner=mock.Mock(),
                    plan_text=plan_text,
                    work_items=None,
                    max_items=3,
                    repo_inputs={"readme": "r", "agents": "a", "docs": "d", "source": "s"},
                )
            cache_exists = context.paths.block_plan_cache_file.exists()
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual([item.item_id for item in first_items], ["PL1"])
        self.assertEqual([item.item_id for item in second_items], ["PL1"])
        self.assertEqual(first_text, second_text)
        self.assertTrue(cache_exists)

    def test_plan_block_items_advances_through_cached_breakdown_queue(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_block_plan_cache_queue_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", test_cmd="python -m pytest")
        context = orchestrator.workspace.initialize_local_project(project_dir=repo_dir, branch="main", runtime=runtime)
        context.loop_state.block_index = 1
        plan_text = "# Project Plan\n\n- [ ] PL1: First task\n- [ ] PL2: Second task\n- [ ] PL3: Third task\n"
        planned_items = [
            PlanItem(item_id="PL1", text="First task"),
            PlanItem(item_id="PL2", text="Second task"),
            PlanItem(item_id="PL3", text="Third task"),
        ]

        try:
            with mock.patch.object(orchestrator, "_generate_codex_work_items", return_value=planned_items):
                first_items, _ = orchestrator._plan_block_items(
                    context=context,
                    runner=mock.Mock(),
                    plan_text=plan_text,
                    work_items=None,
                    max_items=3,
                    repo_inputs={"readme": "r", "agents": "a", "docs": "d", "source": "s"},
                )
            context.loop_state.block_index = 2
            with mock.patch.object(
                orchestrator,
                "_generate_codex_work_items",
                side_effect=AssertionError("cached block plan queue should avoid another breakdown pass."),
            ):
                second_items, second_text = orchestrator._plan_block_items(
                    context=context,
                    runner=mock.Mock(),
                    plan_text=plan_text,
                    work_items=None,
                    max_items=2,
                    repo_inputs={"readme": "r", "agents": "a", "docs": "d", "source": "s"},
                )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual([item.item_id for item in first_items], ["PL1", "PL2", "PL3"])
        self.assertEqual([item.item_id for item in second_items], ["PL2", "PL3"])
        self.assertIn("MT1 -> PL2: Second task", second_text)
        self.assertNotIn("MT1 -> PL1: First task", second_text)

    def test_plan_block_items_cache_survives_task_summary_updates(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_block_plan_cache_memory_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", test_cmd="python -m pytest")
        context = orchestrator.workspace.initialize_local_project(project_dir=repo_dir, branch="main", runtime=runtime)
        plan_text = "# Project Plan\n\n- [ ] PL1: Narrow task\n"
        planned_items = [PlanItem(item_id="PL1", text="Narrow task")]

        try:
            with mock.patch.object(orchestrator, "_generate_codex_work_items", return_value=planned_items):
                orchestrator._plan_block_items(
                    context=context,
                    runner=mock.Mock(),
                    plan_text=plan_text,
                    work_items=None,
                    max_items=3,
                    repo_inputs={"readme": "r", "agents": "a", "docs": "d", "source": "s"},
                )
            context.paths.task_summaries_file.write_text("updated task summary\n", encoding="utf-8")
            with mock.patch.object(
                orchestrator,
                "_generate_codex_work_items",
                side_effect=AssertionError("task summary updates should not invalidate the cached breakdown queue."),
            ):
                second_items, _ = orchestrator._plan_block_items(
                    context=context,
                    runner=mock.Mock(),
                    plan_text=plan_text,
                    work_items=None,
                    max_items=3,
                    repo_inputs={"readme": "r", "agents": "a", "docs": "d", "source": "s"},
                )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual([item.item_id for item in second_items], ["PL1"])

    def test_plan_block_items_prefetches_next_windows_into_cache(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_block_plan_prefetch_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", test_cmd="python -m pytest")
        context = orchestrator.workspace.initialize_local_project(project_dir=repo_dir, branch="main", runtime=runtime)
        context.loop_state.block_index = 1
        plan_text = "# Project Plan\n\n- [ ] PL1: First task\n- [ ] PL2: Second task\n- [ ] PL3: Third task\n- [ ] PL4: Fourth task\n"
        planned_items = [
            PlanItem(item_id="PL1", text="First task"),
            PlanItem(item_id="PL2", text="Second task"),
            PlanItem(item_id="PL3", text="Third task"),
            PlanItem(item_id="PL4", text="Fourth task"),
        ]

        try:
            with mock.patch.object(orchestrator, "_generate_codex_work_items", return_value=planned_items):
                orchestrator._plan_block_items(
                    context=context,
                    runner=mock.Mock(),
                    plan_text=plan_text,
                    work_items=None,
                    max_items=4,
                    repo_inputs={"readme": "r", "agents": "a", "docs": "d", "source": "s"},
                )
            cached = read_json(context.paths.block_plan_cache_file, default={})
            context.loop_state.block_index = 2
            with mock.patch(
                "jakal_flow.orchestrator.build_mid_term_plan_from_plan_items",
                side_effect=AssertionError("prefetched next-block windows should avoid rebuilding mid-term text."),
            ):
                second_items, second_text = orchestrator._plan_block_items(
                    context=context,
                    runner=mock.Mock(),
                    plan_text=plan_text,
                    work_items=None,
                    max_items=3,
                    repo_inputs={"readme": "r", "agents": "a", "docs": "d", "source": "s"},
                )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(int(cached.get("version", 0) or 0), 3)
        self.assertEqual(len(cached.get("prefetched_blocks", [])), 2)
        self.assertEqual([item.item_id for item in second_items], ["PL2", "PL3", "PL4"])
        self.assertIn("Second task", second_text)

    def test_generate_codex_work_items_uses_supplied_repo_inputs_without_rescan(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_generate_codex_work_items_scan_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", test_cmd="python -m pytest")
        context = orchestrator.workspace.initialize_local_project(project_dir=repo_dir, branch="main", runtime=runtime)
        supplied_repo_inputs = {
            "readme": "README summary",
            "agents": "AGENTS summary",
            "docs": "No markdown files under repo/docs.",
            "source": "Existing implementation files detected. Prefer extending src/main.py.",
        }

        try:
            with mock.patch(
                "jakal_flow.orchestrator.scan_repository_inputs",
                side_effect=AssertionError("supplied repo inputs should be reused directly."),
            ), mock.patch.object(
                MemoryStore,
                "render_context",
                return_value="memory context",
            ), mock.patch.object(
                orchestrator,
                "_run_pass_with_provider_fallback",
                return_value=SimpleNamespace(returncode=1, last_message=""),
            ):
                items = orchestrator._generate_codex_work_items(
                    context=context,
                    runner=mock.Mock(),
                    plan_text="# Plan\n\n- [ ] PL1: Demo\n",
                    max_items=3,
                    repo_inputs=supplied_repo_inputs,
                )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(items, [])

    def test_generate_codex_work_items_logs_planning_metrics(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_generate_codex_work_items_metrics_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        (repo_dir / "docs").mkdir(parents=True, exist_ok=True)
        (repo_dir / "src").mkdir(parents=True, exist_ok=True)
        (repo_dir / "README.md").write_text("README summary", encoding="utf-8")
        (repo_dir / "AGENTS.md").write_text("AGENTS summary", encoding="utf-8")
        (repo_dir / "src" / "main.py").write_text("def run() -> None:\n    pass\n", encoding="utf-8")
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", test_cmd="python -m pytest")
        context = orchestrator.workspace.initialize_local_project(project_dir=repo_dir, branch="main", runtime=runtime)

        try:
            with mock.patch.object(
                MemoryStore,
                "render_context",
                return_value="memory context",
            ), mock.patch.object(
                orchestrator,
                "_run_pass_with_provider_fallback",
                return_value=SimpleNamespace(
                    returncode=0,
                    last_message='{"tasks":[{"title":"Do the task","primary_ref":"PL1","reason":"Because it is the next narrow step."}]}',
                ),
            ):
                items = orchestrator._generate_codex_work_items(
                    context=context,
                    runner=mock.Mock(),
                    plan_text="# Project Plan\n\n- [ ] PL1: Do the task\n",
                    max_items=3,
                )
                metrics = read_jsonl_tail(context.paths.planning_metrics_file, 10)
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        stages = {entry["stage"] for entry in metrics}
        self.assertEqual(len(items), 1)
        self.assertIn("block_context_scan", stages)
        self.assertIn("block_prompt_build", stages)
        self.assertIn("block_agent_breakdown", stages)
        self.assertIn("block_breakdown_parse", stages)

    def test_save_execution_plan_state_skips_static_artifact_refresh_when_only_status_changes(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_plan_artifact_refresh_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", test_cmd="python -m pytest")
        context = orchestrator.workspace.initialize_local_project(project_dir=repo_dir, branch="main", runtime=runtime)
        initial_state = ExecutionPlanState(
            plan_title="Artifact refresh demo",
            project_prompt="Keep the plan stable.",
            summary="Plan structure should not be rewritten for status-only changes.",
            default_test_command="python -m pytest",
            steps=[
                ExecutionStep(
                    step_id="ST1",
                    title="Stabilize the plan artifacts",
                    display_description="Keep the static documents stable.",
                    codex_description="Preserve the plan docs while runtime status changes.",
                    owned_paths=["src/jakal_flow/orchestrator.py"],
                )
            ],
        )
        running_state = ExecutionPlanState(
            plan_title=initial_state.plan_title,
            project_prompt=initial_state.project_prompt,
            summary=initial_state.summary,
            default_test_command=initial_state.default_test_command,
            steps=[
                ExecutionStep(
                    step_id="ST1",
                    title="Stabilize the plan artifacts",
                    display_description="Keep the static documents stable.",
                    codex_description="Preserve the plan docs while runtime status changes.",
                    owned_paths=["src/jakal_flow/orchestrator.py"],
                    status="running",
                    started_at="2026-03-30T00:00:00+00:00",
                )
            ],
        )

        try:
            with mock.patch("jakal_flow.orchestrator.execution_plan_markdown", return_value="plan doc\n") as mocked_plan_markdown, mock.patch(
                "jakal_flow.orchestrator.build_mid_term_plan_from_plan_items",
                return_value=("mid term doc\n", []),
            ) as mocked_mid_term, mock.patch(
                "jakal_flow.orchestrator.ensure_scope_guard",
                return_value="scope guard\n",
            ) as mocked_scope_guard:
                orchestrator.save_execution_plan_state(context, initial_state)
                saved = orchestrator.save_execution_plan_state(context, running_state)
                checkpoint_payload = read_json(context.paths.checkpoint_state_file, default={})
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(mocked_plan_markdown.call_count, 1)
        self.assertEqual(mocked_mid_term.call_count, 1)
        self.assertEqual(mocked_scope_guard.call_count, 1)
        self.assertEqual(saved.steps[0].status, "running")
        self.assertEqual(checkpoint_payload["checkpoints"][0]["status"], "running")
        self.assertFalse(context.paths.execution_flow_svg_file.exists())

    def test_save_execution_plan_state_preserves_timestamp_when_content_is_unchanged(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_plan_timestamp_stability_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(model="gpt-5.4", effort="medium", test_cmd="python -m pytest")
        context = orchestrator.workspace.initialize_local_project(project_dir=repo_dir, branch="main", runtime=runtime)
        initial_state = ExecutionPlanState(
            plan_title="Stable timestamp demo",
            project_prompt="Keep identical plan saves cheap.",
            summary="Repeated identical saves should not churn timestamps.",
            default_test_command="python -m pytest",
            steps=[
                ExecutionStep(
                    step_id="ST1",
                    title="Keep state stable",
                    codex_description="Avoid rewriting identical execution plan state.",
                    owned_paths=["src/jakal_flow/orchestrator.py"],
                )
            ],
        )

        try:
            first = orchestrator.save_execution_plan_state(context, initial_state)
            second = orchestrator.save_execution_plan_state(context, initial_state)
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(first.last_updated_at, second.last_updated_at)


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
        self.assertIn("Compact planning mode", outline_text)
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

    def test_generate_execution_plan_skips_planner_agent_a_for_compact_existing_plan(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_adaptive_fast_planner_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / "README.md").write_text("README summary", encoding="utf-8")
        (repo_dir / "AGENTS.md").write_text("AGENTS summary", encoding="utf-8")
        (repo_dir / "src").mkdir(parents=True, exist_ok=True)
        (repo_dir / "src" / "planner.py").write_text("def run() -> None:\n    pass\n", encoding="utf-8")
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(
            model="gpt-5.4",
            effort="medium",
            planning_effort="medium",
            execution_mode="parallel",
            use_fast_mode=False,
            test_cmd="python -m pytest",
        )

        try:
            context = orchestrator.workspace.initialize_local_project(project_dir=repo_dir, branch="main", runtime=runtime)
            orchestrator.save_execution_plan_state(
                context,
                ExecutionPlanState(
                    plan_title="Existing compact plan",
                    project_prompt="Keep the plan compact.",
                    summary="A previously reviewed compact plan already exists.",
                    default_test_command="python -m pytest",
                    steps=[
                        ExecutionStep(
                            step_id="ST1",
                            title="Keep the compact plan current",
                            display_description="Refresh the small saved plan.",
                            codex_description="Refresh the compact saved plan without widening scope.",
                            owned_paths=["src/planner.py"],
                        )
                    ],
                ),
            )
            planning_events: list[tuple[str, str, dict[str, object] | None]] = []
            final_plan_json = """
            {
              "title": "Adaptive fast planner demo",
              "summary": "Reuse the compact outline and emit the final DAG directly.",
              "tasks": [
                {
                  "step_id": "ST1",
                  "task_title": "Refresh the compact planning path",
                  "display_description": "Keep the planning path current.",
                  "codex_description": "Update the compact planning path while preserving traceability.",
                  "reasoning_effort": "medium",
                  "depends_on": [],
                  "owned_paths": ["src/planner.py"],
                  "success_criteria": "The planning path is updated safely."
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
                usage={"input_tokens": 8},
                last_message=final_plan_json,
            )

            with mock.patch.object(orchestrator, "setup_local_project", return_value=context), mock.patch(
                "jakal_flow.orchestrator.CodexRunner.run_pass",
                return_value=run_result,
            ) as mocked_run_pass:
                _context, plan_state = orchestrator.generate_execution_plan(
                    project_dir=repo_dir,
                    runtime=runtime,
                    project_prompt="Refresh the planner.",
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
        self.assertIn("Compact planning mode", outline_text)
        self.assertIn("Planner Agent A decomposition artifact:", prompt)
        self.assertTrue(planning_events[2][2]["skipped"])
        self.assertEqual(plan_state.plan_title, "Adaptive fast planner demo")
        self.assertEqual([step.step_id for step in plan_state.steps], ["ST1"])

    def test_generate_execution_plan_uses_selected_planning_model_and_downgrades_gpt_54_effort(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_planning_model_effort_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / "README.md").write_text("README summary", encoding="utf-8")
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(
            model_provider="openai",
            model="gpt-5.4",
            planning_effort="high",
            effort="high",
            execution_mode="parallel",
            use_fast_mode=True,
            test_cmd="python -m pytest",
        )
        final_plan_json = """
        {
          "title": "Planner model demo",
          "summary": "Keep the configured planner model.",
          "tasks": [
            {
              "step_id": "ST1",
              "task_title": "Implement the requested change",
              "display_description": "Apply the change safely.",
              "codex_description": "Use the configured planner model and preserve the runtime choice.",
              "reasoning_effort": "medium",
              "depends_on": [],
              "owned_paths": ["src/demo.py"],
              "success_criteria": "The change is saved."
            }
          ]
        }
        """

        try:
            context = orchestrator.workspace.initialize_local_project(project_dir=repo_dir, branch="main", runtime=runtime)
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
                orchestrator.generate_execution_plan(
                    project_dir=repo_dir,
                    runtime=runtime,
                    project_prompt="Use the selected planning model.",
                    max_steps=3,
                )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(mocked_run_pass.call_count, 1)
        self.assertEqual(mocked_run_pass.call_args.kwargs["context"].runtime.model, "gpt-5.4")
        self.assertEqual(mocked_run_pass.call_args.kwargs["reasoning_effort"], "medium")

    def test_generate_execution_plan_keeps_non_gpt_54_planning_effort(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_planning_model_keep_effort_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / "README.md").write_text("README summary", encoding="utf-8")
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(
            model_provider="gemini",
            model="gemini-2.5-pro",
            planning_effort="medium",
            effort="medium",
            execution_mode="parallel",
            test_cmd="python -m pytest",
        )
        final_plan_json = """
        {
          "title": "Planner model demo",
          "summary": "Keep the configured planner model.",
          "tasks": [
            {
              "step_id": "ST1",
              "task_title": "Implement the requested change",
              "display_description": "Apply the change safely.",
              "codex_description": "Use the configured planner model and preserve the runtime choice.",
              "reasoning_effort": "medium",
              "depends_on": [],
              "owned_paths": ["src/demo.py"],
              "success_criteria": "The change is saved."
            }
          ]
        }
        """

        try:
            context = orchestrator.workspace.initialize_local_project(project_dir=repo_dir, branch="main", runtime=runtime)
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
                orchestrator.generate_execution_plan(
                    project_dir=repo_dir,
                    runtime=runtime,
                    project_prompt="Use the selected planning model.",
                    max_steps=3,
                )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(mocked_run_pass.call_args.kwargs["context"].runtime.model, "gemini-2.5-pro")
        self.assertEqual(mocked_run_pass.call_args.kwargs["reasoning_effort"], "medium")

    def test_generate_execution_plan_materializes_ensemble_step_models(self) -> None:
        temp_root = Path(__file__).resolve().parents[1] / ".tmp_ensemble_planner_test"
        shutil.rmtree(temp_root, ignore_errors=True)
        workspace_root = temp_root / "workspace"
        repo_dir = temp_root / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / "README.md").write_text("README summary", encoding="utf-8")
        (repo_dir / "desktop").mkdir(parents=True, exist_ok=True)
        (repo_dir / "desktop" / "ui.jsx").write_text("export default function Demo() { return null; }\n", encoding="utf-8")
        (repo_dir / "src").mkdir(parents=True, exist_ok=True)
        (repo_dir / "src" / "planner.py").write_text("def run() -> None:\n    pass\n", encoding="utf-8")
        orchestrator = Orchestrator(workspace_root)
        runtime = RuntimeOptions(
            model="gpt-5.4",
            effort="medium",
            planning_effort="medium",
            execution_mode="parallel",
            model_provider="ensemble",
            ensemble_openai_model="gpt-5.4-mini",
            ensemble_gemini_model="gemini-2.5-pro",
            ensemble_claude_model="claude-3.7-sonnet",
            use_fast_mode=True,
            test_cmd="python -m pytest",
        )

        try:
            context = orchestrator.workspace.initialize_local_project(project_dir=repo_dir, branch="main", runtime=runtime)
            final_plan_json = """
            {
              "title": "Ensemble planner demo",
              "summary": "Route UI work to Claude and backend work to Codex.",
              "tasks": [
                {
                  "step_id": "ST1",
                  "task_title": "Polish the desktop UI",
                  "display_description": "Update the desktop layout and visual polish.",
                  "codex_description": "Adjust the desktop UI and keep the Tauri entrypoint intact.",
                  "reasoning_effort": "medium",
                  "depends_on": [],
                  "owned_paths": ["desktop/src/components/views/AppSettingsView.jsx"],
                  "success_criteria": "The desktop UI reflects the new model routing controls."
                },
                {
                  "step_id": "ST2",
                  "task_title": "Update orchestrator routing",
                  "display_description": "Wire ensemble routing into planning and execution.",
                  "codex_description": "Update the orchestrator to preserve traceable backend routing.",
                  "reasoning_effort": "medium",
                  "depends_on": ["ST1"],
                  "owned_paths": ["src/jakal_flow/orchestrator.py"],
                  "success_criteria": "The planner and orchestrator share the same routing policy."
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
            ), mock.patch("jakal_flow.step_models.claude_available_for_auto_selection", return_value=True), mock.patch(
                "jakal_flow.step_models.gemini_available_for_auto_selection",
                return_value=False,
            ):
                _context, plan_state = orchestrator.generate_execution_plan(
                    project_dir=repo_dir,
                    runtime=runtime,
                    project_prompt="Route frontend work to Claude and backend work to Codex.",
                    max_steps=4,
                )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        self.assertEqual(plan_state.plan_title, "Ensemble planner demo")
        self.assertEqual(plan_state.steps[0].model_provider, "claude")
        self.assertEqual(plan_state.steps[0].model, "claude-3.7-sonnet")
        self.assertEqual(plan_state.steps[0].metadata["model_selection_source"], "auto")
        self.assertIn("Ensemble UI preference", plan_state.steps[0].metadata["model_selection_reason"])
        self.assertEqual(plan_state.steps[1].model_provider, "openai")
        self.assertEqual(plan_state.steps[1].model, "gpt-5.4-mini")
        self.assertEqual(plan_state.steps[1].metadata["model_selection_source"], "auto")

    def test_ensure_gitignore_adds_missing_entries_once(self) -> None:
        project_dir = Path(__file__).resolve().parents[1] / ".tmp_gitignore_test"
        shutil.rmtree(project_dir, ignore_errors=True)
        project_dir.mkdir(parents=True, exist_ok=True)
        gitignore = project_dir / ".gitignore"
        gitignore.write_text("node_modules/\n", encoding="utf-8")

        changed_first = ensure_gitignore(project_dir, entries=["_tmp_*/", ".venv/", "__pycache__/", ".parallel_runs/"])
        changed_second = ensure_gitignore(project_dir, entries=["_tmp_*/", ".venv/", "__pycache__/", ".parallel_runs/"])
        content = gitignore.read_text(encoding="utf-8")
        shutil.rmtree(project_dir, ignore_errors=True)

        self.assertTrue(changed_first)
        self.assertFalse(changed_second)
        self.assertIn("_tmp_*/", content)
        self.assertIn(".venv/", content)
        self.assertIn("__pycache__/", content)
        self.assertIn(".parallel_runs/", content)

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
