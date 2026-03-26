from __future__ import annotations

import subprocess
import unittest
from unittest import mock

from jakal_flow.process_supervisor import hidden_window_startupinfo, spawn_background_process


class ProcessSupervisorTests(unittest.TestCase):
    @mock.patch("jakal_flow.process_supervisor.os.name", "posix")
    def test_hidden_window_startupinfo_returns_none_off_windows(self) -> None:
        self.assertIsNone(hidden_window_startupinfo())

    @mock.patch("jakal_flow.process_supervisor.os.name", "nt")
    def test_hidden_window_startupinfo_hides_windows_console(self) -> None:
        if not hasattr(subprocess, "STARTUPINFO"):
            self.skipTest("Windows startupinfo is unavailable on this platform.")
        startupinfo = hidden_window_startupinfo()
        self.assertIsNotNone(startupinfo)
        assert startupinfo is not None
        self.assertTrue(startupinfo.dwFlags & getattr(subprocess, "STARTF_USESHOWWINDOW", 0))
        self.assertEqual(startupinfo.wShowWindow, getattr(subprocess, "SW_HIDE", 0))

    @mock.patch("jakal_flow.process_supervisor.os.name", "nt")
    @mock.patch("jakal_flow.process_supervisor.subprocess.Popen")
    def test_spawn_background_process_retries_without_startupinfo_when_needed(self, popen_mock: mock.Mock) -> None:
        first_error = OSError("startupinfo rejected")
        process = mock.Mock()
        popen_mock.side_effect = [first_error, process]

        result = spawn_background_process(["python", "-V"])

        self.assertIs(result, process)
        self.assertEqual(popen_mock.call_count, 2)
        self.assertIsNotNone(popen_mock.call_args_list[0].kwargs["startupinfo"])
        self.assertIsNone(popen_mock.call_args_list[1].kwargs["startupinfo"])


if __name__ == "__main__":
    unittest.main()
