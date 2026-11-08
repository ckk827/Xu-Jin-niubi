"""Real Ollama end-to-end checks, never a mock or normal user database."""
import json
from pathlib import Path
import sys
import time
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import app
import storage as db


def main():
    db.DB_PATH = Path(__file__).parent / ".data" / ("real-model-" + uuid.uuid4().hex + ".sqlite3")
    client = TestClient(app.app, client=("127.0.0.1", 4000))
    results = []
    def request(path, body=None, who="m1", method="POST"):
        start = time.perf_counter()
        r = client.request(method, "/api" + path, json=body, headers={"X-Member-Id": who})
        if r.status_code != 200:
            raise RuntimeError(path + ": " + r.text)
        return r.json(), round(time.perf_counter() - start, 3)
    request("/settings", {"mode": "ollama", "model": "qwen2.5:7b"}, method="PUT")
    try:
        need, elapsed = request("/needs/prepare", {"text": "希望23:30到07:00保持安静，不能外放，可以戴耳机。"})
        assert "23:30" in need["text"] and need["saved"] is False
        results.append({"check": "real_need_card", "seconds": elapsed})
        p, elapsed = request("/proposals/generate")
        assert any(c["kind"] == "quiet" and c["start"] == "23:30" and c["end"] == "07:00" for c in p["clauses"])
        assert not p["conflicts"], p["conflicts"]
        results.append({"check": "real_covenant_generation", "seconds": elapsed})
        for who in ("m1", "m2", "m3", "m4"):
            recorded, elapsed = request(f"/proposals/{p['id']}/approve", who=who)
        assert recorded["record_receipt"]["source"] == "Ollama"
        results.append({"check": "real_model_record_tool_with_all_approvals", "seconds": elapsed})
        a, elapsed = request("/analyze")
        assert {s["member_id"]:s["status"] for s in a["states"]} == {"m1":"resting", "m2":"active", "m3":"resting", "m4":"resting"}, a
        assert len(db.read()["reminders"]) == 1 and db.read()["reminders"][0]["target"] == "m2", a
        results.append({"check": "real_activity_and_reminder", "seconds": elapsed})
        _, elapsed = request("/analyze")
        assert len(db.read()["reminders"]) == 1
        results.append({"check": "real_no_repeat", "seconds": elapsed})
        _, elapsed = request("/feedback", {"target":"m2", "result":"still"})
        assert len(db.read()["reminders"]) == 2 and db.read()["reminders"][-1]["source"] == "Ollama"
        results.append({"check": "real_feedback_wording", "seconds": elapsed})
        request("/feedback", {"target":"m2", "result":"still"}, who="m3")
        n = db.read()["negotiations"][-1]
        suggestion, elapsed = request(f"/negotiations/{n['id']}/suggest")
        assert suggestion["suggestion_source"] == "Ollama" and suggestion["suggestion"]
        results.append({"check": "real_negotiation_suggestion", "seconds": elapsed})
        answer, elapsed = request("/assistant", {"text":"当前正式公约几点开始静音？"})
        assert answer["tool"] == "covenant" and "23:30" in answer["reply"]
        results.append({"check": "real_query_tool_and_explanation", "seconds": elapsed})
        private, elapsed = request("/private", {"text":"半夜唱歌让我睡不着，我想商量一下", "style":"gentle"})
        assert private["saved"] is False and "半夜唱歌让我睡不着" not in str(db.read())
        results.append({"check": "real_private_expression", "seconds": elapsed})
        request("/clock", {"date":"2026-11-08", "time":"15:00"}, method="PUT")
        _, elapsed = request("/analyze")
        assert len(db.read()["reminders"]) == 2
        results.append({"check": "real_daytime_no_rule_expansion", "seconds": elapsed})
    finally:
        output = Path(__file__).resolve().parents[2] / "output/release-2026-11-08/model-live.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({"model":"qwen2.5:7b", "real_ollama":True, "checks":results, "passed":len(results), "database":str(db.DB_PATH)}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(results, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__": main()
