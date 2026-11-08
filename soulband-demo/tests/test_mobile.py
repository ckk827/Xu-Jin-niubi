import copy
import hashlib
from pathlib import Path
import sys
import time
import unittest
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import app
import engine
import sensing
import storage as db


class MobileTests(unittest.TestCase):
    def setUp(self):
        db.DB_PATH=Path(__file__).parent/'.data'/('mobile-'+uuid.uuid4().hex+'.sqlite3')
        self.client=TestClient(app.app,client=('127.0.0.1',51000))
        self.installation=str(uuid.uuid4())

    def pair(self,owner='m2',installation=None):
        response=self.client.post('/api/mobile/pair-code',headers={'X-Member-Id':owner})
        self.assertEqual(response.status_code,200,response.text)
        code=response.json()['code']
        response=self.client.post('/api/mobile/pair',json={'code':code,'installation_id':installation or self.installation})
        self.assertEqual(response.status_code,200,response.text)
        result=response.json()
        return {'Authorization':'Bearer '+result['token']},code,result['token']

    def sample(self,seq=1,**updates):
        value={'sequence':seq,'sampled_at_ms':int(time.time()*1000),'interactive':True,'locked':False,
               'usage_access':True,'interaction_age_seconds':3,'inactive_seconds':0}
        value.update(updates)
        return value

    def test_pairing_is_single_use_and_secrets_not_returned_by_state(self):
        headers,code,token=self.pair()
        retry=self.client.post('/api/mobile/pair',json={'code':code,'installation_id':str(uuid.uuid4())})
        self.assertEqual(retry.status_code,401)
        raw=str(db.read())
        self.assertNotIn(token,raw)
        response=self.client.get('/api/state').json()
        self.assertNotIn('mobile_sessions',response)
        self.assertNotIn('mobile_pair_codes',response)
        self.assertIn('m2',response['mobile_paired'])

    def test_only_local_client_can_generate_codes(self):
        remote=TestClient(app.app,client=('192.0.2.3',4000))
        self.assertEqual(remote.post('/api/mobile/pair-code').status_code,403)

    def test_paired_recent_interaction_becomes_active_native_phone(self):
        headers,_,_=self.pair()
        response=self.client.post('/api/mobile/heartbeat',json=self.sample(),headers=headers)
        self.assertEqual(response.status_code,200,response.text)
        phone=db.read()['members'][1]['devices'][1]
        self.assertEqual(phone['source'],'android_live')
        self.assertEqual(phone['signal'],'active')

    def test_screen_on_alone_is_not_explicit_activity(self):
        headers,_,_=self.pair()
        response=self.client.post('/api/mobile/heartbeat',json=self.sample(interaction_age_seconds=None),headers=headers)
        self.assertEqual(response.json()['signal'],'away')

    def test_without_usage_access_is_unknown_even_screen_off(self):
        headers,_,_=self.pair()
        response=self.client.post('/api/mobile/heartbeat',json=self.sample(usage_access=False,interactive=False,locked=True,inactive_seconds=1500),headers=headers)
        self.assertEqual(response.json()['signal'],'unknown')

    def test_sustained_screen_off_is_inactivity_evidence_not_sleep_proof(self):
        headers,_,_=self.pair()
        response=self.client.post('/api/mobile/heartbeat',json=self.sample(interactive=False,locked=True,inactive_seconds=1500),headers=headers)
        self.assertEqual(response.json()['signal'],'idle')

    def test_duplicate_and_older_packets_do_not_refresh_expiry(self):
        headers,_,_=self.pair()
        self.client.post('/api/mobile/heartbeat',json=self.sample(2),headers=headers)
        before=db.read()['members'][1]['devices'][1]['expires_at']
        response=self.client.post('/api/mobile/heartbeat',json=self.sample(1),headers=headers)
        self.assertFalse(response.json()['accepted'])
        self.assertEqual(before,db.read()['members'][1]['devices'][1]['expires_at'])

    def test_expired_buffered_sample_is_rejected(self):
        headers,_,_=self.pair()
        response=self.client.post('/api/mobile/heartbeat',json=self.sample(sampled_at_ms=int((time.time()-100)*1000)),headers=headers)
        self.assertEqual(response.status_code,409)
        self.assertEqual(db.read()['members'][1]['devices'][1]['signal'],'unknown')

    def test_pause_blocks_inflight_older_heartbeat_and_newer_sampling_can_resume(self):
        headers,_,_=self.pair()
        self.client.post('/api/mobile/heartbeat',json=self.sample(1),headers=headers)
        self.assertEqual(self.client.post('/api/mobile/pause',json={'sequence':3},headers=headers).status_code,200)
        response=self.client.post('/api/mobile/heartbeat',json=self.sample(2),headers=headers)
        self.assertFalse(response.json()['accepted'])
        self.assertEqual(db.read()['members'][1]['devices'][1]['signal'],'unknown')
        response=self.client.post('/api/mobile/heartbeat',json=self.sample(4),headers=headers)
        self.assertEqual(response.json()['signal'],'active')
        response=self.client.post('/api/mobile/pause',json={'sequence':3},headers=headers)
        self.assertFalse(response.json()['ok'])

    def test_rebinding_same_installation_invalidates_previous_member(self):
        old,_,_=self.pair('m1')
        self.client.post('/api/mobile/heartbeat',json=self.sample(),headers=old)
        new,_,_=self.pair('m2')
        self.assertEqual(self.client.get('/api/mobile/inbox',headers=old).status_code,401)
        self.assertEqual(db.read()['members'][0]['devices'][1]['signal'],'unknown')
        self.assertEqual(self.client.get('/api/mobile/inbox',headers=new).status_code,200)

    def test_revoke_invalidates_token_and_allows_explicit_simulation(self):
        headers,_,_=self.pair()
        self.assertEqual(self.client.put('/api/devices/m2/phone',json={'signal':'idle'}).status_code,409)
        self.client.post('/api/mobile/revoke',headers={'X-Member-Id':'m2'})
        self.assertEqual(self.client.get('/api/mobile/inbox',headers=headers).status_code,401)
        self.assertEqual(self.client.put('/api/devices/m2/phone',json={'signal':'idle'}).status_code,200)

    def test_old_phone_evidence_expires_even_without_new_packet(self):
        headers,_,_=self.pair()
        self.client.post('/api/mobile/heartbeat',json=self.sample(),headers=headers)
        phone=db.read()['members'][1]['devices'][1]
        expired=sensing.device_view(phone,now=phone['expires_at']+1)
        self.assertEqual(expired['signal'],'unknown')

    def test_payload_rejects_application_details(self):
        headers,_,_=self.pair()
        response=self.client.post('/api/mobile/heartbeat',json=self.sample(package_names=['not-allowed']),headers=headers)
        self.assertEqual(response.status_code,422)

    def test_mobile_inbox_is_member_scoped_and_read_synchronizes(self):
        headers,_,_=self.pair('m2')
        proposal=self.client.post('/api/proposals/generate').json()
        for i in range(1,5):
            self.client.post(f"/api/proposals/{proposal['id']}/approve",headers={'X-Member-Id':f'm{i}'})
        context=sensing.prepare(db.read())
        clause=next(c for c in proposal['clauses'] if c['kind']=='quiet')
        inside,cycle=engine.quiet_window(context,clause)
        self.assertTrue(inside)
        def insert(state):
            for target in ['m1','m2']:
                state['reminders'].append({'id':'n-'+target,'target':target,'message':'sample '+target,'read':False,'time':'00:10','kind':'auto','devices':['phone'],'version':proposal['id'],'clause_id':clause['id'],'cycle':cycle})
        db.mutate(insert)
        inbox=self.client.get('/api/mobile/inbox',headers=headers).json()['items']
        self.assertEqual([r['id'] for r in inbox],['n-m2'])
        self.assertEqual(self.client.post('/api/mobile/inbox/n-m1/read',headers=headers).status_code,404)
        self.assertEqual(self.client.post('/api/mobile/inbox/n-m2/read',headers=headers).status_code,200)
        self.assertTrue(db.read()['reminders'][1]['read'])

    def test_phone_active_and_pc_idle_reaches_reminder_pipeline(self):
        headers,_,_=self.pair('m2')
        self.client.put('/api/devices/m2/pc',json={'signal':'idle'})
        self.client.post('/api/mobile/heartbeat',json=self.sample(),headers=headers)
        proposal=self.client.post('/api/proposals/generate').json()
        for i in range(1,5):
            self.client.post(f"/api/proposals/{proposal['id']}/approve",headers={'X-Member-Id':f'm{i}'})
        response=self.client.post('/api/analyze')
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(next(s['status'] for s in response.json()['states'] if s['member_id']=='m2'),'active')
        self.assertEqual(db.read()['reminders'][0]['devices'],['phone'])


if __name__=='__main__':
    unittest.main(verbosity=2)
