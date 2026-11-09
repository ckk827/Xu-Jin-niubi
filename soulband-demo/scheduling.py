"""Deterministic reminder scheduling.

A reminder run happens when an approved quiet window opens, or when the host
starts while one is already open (catch-up). The next fire time is persisted so
a restart can rebuild it, and the business clock ticking minute by minute never
triggers inference on its own.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import engine
import storage as db
import quiet_rules

GRACE_SECONDS = 900      # a start missed by more than this is reported, not silently replayed
TICK_SECONDS = 2


def _start_of(clause, day):
    return datetime.fromisoformat(f"{day.isoformat()}T{clause['start']}")


def open_windows(state):
    """Approved, unpaused quiet windows that are open now."""
    active = engine.active_proposal(state)
    if not active:
        return []
    opened = []
    for clause in active["clauses"]:
        if clause.get("kind") != "quiet":
            continue
        inside, cycle = engine.quiet_window(state, clause)
        if inside:
            try:
                start = _start_of(clause, date.fromisoformat(cycle[:10]))
            except ValueError:
                start = None
            opened.append({"clause_id": clause["id"], "cycle": cycle,
                           "start": start.isoformat() if start else None,
                           "resumed_at": quiet_rules.resumed_at(state, clause)})
    return opened


def current_cycle(state):
    opened = open_windows(state)
    return sorted({item["cycle"] for item in opened})[0] if opened else None


def next_start(state, now=None):
    """Earliest upcoming quiet-window start for the active covenant."""
    now = now or db.business_now(state)
    active = engine.active_proposal(state)
    if not active:
        return None
    stamps = []
    for clause in active["clauses"]:
        if clause.get("kind") != "quiet" or not clause.get("start"):
            continue
        limits = quiet_rules.scope(clause, [m["id"] for m in state["members"]])
        if limits["issue"] or not limits["weekdays"]:
            continue
        anchor = max(now.date(), date.fromisoformat(clause["starts_on"])) if clause.get("starts_on") else now.date()
        for offset in range(8):
            candidate = _start_of(clause, anchor + timedelta(days=offset))
            if candidate > now and quiet_rules.window(state, clause, candidate)[0]:
                stamps.append(candidate)
                break
        for adjustment in state.get("adjustments", []):
            if (adjustment["status"] == "approved" and adjustment["version_id"] == active["id"]
                    and adjustment["clause_id"] == clause["id"]):
                end = datetime.fromisoformat(adjustment["ends"])
                if end > now and quiet_rules.window(state, clause, end)[0]:
                    stamps.append(end)
    return min(stamps) if stamps else None


def rebuild(state, now=None):
    """Recompute the persisted schedule; safe to call inside db.mutate."""
    now = now or db.business_now(state)
    previous = state.get("scheduler") or {}
    keep_cycle = previous.get("last_cycle") if previous.get("version") == state.get("active_id") else None
    upcoming = next_start(state, now)
    state["scheduler"] = {"version": state.get("active_id"), "last_cycle": keep_cycle,
                          "handled_resumptions": previous.get("handled_resumptions", {}) if previous.get("version") == state.get("active_id") else {},
                          "next_fire_at": upcoming.isoformat() if upcoming else None,
                          "computed_at": now.isoformat()}
    return state["scheduler"]


def mark_fired(state, now=None):
    """Record that this cycle was handled and point at the following start."""
    now = now or db.business_now(state)
    upcoming = next_start(state, now)
    state["scheduler"] = {"version": state.get("active_id"), "last_cycle": current_cycle(state),
                          "handled_resumptions": _handled_resumptions(state),
                          "next_fire_at": upcoming.isoformat() if upcoming else None,
                          "computed_at": now.isoformat()}
    return state["scheduler"]


def mark_missed(state, cycle=None, now=None):
    """Remember a skipped start so the worker does not replay it every tick."""
    now = now or db.business_now(state)
    upcoming = next_start(state, now)
    state["scheduler"] = {"version": state.get("active_id"), "last_cycle": cycle or current_cycle(state),
                          "handled_resumptions": _handled_resumptions(state),
                          "next_fire_at": upcoming.isoformat() if upcoming else None,
                          "computed_at": now.isoformat()}
    return state["scheduler"]


def _handled_resumptions(state):
    previous = state.get("scheduler") or {}
    handled = dict(previous.get("handled_resumptions", {})) if previous.get("version") == state.get("active_id") else {}
    for item in open_windows(state):
        if item["resumed_at"]:
            handled[item["clause_id"]] = item["resumed_at"].isoformat()
    return handled


def evaluate(state, now=None):
    """Decide what the worker should do next. Pure function, no writes."""
    now = now or db.business_now(state)
    active = engine.active_proposal(state)
    if not active:
        return {"action": "idle", "reason": "没有生效公约"}
    schedule = state.get("scheduler") or {}
    if schedule.get("version") != active["id"]:
        return {"action": "rebuild", "reason": "公约版本已变化"}
    opened = open_windows(state)
    cycle = sorted({item["cycle"] for item in opened})[0] if opened else None
    for item in opened:
        resumed = item["resumed_at"]
        if resumed and schedule.get("handled_resumptions", {}).get(item["clause_id"]) != resumed.isoformat():
            if now >= resumed + timedelta(seconds=GRACE_SECONDS):
                return {"action": "missed", "cycle": cycle, "reason": "错过临时安排结束后的静音恢复时间"}
            return {"action": "fire", "cycle": cycle, "reason": "临时安排已结束，恢复按公约判断"}
    if opened:
        if schedule.get("last_cycle") != cycle:
            start = opened[0].get("start")
            if start:
                start_at = datetime.fromisoformat(start)
                if now >= start_at + timedelta(seconds=GRACE_SECONDS):
                    return {"action": "missed", "cycle": cycle, "at": start,
                            "reason": f"错过 {start_at:%H:%M} 的静音时段起点",
                            "clauses": [item["clause_id"] for item in opened]}
            return {"action": "fire", "reason": "进入已审核的静音时段", "cycle": cycle,
                    "clauses": [item["clause_id"] for item in opened]}
        return {"action": "idle", "reason": "本时段已完成判断"}
    due = schedule.get("next_fire_at")
    if due:
        start = datetime.fromisoformat(due)
        if now >= start + timedelta(seconds=GRACE_SECONDS):
            return {"action": "missed", "reason": f"错过 {start:%H:%M} 的静音时段起点", "at": due}
        if now >= start:
            return {"action": "fire", "reason": "到达静音时段起点", "cycle": cycle}
    return {"action": "idle", "reason": "未到下次判断时间"}


def describe(state):
    schedule = state.get("scheduler") or {}
    return {"next_fire_at": schedule.get("next_fire_at"), "last_cycle": schedule.get("last_cycle"),
            "version": schedule.get("version"), "grace_seconds": GRACE_SECONDS}
