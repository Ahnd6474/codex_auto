from __future__ import annotations

import subprocess
import signal
import unittest
from unittest import mock

from jakal_flow.process_supervisor import hidden_window_startupinfo, spawn_background_process, terminate_process


class ProcessSupervisorTests(unittest.TestCase):
    @mock.patch("jakal_flow.process_supervisor.os.name", "posix")
    @mock.patch("jakal_flow.process_supervisor.wait_for_condition", return_value=False)
    @mock.patch("jakal_flow.process_supervisor.os.kill")
    def test_terminate_process_escalates_to_sigkill_on_posix(
        self,
        kill_mock: mock.Mock,
        _wait_mock: mock.Mock,
    ) -> None:
        terminate_process(2468)

        kill_mock.assert_has_calls(
            [
                mock.call(2468, signal.SIGTERM),
                mock.call(2468, signal.SIGKILL),
            ]
        )

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

    @mock.patch("jakal_flow.process_supervisor.os.name", "nt")
    @mock.patch("jakal_flow.process_supervisor.subprocess.run")
    def test_terminate_process_uses_taskkill_tree_on_windows(self, run_mock: mock.Mock) -> None:
        terminate_process(4321)

        run_mock.assert_called_once_with(
            ["taskkill", "/PID", "4321", "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    @mock.patch("jakal_flow.process_supervisor.os.name", "nt")
    @mock.patch("jakal_flow.process_supervisor.subprocess.run", side_effect=OSError("taskkill unavailable"))
    def test_terminate_process_falls_back_when_taskkill_is_unavailable(self, _run_mock: mock.Mock) -> None:
        fake_kernel32 = mock.Mock()
        fake_kernel32.OpenProcess.return_value = object()
        fake_ctypes = mock.Mock()
        fake_ctypes.WinDLL.return_value = fake_kernel32
        fake_wintypes = mock.Mock(DWORD=object(), BOOL=object(), HANDLE=object(), UINT=object())

        with mock.patch.dict("sys.modules", {"ctypes": fake_ctypes, "ctypes.wintypes": fake_wintypes}):
            terminate_process(9876)

        fake_kernel32.OpenProcess.assert_called_once()
        fake_kernel32.TerminateProcess.assert_called_once()
        fake_kernel32.CloseHandle.assert_called_once()


if __name__ == "__main__":
    unittest.main()
