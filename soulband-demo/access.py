"""Device credentials: LAN callers cannot select an identity with a header."""
import hashlib
import ipaddress
import os
import secrets
import time
from urllib.parse import urlsplit

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import storage as db
from members import require_member

router = APIRouter(prefix="/api/access", tags=["成员设备授权"])


def local(request):
    host = request.client.host if request.client else ""
    if host == "testclient":  # Starlette's in-process transport, never a TCP peer.
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def session(state, token):
    key = digest(token)
    value = state.get("client_sessions", {}).get(key) or state.get("mobile_sessions", {}).get(key)
    if not value or value.get("expires", float("inf")) <= time.time():
        raise HTTPException(401, "设备授权已失效，请重新使用配对码登录")
    return value


async def protect(request, call_next):
    path = request.url.path
    if not path.startswith("/api/") or path in ("/api/health", "/api/access/redeem", "/api/mobile/pair"):
        return await call_next(request)
    token = request.headers.get("authorization", "")
    is_local = local(request)
    origin = request.headers.get("origin")
    if origin and request.method not in ("GET", "HEAD", "OPTIONS") and urlsplit(origin).netloc != request.headers.get("host"):
        return JSONResponse({"detail": "跨站操作被拒绝，请直接打开宿伴页面"}, status_code=403)
    if is_local and request.url.hostname not in ("localhost", "testserver"):
        try:
            ipaddress.ip_address(request.url.hostname)
        except ValueError:
            return JSONResponse({"detail": "请通过本机或局域网 IP 访问宿伴"}, status_code=403)
    if path in ("/api/sensing", "/api/mobile/pair-code", "/api/mobile/revoke") and not is_local:
        return JSONResponse({"detail": "此操作仅允许在宿主本机进行"}, status_code=403)
    request.state.local_demo = is_local and not token and os.getenv("SOULBAND_STRICT_AUTH") != "1"
    if request.state.local_demo:
        request.state.member_id = request.headers.get("x-member-id", "m1")
    else:
        try:
            if not token.startswith("Bearer "):
                raise HTTPException(401, "请使用电脑本机生成的配对码登录")
            account = session(db.read(), token[7:])
            request.state.member_id = account["member_id"]
            # Route handlers use this trusted identity, never the caller's claim.
            request.scope["headers"] = [(k, v) for k, v in request.scope["headers"] if k.lower() != b"x-member-id"] + [(b"x-member-id", account["member_id"].encode())]
            request.state.platform = account.get("platform", "phone")
        except HTTPException as exc:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    controls = ("/api/settings", "/api/clock", "/api/devices/", "/api/members", "/api/access/code", "/api/access/revoke")
    if request.method != "GET" and any(path.startswith(p) for p in controls) and not is_local:
        return JSONResponse({"detail": "演示控制及设备授权管理仅允许在宿主本机操作"}, status_code=403)
    return await call_next(request)


class CodeInput(BaseModel):
    member_id: str


@router.post("/code")
def code(body: CodeInput, request: Request):
    if not local(request):
        raise HTTPException(403, "请在宿主本机生成登录码")
    value = secrets.token_hex(5).upper()
    def save(state):
        require_member(state, body.member_id)
        state.setdefault("access_codes", {})[digest(value)] = {"member_id": body.member_id, "expires": time.time() + 300}
    db.mutate(save)
    return {"code": value, "expires_seconds": 300}


class RedeemInput(BaseModel):
    code: str = Field(pattern=r"^[A-Fa-f0-9]{10}$")
    platform: str = Field(pattern=r"^(web|pc)$", default="web")


@router.post("/redeem")
def redeem(body: RedeemInput):
    token = secrets.token_urlsafe(32)
    def save(state):
        key = digest(body.code.upper())
        item = state.setdefault("access_codes", {}).get(key)
        if not item or item["expires"] <= time.time():
            raise HTTPException(401, "登录码错误、已使用或已过期")
        del state["access_codes"][key]
        state.setdefault("client_sessions", {})[digest(token)] = {"member_id": item["member_id"], "platform": body.platform, "expires": time.time() + 30 * 86400, "last_sequence": 0}
        return {"token": token, "member_id": item["member_id"], "member_name": require_member(state, item["member_id"])["name"]}
    return db.mutate(save)


@router.get("/me")
def me(request: Request):
    return {"member_id": request.state.member_id, "local_demo": request.state.local_demo}


@router.post("/logout")
def logout(authorization: str = Header(default="")):
    def save(state):
        state.setdefault("client_sessions", {}).pop(digest(authorization.removeprefix("Bearer ")), None)
    db.mutate(save)
    return {"ok": True}


@router.post("/revoke")
def revoke(body: CodeInput):
    def save(state):
        state["client_sessions"] = {k:v for k,v in state.get("client_sessions", {}).items() if v["member_id"] != body.member_id}
    db.mutate(save)
    return {"ok": True}
