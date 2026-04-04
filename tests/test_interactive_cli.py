from __future__ import annotations

from unittest import TestCase, mock

from jakal_flow.cli import main as cli_main
from jakal_flow.interactive_flow import apply_flow_edit, render_ascii_flow
from jakal_flow.models import ExecutionPlanState, ExecutionStep


class InteractiveCliTests(TestCase):
    def test_cli_no_args_enters_interactive_shell(self) -> None:
        with mock.patch("jakal_flow.cli.interactive_main", return_value=0) as interactive_main:
            exit_code = cli_main([])

        self.assertEqual(exit_code, 0)
        interactive_main.assert_called_once_with([])

    def test_apply_flow_edit_add_and_update_closeout(self) -> None:
        plan_state = ExecutionPlanState(default_test_command="python -m pytest")

        add_result = apply_flow_edit(plan_state, "add First step :: Build the first slice")
        self.assertTrue(add_result.changed)
        self.assertEqual(len(plan_state.steps), 1)
        self.assertEqual(plan_state.steps[0].step_id, "TMP1")
        self.assertEqual(plan_state.steps[0].display_description, "Build the first slice")

        closeout_result = apply_flow_edit(plan_state, "closeout title :: Ship it")
        self.assertTrue(closeout_result.changed)
        self.assertEqual(plan_state.closeout_title, "Ship it")

    def test_apply_flow_edit_set_and_swap_steps(self) -> None:
        plan_state = ExecutionPlanState(
            default_test_command="python -m pytest",
            steps=[
                ExecutionStep(step_id="ST1", title="One", status="pending"),
                ExecutionStep(step_id="ST2", title="Two", status="pending"),
            ],
        )

        apply_flow_edit(plan_state, "set ST1 title :: Renamed step")
        apply_flow_edit(plan_state, "swap ST1 ST2")

        self.assertEqual(plan_state.steps[0].step_id, "ST2")
        self.assertEqual(plan_state.steps[1].title, "Renamed step")

    def test_render_ascii_flow_shows_levels_and_closeout(self) -> None:
        plan_state = ExecutionPlanState(
            plan_title="Demo plan",
            execution_mode="parallel",
            default_test_command="python -m pytest",
            steps=[
                ExecutionStep(step_id="ST1", title="Prep", status="completed"),
                ExecutionStep(step_id="ST2", title="Build", status="running"),
                ExecutionStep(step_id="ST3", title="Wrap", status="pending", depends_on=["ST1", "ST2"]),
            ],
        )

        rendered = render_ascii_flow(plan_state, use_color=False)

        self.assertIn("jakal-flow execution board", rendered)
        self.assertIn("START", rendered)
        self.assertIn("ST1 Prep", rendered)
        self.assertIn("ST2 Build", rendered)
        self.assertIn("ST3 Wrap", rendered)
        self.assertIn("CLOSEOUT", rendered)
