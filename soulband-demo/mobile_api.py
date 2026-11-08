"""Paired native Android devices. Tokens are hashed at rest and never included in /state."""
import hashlib
import ipaddress
import secrets
import time

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

import storage as db
from notification_policy import deliverable
from members import require_member as person
from policy import (
    ANDROID_STALE_SECONDS as TTL,
    ANDROID_HEARTBEAT_SECONDS,
    ANDROID_CLOCK_SKEW_SECONDS,
    DEFAULT_ACTIVE_SECONDS,
    DEFAULT_REST_SECONDS,
    PAIR_CODE_LIFETIME_SECONDS,
)

router = APIRouter(prefix="/api/mobile", tags=["Android"])
SOURCE = "android_live"


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def require_local(request):
    try:
        if ipaddress.ip_address(request.client.host).is_loopback:
            return
    except (ValueError, AttributeError):
        pass
    raise HTTPException(403, "配对码只能由宿主机本机页面创建")


def authorized(state, authorization):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "请先使用宿主机配对码绑定手机")
    key = digest(authorization[7:])
    session = state.get("mobile_sessions", {}).get(key)
    if not session:
        raise HTTPException(401, "手机凭据已失效，请重新配对")
    return session


@router.post("/pair-code")
def pair_code(request: Request, x_member_id: str = Header(default="m1")):
    require_local(request)
    code = secrets.token_hex(5).upper()
    expires = time.time() + PAIR_CODE_LIFETIME_SECONDS
    def change(state):
        person(state, x_member_id)
        codes = state.setdefault("mobile_pair_codes", {})
        codes_copy = {k:v for k,v in codes.items() if v["expires"] > time.time() and v["member_id"] != x_member_id}
        codes_copy[digest(code)] = {"member_id":x_member_id,"expires":expires}
        state["mobile_pair_codes"] = codes_copy
        db.trace(state,"手机配对码已创建","有效期 5 分钟，仅能使用一次","本机设置")
    db.mutate(change)
    return {"code":code,"expires_at":expires}


class PairInput(BaseModel):
    code: str = Field(min_length=10,max_length=10,pattern=r"^[a-fA-F0-9]{10}$")
    installation_id: str = Field(min_length=10,max_length=80,pattern=r"^[a-zA-Z0-9-]+$")


@router.post("/pair")
def pair(body: PairInput):
    token = secrets.token_urlsafe(32)
    def change(state):
        entry = state.setdefault("mobile_pair_codes", {}).get(digest(body.code.upper()))
        if not entry or entry["expires"] <= time.time():
            raise HTTPException(401,"配对码错误或过期，请在电脑上重新生成")
        owner = entry["member_id"]
        p = person(state,owner)
        sessions = state.setdefault("mobile_sessions",{})
        for old in sessions.values():
            if old["installation_id"] == body.installation_id and old["member_id"] != owner:
                old_phone = next(d for d in person(state,old["member_id"])["devices"] if d["id"]=="phone")
                old_phone.update(signal="unknown",expires_at=0,error="该手机已重新绑定到其他成员")
        state["mobile_sessions"] = {k:v for k,v in sessions.items() if v["member_id"] != owner and v["installation_id"] != body.installation_id}
        state["mobile_sessions"][digest(token)] = {"member_id":owner,"installation_id":body.installation_id,"last_sequence":0}
        del state["mobile_pair_codes"][digest(body.code.upper())]
        phone = next(d for d in p["devices"] if d["id"] == "phone")
        phone.clear()
        phone.update(id="phone",label="Android",source=SOURCE,signal="unknown",expires_at=0,error="已配对，等待采样")
        state["analysis"] = None
        db.trace(state,"原生 Android 已配对",p["name"]+"的手机，等待授权后主动开启采集","Android")
        return {"token":token,"member_id":owner,"member_name":p["name"],"heartbeat_seconds":ANDROID_HEARTBEAT_SECONDS,"expires_seconds":TTL}
    return db.mutate(change)


class Heartbeat(BaseModel):
    sequence: int = Field(ge=1)
    sampled_at_ms: int = Field(ge=0)
    interactive: bool
    locked: bool
    usage_access: bool
    interaction_age_seconds: float | None = Field(default=None,ge=0,le=604800)
    inactive_seconds: float = Field(ge=0,le=604800)

    model_config = {"extra":"forbid"}


@router.post("/heartbeat")
def heartbeat(body: Heartbeat, authorization: str | None = Header(default=None)):
    now = time.time()
    sampled = body.sampled_at_ms / 1000
    if sampled > now + ANDROID_CLOCK_SKEW_SECONDS or sampled < now - TTL:
        raise HTTPException(409,"采样时间偏差过大或数据过期，请校准手机时钟并发送新采样")
    def change(state):
        session = authorized(state,authorization)
        if body.sequence <= session["last_sequence"]:
            return {"accepted":False,"reason":"重复或较旧的采样未刷新有效期"}
        session["last_sequence"] = body.sequence
        p = person(state,session["member_id"])
        if not body.usage_access:
            signal,error = "unknown","未授予使用情况访问权限"
        elif body.interactive and not body.locked and body.interaction_age_seconds is not None and body.interaction_age_seconds <= DEFAULT_ACTIVE_SECONDS:
            signal,error = "active",None
        elif (not body.interactive or body.locked) and body.inactive_seconds >= DEFAULT_REST_SECONDS:
            signal,error = "idle",None
        else:
            signal,error = "away",None
        phone = next(d for d in p["devices"] if d["id"] == "phone")
        changed = any(phone.get(k)!=v for k,v in {"source":SOURCE,"signal":signal,"locked":body.locked,"error":error}.items())
        phone.update(source=SOURCE,signal=signal,locked=body.locked,interactive=body.interactive,
                     usage_access=body.usage_access,interaction_age_seconds=body.interaction_age_seconds,
                     idle_seconds=body.inactive_seconds,observed_at=sampled,received_at=now,
                     expires_at=min(sampled+TTL,now+TTL),error=error)
        if changed:
            state["analysis"] = None
            db.trace(state,"Android 真实信号变化",p["name"]+" · "+signal+"；不代表真实睡眠或噪声","Android API")
        return {"accepted":True,"signal":signal,"expires_at":phone["expires_at"]}
    return db.mutate(change)


class PauseInput(BaseModel):
    sequence: int = Field(ge=1)


@router.post("/pause")
def pause(body: PauseInput,authorization: str | None = Header(default=None)):
    def change(state):
        session=authorized(state,authorization)
        if body.sequence <= session["last_sequence"]:
            return {"ok":False,"reason":"较旧的暂停请求未覆盖新状态"}
        session["last_sequence"]=body.sequence
        p=person(state,session["member_id"])
        phone=next(d for d in p["devices"] if d["id"]=="phone")
        phone.update(signal="unknown",expires_at=0,error="手机主动暂停采集")
        state["analysis"]=None
        return {"ok":True}
    return db.mutate(change)


@router.post("/revoke")
def revoke(request: Request,x_member_id: str = Header(default="m1")):
    require_local(request)
    def change(state):
        p=person(state,x_member_id)
        state["mobile_sessions"]={k:v for k,v in state.get("mobile_sessions",{}).items() if v["member_id"]!=x_member_id}
        phone=next(d for d in p["devices"] if d["id"]=="phone")
        phone.update(signal="unknown",expires_at=0,error="手机配对已解除")
        state["analysis"]=None
        return {"ok":True}
    return db.mutate(change)


@router.get("/inbox")
def inbox(authorization: str | None = Header(default=None)):
    state=db.read()
    session=authorized(state,authorization)
    owner=person(state,session["member_id"])
    items=[{k:r[k] for k in ("id","message","read","time","kind")} for r in state["reminders"]
           if r["target"]==owner["id"] and "phone" in r["devices"] and (r["read"] or deliverable(state, r))]
    return {"member_name":owner["name"],"items":items[-30:]}


@router.post("/inbox/{reminder_id}/read")
def read_reminder(reminder_id: str,authorization: str | None = Header(default=None)):
    def change(state):
        session=authorized(state,authorization)
        item=next((r for r in state["reminders"] if r["id"]==reminder_id and r["target"]==session["member_id"] and "phone" in r["devices"]),None)
        if not item:
            raise HTTPException(404,"提醒不存在")
        item["read"]=True
        return {"ok":True}
    return db.mutate(change)
