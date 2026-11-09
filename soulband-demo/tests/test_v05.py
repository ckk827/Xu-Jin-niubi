"""v0.5 boundaries: covenant expiry, deterministic scheduling, host seats, private cards."""
import json
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import app
import engine
import scheduling
import sensing
import storage as db


class V05Tests(unittest.TestCase):
    def setUp(self):
        db.DB_PATH = Path(__file__).parent / ".data" / (uuid.uuid4().hex + ".sqlite3")
        db.mutate(lambda state: state.update(mode="demo", model="qwen2.5:7b", model_configured=True))
        app.runtime.update(busy=False, error=None, last_signature=None, last_analysis_at=0.0, schedule_block_until=0.0)
        self.client = TestClient(app.app)

    def request(self, method, path, body=None, who="m1", expected=200, headers=None):
        merged = {"X-Member-Id": who, **(headers or {})}
        response = self.client.request(method, "/api" + path, json=body, headers=merged)
        self.assertEqual(response.status_code, expected, response.text)
        return response.json()

    def activate(self):
        proposal = self.request("POST", "/proposals/generate")
        for i in range(1, 5):
            self.request("POST", f"/proposals/{proposal['id']}/approve", who=f"m{i}")
        return proposal

    def test_expired_covenant_frees_members_and_explains_revoke(self):
        proposal = self.activate()
        db.mutate(lambda state: state["proposals"][-1].update(valid_until="2026-10-27T23:59"))
        state = self.request("GET", "/state")
        self.assertIsNone(state["active_id"])
        self.assertEqual(state["proposals"][-1]["status"], "expired")
        # The old deadlock: adding a member used to be blocked by a covenant that no longer runs.
        self.request("POST", "/members", {"name": "小周"})
        self.request("POST", "/covenant/revoke-request", expected=409)
        message = self.client.post("/api/covenant/revoke-request", headers={"X-Member-Id": "m1"}).json()["detail"]
        self.assertIn("已到期", message)
        self.assertEqual(len(db.read()["members"]), 5)
        self.assertEqual(len(self.request("GET", "/state")["proposals"]), 1)
        self.assertEqual(self.request("GET", "/state")["proposals"][0]["id"], proposal["id"])

    def test_expiry_is_persisted_and_visible_to_incremental_pollers(self):
        self.activate()
        self.request("GET", "/state")
        # The edit bumps the revision but does not apply the deadline until the next load.
        stale = db.mutate(lambda state: (state["proposals"][-1].update(valid_until="2026-10-27T23:59"),
                                         state["revision"])[1])
        fresh = self.request("GET", f"/state?since={stale}")
        self.assertNotIn("unchanged", fresh)   # expiry itself must invalidate the cursor
        self.assertGreater(fresh["revision"], stale)
        self.assertEqual(fresh["proposals"][-1]["status"], "expired")
        self.assertTrue(any("到期" in item["action"] for item in fresh["traces"]))
        # Persisted, not recomputed into a different shape on every read.
        self.assertEqual(self.request("GET", f"/state?since={fresh['revision']}")["unchanged"], True)
        self.assertEqual(db.read()["revision"], fresh["revision"])

    def test_scheduler_fires_on_window_start_and_reports_missed_start(self):
        self.activate()
        self.request("PUT", "/clock", {"date": "2026-10-28", "time": "15:00"})
        db.mutate(scheduling.rebuild)
        schedule = db.read()["scheduler"]
        self.assertTrue(schedule["next_fire_at"].endswith("23:30:00"))
        self.assertEqual(scheduling.evaluate(db.read())["action"], "idle")

        db.mutate(lambda state: state["clock"].update(time="23:31"))
        self.assertEqual(scheduling.evaluate(db.read())["action"], "fire")

        db.mutate(lambda state: state["clock"].update(time="23:50"))
        verdict = scheduling.evaluate(db.read())
        self.assertEqual(verdict["action"], "missed")
        self.assertIn("23:30", verdict["reason"])
        # A reported miss must not be replayed on every following tick.
        db.mutate(lambda state: scheduling.mark_missed(state, verdict.get("cycle")))
        self.assertEqual(scheduling.evaluate(db.read())["action"], "idle")

    def test_window_entry_triggers_one_analysis_not_one_per_minute(self):
        self.activate()
        self.request("PUT", "/clock", {"date": "2026-10-28", "time": "23:29"})
        self.request("POST", "/analyze")
        self.assertEqual(db.read()["reminders"], [])
        self.request("PUT", "/clock", {"date": "2026-10-28", "time": "23:30"})
        self.request("POST", "/analyze")
        self.assertEqual(len(db.read()["reminders"]), 1)
        for minute in ("23:31", "23:45", "23:59"):
            self.request("PUT", "/clock", {"date": "2026-10-28", "time": minute})
            self.request("POST", "/analyze")
        self.assertEqual(len(db.read()["reminders"]), 1)

    def test_clock_tick_does_not_invalidate_analysis_context(self):
        self.activate()
        state = sensing.prepare(db.read())
        before = sensing.analysis_key(state)
        state["clock"]["time"] = "00:20"
        self.assertEqual(before, sensing.analysis_key(state))
        state["clock"]["time"] = "15:00"
        self.assertNotEqual(before, sensing.analysis_key(state))

    def test_two_clauses_in_one_window_merge_into_one_reminder(self):
        proposal = self.activate()
        clauses = [dict(proposal["clauses"][0])]
        second = dict(clauses[0])
        second["id"] = "quiet2"
        second["title"] = "第二段安静约定"
        clauses.append(second)
        revised = self.request("POST", f"/proposals/{proposal['id']}/revise",
                               {"title": proposal["title"], "clauses": clauses, "conflicts": []})
        for i in range(1, 5):
            self.request("POST", f"/proposals/{revised['id']}/approve", who=f"m{i}")
        original = engine.analyze
        async def duplicated(snapshot):
            result = await original(snapshot)
            first = result.decisions[0]
            result.decisions.append(first.model_copy(update={"clause_id": "quiet2"}))
            return result
        with patch("engine.analyze", duplicated):
            self.request("POST", "/analyze")
        reminders = db.read()["reminders"]
        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders[0]["clause_ids"], ["quiet", "quiet2"])

    def test_host_seat_is_a_real_session_but_not_an_admin_bypass(self):
        seat = self.request("POST", "/demo/seat", {"member_id": "m2"})
        auth = {"Authorization": "Bearer " + seat["token"]}
        # A seat header cannot impersonate another member.
        state = self.request("GET", "/state", who="m4", headers=auth)
        self.assertEqual(state["identity"]["member_id"], "m2")
        self.assertTrue(state["identity"]["seat"])
        self.assertFalse(state["identity"]["local_demo"])
        # Seats are members, not hosts: management stays on the management page.
        self.request("POST", "/members", {"name": "外来者"}, headers=auth, expected=403)
        self.request("PUT", "/settings", {"mode": "demo", "model": "qwen2.5:7b"}, headers=auth, expected=403)
        # Seats are visible to the host with liveness.
        seats = self.request("GET", "/demo/seats")
        online = {item["member_id"]: item["online"] for item in seats["seats"]}
        self.assertTrue(online["m2"])

    def test_private_card_is_not_in_shared_state_or_export(self):
        before = len(db.read()["demands"])
        self.request("POST", "/needs", {"text": "私人原因不便公开", "visibility": "private"})
        state = db.read()
        self.assertEqual(len(state["demands"]), before)
        self.assertNotIn("私人原因不便公开", json.dumps(state, ensure_ascii=False))
        mine = db.private_needs("m1")
        self.assertEqual(len(mine), 1)
        self.assertEqual(db.private_needs("m2"), [])
        public = self.request("GET", "/state", who="m2")
        self.assertNotIn("私人原因不便公开", json.dumps(public, ensure_ascii=False))

    def test_state_polling_supports_incremental_cursor(self):
        first = self.request("GET", "/state")
        self.assertNotIn("unchanged", first)
        again = self.request("GET", f"/state?since={first['revision']}")
        self.assertTrue(again["unchanged"])
        self.request("PUT", "/clock", {"date": "2026-10-28", "time": "00:11"})
        full = self.request("GET", f"/state?since={first['revision']}")
        self.assertNotIn("unchanged", full)
        self.assertGreater(full["revision"], first["revision"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
