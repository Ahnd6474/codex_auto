from __future__ import annotations

import unittest
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codex_auto.environment import ensure_gitignore
from codex_auto.models import ExecutionStep
from codex_auto.planning import execution_plan_svg, parse_execution_plan_response


class ExecutionPlanHelperTests(unittest.TestCase):
    def test_parse_execution_plan_response_reads_json_tasks(self) -> None:
        response = """
        {
          "summary": "Build the feature in small verified steps.",
          "tasks": [
            {
              "title": "Add the CLI flag",
              "description": "Expose the new flag to users.",
              "test_command": "python -m unittest tests.test_cli",
              "success_criteria": "CLI parsing succeeds."
            },
            {
              "title": "Wire the backend",
              "description": "Connect the new option to execution.",
              "test_command": "",
              "success_criteria": "Backend path is covered."
            }
          ]
        }
        """
        summary, steps = parse_execution_plan_response(response, "python -m unittest", limit=4)

        self.assertEqual(summary, "Build the feature in small verified steps.")
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0].step_id, "LT1")
        self.assertEqual(steps[0].test_command, "python -m unittest tests.test_cli")
        self.assertEqual(steps[1].step_id, "LT2")
        self.assertEqual(steps[1].test_command, "python -m unittest")

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


if __name__ == "__main__":
    unittest.main()
