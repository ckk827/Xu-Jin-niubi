"""Injected worker failure plus a headless browser fixture, on an isolated DB."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import uuid
from unittest.mock import patch

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import desktop
import desktop_launcher


def main():
    folder = ROOT / "tests/.data" / ("desktop-recovery-" + uuid.uuid4().hex)
    folder.mkdir(parents=True)
    os.environ.update(SOULBAND_DB=str(folder / "state.sqlite3"), SOULBAND_INITIAL_MODE="",
                      TEMP=str(folder), TMP=str(folder))
    os.environ.pop("QTWEBENGINE_DISABLE_SANDBOX", None)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    desktop.URL = f"http://127.0.0.1:{port}"
    errors, fallback = [], []
    def browser_fixture(url, target, smoke_test):
        fallback.append(True)
        with sync_playwright() as pw:
            # Restricted test execution cannot create Chromium's sandbox child.
            # This is confined to the test browser; production has no such flags.
            browser = pw.chromium.launch(channel="msedge", headless=True, chromium_sandbox=False)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(url)
            expect(page.get_by_role("heading", name="选择你的大模型")).to_be_visible()
            page.locator("#model-mode").select_option("external")
            expect(page.locator("#model-api-key")).to_be_visible()
            page.screenshot(path=str(folder / "recovered-ui.png"), full_page=True)
            assert page.request.get(url + "/api/health").ok
            browser.close()
    real_popen = subprocess.Popen
    def spawn_with_failed_worker(command, *args, **kwargs):
        if "--qt-worker" in command:
            command = [sys.executable, "-c", "raise SystemExit(17)"]
        return real_popen(command, *args, **kwargs)
    with patch.object(desktop_launcher, "open_browser_window", side_effect=browser_fixture), \
         patch.object(subprocess, "Popen", side_effect=spawn_with_failed_worker):
        code = desktop_launcher.launch(ROOT, desktop.URL, port, desktop.ensure_server, smoke_test=True)
    assert code == 0
    assert not errors, errors
    with socket.socket() as sock:
        assert sock.connect_ex(("127.0.0.1", port)) != 0, "Owned backend was not stopped"
    result = json.loads((folder / "desktop-startup.json").read_text(encoding="utf-8"))
    assert fallback and result["renderer"] == "browser" and result["qt_exit_code"] == 17, result
    result.update(browser_fixture_used=bool(fallback), browser_sandbox_disabled_for_test=bool(fallback),
                  qt_failure_injected=True, qt_sandbox_disabled=False, real_user_window_opened=False, errors=errors,
                  backend_stopped=True, artifacts=str(folder))
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
