"""Provider selection and OpenAI-compatible contract checks; no real provider calls."""
import asyncio
import json
import os
from pathlib import Path
import sys
import unittest
import uuid
from unittest.mock import patch

import httpx
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import app
import configure_test
import engine
import sensing
import model_connection as config
import storage as db


class ModelConnectionTests(unittest.TestCase):
    def setUp(self):
        self.old_path = db.DB_PATH
        db.DB_PATH = Path(__file__).parent / ".data" / ("model-config-" + uuid.uuid4().hex) / "state.sqlite3"
        self.client = TestClient(app.app)
        self.external = {"mode": "external", "model": "test-chat", "api_base_url": "https://provider.example/v1",
                         "api_key": "test-secret-not-a-real-key"}
        self.async_client = httpx.AsyncClient

    def tearDown(self):
        self.client.close()
        db.DB_PATH = self.old_path

    def transport(self, handler):
        def client(**kwargs):
            return self.async_client(transport=httpx.MockTransport(handler), **kwargs)
        return patch.object(engine.httpx, "AsyncClient", side_effect=client)

    def save_external(self, **changes):
        response = self.client.put("/api/settings", json={**self.external, **changes})
        self.assertEqual(response.status_code, 200, response.text)

    def proposal_fixture(self):
        output = engine.demo_proposal(db.read()).model_dump()
        output["clauses"] = [c for c in output["clauses"] if c["id"] not in ("req-r1", "req-r2")]
        return output

    def test_first_boot_is_unconfigured_and_never_uses_simulation(self):
        with patch.dict(os.environ, {"SOULBAND_INITIAL_MODE": ""}):
            self.assertEqual(db.read()["mode"], "unconfigured")
        with patch("local_model_setup.start") as prepare:
            response = self.client.post("/api/private", json={"text": "想商量一下", "style": "gentle"})
            self.assertEqual(response.status_code, 502)
            self.assertIn("先", response.text)
            prepare.assert_not_called()

    def test_external_save_does_not_download_and_never_exports_the_key(self):
        with patch("local_model_setup.start") as prepare:
            self.save_external()
            prepare.assert_not_called()
        self.assertNotIn(self.external["api_key"], json.dumps(db.read()))
        state = self.client.get("/api/state").json()
        self.assertTrue(state["api_key_saved"])
        self.assertNotIn(self.external["api_key"], json.dumps(state))
        self.assertEqual(self.client.post("/api/settings/local-setup").status_code, 409)
        self.assertEqual(self.client.get("/api/models").json()["provider"], "external")
        backup = db.backup("model-test")
        self.assertNotIn(self.external["api_key"], backup.with_suffix(".json").read_text(encoding="utf-8"))

    def test_blank_key_keeps_same_endpoint_but_does_not_follow_a_changed_host(self):
        self.save_external()
        self.save_external(api_key="", model="test-chat-2")
        self.assertEqual(config.saved_key(self.external["api_base_url"]), self.external["api_key"])
        response = self.client.put("/api/settings", json={**self.external, "api_base_url": "https://other.example/v1", "api_key": ""})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(db.read()["api_base_url"], self.external["api_base_url"])

    def test_restart_preserves_external_configuration(self):
        self.save_external()
        configure_test.main()
        self.assertEqual(db.read()["mode"], "external")
        self.assertEqual(db.read()["model"], "test-chat")
        self.assertEqual(config.saved_key(self.external["api_base_url"]), self.external["api_key"])

    def test_model_url_is_rejected_without_changing_saved_connection(self):
        self.save_external()
        for path in ("/api/settings", "/api/settings/test"):
            response = self.client.request("PUT" if path == "/api/settings" else "POST", path,
                                           json={**self.external, "model": "https://provider.example"})
            self.assertEqual(response.status_code, 422, response.text)
            self.assertIn("模型 ID", response.text)
        self.assertEqual(db.read()["model"], "test-chat")

    def test_legacy_launcher_config_asks_for_choice_without_resetting_room(self):
        db.mutate(lambda state: state.update(mode="ollama", model="qwen2.5:7b", environment="legacy"))
        before = db.read()["demands"]
        configure_test.main()
        self.assertEqual(db.read()["mode"], "unconfigured")
        self.assertEqual(db.read()["demands"], before)

    def test_pending_connection_test_uses_openai_protocol_without_saving(self):
        captured = []
        def handler(request):
            captured.append(request)
            return httpx.Response(200, json={"choices": [{"message": {"content": '{"reply":"连接成功"}'}}]})
        with self.transport(handler):
            response = self.client.post("/api/settings/test", json=self.external)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(db.read()["mode"], "unconfigured")
        self.assertEqual(str(captured[0].url), "https://provider.example/v1/chat/completions")
        self.assertEqual(captured[0].headers["authorization"], "Bearer " + self.external["api_key"])
        body = json.loads(captured[0].content)
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertIn("schema", body["messages"][0]["content"])
        self.assertEqual(body["model"], "test-chat")

    def test_saved_external_provider_runs_private_and_need_features(self):
        self.save_external()
        def handler(request):
            user = json.loads(request.content)["messages"][1]["content"]
            output = {"text": "想协商安静时间", "category": "quiet", "questions": []} if "整理诉求卡" in user else {"reply": "外部接口测试回复"}
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(output)}}]})
        with self.transport(handler):
            response = self.client.post("/api/private", json={"text": "想商量一下", "style": "gentle"})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["reply"], "外部接口测试回复")
            response = self.client.post("/api/needs/prepare", json={"text": "想协商安静时间"})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["category"], "quiet")

    def test_external_generate_approve_and_two_stage_analysis_use_same_provider(self):
        self.save_external()
        calls = []
        def handler(request):
            task, raw = json.loads(request.content)["messages"][1]["content"].split("\n数据：", 1)
            payload = json.loads(raw)
            calls.append(task)
            if "综合公开诉求" in task:
                output = self.proposal_fixture()
            elif "record_covenant" in task:
                output = {"tool": "record_covenant", "proposal_id": payload["reviewed_proposal"]["id"]}
            elif "Infer the coarse activity" in task:
                members = sensing.prepare(db.read())["members"]
                output = {"states": [{"member_id": m["id"], "status": engine.evidence_status(m)[0],
                                      "reason": "本地接口夹具提供的活动判断"} for m in members]}
            else:
                self.assertIn("Determine gate FIRST", task)
                output = {"result": {"gate": "remind", "decisions": [{"clause_id": "quiet", "target": "m2",
                    "message": "静音时段请留意音量", "reason": "依据已审阅公约与活动状态"}], "summary": "接口夹具的提醒判断"}}
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(output)}}]})
        with self.transport(handler):
            proposal = self.client.post("/api/proposals/generate")
            self.assertEqual(proposal.status_code, 200, proposal.text)
            self.assertEqual(proposal.json()["source"], "外部 API")
            for who in ("m1", "m2", "m3", "m4"):
                approved = self.client.post("/api/proposals/" + proposal.json()["id"] + "/approve", headers={"X-Member-Id": who})
                self.assertEqual(approved.status_code, 200, approved.text)
            self.assertEqual(approved.json()["record_receipt"]["source"], "外部 API")
            analysis = self.client.post("/api/analyze")
            self.assertEqual(analysis.status_code, 200, analysis.text)
            self.assertEqual(analysis.json()["source"], "外部 API · test-chat")
            self.assertEqual([r["target"] for r in db.read()["reminders"]], ["m2"])
        self.assertEqual(len(calls), 4)

    def test_key_change_during_model_call_rejects_old_generated_proposal(self):
        self.save_external()
        def handler(request):
            output = self.proposal_fixture()
            config.save(config.SettingsInput(**{**self.external, "api_key": "replacement-test-key"}))
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(output)}}]})
        with self.transport(handler):
            response = self.client.post("/api/proposals/generate")
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(db.read()["proposals"], [])

    def test_saved_local_choice_resumes_but_external_choice_does_not_prepare(self):
        self.save_external()
        with patch("local_model_setup.start") as prepare:
            with TestClient(app.app):
                prepare.assert_not_called()
        self.client.put("/api/settings", json={"mode": "ollama", "model": "qwen2.5:7b"})
        with patch("local_model_setup.start") as prepare:
            with TestClient(app.app):
                prepare.assert_called_once_with("qwen2.5:7b")

    def test_provider_error_does_not_echo_key_or_fall_back(self):
        self.save_external()
        for code in (401, 429, 500):
            with self.transport(lambda request: httpx.Response(code, json={"error": self.external["api_key"]})):
                response = self.client.post("/api/private", json={"text": "想商量一下", "style": "gentle"})
            self.assertEqual(response.status_code, 502)
            self.assertIn(str(code), response.text)
            self.assertNotIn(self.external["api_key"], response.text)
            self.assertEqual(db.read()["mode"], "external")

    def test_invalid_model_json_is_rejected(self):
        self.save_external()
        with self.transport(lambda request: httpx.Response(200, json={"choices": [{"message": {"content": 'not json'}}]})):
            response = self.client.post("/api/private", json={"text": "想商量一下", "style": "gentle"})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(db.read()["mode"], "external")

    def test_download_requires_explicit_local_selection_and_button(self):
        with patch("local_model_setup.start", return_value={"running": True}) as prepare:
            self.assertEqual(self.client.post("/api/settings/local-setup").status_code, 409)
            self.assertEqual(self.client.put("/api/settings", json={"mode": "ollama", "model": "qwen2.5:7b"}).status_code, 200)
            prepare.assert_not_called()
            self.assertEqual(self.client.post("/api/settings/local-setup").status_code, 200)
            prepare.assert_called_once_with("qwen2.5:7b")

    def test_member_cannot_change_or_test_model_or_start_download(self):
        code = self.client.post("/api/access/code", json={"member_id": "m1"}).json()["code"]
        token = self.client.post("/api/access/redeem", json={"code": code, "platform": "web"}).json()["token"]
        with TestClient(app.app, client=("192.0.2.2", 1234)) as remote:
            for path in ("/api/settings/test", "/api/settings/local-setup"):
                response = remote.post(path, json=self.external, headers={"Authorization": "Bearer " + token})
                self.assertEqual(response.status_code, 403)
            self.assertEqual(remote.get("/api/settings/local-setup", headers={"Authorization": "Bearer " + token}).status_code, 403)

    def test_endpoint_validation_and_complete_endpoint_normalization(self):
        for base in ("http://provider.example/v1", "https://key@provider.example", "https://provider.example?key=hidden"):
            self.assertEqual(self.client.put("/api/settings", json={**self.external, "api_base_url": base}).status_code, 422)
        self.assertEqual(config.normalize_base("https://provider.example/v1/chat/completions/"), "https://provider.example/v1")


if __name__ == "__main__":
    unittest.main()
