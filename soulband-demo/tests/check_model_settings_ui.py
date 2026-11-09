"""Browser plus local OpenAI-compatible fixture; never downloads or calls a real model."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    folder = ROOT / "tests/.data" / ("model-ui-" + uuid.uuid4().hex)
    folder.mkdir(parents=True)
    captured = []

    class Provider(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            captured.append({"path": self.path, "authorization": self.headers.get("Authorization"), "body": body})
            content = body["messages"][1]["content"]
            if "整理诉求卡" in content:
                output = {"text": "希望夜间保持安静", "category": "quiet", "questions": []}
            else:
                output = {"reply": "外部接口联调成功（模拟服务）"}
            data = json.dumps({"choices": [{"message": {"content": json.dumps(output, ensure_ascii=False)}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    provider = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    thread = threading.Thread(target=provider.serve_forever, daemon=True)
    thread.start()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {**os.environ, "SOULBAND_DB": str(folder / "state.sqlite3"), "SOULBAND_INITIAL_MODE": ""}
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(port)],
                               cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    base = f"http://127.0.0.1:{port}"
    endpoint = f"http://127.0.0.1:{provider.server_port}/v1"
    checks, errors, preparation_calls = [], [], []
    def state():
        return json.load(urllib.request.urlopen(base + "/api/state", timeout=3))
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/api/health", timeout=1).close()
                break
            except OSError:
                time.sleep(.1)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base)
            expect(page.get_by_role("heading", name="选择你的大模型")).to_be_visible()
            expect(page.locator("#model-mode")).to_have_value("")
            expect(page.locator('[data-model-source="ollama"]')).to_be_visible()
            expect(page.locator('[data-model-source="external"]')).to_be_visible()
            assert not captured
            page.screenshot(path=str(folder / "first-run.png"), full_page=True)
            checks.append("first_run_requires_choice_without_downloading")

            page.locator('[data-model-source="external"]').click()
            page.locator("#model-name").fill("https://provider.example")
            assert not page.locator("#model-name").evaluate("input => input.checkValidity()")
            checks.append("model_id_cannot_be_an_api_url")
            page.locator("#model-name").fill("fixture-chat")
            page.locator("#model-base-url").fill(endpoint)
            page.locator("#model-api-key").fill("fixture-key-not-real")
            expect(page.locator("#model-api-key")).to_have_attribute("type", "password")
            page.get_by_role("button", name="测试连接", exact=True).click()
            expect(page.locator("#toast")).to_contain_text("连接成功")
            assert state()["mode"] == "unconfigured"
            expect(page.locator("#model-api-key")).to_have_value("fixture-key-not-real")
            checks.append("test_pending_external_connection_without_saving")

            page.get_by_role("button", name="保存模型连接", exact=True).click()
            expect(page.get_by_role("heading", name="模型来源与连接")).to_be_visible()
            expect(page.locator(".mode-tag")).to_contain_text("外部 API")
            assert state()["mode"] == "external"
            assert "fixture-key-not-real" not in json.dumps(state())
            expect(page.locator("#model-api-key")).to_have_value("")
            assert captured[-1]["path"] == "/v1/chat/completions"
            assert captured[-1]["authorization"] == "Bearer fixture-key-not-real"
            checks.append("save_external_and_redact_secret")

            page.get_by_role("button", name="寝室概览", exact=True).click()
            page.get_by_role("button", name="模型连接", exact=True).click()
            expect(page.locator("#model-mode")).to_have_value("external")
            page.locator("#model-name").fill("unsaved-model")
            page.locator("#model-api-key").fill("unsaved-fixture-key")
            page.evaluate("window.connectionForm = document.getElementById('settings-form')")
            response = page.request.put(base + "/api/clock", data={"mode": "simulation", "date": "2026-11-09", "time": "13:01"})
            assert response.ok, response.text()
            page.evaluate("refresh(false)")
            assert page.evaluate("window.connectionForm === document.getElementById('settings-form')")
            expect(page.locator("#model-api-key")).to_have_value("unsaved-fixture-key")
            checks.append("persistent_entry_and_room_poll_does_not_replace_model_form")

            page.route("**/api/state*", lambda route: route.abort())
            page.evaluate("poll()")
            expect(page.locator("#connection-error")).to_be_visible()
            assert page.evaluate("window.connectionForm === document.getElementById('settings-form')")
            page.unroute("**/api/state*")
            page.evaluate("poll()")
            expect(page.locator("#connection-error")).to_have_count(0)
            expect(page.locator("#model-api-key")).to_have_value("unsaved-fixture-key")
            checks.append("connection_retry_keeps_unsaved_form")

            page.get_by_role("button", name="私密沟通", exact=True).click()
            expect(page.locator("#private-form")).to_contain_text("外部服务商")
            page.locator("#private-text").fill("希望商量夜间安静时间")
            page.get_by_role("button", name="帮我整理表达").click()
            expect(page.locator(".reply")).to_contain_text("外部接口联调成功")
            checks.append("real_http_adapter_with_local_provider_fixture")

            page.reload()
            page.get_by_role("button", name="演示与设置", exact=True).click()
            expect(page.locator("#model-mode")).to_have_value("external")
            expect(page.locator("#model-api-key")).to_have_value("")
            page.locator("#model-name").fill("fixture-chat-updated")
            page.get_by_role("button", name="保存模型连接", exact=True).click()
            expect(page.locator("#toast")).to_contain_text("已保存")
            assert state()["model"] == "fixture-chat-updated"
            checks.append("reload_and_keep_saved_key_when_blank")

            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "mobile settings overflow"
            page.screenshot(path=str(folder / "external-mobile.png"), full_page=True)
            checks.append("mobile_settings_no_overflow")

            invalid_saved = browser.new_page(viewport={"width": 1440, "height": 1000})
            invalid_state = state()
            invalid_state["model"] = "https://provider.example"
            invalid_saved.route("**/api/state*", lambda route: route.fulfill(json=invalid_state))
            invalid_saved.goto(base)
            expect(invalid_saved.get_by_role("heading", name="模型来源与连接")).to_be_visible()
            expect(invalid_saved.get_by_text("当前保存的模型名称是网址", exact=False)).to_be_visible()
            expect(invalid_saved.locator('[data-model-source="external"]')).to_be_visible()
            invalid_saved.screenshot(path=str(folder / "invalid-saved-model.png"), full_page=True)
            invalid_saved.close()
            checks.append("invalid_saved_model_opens_visible_connection_editor")

            def mock_setup(route):
                if route.request.method == "POST":
                    preparation_calls.append(route.request.url)
                route.fulfill(json={"running": True, "model": "qwen2.5:7b", "ready": False,
                                    "error": None, "output": ["模拟准备任务；未实际下载"]})
            page.route("**/api/settings/local-setup", mock_setup)
            page.locator("#model-mode").select_option("ollama")
            expect(page.locator("#model-name")).to_have_value("qwen2.5:7b")
            assert not preparation_calls
            page.get_by_role("button", name="保存并准备本地模型", exact=True).click()
            expect(page.locator("#model-setup-progress")).to_contain_text("正在准备")
            assert len(preparation_calls) == 1
            checks.append("local_setup_only_after_explicit_save_mocked_download")
            assert not errors, errors
            browser.close()
        print(json.dumps({"count": len(checks), "checks": checks, "errors": errors,
                          "real_external_model_tested": False, "real_download": False,
                          "artifacts": str(folder)}, ensure_ascii=False, indent=2))
    finally:
        process.terminate()
        process.wait(timeout=10)
        provider.shutdown()
        provider.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
