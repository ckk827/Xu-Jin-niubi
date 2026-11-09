"""Local Windows sensing. Only idle duration and lock/session flags leave this module."""
from __future__ import annotations

import copy
import ctypes
import json
import hashlib
import sys
import time
from datetime import datetime, timedelta, timezone

from policy import (
    WINDOWS_POLL_SECONDS as POLL_SECONDS,
    WINDOWS_STALE_SECONDS as STALE_SECONDS,
    DEFAULT_ACTIVE_SECONDS,
    DEFAULT_REST_SECONDS,
)
import storage as db
import quiet_rules
LIVE_SOURCE = "windows_live"
VERSION = "0.5.0"


def defaults():
    return {"enabled": False, "member_id": None, "active_within_seconds": DEFAULT_ACTIVE_SECONDS,
            "rest_after_seconds": DEFAULT_REST_SECONDS, "generation": 0, "last_error": None}


class WindowsSampler:
    def __init__(self):
        if sys.platform != "win32" or sys.getwindowsversion().major < 10:
            raise OSError("本版真实采集仅支持 Windows 10/11 当前登录会话")
        from ctypes import wintypes as w

        class LastInput(ctypes.Structure):
            _fields_ = [("cbSize", w.UINT), ("dwTime", w.DWORD)]

        class WtsLevel1(ctypes.Structure):
            _fields_ = [("SessionId", w.ULONG), ("SessionState", ctypes.c_int), ("SessionFlags", w.LONG),
                        ("WinStationName", w.WCHAR * 33), ("UserName", w.WCHAR * 21), ("DomainName", w.WCHAR * 18),
                        ("LogonTime", ctypes.c_longlong), ("ConnectTime", ctypes.c_longlong),
                        ("DisconnectTime", ctypes.c_longlong), ("LastInputTime", ctypes.c_longlong),
                        ("CurrentTime", ctypes.c_longlong), ("IncomingBytes", w.DWORD), ("OutgoingBytes", w.DWORD),
                        ("IncomingFrames", w.DWORD), ("OutgoingFrames", w.DWORD),
                        ("IncomingCompressedBytes", w.DWORD), ("OutgoingCompressedBytes", w.DWORD)]

        class WtsData(ctypes.Union):
            _fields_ = [("Level1", WtsLevel1)]

        class WtsInfo(ctypes.Structure):
            _fields_ = [("Level", w.DWORD), ("Data", WtsData)]

        self.LastInput, self.WtsInfo = LastInput, WtsInfo
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.wts = ctypes.WinDLL("wtsapi32", use_last_error=True)
        self.user.GetLastInputInfo.argtypes = [ctypes.POINTER(LastInput)]
        self.user.GetLastInputInfo.restype = w.BOOL
        self.kernel.GetTickCount64.argtypes = []
        self.kernel.GetTickCount64.restype = ctypes.c_ulonglong
        self.wts.WTSQuerySessionInformationW.argtypes = [w.HANDLE, w.DWORD, ctypes.c_int,
                                                       ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(w.DWORD)]
        self.wts.WTSQuerySessionInformationW.restype = w.BOOL
        self.wts.WTSFreeMemory.argtypes = [ctypes.c_void_p]
        self.wts.WTSFreeMemory.restype = None

    def sample(self):
        from ctypes import wintypes as w
        info = self.LastInput()
        info.cbSize = ctypes.sizeof(info)
        if not self.user.GetLastInputInfo(ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        # LASTINPUTINFO carries a 32-bit tick value. Use modular subtraction across rollover.
        elapsed_ms = ((self.kernel.GetTickCount64() & 0xFFFFFFFF) - info.dwTime) & 0xFFFFFFFF
        buffer, size = ctypes.c_void_p(), w.DWORD()
        if not self.wts.WTSQuerySessionInformationW(None, 0xFFFFFFFF, 25, ctypes.byref(buffer), ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if size.value < ctypes.sizeof(self.WtsInfo):
                raise OSError("Windows 会话状态返回不完整")
            session = ctypes.cast(buffer, ctypes.POINTER(self.WtsInfo)).contents
            if session.Level != 1 or session.Data.Level1.SessionFlags not in (0, 1):
                raise OSError("Windows 会话锁定状态未知")
            # Never serialize user/domain/window-station names or the full native structure.
            return {"idle_seconds": round(elapsed_ms / 1000, 1),
                    "locked": session.Data.Level1.SessionFlags == 0,
                    "session_active": session.Data.Level1.SessionState == 0}
        finally:
            self.wts.WTSFreeMemory(buffer)


def classify(sample, config, now=None):
    """Classify device evidence only; member rest/activity remains the model's task."""
    now = time.time() if now is None else now
    idle = sample["idle_seconds"]
    if not sample["session_active"]:
        signal = "unknown"
    elif not sample["locked"] and idle <= config["active_within_seconds"]:
        signal = "active"
    elif idle >= config["rest_after_seconds"]:
        signal = "idle"
    else:
        signal = "away"  # Short inactivity or a recent lock is not evidence of rest.
    return {"signal": signal, "source": LIVE_SOURCE, "idle_seconds": idle,
            "locked": sample["locked"], "session_active": sample["session_active"],
            "observed_at": now, "expires_at": now + STALE_SECONDS, "error": None}


def device_view(device, now=None):
    now = time.time() if now is None else now
    device = copy.deepcopy(device)
    device.setdefault("source", "simulation")
    device.setdefault("participating", True)
    if device["source"] == "simulation":
        device["evidence_valid"] = device.get("signal") != "unknown"
        device["simulation_assumption"] = {
            "idle": "人工模拟：持续无操作已达到观察阈值，当前摘要有效，非实测。",
            "active": "人工模拟：当前有近期明确操作，非实测。",
            "unknown": "人工模拟：关键数据缺失。",
        }.get(device.get("signal"), "人工模拟：短暂离开，非实测。")
    if device["source"] in (LIVE_SOURCE, "android_live"):
        stale = not device.get("expires_at") or device["expires_at"] <= now
        device["stale"] = stale
        device["evidence_valid"] = not stale and not device.get("error")
        if stale:
            device["signal"] = "unknown"
    return device


def prepare(state, now=None):
    """Project freshness and clock at read time, including when a poller stops."""
    now = time.time() if now is None else now
    state = copy.deepcopy(state)
    state.setdefault("local_sensor", defaults())
    if state["clock"].get("mode") == "real":
        local = datetime.fromtimestamp(now, timezone(timedelta(hours=8)))
        state["clock"].update(date=local.date().isoformat(), time=local.strftime("%H:%M"))
    for person in state["members"]:
        person["devices"] = [device_view(d, now) for d in person["devices"]]
    return state


def window_phase(state):
    """Which approved quiet windows are open right now, and which cycle they belong to.

    The phase only changes when a window opens, closes, or the covenant changes.
    The minute hand must never trigger inference by itself.
    """
    state = prepare(state)
    active = next((p for p in state["proposals"] if p["id"] == state["active_id"] and p["status"] == "active"), None)
    phase = []
    for clause in (active["clauses"] if active else []):
        if clause.get("kind") != "quiet" or not clause.get("start") or not clause.get("end"):
            continue
        inside, cycle = quiet_rules.window(state, clause)
        resumed = quiet_rules.resumed_at(state, clause)
        phase.append({"clause_id": clause["id"], "inside": inside,
                      "cycle": cycle, "resumed_at": resumed.isoformat() if resumed else None})
    return phase


def analysis_key(state):
    """Only semantic context invalidates inference; minutes and heartbeats do not."""
    state = prepare(state)
    active = next((p for p in state["proposals"] if p["id"] == state["active_id"]), None)
    members = []
    for person in state["members"]:
        manual = person.get("manual")
        if manual and manual["expires"] <= time.time():
            manual = None
        members.append({"id": person["id"], "manual": manual,
                        "devices": [{k:d.get(k) for k in ("id", "source", "signal", "locked", "error")}
                                    for d in person["devices"] if d.get("participating", True)]})
    # No wall clock and no reminder list: entering a window is a phase change,
    # while the minute-by-minute clock and already-sent reminders are not.
    payload = json.dumps({"members": members, "windows": window_phase(state), "active": active,
                       "demands": state["demands"], "mode": state["mode"], "model": state["model"],
                       "model_connection_revision": state.get("model_connection_revision", 0),
                       "adjustments": state.get("adjustments", []), "feedbacks": state["feedbacks"]}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()
