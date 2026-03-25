from __future__ import annotations

import unittest
from pathlib import Path
import shutil
import sys
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codex_auto.environment import ensure_gitignore
from codex_auto.model_selection import (
    DEFAULT_MODEL_PRESET_ID,
    MODEL_MODE_CODEX,
    MODEL_MODE_SLUG,
    ModelSelection,
    model_preset_by_id,
    model_preset_from_runtime,
    model_selection_from_runtime,
)
from codex_auto.models import ExecutionPlanState, ExecutionStep, RuntimeOptions
from codex_auto.orchestrator import Orchestrator
from codex_auto.planning import (
    FINALIZATION_PROMPT_FILENAME,
    PLAN_GENERATION_PROMPT_FILENAME,
    SCOPE_GUARD_TEMPLATE_FILENAME,
    STEP_EXECUTION_PROMPT_FILENAME,
    execution_plan_svg,
    load_source_prompt_template,
    parse_execution_plan_response,
    source_prompt_template_path,
)
from codex_auto.utils import append_jsonl, read_jsonl_tail, read_last_jsonl


class ExecutionPlanHelperTests(unittest.TestCase):
    def test_parse_execution_plan_response_reads_json_tasks(self) -> None:
        response = """
        {
          "title": "CLI rollout",
          "summary": "Build the feature in small verified steps.",
          "tasks": [
            {
              "task_title": "Add the CLI flag",
              "display_description": "Expose the new flag to users.",
              "codex_description": "Inspect the CLI parser, add the flag, and cover it with tests.",
              "reasoning_effort": "medium",
              "success_criteria": "CLI parsing succeeds."
            },
            {
              "task_title": "Wire the backend",
              "display_description": "Connect the new option to execution.",
              "codex_description": "Review the execution path, add targeted tests, and wire the backend.",
              "reasoning_effort": "high",
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
        self.assertEqual(steps[1].step_id, "ST2")
        self.assertEqual(steps[1].test_command, "python -m unittest")
        self.assertEqual(steps[1].reasoning_effort, "high")

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
            }
        )

        self.assertEqual(step.reasoning_effort, "xhigh")

    def test_execution_plan_state_reads_closeout_fields(self) -> None:
        state = ExecutionPlanState.from_dict(
            {
                "plan_title": "demo",
                "closeout_status": "completed",
                "closeout_started_at": "2026-01-01T00:00:00+00:00",
                "closeout_completed_at": "2026-01-01T01:00:00+00:00",
                "closeout_commit_hash": "abc123",
                "closeout_notes": "final tests passed",
                "steps": [],
            }
        )

        self.assertEqual(state.closeout_status, "completed")
        self.assertEqual(state.closeout_commit_hash, "abc123")
        self.assertEqual(state.closeout_notes, "final tests passed")

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
            with mock.patch("codex_auto.orchestrator.ensure_virtualenv", return_value=repo_dir / ".venv"), mock.patch.object(
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
        self.assertEqual(resolved.model, "gpt-5.4")

    def test_model_preset_helpers_return_none_for_custom_runtime(self) -> None:
        runtime = RuntimeOptions(model="custom-preview-model", model_preset="", effort="medium")

        self.assertIsNone(model_preset_from_runtime(runtime))

    def test_source_prompt_templates_exist_and_keep_expected_placeholders(self) -> None:
        plan_template = load_source_prompt_template(PLAN_GENERATION_PROMPT_FILENAME)
        step_template = load_source_prompt_template(STEP_EXECUTION_PROMPT_FILENAME)
        final_template = load_source_prompt_template(FINALIZATION_PROMPT_FILENAME)
        scope_template = load_source_prompt_template(SCOPE_GUARD_TEMPLATE_FILENAME)

        self.assertTrue(source_prompt_template_path(PLAN_GENERATION_PROMPT_FILENAME).exists())
        self.assertTrue(source_prompt_template_path(STEP_EXECUTION_PROMPT_FILENAME).exists())
        self.assertTrue(source_prompt_template_path(FINALIZATION_PROMPT_FILENAME).exists())
        self.assertTrue(source_prompt_template_path(SCOPE_GUARD_TEMPLATE_FILENAME).exists())
        self.assertIn("{repo_dir}", plan_template)
        self.assertIn("{user_prompt}", plan_template)
        self.assertIn("{max_steps}", plan_template)
        self.assertIn("{task_title}", step_template)
        self.assertIn("{display_description}", step_template)
        self.assertIn("{codex_description}", step_template)
        self.assertIn("{success_criteria}", step_template)
        self.assertIn("{plan_snapshot}", step_template)
        self.assertIn("{completed_steps}", final_template)
        self.assertIn("{closeout_report_file}", final_template)
        self.assertIn("{test_command}", final_template)
        self.assertIn("{repo_url}", scope_template)

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
