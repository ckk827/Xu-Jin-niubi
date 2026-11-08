"""Headless Edge end-to-end test; uses a separate local server and isolated SQLite database."""
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
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env["SOULBAND_DB"] = str(ROOT / "tests" / ".data" / ("ui-" + uuid.uuid4().hex + ".sqlite3"))
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(port)],
                               cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    base = f"http://127.0.0.1:{port}"
    checks, errors = [], []
    shots = ROOT / "screenshots"
    shots.mkdir(exist_ok=True)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/api/health", timeout=1).close()
                break
            except OSError:
                time.sleep(.1)
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page(viewport={"width":1440,"height":1080}, device_scale_factor=1)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base)
            expect(page.get_by_role("heading",name="小林，欢迎回到寝室")).to_be_visible()
            page.screenshot(path=str(shots / "overview-initial.png"), full_page=True)
            checks.append("desktop_initial_render")

            page.get_by_role("button",name="开始共建公约").click()
            page.get_by_role("button",name="综合需求，生成公约草案").click()
            expect(page.get_by_role("button",name="以小林身份确认")).to_be_enabled()
            for i, name in enumerate(["小林","阿泽","一诺","子航"],1):
                page.locator('#identity-select').select_option(f"m{i}")
                button = page.get_by_role("button",name=f"以{name}身份确认")
                expect(button).to_be_enabled()
                button.click()
                expect(page.get_by_text(f"{name} · 已确认",exact=True)).to_be_visible()
            expect(page.get_by_role("button",name="已全员确认生效")).to_be_visible()
            checks.append("four_profile_approval_via_ui")

            page.locator('#identity-select').select_option('m1')
            page.get_by_role("button",name="寝室概览",exact=True).click()
            page.get_by_role("button",name="体验主动提醒").click()
            expect(page.get_by_text("可能休息",exact=True).first).to_be_visible()
            page.screenshot(path=str(shots / "overview-desktop.png"), full_page=True)
            checks.append("activity_and_reminder_flow")

            page.locator('#identity-select').select_option('m2')
            page.get_by_role("button",name="我的提醒",exact=True).click()
            expect(page.get_by_text("按约预防性提醒",exact=True)).to_be_visible()
            page.get_by_role("button",name="我已读到").click()
            expect(page.get_by_text("成员已读",exact=False)).to_be_visible()
            checks.append("inbox_and_read_sync")

            page.get_by_role("button",name="公共事务",exact=True).click()
            page.locator('#bill-title').fill('测试垃圾袋')
            page.locator('#bill-amount').fill('10.01')
            page.get_by_role("button",name="记一笔公共账单").click()
            expect(page.get_by_text('测试垃圾袋',exact=True)).to_be_visible()
            checks.append("bill_form")

            page.get_by_role("button",name="私密沟通",exact=True).click()
            page.locator('#private-text').fill('半夜唱歌让我睡不着，但我不好意思直接提醒')
            page.get_by_role("button",name="帮我整理表达").click()
            expect(page.locator('.reply')).to_contain_text('一起找一个彼此都舒服的安排')
            checks.append("private_expression_form")

            page.get_by_role("button",name="演示与设置",exact=True).click()
            page.locator('#clock-time').fill('15:00')
            page.get_by_role("button",name="应用时钟设置").click()
            expect(page.locator('#clock-time')).to_have_value('15:00')
            checks.append("settings_and_clock")

            mobile=browser.new_context(viewport={"width":390,"height":844},device_scale_factor=1,is_mobile=True,has_touch=True)
            phone=mobile.new_page()
            phone.on("pageerror",lambda error:errors.append(str(error)))
            phone.goto(base+'/?device=phone')
            expect(phone.get_by_role("heading",name="小林，欢迎回到寝室")).to_be_visible()
            assert phone.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile horizontal overflow'
            phone.screenshot(path=str(shots/'overview-mobile.png'),full_page=True)
            phone.get_by_role('button',name='诉求与公约',exact=True).click()
            expect(phone.get_by_role('heading',name='每份需要，都值得被听见')).to_be_visible()
            assert phone.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile agreement overflow'
            phone.screenshot(path=str(shots/'agreement-mobile.png'),full_page=True)
            checks.append('mobile_390px_navigation_and_no_overflow')
            browser.close()
        assert not errors, errors
        checks.append('no_javascript_page_errors')
        report={"checks":checks,"count":len(checks),"errors":errors,"browser":"Headless Microsoft Edge", "real_ollama_tested":False}
        (shots/'ui-check-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False,indent=2))
    finally:
        process.terminate()
        process.wait(timeout=10)


if __name__=='__main__':
    main()
