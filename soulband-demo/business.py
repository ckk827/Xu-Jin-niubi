"""Reviewed business operations shared by native and web clients."""
import copy
import time
import uuid
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field, model_validator
import engine
import sensing
import storage as db
from members import require_member

router = APIRouter(prefix="/api", tags=["完整业务"])


class Profile(BaseModel):
    name: str = Field(min_length=1, max_length=20)


@router.put("/profile")
def profile(body: Profile, x_member_id: str = Header(default="m1")):
    if not body.name.strip():
        raise HTTPException(400, "昵称不能为空")
    def save(state):
        require_member(state, x_member_id)["name"] = body.name.strip()
    db.mutate(save)
    return {"ok": True}


@router.post("/members")
def add_member(body: Profile):
    def save(state):
        if len(state["members"]) >= 6:
            raise HTTPException(409, "本版支持最多六名成员")
        if state["active_id"]:
            raise HTTPException(409, "成员范围会影响审核，请先全员同意撤销公约，再添加并重新生成审核")
        if not body.name.strip():
            raise HTTPException(400, "昵称不能为空")
        value = {"id": "m" + str(len(state["members"]) + 1), "name": body.name.strip(), "color": "purple", "manual": None, "notify": "active", "devices": [{"id":"pc", "label":"Windows", "signal":"unknown", "source":"simulation"}, {"id":"phone", "label":"Android", "signal":"unknown", "source":"simulation"}]}
        state["members"].append(value)
        # Existing drafts remain history. A fresh draft requires the new full member set.
        for draft in state["proposals"]:
            if draft["status"] == "draft":
                draft["status"] = "archived"
        state["analysis"] = None
        return value
    return db.mutate(save)


def uid(prefix):
    return prefix + uuid.uuid4().hex[:12]


def item(state, key, identity):
    found = next((v for v in state.get(key, []) if v["id"] == identity), None)
    if not found:
        raise HTTPException(404, "记录不存在")
    return found


class NeedInput(BaseModel):
    text: str = Field(min_length=2, max_length=1500)


@router.post("/needs/prepare")
async def prepare_need(body: NeedInput):
    try:
        output = await engine.prepare_need(db.read(), body.text)
        return {**output.model_dump(), "saved": False}
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc


class NeedSave(NeedInput):
    visibility: Literal["public", "private"] = "public"


@router.post("/needs")
def save_need(body: NeedSave, x_member_id: str = Header(default="m1")):
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "请输入具体诉求")
    if body.visibility == "private":
        # Private cards never enter the shared blob the model, exports or diffs can see.
        require_member(db.read(), x_member_id)
        return db.save_private_need(x_member_id, text)

    def save(state):
        require_member(state, x_member_id)
        value = {"id": uid("r"), "member_id": x_member_id, "text": text, "visibility": "public"}
        state["demands"].append(value)
        return value
    return db.mutate(save)


class Adjustment(BaseModel):
    clause_id: str
    reason: str = Field(min_length=2, max_length=500)
    starts: str
    ends: str

    @model_validator(mode="after")
    def times(self):
        start, end = datetime.fromisoformat(self.starts), datetime.fromisoformat(self.ends)
        if start.tzinfo or end.tzinfo or not start < end or end - start > timedelta(hours=24):
            raise ValueError("临时安排须使用本地业务时间，结束晚于开始，最长 24 小时")
        return self


@router.post("/adjustments")
def adjustment(body: Adjustment, x_member_id: str = Header(default="m1")):
    def save(state):
        require_member(state, x_member_id)
        active = engine.active_proposal(sensing.prepare(state))
        if not active or not any(c["id"] == body.clause_id and c["kind"] == "quiet" for c in active["clauses"]):
            raise HTTPException(409, "请选择当前生效的静音条款")
        value = {**body.model_dump(), "id": uid("a"), "version_id": active["id"], "requester": x_member_id, "approvals": [x_member_id], "status": "pending"}
        state.setdefault("adjustments", []).append(value)
        return value
    return db.mutate(save)


class Vote(BaseModel):
    approve: bool = True


@router.post("/adjustments/{identity}/vote")
def adjustment_vote(identity: str, body: Vote, x_member_id: str = Header(default="m1")):
    def save(state):
        require_member(state, x_member_id)
        value = item(state, "adjustments", identity)
        now = engine.business_now(sensing.prepare(state))
        if value["status"] != "pending" or state["active_id"] != value["version_id"] or now >= datetime.fromisoformat(value["ends"]):
            raise HTTPException(409, "此申请已处理、过期或公约版本已变更")
        if not body.approve:
            value["status"] = "rejected"
        elif x_member_id not in value["approvals"]:
            value["approvals"].append(x_member_id)
        if len(value["approvals"]) == len(state["members"]):
            value["status"] = "approved"
        state["analysis"] = None
        db.trace(state, "临时安排审核", "全员同意后，仅在申请时间暂停对应静音条款；到期自动恢复")
        return value
    return db.mutate(save)


@router.post("/covenant/revoke-request")
def revoke_request(x_member_id: str = Header(default="m1")):
    def save(state):
        require_member(state, x_member_id)
        active = engine.active_proposal(sensing.prepare(state))
        if not active:
            if any(p["status"] == "expired" for p in state["proposals"]):
                raise HTTPException(409, "公约已到期，无需撤销；可直接添加成员或生成新版本")
            raise HTTPException(409, "没有生效公约")
        active.setdefault("revoke_approvals", [])
        # active_proposal is a projection; mutate only the persisted version.
        saved = item(state, "proposals", active["id"])
        votes = saved.setdefault("revoke_approvals", [])
        if x_member_id not in votes:
            votes.append(x_member_id)
        if len(votes) == len(state["members"]):
            saved["status"] = "revoked"
            state["active_id"] = None
            state["analysis"] = None
        return {"approvals": votes, "revoked": state["active_id"] is None}
    return db.mutate(save)


class TaskInput(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    owner: str
    due: str = Field(min_length=1, max_length=40)
    standard: str = Field(default="由相关成员检查完成情况", max_length=500)


@router.post("/tasks")
def task_create(body: TaskInput, x_member_id: str = Header(default="m1")):
    def save(state):
        require_member(state, x_member_id)
        require_member(state, body.owner)
        if not body.title.strip():
            raise HTTPException(400, "任务标题不能为空")
        value = {**body.model_dump(), "id": uid("t"), "done": False, "created_by": x_member_id}
        state["tasks"].append(value)
        return value
    return db.mutate(save)


class RotaInput(BaseModel):
    start: str
    days: int = Field(default=7, ge=1, le=31)
    members: list[str] = Field(min_length=1, max_length=6)
    title: str = Field(default="清运垃圾与清理公共地面", min_length=1, max_length=120)


@router.post("/tasks/rota")
def rota(body: RotaInput, x_member_id: str = Header(default="m1")):
    try:
        day = datetime.strptime(body.start, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(400, "开始日期无效") from exc
    def save(state):
        require_member(state, x_member_id)
        if len(set(body.members)) != len(body.members):
            raise HTTPException(400, "轮值成员不能重复")
        for identity in body.members:
            require_member(state, identity)
        batch = uid("rota")
        result = []
        for n in range(body.days):
            value = {"id": uid("t"), "title": body.title, "owner": body.members[n % len(body.members)], "due": (day + timedelta(days=n)).isoformat(), "done": False, "batch": batch, "created_by": x_member_id, "standard": "清运垃圾、清理公共地面；由成员主动确认完成"}
            state["tasks"].append(value)
            result.append(value)
        return {"items": result}
    return db.mutate(save)


class SwapInput(BaseModel):
    task_id: str
    other_task_id: str


@router.post("/swaps")
def swap(body: SwapInput, x_member_id: str = Header(default="m1")):
    def save(state):
        first, other = item(state, "tasks", body.task_id), item(state, "tasks", body.other_task_id)
        if first["owner"] != x_member_id or other["owner"] == x_member_id or first["done"] or other["done"]:
            raise HTTPException(403, "只能用本人未完成任务申请与其他成员互换")
        value = {**body.model_dump(), "id": uid("s"), "requester": x_member_id, "target": other["owner"], "status": "pending"}
        state.setdefault("swaps", []).append(value)
        return value
    return db.mutate(save)


@router.post("/swaps/{identity}/vote")
def swap_vote(identity: str, body: Vote, x_member_id: str = Header(default="m1")):
    def save(state):
        value = item(state, "swaps", identity)
        if value["target"] != x_member_id:
            raise HTTPException(403, "仅交换对象可以审批")
        if value["status"] != "pending":
            raise HTTPException(409, "互换已处理")
        first, other = item(state, "tasks", value["task_id"]), item(state, "tasks", value["other_task_id"])
        if first["owner"] != value["requester"] or other["owner"] != value["target"] or first["done"] or other["done"]:
            raise HTTPException(409, "任务已变化，请重新申请")
        value["status"] = "approved" if body.approve else "rejected"
        if body.approve:
            first["owner"], other["owner"] = other["owner"], first["owner"]
        return value
    return db.mutate(save)


@router.post("/bills/{identity}/settle")
def settle(identity: str, x_member_id: str = Header(default="m1")):
    def save(state):
        value = item(state, "bills", identity)
        if x_member_id not in [s["member_id"] for s in value["shares"]]:
            raise HTTPException(403, "本人不是此账单参与者")
        paid = value.setdefault("settled", [])
        if x_member_id not in paid:
            paid.append(x_member_id)
        return value
    return db.mutate(save)


class Question(BaseModel):
    text: str = Field(min_length=2, max_length=1500)


@router.post("/assistant")
async def assistant(body: Question, x_member_id: str = Header(default="m1")):
    snapshot = sensing.prepare(db.read())
    require_member(snapshot, x_member_id)
    try:
        plan = await engine.plan_tool(snapshot, body.text, x_member_id)
        tools = {
            "covenant": lambda: engine.active_proposal(snapshot),
            "tasks": lambda: snapshot["tasks"],
            "bills": lambda: snapshot["bills"],
        }
        if plan.tool == "complete_task":
            target = item(snapshot, "tasks", plan.record_id)
            if target["owner"] != x_member_id:
                raise HTTPException(403, "模型只能建议更新本人的任务")
            return {"reply": "请确认完成这项任务：" + target["title"], "tool": plan.tool, "confirm_task_id": target["id"], "data": None}
        data = tools[plan.tool]()
        reply = await engine.explain_tool(snapshot, body.text, plan.tool, data)
        return {"reply": reply, "tool": plan.tool, "data": data}
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/tasks/{identity}/complete")
def complete(identity: str, x_member_id: str = Header(default="m1")):
    def save(state):
        target = item(state, "tasks", identity)
        if target["owner"] != x_member_id:
            raise HTTPException(403, "仅任务负责人可确认完成")
        target["done"] = True
        return target
    return db.mutate(save)


@router.post("/negotiations/{identity}/suggest")
async def suggest(identity: str):
    snapshot = db.read()
    negotiation = item(snapshot, "negotiations", identity)
    try:
        output = await engine.negotiation_suggestion(snapshot, negotiation)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    def save(state):
        if state["active_id"] != snapshot["active_id"]:
            raise HTTPException(409, "公约已变化，请重新整理建议")
        value = item(state, "negotiations", identity)
        value["suggestion"] = output.reply
        value["suggestion_source"] = "演示模板" if snapshot["mode"] == "demo" else engine.model_connection.label(snapshot)
        return value
    return db.mutate(save)


class Opinion(BaseModel):
    category: Literal["quiet", "duties", "other"]
    text: str = Field(min_length=2, max_length=1500)


@router.post("/opinions/preview")
async def preview_opinion(body: Opinion):
    try:
        output = await engine.private_reply(db.read(), body.text, "gentle")
        return {"neutral": output, "saved": False}
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc


class OpinionCommit(BaseModel):
    category: Literal["quiet", "duties", "other"]
    neutral: str = Field(min_length=2, max_length=2500)


@router.post("/opinions")
def opinion(body: OpinionCommit, x_member_id: str = Header(default="m1")):
    def save(state):
        require_member(state, x_member_id)
        value = {"id": uid("g"), "title": body.neutral, "category": body.category, "status": "待相关成员讨论", "version": engine.active_proposal(state)["version"] if engine.active_proposal(state) else None, "target": None, "cycle": uid("opinion")}
        state["negotiations"].append(value)
        return value
    return db.mutate(save)
