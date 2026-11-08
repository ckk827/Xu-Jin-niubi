"""Read-only verification of the actual persistent user testing entry."""
import hashlib
import json
from pathlib import Path
import urllib.request
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
BASE="http://127.0.0.1:8765"


def main():
    def get(path):
        with urllib.request.urlopen(BASE+path,timeout=10) as response: return json.load(response)
    state=get("/api/state")
    assert state["mode"]=="ollama" and state["model"]=="qwen2.5:7b"
    assert "独立验收测试库" in state["environment"]
    models=get("/api/models")
    print("Installed model endpoint:",json.dumps(models,ensure_ascii=False))
    assert "qwen2.5:7b" in str(models)
    with urllib.request.urlopen(BASE+"/downloads/soulband.apk",timeout=10) as response: downloaded=response.read()
    apk=ROOT.parent/"output/apk/Soulband-v0.4.0-debug.apk"
    assert hashlib.sha256(downloaded).hexdigest()==hashlib.sha256(apk.read_bytes()).hexdigest()
    errors=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(channel="msedge",headless=True)
        page=browser.new_page(viewport={"width":1440,"height":1000})
        page.on("pageerror",lambda e:errors.append(str(e)))
        page.goto(BASE)
        expect(page.get_by_text("Ollama · 真实调用",exact=True)).to_be_visible()
        expect(page.get_by_role("button",name="协商与工具",exact=True)).to_be_visible()
        page.screenshot(path=str(ROOT/"screenshots/release-0.4/ready-environment.png"),full_page=True)
        assert not errors,errors
        browser.close()
    report={"url":BASE,"mode":state["mode"],"model":state["model"],"count":4,"checks":["persistent_isolated_real_mode","actual_model_available","served_apk_matches_final_artifact","browser_render_no_page_errors"],"errors":errors}
    (ROOT.parent/"output/release-2026-11-08/ready-environment.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=="__main__":main()
