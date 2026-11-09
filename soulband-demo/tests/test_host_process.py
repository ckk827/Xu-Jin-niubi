"""Windows launcher regressions; only processes created by these tests are touched."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import unittest
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")


@unittest.skipUnless(sys.platform == "win32", "Windows process/venv ownership checks")
class HostProcessTests(unittest.TestCase):
    def run_ps(self, *args):
        return subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", *args],
                              cwd=ROOT, capture_output=True, text=True, timeout=30,
                              creationflags=subprocess.CREATE_NO_WINDOW)

    def test_owner_fixtures_in_windows_powershell_51(self):
        result = self.run_ps("-File", str(ROOT / "tests/check_host_process.ps1"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("fixtures passed: 9", result.stdout)

    def run_server_case(self, module_args, owned):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        folder = ROOT / "tests/.data" / ("host-process-" + uuid.uuid4().hex)
        folder.mkdir(parents=True)
        env = {**os.environ, "SOULBAND_DB": str(folder / "state.sqlite3"), "SOULBAND_INITIAL_MODE": ""}
        args = [str(port) if value == "PORT" else value for value in module_args]
        process = subprocess.Popen([sys.executable, *args], cwd=ROOT, env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            url = f"http://127.0.0.1:{port}" + ("/api/health" if owned else "/")
            for _ in range(100):
                try:
                    urllib.request.urlopen(url, timeout=.5).close()
                    break
                except OSError:
                    self.assertIsNone(process.poll(), "Fixture exited before listening")
                    time.sleep(.1)
            else:
                self.fail("Fixture never became ready")
            def quoted(value):
                return "'" + str(value).replace("'", "''") + "'"
            command = "$ErrorActionPreference='Stop'; . " + quoted(ROOT / "host_process.ps1")
            command += "; Stop-SoulbandHost -Python " + quoted(sys.executable) + " -Port " + str(port)
            result = self.run_ps("-Command", command)
            if owned:
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                process.wait(timeout=5)
                with socket.socket() as sock:
                    self.assertNotEqual(sock.connect_ex(("127.0.0.1", port)), 0)
            else:
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("not a verified host", result.stderr)
                self.assertIsNone(process.poll())
                self.assertEqual(urllib.request.urlopen(url, timeout=2).status, 200)
        finally:
            if process.poll() is None:
                # The venv launcher has a base-Python child: clean up this test's tree.
                subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            process.wait(timeout=5)

    def test_actual_venv_uvicorn_child_is_stopped_and_port_released(self):
        self.run_server_case(["-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "PORT"], True)

    def test_unrelated_python_http_server_is_preserved(self):
        self.run_server_case(["-m", "http.server", "PORT", "--bind", "127.0.0.1"], False)


if __name__ == "__main__":
    unittest.main()
