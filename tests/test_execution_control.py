from __future__ import annotations

import unittest
from unittest import mock

from jakal_flow.execution_control import ExecutionStopRegistry


class ExecutionControlTests(unittest.TestCase):
    def test_active_processes_returns_sorted_pid_entries(self) -> None:
        registry = ExecutionStopRegistry()
        process_a = mock.Mock(pid=3002)
        process_b = mock.Mock(pid=3001)

        with registry.manage_process("scope-1", process_a, label="Block B"), registry.manage_process(
            "scope-1",
            process_b,
            label="Block A",
        ):
            self.assertEqual(
                registry.active_processes("scope-1"),
                [
                    {"scope_id": "scope-1", "label": "Block A", "pid": 3001},
                    {"scope_id": "scope-1", "label": "Block B", "pid": 3002},
                ],
            )

    def test_request_stop_targets_only_matching_pids(self) -> None:
        registry = ExecutionStopRegistry()
        process_a = mock.Mock(pid=4101)
        process_b = mock.Mock(pid=4102)

        with registry.manage_process("scope-2", process_a, label="Block A"), registry.manage_process(
            "scope-2",
            process_b,
            label="Block B",
        ), mock.patch("jakal_flow.execution_control.terminate_process") as terminate_mock:
            registry.request_stop("scope-2", process_pids=[4102])

        terminate_mock.assert_called_once_with(4102)
        self.assertTrue(registry.stop_requested("scope-2"))


if __name__ == "__main__":
    unittest.main()
