"""Exercise the added review workflows in Edge against an isolated server."""
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
        sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
    env = {**os.environ, "SOULBAND_DB": str(ROOT / "tests/.data" / ("release-ui-" + uuid.uuid4().hex + ".sqlite3"))}
    env["SOULBAND_INITIAL_MODE"] = "demo"
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    base = f"http://127.0.0.1:{port}"
    shots = ROOT / "screenshots/release-0.4"; shots.mkdir(parents=True, exist_ok=True)
    errors, checks = [], []
    def shot(page, check):
        page.screenshot(path=str(shots / (check + ".png")), full_page=True)
        checks.append(check)
    try:
        for _ in range(100):
            try: urllib.request.urlopen(base + "/api/health", timeout=1).close(); break
            except OSError: time.sleep(.1)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(base)
            page.get_by_role("button", name="协商与工具", exact=True).click()
            expect(page.get_by_role("heading", name="协商与受控工具")).to_be_visible()
            page.locator("#need-raw").fill("我的私人安排，不应进入寝室公约")
            page.get_by_role("button", name="先整理为需求卡").click()
            expect(page.locator("#need-final")).to_have_value("我的私人安排，不应进入寝室公约")
            page.locator("#need-visibility").select_option("private")
            page.get_by_role("button", name="确认保存需求卡").click()
            expect(page.locator("#need-final")).to_have_count(0)
            shot(page, "01-reviewed-private-need")
            page.locator("#question").fill("值日任务有哪些？")
            page.get_by_role("button", name="查询正式记录").click()
            expect(page.locator(".tool-result")).to_contain_text("清运垃圾")
            shot(page, "02-model-tool-read")
            page.locator("#task-title").fill("新增测试任务")
            page.get_by_role("button", name="创建公共任务", exact=True).click()
            page.locator("#rota-days").fill("2")
            page.get_by_role("button", name="按成员顺序生成轮值").click()
            expect(page.locator("#swap-own")).to_contain_text("新增测试任务")
            page.locator("#swap-own").select_option("t1")
            page.locator("#swap-other").select_option("t2")
            page.get_by_role("button", name="申请互换", exact=True).click()
            expect(page.get_by_text("小林 → 一诺 · 待审批")).to_be_visible()
            page.locator("#identity-select").select_option("m3")
            page.get_by_role("button", name="同意交换", exact=True).click()
            expect(page.get_by_text("小林 → 一诺 · 已同意")).to_be_visible()
            shot(page, "03-swap-approval")
            page.locator("#opinion-raw").fill("希望分工说得更清楚一点")
            page.locator("#opinion-category").select_option("duties")
            page.get_by_role("button", name="预览中性表达").click()
            expect(page.locator("#opinion-neutral")).to_contain_text("希望分工")
            page.locator("#opinion-neutral").fill("希望共同讨论卫生分工")
            page.get_by_role("button", name="确认公开并发起协商").click()
            expect(page.get_by_text("希望共同讨论卫生分工", exact=True)).to_be_visible()
            page.get_by_role("button", name="整理待审核协商建议").click()
            expect(page.get_by_text("演示建议：", exact=False)).to_be_visible()
            shot(page, "04-opinion-preview-and-suggestion")
            page.get_by_role("button", name="诉求与公约", exact=True).click()
            page.get_by_role("button", name="综合需求，生成公约草案").click()
            for i, name in enumerate(("小林", "阿泽", "一诺", "子航"), 1):
                page.locator("#identity-select").select_option(f"m{i}")
                page.get_by_role("button", name=f"以{name}身份确认").click()
                expect(page.get_by_text(name + " · 已确认", exact=True)).to_be_visible()
            page.get_by_role("button", name="协商与工具", exact=True).click()
            page.locator("#adjust-reason").fill("临时讨论测试")
            page.locator("#adjust-start").fill("2026-10-28T00:00")
            page.locator("#adjust-end").fill("2026-10-28T00:30")
            page.get_by_role("button", name="提交临时安排").click()
            for i in (1, 2, 3):
                page.locator("#identity-select").select_option(f"m{i}")
                page.get_by_role("button", name="同意临时安排", exact=True).click()
                expect(page.get_by_text(f"{i+1}/4 已同意", exact=False)).to_be_visible()
            shot(page, "05-temporary-arrangement-four-votes")
            page.get_by_role("button", name="公共事务", exact=True).click()
            page.locator("#bill-title").fill("三人分账测试")
            page.locator("#bill-amount").fill("10.01")
            page.locator('[name="bill-member"][value="m4"]').uncheck()
            page.get_by_role("button", name="记一笔公共账单").click()
            expect(page.get_by_text("一诺 · ¥ 3.33", exact=True)).to_be_visible()
            page.get_by_role("button", name="确认本人已结清").click()
            expect(page.get_by_role("button", name="本人已确认结清")).to_be_visible()
            shot(page, "06-selected-bill-and-settlement")
            page.get_by_role("button", name="协商与工具", exact=True).click()
            page.locator("#access-owner").select_option("m2")
            page.get_by_role("button", name="生成成员登录码", exact=True).click()
            expect(page.get_by_text("一次性登录码：", exact=False)).to_be_visible()
            import re
            code = re.search(r"一次性登录码：([A-F0-9]{10})", page.inner_text("body")).group(1)
            token = page.request.post(base + "/api/access/redeem", data={"code": code, "platform": "web"}).json()["token"]
            context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
            context.add_init_script("sessionStorage.setItem('soulband-token'," + json.dumps(token) + ");")
            phone = context.new_page(); phone.on("pageerror", lambda e: errors.append(str(e)))
            phone.goto(base + "/?device=phone")
            expect(phone.locator("#identity-select")).to_be_disabled()
            expect(phone.get_by_role("heading", name="阿泽，欢迎回到寝室")).to_be_visible()
            phone.get_by_role("button", name="协商与工具", exact=True).click()
            expect(phone.locator("#question")).to_be_visible()
            assert phone.evaluate("document.documentElement.scrollWidth <= innerWidth")
            shot(phone, "07-paired-mobile-workflows")
            phone.get_by_role("button", name="退出当前设备登录", exact=True).click()
            expect(phone.locator("#login-form")).to_be_visible()
            shot(phone, "08-login-screen")
            browser.close()
        assert not errors, errors
        result = {"checks": checks, "count": len(checks), "errors": errors, "browser": "Microsoft Edge", "phone_hardware": False}
        (shots / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        process.terminate(); process.wait(timeout=10)


if __name__ == "__main__": main()
