"""Native crash containment and owned-process lifecycle; no user windows are opened."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import desktop_launcher as launcher


class DesktopLauncherTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="soulband-launcher-")
        self.addCleanup(self.directory.cleanup)
        self.folder = Path(self.directory.name)
        self.environment = patch.dict(os.environ, {"SOULBAND_DB": str(self.folder / "state.sqlite3")})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.server = Mock(name="owned_server")
        self.worker = Mock(name="qt_worker")

    def run_launch(self, result=0, browser=False, fallback=None):
        with patch.object(launcher.subprocess, "Popen", return_value=self.worker), \
             patch.object(launcher, "wait_for_renderer", return_value=result), \
             patch.object(launcher, "stop_child") as stop, \
             patch.object(launcher, "open_browser_window", side_effect=fallback) as opened:
            code = launcher.launch(self.folder, "http://127.0.0.1:18765", 18765,
                                   lambda: self.server, browser=browser)
            return code, stop.call_args_list, opened.call_args_list

    def test_native_crash_falls_back_before_stopping_the_server(self):
        with patch.object(launcher, "stop_child") as stopped:
            def browser_window(*args):
                self.assertFalse(stopped.called, "Host must stay alive while the fallback window is in use")
            with patch.object(launcher.subprocess, "Popen", return_value=self.worker), \
                 patch.object(launcher, "wait_for_renderer", return_value=0xC000041D), \
                 patch.object(launcher, "open_browser_window", side_effect=browser_window) as browser:
                code = launcher.launch(self.folder, "http://127.0.0.1:18765", 18765, lambda: self.server)
            self.assertEqual(code, 0)
            browser.assert_called_once()
            stopped.assert_any_call(self.server)
        report = json.loads((self.folder / "desktop-startup.json").read_text())
        self.assertEqual(report["renderer"], "browser")
        self.assertEqual(report["qt_exit_code"], 0xC000041D)

    def test_timeout_also_opens_fallback(self):
        code, stopped, opened = self.run_launch(result=124)
        self.assertEqual(code, 0)
        self.assertEqual(len(opened), 1)
        self.assertEqual(len(stopped), 2)

    def test_normal_native_close_does_not_open_a_browser(self):
        code, _, opened = self.run_launch(result=0)
        self.assertEqual(code, 0)
        self.assertEqual(opened, [])

    def test_browser_error_is_reported_and_server_is_cleaned_up(self):
        code, stopped, _ = self.run_launch(result=17, fallback=RuntimeError("fixture browser error"))
        self.assertEqual(code, 1)
        self.assertEqual(stopped[-1].args, (self.server,))

    def test_explicit_browser_mode_never_starts_qt(self):
        with patch.object(launcher.subprocess, "Popen") as worker, \
             patch.object(launcher, "open_browser_window") as browser, \
             patch.object(launcher, "stop_child"):
            self.assertEqual(launcher.launch(self.folder, "http://127.0.0.1:18765", 18765,
                                            lambda: self.server, browser=True), 0)
            worker.assert_not_called()
            browser.assert_called_once()

    def test_hung_child_is_terminated_on_deadline(self):
        process = Mock(returncode=None)
        process.poll.return_value = None
        with patch.object(launcher.time, "monotonic", side_effect=[0, 21]), \
             patch.object(launcher, "stop_child") as stopped:
            self.assertEqual(launcher.wait_for_renderer(process, self.folder / "not-ready"), 124)
            stopped.assert_called_once_with(process)

    @unittest.skipUnless(sys.platform == "win32", "Windows shell handoff")
    def test_default_browser_receives_url_and_keeps_console_alive(self):
        with patch.object(launcher.os, "startfile") as shell, patch("builtins.input", return_value="") as hold, \
             patch("builtins.print") as output:
            launcher.open_browser_window("http://127.0.0.1:18765", self.folder)
        shell.assert_called_once_with("http://127.0.0.1:18765")
        self.assertFalse(any("已在" in str(call) and "打开" in str(call) for call in output.call_args_list))
        hold.assert_called_once()

    def test_failed_browser_request_leaves_manual_url_available_and_can_retry(self):
        with patch.object(launcher, "request_browser", side_effect=[OSError("not registered"), None, None]) as request, \
             patch("builtins.input", side_effect=["r", "e", ""]), patch("builtins.print") as output:
            launcher.open_browser_window("http://127.0.0.1:18765", self.folder)
        self.assertEqual([call.kwargs["edge"] for call in request.call_args_list], [False, False, True])
        self.assertTrue(any("http://127.0.0.1:18765" in str(call) for call in output.call_args_list))

    def test_invalid_console_input_does_not_stop_host_or_open_duplicate_windows(self):
        with patch.object(launcher, "request_browser") as request, \
             patch("builtins.input", side_effect=["invalid", ""]), patch("builtins.print"):
            launcher.open_browser_window("http://127.0.0.1:18765", self.folder)
        request.assert_called_once()

    def test_explicit_edge_retry_uses_normal_window_without_security_overrides(self):
        with patch.object(launcher, "find_edge", return_value=r"C:\Program Files\Edge\msedge.exe"), \
             patch.object(launcher.subprocess, "Popen") as start:
            start.return_value.wait.return_value = 0
            launcher.request_browser("http://127.0.0.1:18765", edge=True)
        self.assertEqual(start.call_args.args[0], [r"C:\Program Files\Edge\msedge.exe", "--new-window", "http://127.0.0.1:18765"])

    def test_explicit_edge_launch_failure_is_reported(self):
        with patch.object(launcher, "find_edge", return_value="msedge.exe"), \
             patch.object(launcher.subprocess, "Popen") as start:
            start.return_value.wait.return_value = 21
            with self.assertRaisesRegex(OSError, "21"):
                launcher.request_browser("http://127.0.0.1:18765", edge=True)

    def test_native_check_failure_cannot_be_reported_as_native_success(self):
        with self.assertRaises(RuntimeError):
            launcher.open_browser_window("http://127.0.0.1:18765", self.folder, smoke_test=True)


if __name__ == "__main__":
    unittest.main()
