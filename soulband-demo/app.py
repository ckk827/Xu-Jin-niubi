from __future__ import annotations

import asyncio
import copy
import json
import logging
import re
import time
import uuid
import sys
import ipaddress
from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import engine
import storage as db
import sensing
import mobile_api
import access
import business
import pc_api
import scheduling
import quiet_rules
import model_connection
import local_model_setup
from model_connection import SettingsInput
from notification_policy import deliverable
from members import demo_member as member
from policy import MANUAL_STATE_LIFETIME_SECONDS

ROOT = Path(__file__).resolve().parent
INFERENCE_LOCK = asyncio.Lock()
runtime = {"busy": False, "error": None, "last_signature": None, "last_analysis_at": 0.0,
           "schedule_block_until": 0.0}


def _setup_logging():
    try:
        folder = ROOT / "data" / "logs"
        folder.mkdir(parents=True, exist_ok=True)
        target = str(folder / "soulband.log")
        root = logging.getLogger()
        if not any(getattr(h, "baseFilename", "") == target for h in root.handlers):
            handler = RotatingFileHandler(target, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
            root.addHandler(handler)
            root.setLevel(logging.INFO)
    except OSError:
        # A read-only checkout must still run; only durable logs are lost.
        logging.getLogger(__name__).warning("无法写入日志文件，继续使用控制台输出")


_setup_logging()
LOG = logging.getLogger("soulband")


def uid(prefix):
    return prefix + uuid.uuid4().hex[:10]


def invalidate(state):
    state["analysis"] = None


def notify(state, target, clause, cycle, message, reason, source, kind="auto"):
    person = member(state, target)
    mode = person["notify"]
    devices = ["pc", "phone"] if mode == "all" else (["pc"] if mode == "pc" else ["phone"])
    if mode == "active":
        active = [d["id"] for d in person["devices"] if sensing.device_view(d)["signal"] == "active"]
        devices = active[:1] or ["phone"]
    state["reminders"].append({"id": uid("n"), "target": target, "clause_id": clause["id"],
                               "clause_ids": [clause["id"]],
                               "version": state["active_id"], "cycle": cycle, "message": message,
                               "reason": reason, "source": source, "kind": kind, "devices": devices,
                               "time": sensing.prepare(state)["clock"]["time"], "read": False,
                               "status": "应用内消息已生成", "created": time.time()})
    db.trace(state, "提醒已生成", f"{person['name']} · {clause['title']} · {kind}", source)


async def run_analysis(trigger="manual"):
    if INFERENCE_LOCK.locked():
        raise HTTPException(409, "已有模型任务进行中，请稍候")
    async with INFERENCE_LOCK:
        snapshot = sensing.prepare(db.read())
        snapshot_key = sensing.analysis_key(snapshot)
        started = time.perf_counter()
        runtime.update(busy=True, error=None)
        source = model_connection.label(snapshot) + (" · " + snapshot["model"] if snapshot["mode"] != "demo" else "")
        try:
            result = await engine.analyze(snapshot)

            def commit(state):
                if sensing.analysis_key(state) != snapshot_key:
                    raise HTTPException(409, "输入已变化，本次旧判断未执行；请重新判断")
                context = sensing.prepare(state)
                engine.validate_analysis(context, result)
                active = engine.active_proposal(context)
                blocked = []
                state_map = {s.member_id: s.status for s in result.states}
                for decision in result.decisions:
                    clause = next((c for c in active["clauses"] if c["id"] == decision.clause_id), None) if active else None
                    if not clause or clause["kind"] != "quiet":
                        blocked.append("未引用有效静音条款")
                        continue
                    inside, cycle = engine.quiet_window(context, clause)
                    eligible = quiet_rules.scope(clause, list(state_map))["member_ids"]
                    if (not inside or decision.target not in eligible or state_map.get(decision.target) != "active"
                            or not any(state_map.get(identity) == "resting" for identity in eligible)):
                        blocked.append("时段或活动依据不满足")
                        continue
                    existing = next((r for r in state["reminders"] if r["target"] == decision.target
                                     and r["cycle"] == cycle and r.get("version") == state["active_id"]), None)
                    if existing:
                        # Two clauses can share one quiet window; keep one reminder and merge the rules.
                        merged = sorted(set(existing.get("clause_ids") or [existing["clause_id"]]) | {clause["id"]})
                        if merged != existing.get("clause_ids"):
                            existing["clause_ids"] = merged
                            blocked.append(f"{member(state, decision.target)['name']} 本时段已提醒，已将「{clause['title']}」并入原提醒")
                        else:
                            blocked.append("本静音时段已提醒该成员")
                        continue
                    if any(word in decision.message for word in ["检测到噪声", "已经违规", "你违反", "正在吵闹"]):
                        blocked.append("文案包含无依据的违规或噪声认定")
                        continue
                    notify(state, decision.target, clause, cycle, decision.message, decision.reason, source)
                if active:
                    scheduling.mark_fired(state)
                else:
                    state["scheduler"] = None
                state["analysis"] = {**result.model_dump(), "source": source, "elapsed": round(time.perf_counter() - started, 3),
                                     "blocked": blocked, "time": context["clock"]["time"], "version": state["active_id"],
                                     "trigger": trigger, "context_key": sensing.analysis_key(state)}
                db.trace(state, "活动与提醒判断", result.summary + (" 拦截：" + "；".join(blocked) if blocked else ""), source)
                return state["analysis"]
            analysis = db.mutate(commit)
            # Any completed run covers this context, so the device watcher must not repeat it.
            runtime["last_signature"] = analysis["context_key"]
            return analysis
        except HTTPException:
            raise
        except (RuntimeError, ValueError) as exc:
            runtime["error"] = str(exc)
            raise HTTPException(502, str(exc)) from exc
        finally:
            runtime["busy"] = False
            runtime["last_analysis_at"] = time.time()


def signature(state):
    return sensing.analysis_key(state)


async def collect_windows_once():
    config = db.read().get("local_sensor", sensing.defaults())
    if not config["enabled"] or not config["member_id"]:
        return
    try:
        sample = await asyncio.to_thread(lambda: sensing.WindowsSampler().sample())
        reading = sensing.classify(sample, config)
    except Exception as exc:
        # A failed API call is unknown data, never a simulated or resting observation.
        reading = {"source": sensing.LIVE_SOURCE, "signal": "unknown", "idle_seconds": None,
                   "locked": None, "observed_at": time.time(), "expires_at": time.time() + sensing.STALE_SECONDS,
                   "error": f"采集失败（{type(exc).__name__}）：{exc}"}
    def commit(state):
        current = state.get("local_sensor", sensing.defaults())
        if not current["enabled"] or current["generation"] != config["generation"]:
            return
        person = member(state, current["member_id"])
        pc = next(d for d in person["devices"] if d["id"] == "pc")
        changed = any(pc.get(k) != reading.get(k) for k in ("source", "signal", "locked", "error"))
        pc.update(reading)
        current["last_error"] = reading["error"]
        if changed:
            invalidate(state)
            db.trace(state, "Windows 真实信号变化", f"{person['name']} · {reading['signal']}；仅表示设备状态", "Windows API")
    db.mutate(commit)


async def sensor_worker():
    while True:
        try:
            await collect_windows_once()
        except Exception as exc:
            # Keep a failed collection loop visible without taking down the host service.
            runtime["error"] = "设备采集处理失败（" + type(exc).__name__ + "）"
        await asyncio.sleep(sensing.POLL_SECONDS)


async def watcher():
    while True:
        await asyncio.sleep(3)
        state = sensing.prepare(db.read())
        current = signature(state)
        # The clock is no longer part of the key; scheduled windows are handled by the scheduler.
        cooled = time.time() - runtime["last_analysis_at"] < 2.5
        if state["mode"] != "unconfigured" and state["active_id"] and current != runtime["last_signature"] and not cooled and not INFERENCE_LOCK.locked():
            try:
                result = await run_analysis(trigger="devices")
                runtime["last_signature"] = result["context_key"]
            except HTTPException as exc:
                runtime["error"] = str(exc.detail)
                if exc.status_code != 409:
                    runtime["last_signature"] = current


async def scheduler_step():
    """Fire the reminder that belongs to the current window, once per cycle."""
    if INFERENCE_LOCK.locked() or time.time() < runtime["schedule_block_until"]:
        return
    if db.read()["mode"] == "unconfigured":
        return
    verdict = scheduling.evaluate(db.read())
    action = verdict["action"]
    if action == "rebuild":
        db.mutate(scheduling.rebuild)
        return
    if action == "missed":
        def note(state):
            if scheduling.evaluate(state)["action"] == "missed":
                db.trace(state, "提醒时段已错过", verdict["reason"] + "；不补发已过期的提醒", "定时调度")
            scheduling.mark_missed(state, verdict.get("cycle"))
        db.mutate(note)
        return
    if action == "fire":
        try:
            await run_analysis(trigger="scheduled")
        except HTTPException as exc:
            runtime["error"] = str(exc.detail)
            runtime["schedule_block_until"] = time.time() + 30


async def scheduler_worker():
    while True:
        await asyncio.sleep(scheduling.TICK_SECONDS)
        try:
            await scheduler_step()
        except Exception as exc:
            LOG.exception("scheduler tick failed")
            runtime["error"] = "定时提醒处理失败（" + type(exc).__name__ + "）"


@asynccontextmanager
async def lifespan(app):
    initial = db.read()
    # A saved local choice may resume on subsequent boots; first boot never downloads.
    if initial["mode"] == "ollama" and initial.get("model_configured"):
        local_model_setup.start(initial["model"])
    try:
        db.backup("startup")
    except Exception:
        LOG.exception("startup backup failed")
    worker = asyncio.create_task(watcher())
    collector = asyncio.create_task(sensor_worker())
    ticker = asyncio.create_task(scheduler_worker())
    yield
    worker.cancel()
    collector.cancel()
    ticker.cancel()
    await asyncio.gather(worker, collector, ticker, return_exceptions=True)


app = FastAPI(title="宿伴 Soulband Demo", version=sensing.VERSION, lifespan=lifespan)
app.include_router(mobile_api.router)
app.include_router(access.router)
app.include_router(access.seat_router)
app.include_router(business.router)
app.include_router(pc_api.router)
app.middleware("http")(access.protect)


@app.get("/api/health")
def health():
    return {"app": "soulband-demo", "version": sensing.VERSION, "ok": True}


@app.get("/api/state")
def state_view(request: Request, x_member_id: str = Header(default="m1"), since: int | None = None):
    raw = db.read()
    identity = {"member_id": x_member_id, "local_demo": request.state.local_demo,
                "seat": getattr(request.state, "seat", False)}
    if since is not None and since == raw["revision"]:
        return {"unchanged": True, "revision": raw["revision"], "server_time": time.time(),
                "runtime": {k: v for k, v in runtime.items() if k != "last_signature"},
                "identity": identity}
    state = sensing.prepare(raw)
    if state["analysis"] and state["analysis"].get("context_key") != sensing.analysis_key(state):
        state["analysis"] = None
    member(state, x_member_id)
    # Shared demo data plus only the selected profile's inbox. Private requests are never stored here.
    state["reminders"] = [r for r in state["reminders"] if r["target"] == x_member_id]
    for reminder in state["reminders"]:
        if not deliverable(state, reminder):
            reminder["original_devices"] = reminder["devices"]
            reminder["devices"] = []
            reminder["status"] = "历史提醒，当前公约或时段已失效，不再弹出"
    state["runtime"] = copy.deepcopy(runtime)
    state["runtime"].pop("last_signature", None)
    state["local_sensor"]["available"] = sys.platform == "win32"
    state["mobile_paired"] = list({s["member_id"] for s in state.get("mobile_sessions",{}).values()})
    state.pop("mobile_sessions",None)
    state.pop("mobile_pair_codes",None)
    for key in ("access_codes", "client_sessions"):
        state.pop(key, None)
    state["demands"] = [d for d in state["demands"] if d.get("visibility", "public") == "public" or d["member_id"] == x_member_id]
    state["feedbacks"] = [{k:v for k,v in f.items() if k != "reporter"} for f in state["feedbacks"]]
    state["identity"] = identity
    if request.state.local_demo:
        state["api_key_saved"] = bool(model_connection.saved_key(state.get("api_base_url", "")))
    else:
        state.pop("api_base_url", None)
    state["scheduler"] = scheduling.describe(state)
    for key in ("adjustments", "swaps"):
        state.setdefault(key, [])
    for person in state["members"]:
        for device in person["devices"]:
            device.pop("peer_key", None)
    for proposal in state["proposals"]:
        for clause in proposal["clauses"]:
            if clause["kind"] == "quiet":
                clause["execution_scope"] = quiet_rules.scope(clause, [m["id"] for m in state["members"]])
    return state


class DemandInput(BaseModel):
    text: str = Field(min_length=2, max_length=1500)


@app.post("/api/demands")
def add_demand(body: DemandInput, x_member_id: str = Header(default="m1")):
    text = body.text.strip()
    if len(text) < 2:
        raise HTTPException(400, "请输入具体诉求")
    def change(state):
        member(state, x_member_id)
        if len(state["demands"]) >= 100:
            raise HTTPException(400, "诉求记录已达 100 条，请先整理现有诉求")
        item = {"id": uid("r"), "member_id": x_member_id, "text": text}
        state["demands"].append(item)
        db.trace(state, "公开需求已提交", "成员主动提交一条公开需求")
        return item
    return db.mutate(change)


@app.post("/api/proposals/generate")
async def generate_proposal():
    if INFERENCE_LOCK.locked():
        raise HTTPException(409, "已有模型任务进行中，请稍候")
    async with INFERENCE_LOCK:
        snapshot = db.read()
        runtime.update(busy=True, error=None)
        try:
            output = await engine.generate(snapshot)
            clause_ids = [c.id for c in output.clauses]
            sources = {d["id"] for d in snapshot["demands"]}
            if len(set(clause_ids)) != len(clause_ids) or any(not set(c.sources) <= sources for c in output.clauses):
                raise ValueError("条款标识重复或引用了不存在的需求")
            def change(state):
                if any(state.get(k) != snapshot.get(k) for k in ("demands", "mode", "model", "model_connection_revision")) or len(state["proposals"]) != len(snapshot["proposals"]):
                    raise HTTPException(409, "需求或状态已变化，请重新生成草案")
                item = {**output.model_dump(), "id": uid("p"), "version": len(state["proposals"]) + 1,
                        "approvals": [], "status": "draft", "source": model_connection.label(state)}
                state["proposals"].append(item)
                db.trace(state, "公约草案已生成", f"v{item['version']}，等待四名成员分别审核", item["source"])
                return item
            return db.mutate(change)
        except (RuntimeError, ValueError) as exc:
            runtime["error"] = str(exc)
            raise HTTPException(502, str(exc)) from exc
        finally:
            runtime["busy"] = False


class EditProposal(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    clauses: list[engine.Clause] = Field(min_length=1, max_length=12)
    conflicts: list[str] = Field(default_factory=list, max_length=12)
    valid_until: str | None = None


@app.post("/api/proposals/{proposal_id}/revise")
def revise(proposal_id: str, body: EditProposal):
    if body.valid_until:
        try:
            value = datetime.fromisoformat(body.valid_until)
            if value.tzinfo:
                raise ValueError()
        except ValueError as exc:
            raise HTTPException(400, "公约截止时间须使用本地业务时间") from exc
    if len({c.id for c in body.clauses}) != len(body.clauses):
        raise HTTPException(400, "条款标识不能重复")
    def change(state):
        previous = next((p for p in state["proposals"] if p["id"] == proposal_id), None)
        if not previous or previous["id"] != state["proposals"][-1]["id"]:
            raise HTTPException(409, "只能修订最新草案或公约")
        if any(not set(c.member_ids) <= {m["id"] for m in state["members"]} for c in body.clauses):
            raise HTTPException(400, "条款适用成员不存在")
        item = {**body.model_dump(), "id": uid("p"), "version": len(state["proposals"]) + 1,
                "approvals": [], "status": "draft", "source": "人工修订"}
        state["proposals"].append(item)
        db.trace(state, "修订生成新版本", f"v{item['version']}，旧确认不沿用，原生效公约在新版通过前仍有效")
        return item
    return db.mutate(change)


@app.post("/api/proposals/{proposal_id}/approve")
async def approve(proposal_id: str, x_member_id: str = Header(default="m1")):
    snapshot = db.read()
    reviewed = next((p for p in snapshot["proposals"] if p["id"] == proposal_id), None)
    receipt = None
    receipt_source = None
    degraded = None
    if reviewed and not reviewed["conflicts"] and set(reviewed["approvals"]) | {x_member_id} == {m["id"] for m in snapshot["members"]}:
        if reviewed.get("record_receipt"):
            receipt = reviewed["record_receipt"]
            receipt_source = receipt.get("source", "程序受控记录")
        else:
            try:
                command = await asyncio.wait_for(engine.record_request(snapshot, reviewed), timeout=20)
                if command.proposal_id != proposal_id:
                    raise ValueError("模型工具引用了其他版本，未记录公约")
                receipt = command.model_dump()
                receipt_source = "演示工具" if snapshot["mode"] == "demo" else model_connection.label(snapshot)
            except (RuntimeError, ValueError, asyncio.TimeoutError) as exc:
                if snapshot["mode"] == "demo":
                    raise HTTPException(502, str(exc)) from exc
                # A dead model must not block the room: the deterministic record replaces it.
                degraded = "模型未能记录，已由程序受控记录替代（" + (str(exc) or "超时") + "）"
                receipt = {"tool": "record_covenant", "proposal_id": proposal_id, "clauses": len(reviewed["clauses"])}
                receipt_source = "程序受控记录"
    def change(state):
        person = member(state, x_member_id)
        item = next((p for p in state["proposals"] if p["id"] == proposal_id), None)
        if not item or item["id"] != state["proposals"][-1]["id"]:
            raise HTTPException(409, "请审核最新版本，旧草案不能再生效")
        if item["status"] in ("revoked", "archived"):
            raise HTTPException(409, "已撤销或归档公约不可重新确认，请修订为新版本")
        if item["conflicts"]:
            raise HTTPException(409, "仍有待协商冲突，请修订解决后再确认")
        if any(state.get(k) != snapshot.get(k) for k in ("proposals", "mode", "model", "model_connection_revision")):
            raise HTTPException(409, "审核内容或配置已变化，请刷新后重新确认")
        if item.get("valid_until") and engine.business_now(sensing.prepare(state)) >= datetime.fromisoformat(item["valid_until"]):
            raise HTTPException(409, "公约截止时间已过，请先修订")
        if x_member_id not in item["approvals"]:
            item["approvals"].append(x_member_id)
            item.setdefault("approval_records", []).append({"member_id": x_member_id, "at": time.time()})
            db.trace(state, "成员审核通过", f"{person['name']} 确认 v{item['version']}")
        if len(item["approvals"]) == len(state["members"]) and state["active_id"] != item["id"]:
            if not receipt:
                raise HTTPException(409, "尚未取得此版本的受控记录请求，请重试确认")
            for previous in state["proposals"]:
                if previous["status"] == "active":
                    previous["status"] = "archived"
            item["status"] = "active"
            state["active_id"] = item["id"]
            invalidate(state)
            db.trace(state, "公约正式记录生效", f"v{item['version']} 全员确认，后续判断只使用此版本")
            item["record_receipt"] = {**receipt, "at": time.time(), "source": receipt_source, "persisted": True}
            if degraded:
                item["record_receipt"]["degraded"] = degraded
                db.trace(state, "模型记录降级", degraded, "程序受控记录")
        return item
    return db.mutate(change)


class SignalInput(BaseModel):
    signal: Literal["active", "idle", "unknown"]


@app.put("/api/devices/{member_id}/{device_id}")
def signal(member_id: str, device_id: str, body: SignalInput):
    # Intentionally a demo controller: any profile may stage other sample members' device inputs.
    def change(state):
        person = member(state, member_id)
        config = state.get("local_sensor", sensing.defaults())
        if device_id == "pc" and config["enabled"] and config["member_id"] == member_id:
            raise HTTPException(409, "此电脑正在真实采集，请先暂停采集再切回模拟")
        if device_id == "phone" and any(s["member_id"] == member_id for s in state.get("mobile_sessions",{}).values()):
            raise HTTPException(409,"此成员已配对原生手机，请在设置解除配对后再模拟")
        device = next((d for d in person["devices"] if d["id"] == device_id), None)
        if not device:
            raise HTTPException(404, "设备不存在")
        label = device["label"]
        device.clear()
        device.update(id=device_id, label=label, signal=body.signal, source="simulation")
        invalidate(state)
        return {"ok": True}
    return db.mutate(change)


class SensorInput(BaseModel):
    enabled: bool
    active_within_seconds: int = Field(default=sensing.DEFAULT_ACTIVE_SECONDS, ge=1, le=300)
    rest_after_seconds: int = Field(default=sensing.DEFAULT_REST_SECONDS, ge=30, le=7200)


@app.put("/api/sensing")
async def configure_sensing(body: SensorInput, request: Request, x_member_id: str = Header(default="m1")):
    try:
        local = ipaddress.ip_address(request.client.host).is_loopback
    except (ValueError, AttributeError):
        local = False
    if not local:
        raise HTTPException(403, "只能在宿主机本机页面绑定或控制这台 Windows，手机页面不会采集手机状态")
    if body.enabled and sys.platform != "win32":
        raise HTTPException(409, "当前宿主不是 Windows，不能开启真实采集")
    if body.rest_after_seconds <= body.active_within_seconds:
        raise HTTPException(400, "持续无操作观察时间必须大于近期操作窗口")
    def change(state):
        person = member(state, x_member_id)
        config = state.setdefault("local_sensor", sensing.defaults())
        if config["member_id"]:
            previous = member(state, config["member_id"])
            old_pc = next(d for d in previous["devices"] if d["id"] == "pc")
            if old_pc.get("source") == sensing.LIVE_SOURCE:
                old_pc.update(signal="unknown", expires_at=0, idle_seconds=None, locked=None,
                              error="采集已暂停或本机已重新绑定")
        if body.enabled:
            pc = next(d for d in person["devices"] if d["id"] == "pc")
            pc.update(signal="unknown", source=sensing.LIVE_SOURCE, expires_at=0, error="等待首次采样")
            # Do not silently combine real PC evidence with a previously seeded sleeping phone.
            if config["member_id"] != x_member_id:
                phone = next(d for d in person["devices"] if d["id"] == "phone")
                if phone.get("source", "simulation") == "simulation":
                    phone["signal"] = "unknown"
            config["member_id"] = x_member_id
        config.update(enabled=body.enabled, active_within_seconds=body.active_within_seconds,
                      rest_after_seconds=body.rest_after_seconds, generation=config["generation"] + 1, last_error=None)
        invalidate(state)
        db.trace(state, "Windows 采集已开启" if body.enabled else "Windows 采集已暂停",
                 f"绑定 {member(state, config['member_id'])['name']}；不会随顶栏身份切换自动改绑" if config["member_id"] else "尚未绑定", "本机设置")
        return {"ok": True}
    result = db.mutate(change)
    if body.enabled:
        await collect_windows_once()
    return result


class ManualInput(BaseModel):
    status: Literal["active", "resting", "unknown", "clear"]
    activity: str = Field(default="", max_length=50)


@app.put("/api/manual")
def manual(body: ManualInput, x_member_id: str = Header(default="m1")):
    def change(state):
        person = member(state, x_member_id)
        person["manual"] = None if body.status == "clear" else {
            "status": body.status, "activity": body.activity, "expires": time.time() + MANUAL_STATE_LIFETIME_SECONDS}
        invalidate(state)
        db.trace(state, "本人状态设置", f"{person['name']} 更新有效人工状态；Demo 有效期 30 分钟")
        return {"ok": True}
    return db.mutate(change)


class ClockInput(BaseModel):
    date: str
    time: str
    mode: Literal["simulation", "real"] = "simulation"


@app.put("/api/clock")
def clock(body: ClockInput):
    try:
        date.fromisoformat(body.date)
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", body.time):
            raise ValueError()
    except ValueError:
        raise HTTPException(400, "请输入合法的模拟日期和时间")
    def change(state):
        state["clock"] = body.model_dump()
        invalidate(state)
        db.trace(state, "模拟时间调整", f"{body.date} {body.time}")
        return {"ok": True}
    return db.mutate(change)


@app.post("/api/analyze")
async def analyze_now():
    return await run_analysis()


@app.put("/api/settings")
def settings(body: SettingsInput):
    try:
        model_connection.save(body)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    runtime["error"] = None
    return {"ok": True}


@app.post("/api/settings/test")
async def test_model_connection(body: SettingsInput):
    if body.mode == "demo":
        raise HTTPException(422, "演示模式不调用模型，无需连接测试")
    try:
        base, key = model_connection.connection_values(body)
        candidate = {"mode": body.mode, "model": body.model, "api_base_url": base}
        if body.mode == "external":
            await engine.external_model(candidate, "连接测试，请返回 reply 字段，内容为连接成功", {}, engine.PrivateReply, api_key=key)
        else:
            await engine.ollama(candidate, "连接测试，请返回 reply 字段，内容为连接成功", {}, engine.PrivateReply)
        return {"ok": True, "message": "连接成功，模型已通过 JSON 响应校验"}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from None


@app.post("/api/settings/local-setup")
def prepare_local_model():
    state = db.read()
    if state["mode"] != "ollama":
        raise HTTPException(409, "请先保存本地模型选项；外部 API 不需要下载 Ollama")
    try:
        return local_model_setup.start(state["model"])
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@app.get("/api/settings/local-setup")
def local_setup_status(request: Request):
    if not request.state.local_demo:
        raise HTTPException(403, "本地模型准备日志仅供宿主本机查看")
    return local_model_setup.status()


class NotifyInput(BaseModel):
    strategy: Literal["active", "all", "pc", "phone"]


@app.put("/api/notification-preference")
def preference(body: NotifyInput, x_member_id: str = Header(default="m1")):
    def change(state):
        member(state, x_member_id)["notify"] = body.strategy
        return {"ok": True}
    return db.mutate(change)


@app.post("/api/reminders/{reminder_id}/read")
def mark_read(reminder_id: str, x_member_id: str = Header(default="m1")):
    def change(state):
        item = next((r for r in state["reminders"] if r["id"] == reminder_id and r["target"] == x_member_id), None)
        if not item:
            raise HTTPException(404, "提醒不存在")
        item["read"] = True
        return {"ok": True}
    return db.mutate(change)


class FeedbackInput(BaseModel):
    target: str
    result: Literal["improved", "still"]


@app.post("/api/feedback")
async def feedback(body: FeedbackInput, x_member_id: str = Header(default="m1")):
    snapshot = sensing.prepare(db.read())
    followup = "有成员反馈仍希望保持安静，请再次留意当前公约。若安排不合适，可以一起协商。"
    source = "演示反馈流程" if snapshot["mode"] == "demo" else model_connection.label(snapshot)
    if snapshot["mode"] != "demo" and body.result == "still":
        try:
            followup = (await engine.ollama(snapshot, "有成员主动反馈仍受影响。只整理一次中性后续提醒，不认定噪声、违规或公开反馈者。", {"covenant": engine.active_proposal(snapshot), "target": body.target}, engine.PrivateReply)).reply
        except RuntimeError as exc:
            raise HTTPException(502, str(exc)) from exc
        if any(word in followup for word in ("检测到噪声", "已经违规", "你违反", "正在吵闹")):
            raise HTTPException(502, "模型提醒包含无依据认定，未发送")
    def change(state):
        if any(state.get(k) != snapshot.get(k) for k in ("active_id", "mode", "model", "model_connection_revision")):
            raise HTTPException(409, "公约或模型配置已变化，请重新提交反馈")
        member(state, x_member_id)
        member(state, body.target)
        active = engine.active_proposal(state)
        if not active:
            raise HTTPException(409, "尚无生效公约，请先完成审核")
        if x_member_id == body.target:
            raise HTTPException(400, "请选择与该问题有关的另一位成员")
        context = sensing.prepare(state)
        clause = next((c for c in active["clauses"] if c["kind"] == "quiet" and engine.quiet_window(context, c)[0]
                       and body.target in quiet_rules.scope(c, [m["id"] for m in state["members"]])["member_ids"]), None)
        if not clause:
            raise HTTPException(409, "当前不在已约定静音时段，不能据此扩展静音要求")
        _, cycle = engine.quiet_window(context, clause)
        sent = [r for r in state["reminders"] if r["target"] == body.target and r["cycle"] == cycle]
        if not sent:
            raise HTTPException(409, "本 Demo 的回访须关联已发出的提醒，请先运行状态判断")
        same = [f for f in state["feedbacks"] if f["target"] == body.target and f["cycle"] == cycle]
        if same and same[-1]["reporter"] == x_member_id and time.time() - same[-1]["created"] < 5:
            raise HTTPException(429, "刚刚已提交，请勿连续点击；稍后再确认实际情况")
        state["feedbacks"].append({"id": uid("f"), "reporter": x_member_id, "target": body.target,
                                   "result": body.result, "cycle": cycle, "created": time.time()})
        if body.result == "improved":
            db.trace(state, "自愿回访", "成员反馈已改善；不据此给成员打分")
            return {"message": "已记录改善反馈，谢谢你的回访。"}
        if len(sent) == 1:
            notify(state, body.target, clause, cycle,
                   followup,
                   "成员主动反馈，允许一次后续提醒", source, kind="followup")
            return {"message": "已传达中性提醒，没有公开你的原始表达。"}
        if not any(n["target"] == body.target and n["cycle"] == cycle for n in state["negotiations"]):
            state["negotiations"].append({"id": uid("g"), "target": body.target, "cycle": cycle,
                                          "clause_id": clause["id"], "version": active["version"],
                                          "title": "静音安排需要再次协商", "status": "待相关成员讨论"})
            db.trace(state, "邀请再次协商", "再次提醒后仍有反馈，停止继续催促；建议待成员审核")
        return {"message": "已建立再次协商事项，不再追加催促通知。"}
    return db.mutate(change)


@app.post("/api/tasks/{task_id}/toggle")
def toggle_task(task_id: str, request: Request, x_member_id: str = Header(default="m1")):
    def change(state):
        item = next((t for t in state["tasks"] if t["id"] == task_id), None)
        if not item:
            raise HTTPException(404, "任务不存在")
        if not request.state.local_demo and item["owner"] != x_member_id:
            raise HTTPException(403, "仅任务负责人可修改完成状态")
        item["done"] = not item["done"]
        return item
    return db.mutate(change)


class BillInput(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    amount: str = Field(pattern=r"^\d{1,6}(?:\.\d{1,2})?$")
    participants: list[str] | None = Field(default=None, min_length=1, max_length=6)


@app.post("/api/bills")
def create_bill(body: BillInput):
    total = int(Decimal(body.amount) * 100)
    if total <= 0:
        raise HTTPException(400, "金额必须大于零")
    def change(state):
        chosen = body.participants or [m["id"] for m in state["members"]]
        if not body.title.strip():
            raise HTTPException(400, "账单名称不能为空")
        if len(set(chosen)) != len(chosen):
            raise HTTPException(400, "参与成员不能重复")
        people = [member(state, identity) for identity in chosen]
        count = len(people)
        base, extra = divmod(total, count)
        item = {"id": uid("b"), "title": body.title.strip(), "total_cents": total,
                "shares": [{"member_id": m["id"], "cents": base + (1 if i < extra else 0)} for i, m in enumerate(people)], "settled": []}
        state["bills"].append(item)
        return item
    return db.mutate(change)


class PrivateInput(BaseModel):
    text: str = Field(min_length=2, max_length=1500)
    style: Literal["gentle", "direct", "friendly"]


@app.post("/api/private")
async def private_help(body: PrivateInput):
    if not body.text.strip():
        raise HTTPException(400, "请输入想表达的内容")
    try:
        reply = await engine.private_reply(db.read(), body.text.strip(), body.style)
        return {"reply": reply, "saved": False}
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/api/admin/backup")
def backup_now(request: Request):
    if not access.local(request):
        raise HTTPException(403, "备份只允许在宿主机本机执行")
    target = db.backup("manual", keep=7)
    if not target:
        raise HTTPException(500, "备份失败，请查看 data/logs/soulband.log")
    return {"ok": True, "file": target.name, "folder": str(target.parent)}


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/downloads/soulband.apk",include_in_schema=False)
def download_android():
    apk = ROOT.parent / "output" / "apk" / "Soulband-v0.4.0-debug.apk"
    if not apk.is_file():
        raise HTTPException(404,"APK 尚未构建，请先执行 soulband-android/Build-APK.ps1")
    return FileResponse(apk,media_type="application/vnd.android.package-archive",filename=apk.name)


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
