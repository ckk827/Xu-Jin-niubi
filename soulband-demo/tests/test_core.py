"""Functional boundary tests. Each test keeps an isolated SQLite artifact under tests/.data."""
import asyncio
import json
from pathlib import Path
import sys
import threading
import time
import unittest
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import app
import engine
import storage as db


class DemoTests(unittest.TestCase):
    def setUp(self):
        db.DB_PATH = Path(__file__).parent / ".data" / (uuid.uuid4().hex + ".sqlite3")
        db.mutate(lambda state: state.update(mode="demo", model="qwen2.5:7b", model_configured=True))
        app.runtime.update(busy=False, error=None, last_signature=None)
        self.client = TestClient(app.app)

    def request(self, method, path, body=None, who="m1", expected=200):
        response = self.client.request(method, "/api" + path, json=body, headers={"X-Member-Id": who})
        self.assertEqual(response.status_code, expected, response.text)
        return response.json()

    def activate(self):
        proposal = self.request("POST", "/proposals/generate")
        for i in range(1, 5):
            self.request("POST", f"/proposals/{proposal['id']}/approve", who=f"m{i}")
        return proposal

    def test_no_approval_no_reminder_and_full_approval_activates(self):
        proposal = self.request("POST", "/proposals/generate")
        self.request("POST", "/analyze")
        self.assertEqual(db.read()["reminders"], [])
        for i in range(1, 4):
            self.request("POST", f"/proposals/{proposal['id']}/approve", who=f"m{i}")
        self.assertIsNone(db.read()["active_id"])
        self.request("POST", f"/proposals/{proposal['id']}/approve", who="m4")
        self.request("POST", "/analyze")
        self.assertEqual([r["target"] for r in db.read()["reminders"]], ["m2"])

    def test_background_watcher_sends_without_manual_analysis(self):
        with TestClient(app.app) as client:
            self.client = client
            self.activate()
            deadline = time.monotonic() + 6
            while time.monotonic() < deadline and not db.read()["reminders"]:
                time.sleep(.1)
            self.assertEqual([r["target"] for r in db.read()["reminders"]], ["m2"])

    def test_dedupe_survives_revision_and_midnight(self):
        p = self.activate()
        self.request("POST", "/analyze")
        self.request("POST", "/analyze")
        self.assertEqual(len(db.read()["reminders"]), 1)
        revised = self.request("POST", f"/proposals/{p['id']}/revise", {"title":p["title"], "clauses":p["clauses"], "conflicts":[]})
        self.assertEqual(revised["approvals"], [])
        for i in range(1,5):
            self.request("POST", f"/proposals/{revised['id']}/approve", who=f"m{i}")
        self.request("POST", "/analyze")
        self.assertEqual(len(db.read()["reminders"]), 1)
        self.request("PUT", "/clock", {"date":"2026-10-28", "time":"23:40"})
        self.request("POST", "/analyze")
        self.assertEqual(len(db.read()["reminders"]), 2)
        self.request("PUT", "/clock", {"date":"2026-10-29", "time":"00:10"})
        self.request("POST", "/analyze")
        self.assertEqual(len(db.read()["reminders"]), 2)

    def test_pc_locked_phone_active_and_missing_unknown(self):
        self.activate()
        self.request("PUT", "/devices/m1/phone", {"signal":"active"})
        self.request("PUT", "/devices/m3/phone", {"signal":"unknown"})
        result = self.request("POST", "/analyze")
        states = {s["member_id"]:s["status"] for s in result["states"]}
        self.assertEqual(states["m1"], "active")
        self.assertEqual(states["m3"], "unknown")

    def test_daytime_no_automatic_quiet_requirement(self):
        self.activate()
        self.request("PUT", "/clock", {"date":"2026-10-28", "time":"15:00"})
        self.request("POST", "/analyze")
        self.assertEqual(db.read()["reminders"], [])

    def test_manual_override_and_private_inbox(self):
        self.activate()
        self.request("PUT", "/manual", {"status":"active", "activity":"安静学习"}, who="m1")
        result = self.request("POST", "/analyze")
        self.assertEqual(next(s["status"] for s in result["states"] if s["member_id"]=="m1"), "active")
        inbox = self.request("GET", "/state", who="m3")
        self.assertEqual(inbox["reminders"], [])

    def test_feedback_followup_then_negotiation(self):
        self.activate()
        self.request("POST", "/analyze")
        self.request("POST", "/feedback", {"target":"m2", "result":"still"}, who="m1")
        self.assertEqual(len(db.read()["reminders"]), 2)
        self.request("POST", "/feedback", {"target":"m2", "result":"still"}, who="m3")
        self.assertEqual(len(db.read()["reminders"]), 2)
        self.assertEqual(len(db.read()["negotiations"]), 1)
        self.request("POST", "/analyze")
        self.assertEqual(len(db.read()["reminders"]), 2)

    def test_old_proposal_cannot_be_approved_after_revision(self):
        p = self.request("POST", "/proposals/generate")
        self.request("POST", f"/proposals/{p['id']}/revise", {"title":p["title"], "clauses":p["clauses"], "conflicts":[]})
        self.request("POST", f"/proposals/{p['id']}/approve", expected=409)

    def test_bill_cent_conservation_and_private_not_stored(self):
        bill = self.request("POST", "/bills", {"title":"垃圾袋", "amount":"10.01"})
        self.assertEqual(sum(s["cents"] for s in bill["shares"]), 1001)
        self.request("POST", "/bills", {"title":"垃圾袋", "amount":"10.001"}, expected=422)
        self.request("POST", "/private", {"text":"这是私密测试内容xyz", "style":"gentle"})
        self.assertNotIn("这是私密测试内容xyz", json.dumps(db.read(), ensure_ascii=False))

    def test_model_failure_never_falls_back(self):
        self.request("PUT", "/settings", {"mode":"ollama", "model":"not-installed"})
        async def broken(*args, **kwargs):
            raise RuntimeError("模型服务不可用，不切换模拟")
        with patch("engine.ollama", broken):
            self.request("POST", "/proposals/generate", expected=502)
        self.assertEqual(db.read()["proposals"], [])

    def test_context_change_during_inference_does_not_commit(self):
        self.activate()
        original = engine.analyze
        async def changing(snapshot):
            result = await original(snapshot)
            db.mutate(lambda state: state["demands"].append({"id": "r-late", "member_id": "m1", "text": "判断期间新增的诉求", "visibility": "public"}))
            return result
        with patch("engine.analyze", changing):
            self.request("POST", "/analyze", expected=409)
        self.assertEqual(db.read()["reminders"], [])

    def test_invalid_model_inference_is_rejected(self):
        self.activate()
        self.request("PUT", "/devices/m1/phone", {"signal":"unknown"})
        original = engine.analyze
        async def bad(snapshot):
            result = await original(snapshot)
            result.states[0].status = "resting"
            return result
        with patch("engine.analyze", bad):
            self.request("POST", "/analyze", expected=502)
        self.assertEqual(db.read()["reminders"], [])

    def test_ollama_http_adapter_sends_schema_and_parses_response(self):
        captured = {}
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                captured.update(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                data = json.dumps({"message":{"content":json.dumps({"reply":"这是接口联调用的模拟服务回复"},ensure_ascii=False)}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            def log_message(self, *args):
                pass
        server = HTTPServer(("127.0.0.1",0),Handler)
        thread = threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            with patch.dict("os.environ", {"OLLAMA_BASE_URL":f"http://127.0.0.1:{server.server_port}"}):
                result = asyncio.run(engine.ollama(db.read(), "接口测试", {}, engine.PrivateReply))
            self.assertIn("联调", result.reply)
            self.assertIn("properties", captured["format"])
            self.assertFalse(captured["stream"])
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
