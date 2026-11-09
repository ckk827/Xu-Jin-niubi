import asyncio
import copy
import json
from pathlib import Path
import sys
import time
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import app
import engine
import sensing
import storage as db


def sample(idle=3, locked=False, session_active=True):
    return {"idle_seconds": idle, "locked": locked, "session_active": session_active}


class SensingTests(unittest.TestCase):
    def setUp(self):
        db.DB_PATH = Path(__file__).parent / ".data" / ("sensing-" + uuid.uuid4().hex + ".sqlite3")
        db.mutate(lambda state: state.update(mode="demo", model="qwen2.5:7b", model_configured=True))
        app.runtime.update(busy=False, error=None, last_signature=None)
        self.client = TestClient(app.app, client=("127.0.0.1", 51000))

    def enable(self, who="m1", **kwargs):
        with patch.object(sensing.WindowsSampler, "sample", return_value=sample(**kwargs)):
            response = self.client.put("/api/sensing", json={"enabled":True}, headers={"X-Member-Id":who})
        self.assertEqual(response.status_code, 200, response.text)
        return db.read()

    def activate(self):
        proposal = self.client.post("/api/proposals/generate").json()
        for i in range(1,5):
            r = self.client.post(f"/api/proposals/{proposal['id']}/approve", headers={"X-Member-Id":f"m{i}"})
            self.assertEqual(r.status_code,200)

    def test_device_categories_do_not_turn_recent_lock_into_rest(self):
        cfg = sensing.defaults()
        self.assertEqual(sensing.classify(sample(),cfg)["signal"], "active")
        self.assertEqual(sensing.classify(sample(idle=3,locked=True),cfg)["signal"], "away")
        self.assertEqual(sensing.classify(sample(idle=100),cfg)["signal"], "away")
        self.assertEqual(sensing.classify(sample(idle=1500,locked=True),cfg)["signal"], "idle")
        self.assertEqual(sensing.classify(sample(session_active=False),cfg)["signal"], "unknown")

    def test_expired_real_data_is_unknown_and_not_rest_evidence(self):
        reading=sensing.classify(sample(idle=1500),sensing.defaults(),now=100)
        expired=sensing.device_view(reading,now=116)
        self.assertEqual(expired["signal"],"unknown")
        self.assertTrue(expired["stale"])
        member={"manual":None,"devices":[expired,{"signal":"idle"}]}
        self.assertEqual(engine.evidence_status(member)[0],"unknown")

    def test_binding_real_source_clears_seeded_phone_and_blocks_manual_override(self):
        state = self.enable()
        pc, phone = state["members"][0]["devices"]
        self.assertEqual(pc["source"],"windows_live")
        self.assertEqual(pc["signal"],"active")
        self.assertEqual(phone["signal"],"unknown")
        result=self.client.put('/api/devices/m1/pc',json={"signal":"idle"})
        self.assertEqual(result.status_code,409)

    def test_switching_profile_does_not_rebind_host_pc(self):
        self.enable()
        self.client.get('/api/state',headers={"X-Member-Id":"m2"})
        self.assertEqual(db.read()["local_sensor"]["member_id"],"m1")

    def test_pause_clears_real_evidence_without_fallback_to_simulation(self):
        self.enable()
        result=self.client.put('/api/sensing',json={"enabled":False})
        self.assertEqual(result.status_code,200)
        state=self.client.get('/api/state').json()
        pc=state["members"][0]["devices"][0]
        self.assertEqual(pc["signal"],"unknown")
        self.assertEqual(pc["source"],"windows_live")
        result=self.client.put('/api/devices/m1/pc',json={"signal":"active"})
        self.assertEqual(result.status_code,200)
        self.assertEqual(db.read()["members"][0]["devices"][0]["source"],"simulation")

    def test_collection_failure_becomes_unknown_and_error_is_visible(self):
        self.enable()
        with patch.object(sensing.WindowsSampler,"sample",side_effect=OSError('test unavailable')):
            asyncio.run(app.collect_windows_once())
        state=db.read()
        self.assertEqual(state["members"][0]["devices"][0]["signal"],"unknown")
        self.assertIn("test unavailable",state["local_sensor"]["last_error"])

    def test_heartbeat_does_not_starve_inference(self):
        self.enable()
        self.activate()
        original=engine.analyze
        async def with_heartbeat(snapshot):
            result=await original(snapshot)
            def update(state):
                pc=state["members"][0]["devices"][0]
                pc.update(idle_seconds=4,observed_at=time.time(),expires_at=time.time()+15)
            db.mutate(update)
            return result
        with patch('engine.analyze',with_heartbeat):
            response=self.client.post('/api/analyze')
        self.assertEqual(response.status_code,200,response.text)

    def test_material_signal_change_during_inference_rejects_old_result(self):
        self.enable()
        self.activate()
        original=engine.analyze
        async def with_change(snapshot):
            result=await original(snapshot)
            db.mutate(lambda state:state["members"][0]["devices"][0].update(signal="away"))
            return result
        with patch('engine.analyze',with_change):
            response=self.client.post('/api/analyze')
        self.assertEqual(response.status_code,409,response.text)
        self.assertEqual(db.read()["reminders"],[])

    def test_freshness_hides_obsolete_member_analysis(self):
        self.enable()
        self.client.post('/api/analyze')
        def expire(state):
            state["members"][0]["devices"][0]["expires_at"]=time.time()-1
        db.mutate(expire)
        response=self.client.get('/api/state').json()
        self.assertIsNone(response["analysis"])
        self.assertEqual(response["members"][0]["devices"][0]["signal"],"unknown")

    def test_remote_browser_cannot_bind_host_and_invalid_windows_are_rejected(self):
        remote=TestClient(app.app,client=("192.0.2.20",51001))
        self.assertEqual(remote.put('/api/sensing',json={"enabled":True}).status_code,403)
        self.assertEqual(self.client.put('/api/sensing',json={"enabled":True,"active_within_seconds":60,"rest_after_seconds":30}).status_code,400)

    def test_real_clock_is_projected_in_shanghai_time(self):
        state=db.seed()
        state["clock"]["mode"]="real"
        projected=sensing.prepare(state,now=0)
        self.assertEqual(projected["clock"]["date"],"1970-01-01")
        self.assertEqual(projected["clock"]["time"],"08:00")
        self.assertEqual(state["clock"]["time"],"00:10")

    def test_real_signal_reaches_model_context_and_reminder_pipeline(self):
        self.enable(who="m2")
        self.activate()
        observed=[]
        original=engine.analyze
        async def capture(snapshot):
            observed.append(engine.model_payload(snapshot))
            return await original(snapshot)
        with patch('engine.analyze',capture):
            response=self.client.post('/api/analyze')
        self.assertEqual(response.status_code,200,response.text)
        pc=observed[0]["members"][1]["devices"][0]
        self.assertEqual(pc["source"],"windows_live")
        self.assertEqual(pc["signal"],"active")
        self.assertEqual([r["target"] for r in db.read()["reminders"]],["m2"])


if __name__=='__main__':
    unittest.main(verbosity=2)
