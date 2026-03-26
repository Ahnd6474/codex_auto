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
from jakal_flow.models import ExecutionPlanState, ExecutionStep, RuntimeOptions
from jakal_flow.orchestrator import Orchestrator
from jakal_flow.planning import (
    FINALIZATION_PROMPT_FILENAME,
    PLAN_GENERATION_PROMPT_FILENAME,
    REFERENCE_GUIDE_FILENAME,
    SCOPE_GUARD_TEMPLATE_FILENAME,
    STEP_EXECUTION_PROMPT_FILENAME,
    bootstrap_plan_prompt,
    execution_plan_svg,
    load_reference_guide_text,
    load_source_prompt_template,
    parse_execution_plan_response,
    prompt_to_execution_plan_prompt,
    scan_repository_inputs,
    source_prompt_template_path,
)
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
        plan_template = load_source_prompt_template(PLAN_GENERATION_PROMPT_FILENAME)
        step_template = load_source_prompt_template(STEP_EXECUTION_PROMPT_FILENAME)
        final_template = load_source_prompt_template(FINALIZATION_PROMPT_FILENAME)
        scope_template = load_source_prompt_template(SCOPE_GUARD_TEMPLATE_FILENAME)

        self.assertTrue(source_prompt_template_path(PLAN_GENERATION_PROMPT_FILENAME).exists())
        self.assertTrue(source_prompt_template_path(STEP_EXECUTION_PROMPT_FILENAME).exists())
        self.assertTrue(source_prompt_template_path(FINALIZATION_PROMPT_FILENAME).exists())
        self.assertTrue(source_prompt_template_path(SCOPE_GUARD_TEMPLATE_FILENAME).exists())
        self.assertTrue(source_prompt_template_path(REFERENCE_GUIDE_FILENAME).exists())
        self.assertIn("{repo_dir}", plan_template)
        self.assertIn("{user_prompt}", plan_template)
        self.assertIn("{max_steps}", plan_template)
        self.assertIn("{execution_mode}", plan_template)
        self.assertIn('"step_id": "stable id like ST1"', plan_template)
        self.assertIn('"depends_on": ["step ids that must complete first"]', plan_template)
        self.assertIn('"owned_paths": ["repo-relative paths or directories this step primarily owns"]', plan_template)
        self.assertIn("{reference_notes}", plan_template)
        self.assertIn("src/jakal_flow/docs/REFERENCE_GUIDE.md", plan_template)
        self.assertIn("{task_title}", step_template)
        self.assertIn("{display_description}", step_template)
        self.assertIn("{codex_description}", step_template)
        self.assertIn("{success_criteria}", step_template)
        self.assertIn("{depends_on}", step_template)
        self.assertIn("{owned_paths}", step_template)
        self.assertIn("{plan_snapshot}", step_template)
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
