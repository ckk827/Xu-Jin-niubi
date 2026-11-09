"""Regressions for reviewed scope and automatic resumption, using isolated DBs."""
import asyncio
from pathlib import Path
import sys
import unittest
import uuid
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import app
import engine
import quiet_rules
import scheduling
import sensing
import storage as db


class ReviewFixTests(unittest.TestCase):
    def setUp(self):
        self.original_path = db.DB_PATH
        db.DB_PATH = Path(__file__).parent / ".data" / ("review-fix-" + uuid.uuid4().hex + ".sqlite3")
        db.mutate(lambda state: state.update(mode="demo", model="qwen2.5:7b", model_configured=True))
        app.runtime.update(busy=False, error=None, last_signature=None, last_analysis_at=0., schedule_block_until=0.)
        self.client = TestClient(app.app)

    def tearDown(self):
        self.client.close()
        db.DB_PATH = self.original_path

    def request(self, method, path, body=None, who="m1"):
        response = self.client.request(method, "/api" + path, json=body, headers={"X-Member-Id": who})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def activate(self, **clause_changes):
        proposal = self.request("POST", "/proposals/generate")
        if clause_changes:
            clause = {**proposal["clauses"][0], **clause_changes}
            proposal = self.request("POST", f"/proposals/{proposal['id']}/revise",
                                    {"title": proposal["title"], "clauses": [clause], "conflicts": []})
        for i in range(1, 5):
            self.request("POST", f"/proposals/{proposal['id']}/approve", who=f"m{i}")
        return proposal

    def clock(self, day, hhmm):
        self.request("PUT", "/clock", {"date": day, "time": hhmm})

    def pause(self, starts="2026-10-28T00:00", ends="2026-10-28T00:30"):
        adjustment = self.request("POST", "/adjustments", {"clause_id": "quiet", "starts": starts, "ends": ends, "reason": "临时讨论"})
        for i in range(2, 5):
            self.request("POST", f"/adjustments/{adjustment['id']}/vote", {"approve": True}, who=f"m{i}")
        return adjustment

    def test_legacy_weekday_text_cannot_remind_on_saturday(self):
        self.activate(text="仅星期一至星期五 23:30 至次日 07:00 保持安静；周六、周日不执行静音提醒。")
        self.clock("2026-10-31", "23:31")
        self.request("POST", "/analyze")
        self.assertEqual(db.read()["reminders"], [])
        self.clock("2026-10-31", "00:10")  # Friday's overnight window
        self.request("POST", "/analyze")
        self.assertEqual(len(db.read()["reminders"]), 1)

    def test_date_and_member_scope_is_enforced(self):
        self.activate(weekdays=list(range(7)), member_ids=["m1", "m3"], starts_on="2026-10-28", ends_on="2026-10-29")
        self.clock("2026-10-28", "23:31")
        self.request("POST", "/analyze")  # m2 is active but excluded
        self.assertEqual(db.read()["reminders"], [])
        self.request("PUT", "/manual", {"status": "active"}, who="m3")
        self.request("POST", "/analyze")
        self.assertEqual([r["target"] for r in db.read()["reminders"]], ["m3"])
        self.clock("2026-10-30", "23:31")
        state = db.read()
        self.assertFalse(engine.quiet_window(state, state["proposals"][-1]["clauses"][0])[0])

    def test_real_model_sees_full_reviewed_rules_and_clock(self):
        self.activate(member_ids=["m1", "m2"], weekdays=[0, 1, 2, 3, 4])
        state = sensing.prepare(db.read())
        state["mode"] = "ollama"
        activities = engine.ActivityReport(states=[engine.Activity(member_id=m["id"], status=engine.evidence_status(m)[0], reason="有效摘要") for m in state["members"]])
        plan = engine.ReminderPlan(result=engine.NoReminder(gate="no_unreminded_active_member", summary="无新提醒"))
        model = AsyncMock(side_effect=[activities, plan])
        with patch("engine.ollama", model):
            asyncio.run(engine.analyze(state))
        payload = model.await_args_list[1].args[2]
        self.assertEqual(payload["active_covenant"], engine.active_proposal(state))
        self.assertEqual(payload["clock"], state["clock"])
        self.assertEqual(payload["applicable_windows"][0]["clause"]["text"], state["proposals"][-1]["clauses"][0]["text"])
        self.assertEqual(payload["applicable_windows"][0]["eligible_members"], ["m1", "m2"])

    def test_out_of_scope_model_target_is_blocked_at_commit(self):
        self.activate(member_ids=["m1", "m3"])
        state = sensing.prepare(db.read())
        result = asyncio.run(engine.analyze(state))
        result.decisions = [engine.Decision(clause_id="quiet", target="m2", message="请留意音量", reason="模型越过适用成员")]
        with patch("engine.analyze", AsyncMock(return_value=result)):
            analysis = self.request("POST", "/analyze")
        self.assertEqual(db.read()["reminders"], [])
        self.assertTrue(analysis["blocked"])

    def test_unexecutable_exceptions_remain_visible_but_do_not_remind(self):
        self.activate(exceptions=["考试前另行商议提前时间"], text="23:30 至07:00安静，考试前另行商议")
        self.request("POST", "/analyze")
        self.assertEqual(db.read()["reminders"], [])
        view = self.request("GET", "/state")
        self.assertTrue(view["proposals"][-1]["clauses"][0]["execution_scope"]["issue"])
        self.assertIsNotNone(view["analysis"])  # display metadata must not invalidate analysis

    def test_scope_validation_rejects_unknown_member_and_bad_dates(self):
        p = self.request("POST", "/proposals/generate")
        for changes, status in [({"member_ids": ["m99"]}, 400), ({"weekdays": [7]}, 422), ({"starts_on": "2026-1-1"}, 422)]:
            r = self.client.post(f"/api/proposals/{p['id']}/revise", json={"title": p["title"], "clauses": [{**p["clauses"][0], **changes}], "conflicts": []})
            self.assertEqual(r.status_code, status, r.text)

    def test_weekly_schedule_searches_beyond_three_days(self):
        self.activate(weekdays=[0])
        self.clock("2026-10-28", "15:00")  # Wednesday -> Monday
        self.assertEqual(scheduling.next_start(db.read()).isoformat(), "2026-11-02T23:30:00")

    def test_simulated_generation_preserves_weekday_restriction_from_demand(self):
        self.request("POST", "/demands", {"text": "仅工作日23:30到07:00静音，周末不执行提醒"})
        self.activate()
        self.clock("2026-10-31", "23:31")
        self.request("POST", "/analyze")
        self.assertEqual(db.read()["reminders"], [])

    def test_real_generation_cannot_drop_source_weekday_restriction(self):
        state = db.seed()
        state["demands"] = [{"id": "r1", "text": "仅工作日23:30到07:00静音", "member_id": "m1"}]
        output = engine.Proposal(title="公约", clauses=[engine.Clause(id="quiet", title="静音", kind="quiet", text="每天23:30到07:00安静", start="23:30", end="07:00", sources=["r1"])])
        self.assertTrue(engine.proposal_errors(state, output))
        output.clauses[0].weekdays = list(range(5))
        self.assertEqual(engine.proposal_errors(state, output), [])

    def test_pause_end_triggers_scheduler_once_without_manual_analysis(self):
        self.activate()
        self.pause()
        self.request("POST", "/analyze")
        before = sensing.analysis_key(db.read())
        self.assertEqual(db.read()["reminders"], [])
        self.clock("2026-10-28", "00:30")
        self.assertNotEqual(before, sensing.analysis_key(db.read()))
        self.assertEqual(scheduling.evaluate(db.read())["action"], "fire")
        asyncio.run(app.scheduler_step())
        self.assertEqual(len(db.read()["reminders"]), 1)
        self.assertEqual(db.read()["analysis"]["trigger"], "scheduled")
        self.assertEqual(scheduling.evaluate(db.read())["action"], "idle")
        app.runtime["last_signature"] = None  # persisted scheduler survives process-local reset
        asyncio.run(app.scheduler_step())
        self.assertEqual(len(db.read()["reminders"]), 1)

    def test_pause_begin_and_end_change_semantics_not_every_minute(self):
        self.activate()
        self.pause(starts="2026-10-28T00:15", ends="2026-10-28T00:30")
        before = sensing.analysis_key(db.read())
        self.clock("2026-10-28", "00:15")
        paused = sensing.analysis_key(db.read())
        self.assertNotEqual(before, paused)
        self.clock("2026-10-28", "00:20")
        self.assertEqual(paused, sensing.analysis_key(db.read()))
        self.assertEqual(scheduling.next_start(db.read()).isoformat(), "2026-10-28T00:30:00")

    def test_resuming_does_not_repeat_existing_reminder(self):
        self.activate()
        self.request("POST", "/analyze")
        self.pause()
        self.request("POST", "/analyze")
        self.clock("2026-10-28", "00:30")
        asyncio.run(app.scheduler_step())
        self.assertEqual(len(db.read()["reminders"]), 1)

    def test_overlapping_pauses_resume_only_after_last_end(self):
        self.activate()
        self.pause()
        self.pause(starts="2026-10-28T00:20", ends="2026-10-28T00:45")
        self.request("POST", "/analyze")
        self.clock("2026-10-28", "00:30")
        state = db.read()
        self.assertFalse(engine.quiet_window(state, state["proposals"][-1]["clauses"][0])[0])
        self.assertNotEqual(scheduling.evaluate(state)["action"], "fire")
        self.clock("2026-10-28", "00:45")
        asyncio.run(app.scheduler_step())
        self.assertEqual(len(db.read()["reminders"]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
