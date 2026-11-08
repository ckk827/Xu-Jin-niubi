"""Cross-client functional tests against real isolated SQLite files."""
import time
import uuid
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import app
import engine
import sensing
import storage as db


class BusinessTests(unittest.TestCase):
    def setUp(self):
        db.DB_PATH = Path(__file__).parent / ".data" / ("business-" + uuid.uuid4().hex + ".sqlite3")
        self.local = TestClient(app.app, client=("127.0.0.1", 3000))
        self.remote = TestClient(app.app, client=("192.0.2.1", 3001))

    def request(self, path, body=None, who="m1", method="POST", expected=200):
        r = self.local.request(method, "/api" + path, json=body, headers={"X-Member-Id": who})
        self.assertEqual(r.status_code, expected, r.text)
        return r.json()

    def activate(self):
        p = self.request("/proposals/generate")
        for n in range(1, 5):
            self.request(f"/proposals/{p['id']}/approve", who=f"m{n}")
        return p

    def account(self, who="m2", platform="web"):
        code = self.request("/access/code", {"member_id": who})["code"]
        r = self.remote.post("/api/access/redeem", json={"code": code, "platform": platform})
        self.assertEqual(r.status_code, 200)
        return {"Authorization": "Bearer " + r.json()["token"]}

    def test_lan_cannot_impersonate_and_private_inputs_are_isolated(self):
        self.assertEqual(self.remote.get("/api/state", headers={"X-Member-Id": "m1"}).status_code, 401)
        token = self.account()
        self.request("/needs", {"text": "私人原因不要给其他成员看", "visibility": "private"})
        self.request("/needs", {"text": "共同需求可以看", "visibility": "public"})
        state = self.remote.get("/api/state", headers={**token, "X-Member-Id": "m1"}).json()
        self.assertEqual(state["identity"]["member_id"], "m2")
        self.assertFalse(any("私人原因" in d["text"] for d in state["demands"]))
        self.assertNotIn("client_sessions", state)
        p = self.request("/proposals/generate")
        self.assertNotIn("私人原因", str(p))
        self.remote.post(f"/api/proposals/{p['id']}/approve", headers={**token, "X-Member-Id": "m1"})
        self.assertEqual(db.read()["proposals"][-1]["approvals"], ["m2"])
        self.assertEqual(self.remote.put("/api/settings", headers=token, json={"mode": "demo", "model": "foo"}).status_code, 403)

    def test_auth_code_one_use_revocation_and_read_permissions(self):
        code = self.request("/access/code", {"member_id": "m2"})["code"]
        data = {"code": code, "platform": "web"}
        r = self.remote.post("/api/access/redeem", json=data)
        token = {"Authorization": "Bearer " + r.json()["token"]}
        self.assertEqual(self.remote.post("/api/access/redeem", json=data).status_code, 401)
        self.request("/access/revoke", {"member_id": "m2"})
        self.assertEqual(self.remote.get("/api/state", headers=token).status_code, 401)

    def test_temporary_arrangement_requires_all_votes_and_expires(self):
        p = self.activate()
        clause = next(c for c in p["clauses"] if c["kind"] == "quiet")
        a = self.request("/adjustments", {"clause_id": clause["id"], "reason": "今晚临时讨论", "starts": "2026-10-28T00:00", "ends": "2026-10-28T00:30"})
        self.request(f"/adjustments/{a['id']}/vote", {"approve": True}, who="m2")
        self.assertTrue(engine.quiet_window(sensing.prepare(db.read()), clause)[0])
        for who in ("m3", "m4"):
            self.request(f"/adjustments/{a['id']}/vote", {"approve": True}, who=who)
        self.assertFalse(engine.quiet_window(sensing.prepare(db.read()), clause)[0])
        self.request("/analyze")
        self.assertEqual(db.read()["reminders"], [])
        self.request("/clock", {"date": "2026-10-28", "time": "00:31"}, method="PUT")
        self.request("/analyze")
        self.assertEqual(len(db.read()["reminders"]), 1)

    def test_task_swap_permissions_and_persistence(self):
        tasks = self.request("/tasks/rota", {"start": "2026-11-08", "days": 2, "members": ["m1", "m2"]})["items"]
        swap = self.request("/swaps", {"task_id": tasks[0]["id"], "other_task_id": tasks[1]["id"]})
        self.request(f"/swaps/{swap['id']}/vote", {"approve": True}, who="m3", expected=403)
        self.request(f"/swaps/{swap['id']}/vote", {"approve": True}, who="m2")
        saved = next(t for t in db.read()["tasks"] if t["id"] == tasks[0]["id"])
        self.assertEqual(saved["owner"], "m2")
        headers = self.account("m1")
        self.assertEqual(self.remote.post(f"/api/tasks/{saved['id']}/toggle", headers=headers).status_code, 403)

    def test_split_selected_members_and_settlement(self):
        bill = self.request("/bills", {"title": "三人用品", "amount": "10.01", "participants": ["m1", "m2", "m3"]})
        self.assertEqual(sum(v["cents"] for v in bill["shares"]), 1001)
        self.assertEqual([v["cents"] for v in bill["shares"]], [334, 334, 333])
        self.request(f"/bills/{bill['id']}/settle", who="m4", expected=403)
        self.request(f"/bills/{bill['id']}/settle", who="m2")
        self.assertEqual(db.read()["bills"][-1]["settled"], ["m2"])
        self.request("/bills", {"title": "重复", "amount": "1", "participants": ["m1", "m1"]}, expected=400)

    def test_participation_unknown_and_tool_confirmation(self):
        self.request("/participation", {"devices": []}, method="PUT")
        self.assertEqual(engine.evidence_status(db.read()["members"][0])[0], "unknown")
        result = self.request("/assistant", {"text": "完成清运垃圾与清理公共地面"})
        self.assertEqual(result["confirm_task_id"], "t1")
        self.assertFalse(db.read()["tasks"][0]["done"])
        self.request("/tasks/t1/complete")
        self.assertTrue(db.read()["tasks"][0]["done"])

    def test_opinion_preview_does_not_publish_raw_or_auto_apply_suggestion(self):
        private = "私人原因不能公开"
        result = self.request("/opinions/preview", {"category": "duties", "text": private})
        self.assertFalse(result["saved"])
        self.assertNotIn(private, str(db.read()))
        n = self.request("/opinions", {"category": "duties", "neutral": "希望重新讨论清洁分工"})
        self.request(f"/negotiations/{n['id']}/suggest")
        self.assertIsNone(db.read()["active_id"])
        self.assertIn("suggestion", db.read()["negotiations"][-1])

    def test_revoke_requires_every_member(self):
        p = self.activate()
        for who in ("m1", "m2", "m3"):
            self.request("/covenant/revoke-request", who=who)
        self.assertIsNotNone(db.read()["active_id"])
        self.request("/covenant/revoke-request", who="m4")
        self.request("/analyze")
        self.assertIsNone(db.read()["active_id"])
        self.assertEqual(db.read()["reminders"], [])
        self.request(f"/proposals/{p['id']}/approve", expected=409)

    def test_expired_covenant_does_not_send_and_member_add_requires_reapproval(self):
        p = self.activate()
        self.request("/members", {"name":"新成员"}, expected=409)
        revised = self.request(f"/proposals/{p['id']}/revise", {"title":p["title"],"clauses":p["clauses"],"conflicts":[],"valid_until":"2026-10-28T00:11"})
        for who in ("m1","m2","m3","m4"):
            self.request(f"/proposals/{revised['id']}/approve",who=who)
        self.request("/clock", {"date":"2026-10-28","time":"00:12"},method="PUT")
        self.request("/analyze")
        self.assertEqual(db.read()["reminders"],[])
        state=self.request("/state",method="GET")
        self.assertIsNone(state["active_id"])

    def test_six_members_all_confirm_and_pc_pause_is_ordered(self):
        self.request("/members", {"name":"成员五"})
        self.request("/members", {"name":"成员六"})
        self.request("/members", {"name":"成员七"},expected=409)
        p=self.request("/proposals/generate")
        for n in range(1,6):self.request(f"/proposals/{p['id']}/approve",who=f"m{n}")
        self.assertIsNone(db.read()["active_id"])
        self.request(f"/proposals/{p['id']}/approve",who="m6")
        self.assertEqual(db.read()["active_id"],p["id"])
        token=self.account("m2","pc")
        payload={"sequence":1,"sampled_at":time.time(),"idle_seconds":1,"locked":False,"session_active":True}
        self.assertEqual(self.remote.post("/api/pc/heartbeat",headers=token,json=payload).status_code,200)
        self.remote.post("/api/pc/pause",headers=token,json={"sequence":2})
        self.assertFalse(self.remote.post("/api/pc/heartbeat",headers=token,json=payload).json()["accepted"])
        self.assertEqual(db.read()["members"][1]["devices"][0]["signal"],"unknown")

    def test_pc_evidence_identity_freshness_and_delivery(self):
        token = self.account("m2", "pc")
        payload = {"sequence": 1, "sampled_at": time.time(), "idle_seconds": 2, "locked": False, "session_active": True}
        r = self.remote.post("/api/pc/heartbeat", headers=token, json=payload)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(db.read()["members"][1]["devices"][0]["signal"], "active")
        self.assertFalse(self.remote.post("/api/pc/heartbeat", headers=token, json=payload).json()["accepted"])
        self.activate(); self.request("/analyze")
        reminder = db.read()["reminders"][0]
        r = self.remote.post(f"/api/reminders/{reminder['id']}/delivered", headers=token, json={"device": "pc"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("pc", db.read()["reminders"][0]["delivered"])

    def test_old_reminders_are_history_but_not_late_notifications(self):
        self.activate(); self.request("/analyze")
        reminder=db.read()["reminders"][0]
        self.assertTrue(self.request("/state",who="m2",method="GET")["reminders"][0]["devices"])
        self.request("/clock",{"date":"2026-10-28","time":"15:00"},method="PUT")
        old=self.request("/state",who="m2",method="GET")["reminders"][0]
        self.assertEqual(old["devices"],[])
        self.assertIn("历史提醒",old["status"])
        self.request(f"/reminders/{reminder['id']}/delivered",{"device":"pc"},who="m2",expected=409)
        self.request(f"/reminders/{reminder['id']}/read",who="m2")


if __name__ == "__main__":
    unittest.main()
