"""Repair low image labels in a disposable fake venv, preserving data and DACLs."""
import os
from pathlib import Path
import subprocess
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == "win32", "Windows mandatory integrity labels")
class DesktopRuntimeTests(unittest.TestCase):
    def test_real_image_label_repair_in_windows_powershell_51(self):
        folder = ROOT / "tests/.data" / ("integrity-fixture-" + uuid.uuid4().hex)
        powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        environment = dict(os.environ)
        environment.pop("PSModulePath", None)  # Do not give PS 5.1 PowerShell 7's modules.
        result = subprocess.run([str(powershell), "-NoProfile", "-ExecutionPolicy", "Bypass",
                                 "-File", str(ROOT / "tests/check_desktop_runtime.ps1"), "-Folder", str(folder)],
                                capture_output=True, text=True, timeout=40, env=environment,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Desktop integrity fixtures passed: 7", result.stdout)
