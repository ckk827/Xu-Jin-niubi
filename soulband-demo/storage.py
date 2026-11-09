"""SQLite-backed demo state. All writes are serialized within this server process.

Two rules keep the rest of the app simple:
* ``read()`` never returns a covenant whose end time has passed; expiry is a
  deterministic projection, so no caller can resurrect a dead covenant.
* Private request cards live in their own table, never in the shared JSON blob
  that clients receive, the model reads, or a diffable export contains.
"""
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
LOCAL_TZ = timezone(timedelta(hours=8))
LOCK = threading.RLock()


def seed() -> dict:
    demo = os.environ.get("SOULBAND_INITIAL_MODE") == "demo"
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
            "mode": "demo" if demo else "unconfigured", "model": "qwen2.5:7b" if demo else "",
            "model_configured": demo, "analysis": None,
            "reminders": [], "feedbacks": [], "negotiations": [], "traces": [],
            "scheduler": None,
            "tasks": [{"id": "t1", "title": "清运垃圾与清理公共地面", "owner": "m1", "due": "今天", "done": False},
                      {"id": "t2", "title": "核对本周公共用品清单", "owner": "m3", "due": "明天", "done": False}],
            "bills": []}


def business_now(state) -> datetime:
    """Single source of truth for the business clock, including real mode."""
    clock = state.get("clock") or {}
    if clock.get("mode") == "real":
        return datetime.fromtimestamp(time.time(), LOCAL_TZ).replace(tzinfo=None)
    return datetime.fromisoformat(clock["date"] + "T" + clock["time"])


def expire_due(state) -> list[dict]:
    """Mark ended covenants expired and drop them from the active slot."""
    now = business_now(state)
    ended = []
    for proposal in state.get("proposals", []):
        if proposal.get("status") != "active":
            continue
        until = proposal.get("valid_until")
        if until and datetime.fromisoformat(until) <= now:
            proposal["status"] = "expired"
            ended.append(proposal)
    if ended and state.get("active_id") in {p["id"] for p in ended}:
        state["active_id"] = None
        state["analysis"] = None
        state["scheduler"] = None
        for proposal in ended:
            trace(state, "公约到期", f"v{proposal['version']} 已到截止时间，生效状态自动结束", "存储层")
    return ended


@contextmanager
def connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    try:
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        with conn:
            conn.execute("CREATE TABLE IF NOT EXISTS app_state (id INTEGER PRIMARY KEY CHECK (id=1), value TEXT NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS private_needs (id TEXT PRIMARY KEY, member_id TEXT NOT NULL, text TEXT NOT NULL, created REAL NOT NULL)")
            yield conn
    finally:
        conn.close()


def _load(conn) -> dict:
    row = conn.execute("SELECT value FROM app_state WHERE id=1").fetchone()
    if row is None:
        value = seed()
        conn.execute("INSERT INTO app_state VALUES(1, ?)", (json.dumps(value, ensure_ascii=False),))
        return value
    value = json.loads(row[0])
    ended = expire_due(value)
    dirty = bool(ended)
    value.setdefault("scheduler", None)
    moved = [d for d in value.get("demands", []) if d.get("visibility") == "private"]
    if moved:
        for demand in moved:
            conn.execute("INSERT OR IGNORE INTO private_needs VALUES(?,?,?,?)",
                         (demand["id"], demand["member_id"], demand["text"], time.time()))
        value["demands"] = [d for d in value["demands"] if d.get("visibility") != "private"]
        dirty = True
    if dirty:
        # Expiry is a real state change: persist it and bump the revision so
        # incremental pollers (and backups) actually see the covenant end.
        value["revision"] = value.get("revision", 0) + 1
        conn.execute("UPDATE app_state SET value=? WHERE id=1", (json.dumps(value, ensure_ascii=False),))
    return value


def read() -> dict:
    with LOCK, connection() as conn:
        return _load(conn)


def mutate(fn):
    with LOCK, connection() as conn:
        state = _load(conn)
        result = fn(state)
        state["revision"] += 1
        conn.execute("UPDATE app_state SET value=? WHERE id=1", (json.dumps(state, ensure_ascii=False),))
        return copy.deepcopy(result)


def trace(state, action, detail, source="程序"):
    local = datetime.now(LOCAL_TZ).strftime("%H:%M:%S")
    state["traces"].insert(0, {"action": action, "detail": detail, "source": source,
                               "at": local, "sim": local[:5] if state["clock"].get("mode") == "real" else state["clock"]["time"]})
    state["traces"] = state["traces"][:100]


def save_private_need(member_id, text, identity=None):
    """Private cards are stored apart from the shared state blob."""
    with LOCK, connection() as conn:
        value = {"id": identity or "p" + os.urandom(6).hex(), "member_id": member_id, "text": text, "created": time.time()}
        conn.execute("INSERT OR REPLACE INTO private_needs VALUES(?,?,?,?)",
                     (value["id"], member_id, text, value["created"]))
        return value


def private_needs(member_id):
    with LOCK, connection() as conn:
        rows = conn.execute("SELECT id, member_id, text, created FROM private_needs WHERE member_id=? ORDER BY created",
                            (member_id,)).fetchall()
    return [{"id": r[0], "member_id": r[1], "text": r[2], "created": r[3], "visibility": "private"} for r in rows]


def delete_private_need(member_id, identity):
    with LOCK, connection() as conn:
        conn.execute("DELETE FROM private_needs WHERE id=? AND member_id=?", (identity, member_id))


def backup(label="auto", keep=7) -> Path | None:
    """Consistent snapshot plus a JSON export; keeps the last ``keep`` copies."""
    if not DB_PATH.exists():
        return None
    folder = DB_PATH.parent / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(LOCAL_TZ).strftime("%Y%m%d-%H%M%S")
    target = folder / f"soulband-{label}-{stamp}.sqlite3"
    with LOCK:
        source = sqlite3.connect(DB_PATH, timeout=10)
        try:
            source.execute("VACUUM INTO ?", (str(target),))
        finally:
            source.close()
        target.with_suffix(".json").write_text(json.dumps(read(), ensure_ascii=False, indent=2), encoding="utf-8")
    for old in sorted(folder.glob("soulband-*.sqlite3"))[:-keep]:
        old.unlink(missing_ok=True)
        old.with_suffix(".json").unlink(missing_ok=True)
    return target
