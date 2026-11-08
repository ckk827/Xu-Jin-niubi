"""Authenticated Windows peer sampling and delivery receipts."""
import time
from fastapi import APIRouter, Request, HTTPException, Header
from pydantic import BaseModel, Field
import access
import storage as db
import sensing
from notification_policy import deliverable
from members import require_member

router = APIRouter(prefix="/api", tags=["设备"])


class Participation(BaseModel):
    devices: list[str] = Field(max_length=2)


@router.put("/participation")
def participation(body: Participation, x_member_id: str = Header(default="m1")):
    if len(set(body.devices)) != len(body.devices) or not set(body.devices) <= {"pc", "phone"}:
        raise HTTPException(400, "请选择电脑、手机或均不参与")
    def save(state):
        for device in require_member(state, x_member_id)["devices"]:
            device["participating"] = device["id"] in body.devices
        state["analysis"] = None
    db.mutate(save)
    return {"ok": True}


class PCSample(BaseModel):
    sequence: int = Field(ge=1)
    sampled_at: float
    idle_seconds: float = Field(ge=0, le=604800)
    locked: bool
    session_active: bool
    model_config = {"extra": "forbid"}


@router.post("/pc/heartbeat")
def heartbeat(body: PCSample, authorization: str = Header(default="")):
    now = time.time()
    if not now - sensing.STALE_SECONDS <= body.sampled_at <= now + 5:
        raise HTTPException(409, "采样过期或时钟不一致")
    def save(state):
        account = access.session(state, authorization.removeprefix("Bearer "))
        if account.get("platform") != "pc":
            raise HTTPException(403, "请使用电脑设备配对凭据")
        if body.sequence <= account["last_sequence"]:
            return {"accepted": False}
        person = require_member(state, account["member_id"])
        if state.get("local_sensor", {}).get("enabled") and state["local_sensor"]["member_id"] == person["id"]:
            raise HTTPException(409, "此成员已绑定宿主采集，请先暂停宿主采集")
        key = access.digest(authorization.removeprefix("Bearer "))
        pc = next(d for d in person["devices"] if d["id"] == "pc")
        if pc.get("peer_key") not in (None, key) and pc.get("expires_at", 0) > now:
            raise HTTPException(409, "另一台电脑仍在为此成员采样，请先暂停它")
        account["last_sequence"] = body.sequence
        pc.update(sensing.classify(body.model_dump(), sensing.defaults(), now=body.sampled_at))
        pc["peer_key"] = key
        return {"accepted": True}
    return db.mutate(save)


class Delivery(BaseModel):
    device: str = Field(pattern=r"^(pc|phone)$")


class PCPause(BaseModel):
    sequence: int = Field(ge=1)


@router.post("/pc/pause")
def pause(body: PCPause, authorization: str = Header(default="")):
    def save(state):
        token = authorization.removeprefix("Bearer ")
        account = access.session(state, token)
        if account.get("platform") != "pc":
            raise HTTPException(403, "需要电脑凭据")
        if body.sequence <= account["last_sequence"]:
            return {"accepted": False}
        account["last_sequence"] = body.sequence
        pc = next(d for d in require_member(state, account["member_id"])["devices"] if d["id"] == "pc")
        if pc.get("peer_key") == access.digest(token):
            pc.update(signal="unknown", expires_at=0, error="成员电脑主动暂停采集")
        state["analysis"] = None
        return {"accepted": True}
    return db.mutate(save)


@router.post("/reminders/{identity}/delivered")
def delivered(identity: str, body: Delivery, x_member_id: str = Header(default="m1")):
    def save(state):
        reminder = next((r for r in state["reminders"] if r["id"] == identity and r["target"] == x_member_id and body.device in r["devices"]), None)
        if not reminder:
            raise HTTPException(404, "没有此终端的提醒")
        if not deliverable(state, reminder):
            raise HTTPException(409, "公约或适用时段已变化，此提醒不再投递")
        reminder.setdefault("delivered", {})[body.device] = time.time()
        reminder["status"] = "终端已接收（不等于成员已看到）"
        return {"ok": True}
    return db.mutate(save)


@router.get("/models")
async def models():
    import os
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            response = await client.get(os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/") + "/api/tags")
            response.raise_for_status()
            return {"available": True, "models": [m["name"] for m in response.json()["models"]]}
    except (httpx.HTTPError, KeyError, ValueError):
        return {"available": False, "models": [], "message": "Ollama 未连接，请先运行模型准备脚本"}
