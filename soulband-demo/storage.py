"""SQLite-backed demo state. All writes are serialized within this server process."""
from __future__ import annotations

import copy
import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("SOULBAND_DB", ROOT / "data" / "soulband.sqlite3"))
LOCK = threading.RLock()


def seed() -> dict:
    names = ["小林", "阿泽", "一诺", "子航"]
    wishes = [
        "希望每天23:30到次日07:00保持安静，打游戏可以，但请戴耳机，不外放。",
        "晚上偶尔会继续用电脑，我接受23:30到07:00保持安静，希望提醒不要反复弹出。",
        "希望卫生轮流负责，值日完成要包括清运垃圾和清理公共地面。",
        "公共用品费用按参与人数均分；我希望有意见时可以先用中性方式表达。",
    ]
    members = []
    for i, name in enumerate(names):
        members.append({"id": f"m{i+1}", "name": name,
                        "color": ["purple", "blue", "peach", "green"][i],
                        "manual": None, "notify": "active",
                        "devices": [{"id": "pc", "label": "Windows", "signal": "idle" if i != 1 else "active"},
                                    {"id": "phone", "label": "Android", "signal": "idle" if i != 1 else "active"}]})
    return {"revision": 1, "members": members,
            "demands": [{"id": f"r{i+1}", "member_id": f"m{i+1}", "text": t} for i, t in enumerate(wishes)],
            "proposals": [], "active_id": None,
            "clock": {"date": "2026-10-28", "time": "00:10"},
            "mode": "demo", "model": "qwen2.5:7b", "analysis": None,
            "reminders": [], "feedbacks": [], "negotiations": [], "traces": [],
            "tasks": [{"id": "t1", "title": "清运垃圾与清理公共地面", "owner": "m1", "due": "今天", "done": False},
                      {"id": "t2", "title": "核对本周公共用品清单", "owner": "m3", "due": "明天", "done": False}],
            "bills": []}


@contextmanager
def connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    try:
        with conn:
            conn.execute("CREATE TABLE IF NOT EXISTS app_state (id INTEGER PRIMARY KEY CHECK (id=1), value TEXT NOT NULL)")
            yield conn
    finally:
        conn.close()


def read() -> dict:
    with LOCK, connection() as conn:
        row = conn.execute("SELECT value FROM app_state WHERE id=1").fetchone()
        if row is None:
            value = seed()
            conn.execute("INSERT INTO app_state VALUES(1, ?)", (json.dumps(value, ensure_ascii=False),))
            return value
        return json.loads(row[0])


def mutate(fn):
    with LOCK, connection() as conn:
        state = read()
        result = fn(state)
        state["revision"] += 1
        conn.execute("UPDATE app_state SET value=? WHERE id=1", (json.dumps(state, ensure_ascii=False),))
        return copy.deepcopy(result)


def trace(state, action, detail, source="程序"):
    local = datetime.now(timezone(timedelta(hours=8))).strftime("%H:%M:%S")
    state["traces"].insert(0, {"action": action, "detail": detail, "source": source,
                               "at": local, "sim": local[:5] if state["clock"].get("mode") == "real" else state["clock"]["time"]})
    state["traces"] = state["traces"][:100]
