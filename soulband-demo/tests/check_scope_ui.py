"""Review and persist quiet-clause scope using the real browser form."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


def main():
    folder = ROOT / "tests/.data" / ("scope-ui-" + uuid.uuid4().hex)
    folder.mkdir(parents=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {**os.environ, "SOULBAND_DB": str(folder / "state.sqlite3")}
    env["SOULBAND_INITIAL_MODE"] = "demo"
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(port)],
                              cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    base = f"http://127.0.0.1:{port}"
    def api(path, body=None, who="m1", method=None):
        req = urllib.request.Request(base + "/api" + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", "X-Member-Id": who}, method=method)
        return json.load(urllib.request.urlopen(req, timeout=5))
    try:
        for _ in range(100):
            try:
                api("/health")
                break
            except OSError:
                time.sleep(.1)
        api("/proposals/generate", {}, method="POST")
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base)
            page.get_by_role("button", name="诉求与公约", exact=True).click()
            page.get_by_role("button", name="修改为新版本", exact=True).click()
            page.locator('.clause-weekday[value="5"]').uncheck()
            page.locator('.clause-weekday[value="6"]').uncheck()
            page.locator('.clause-member[value="m2"]').uncheck()
            page.locator('.clause-member[value="m4"]').uncheck()
            page.locator('.clause-from').fill("2026-10-27")
            page.locator('.clause-until').fill("2026-11-30")
            page.get_by_role("button", name="保存为新版本", exact=True).click()
            expect(page.locator("#modal")).not_to_be_visible()
            expect(page.locator(".clause-block").first).to_contain_text("周五")
            expect(page.locator(".clause-block").first).not_to_contain_text("周六")
            clause = api("/state")["proposals"][-1]["clauses"][0]
            assert clause["weekdays"] == list(range(5)), clause
            assert clause["member_ids"] == ["m1", "m3"], clause
            assert clause["starts_on"] == "2026-10-27" and clause["ends_on"] == "2026-11-30"
            page.get_by_role("button", name="修改为新版本", exact=True).click()
            page.locator('.clause-exceptions').fill("考试前需另行确认")
            page.get_by_role("button", name="保存为新版本", exact=True).click()
            expect(page.locator("#modal")).not_to_be_visible()
            expect(page.locator(".clause-block").first).to_contain_text("仅文字约定，不自动提醒")
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path=str(folder / "mobile-scope.png"), full_page=True)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "mobile overflow"
            assert not errors, errors
            browser.close()
        print(json.dumps({"checks": ["review_weekdays", "review_members", "review_date_range", "manual_exception_label", "mobile_layout", "no_page_errors"], "count": 6}, indent=2))
    finally:
        server.terminate()
        server.wait(timeout=10)


if __name__ == "__main__":
    main()
