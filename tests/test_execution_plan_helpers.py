from __future__ import annotations

import unittest
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codex_auto.environment import ensure_gitignore
from codex_auto.gui import _plan_state_with_running_step
from codex_auto.models import ExecutionPlanState, ExecutionStep
from codex_auto.planning import (
    FINALIZATION_PROMPT_FILENAME,
    PLAN_GENERATION_PROMPT_FILENAME,
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
              "success_criteria": "CLI parsing succeeds."
            },
            {
              "task_title": "Wire the backend",
              "display_description": "Connect the new option to execution.",
              "codex_description": "Review the execution path, add targeted tests, and wire the backend.",
              "success_criteria": "Backend path is covered."
            }
          ]
        }
        """
        plan_title, summary, steps = parse_execution_plan_response(response, "python -m unittest", limit=4)

        self.assertEqual(plan_title, "CLI rollout")
        self.assertEqual(summary, "Build the feature in small verified steps.")
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0].step_id, "LT1")
        self.assertEqual(steps[0].display_description, "Expose the new flag to users.")
        self.assertIn("CLI parser", steps[0].codex_description)
        self.assertEqual(steps[0].test_command, "python -m unittest")
        self.assertEqual(steps[1].step_id, "LT2")
        self.assertEqual(steps[1].test_command, "python -m unittest")

    def test_execution_step_from_dict_accepts_legacy_description(self) -> None:
        step = ExecutionStep.from_dict(
            {
                "step_id": "LT1",
                "title": "Legacy task",
                "description": "Old UI description",
                "success_criteria": "Still works.",
            }
        )

        self.assertEqual(step.display_description, "Old UI description")
        self.assertEqual(step.codex_description, "Old UI description")
        self.assertEqual(step.success_criteria, "Still works.")

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

    def test_execution_plan_svg_includes_step_statuses(self) -> None:
        svg = execution_plan_svg(
            "demo flow",
            [
                ExecutionStep(step_id="LT1", title="First", test_command="pytest a", status="completed"),
                ExecutionStep(step_id="LT2", title="Second", test_command="pytest b", status="pending"),
            ],
        )

        self.assertIn("<svg", svg)
        self.assertIn("demo flow", svg)
        self.assertIn("LT1", svg)
        self.assertIn("LT2", svg)
        self.assertIn("#0f766e", svg)
        self.assertIn("#cbd5e1", svg)

    def test_plan_state_with_running_step_marks_selected_step_immediately(self) -> None:
        original = ExecutionPlanState(
            steps=[
                ExecutionStep(step_id="LT1", title="First", status="pending"),
                ExecutionStep(step_id="LT2", title="Second", status="running"),
                ExecutionStep(step_id="LT3", title="Third", status="pending"),
            ]
        )
        updated = _plan_state_with_running_step(original, "LT3")

        self.assertEqual(original.steps[1].status, "running")
        self.assertEqual(updated.steps[0].status, "pending")
        self.assertEqual(updated.steps[1].status, "paused")
        self.assertEqual(updated.steps[2].status, "running")

    def test_source_prompt_templates_exist_and_keep_expected_placeholders(self) -> None:
        plan_template = load_source_prompt_template(PLAN_GENERATION_PROMPT_FILENAME)
        step_template = load_source_prompt_template(STEP_EXECUTION_PROMPT_FILENAME)
        final_template = load_source_prompt_template(FINALIZATION_PROMPT_FILENAME)

        self.assertTrue(source_prompt_template_path(PLAN_GENERATION_PROMPT_FILENAME).exists())
        self.assertTrue(source_prompt_template_path(STEP_EXECUTION_PROMPT_FILENAME).exists())
        self.assertTrue(source_prompt_template_path(FINALIZATION_PROMPT_FILENAME).exists())
        self.assertIn("{repo_dir}", plan_template)
        self.assertIn("{user_prompt}", plan_template)
        self.assertIn("{max_steps}", plan_template)
        self.assertIn("{task_title}", step_template)
        self.assertIn("{display_description}", step_template)
        self.assertIn("{codex_description}", step_template)
        self.assertIn("{success_criteria}", step_template)
        self.assertIn("{completed_steps}", final_template)
        self.assertIn("{closeout_report_file}", final_template)
        self.assertIn("{test_command}", final_template)

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


if __name__ == "__main__":
    unittest.main()
