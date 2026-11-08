"""Shared member lookup with caller-specific HTTP error messages."""
from functools import partial

from fastapi import HTTPException


def require_member(state, member_id, *, detail="成员不存在"):
    person = next((m for m in state["members"] if m["id"] == member_id), None)
    if person is None:
        raise HTTPException(400, detail)
    return person


demo_member = partial(require_member, detail="请选择有效的演示成员身份")
