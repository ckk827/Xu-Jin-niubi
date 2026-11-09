"""Host-side model configuration; secrets never enter the shared room state."""
from __future__ import annotations

import ipaddress
import sqlite3
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, Field, SecretStr, field_validator
from typing import Literal
import storage as db


class SettingsInput(BaseModel):
    mode: Literal["demo", "ollama", "external"]
    model: str = Field(min_length=1, max_length=100)
    api_base_url: str = Field(default="", max_length=2000)
    api_key: SecretStr | None = None

    @field_validator("model")
    @classmethod
    def nonempty_model(cls, value):
        if not value.strip():
            raise ValueError("请填写模型名称")
        if value.strip().lower().startswith(("https://", "http://")):
            raise ValueError("模型名称应填写服务商提供的模型 ID，不能填写网址；网址请填入 API 地址")
        return value.strip()


def normalize_base(value):
    value = value.strip().rstrip("/")
    parts = urlsplit(value)
    _ = parts.port  # Reject malformed ports before attempting any network request.
    if not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("API 地址须包含主机名，不能包含密钥、账号、查询参数或片段")
    try:
        local = parts.hostname == "localhost" or ipaddress.ip_address(parts.hostname).is_loopback
    except ValueError:
        local = False
    if parts.scheme != "https" and not (parts.scheme == "http" and local):
        raise ValueError("外部 API 必须使用 HTTPS；本机调试可使用 HTTP")
    # Accept either the provider's base URL or its complete chat endpoint.
    path = parts.path.rstrip("/")
    if path.endswith("/chat/completions"):
        path = path[:-len("/chat/completions")]
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _credentials():
    # Separate from app_state, room exports and normal database backups.
    path = db.DB_PATH.with_suffix(".model-credentials.sqlite3")
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.execute("CREATE TABLE IF NOT EXISTS credentials (endpoint TEXT PRIMARY KEY, secret TEXT NOT NULL)")
    return conn


def saved_key(base):
    path = db.DB_PATH.with_suffix(".model-credentials.sqlite3")
    if not path.exists():
        return ""
    with db.LOCK:
        conn = _credentials()
        try:
            row = conn.execute("SELECT secret FROM credentials WHERE endpoint=?", (base,)).fetchone()
            return row[0] if row else ""
        finally:
            conn.close()


def connection_values(body):
    if body.mode != "external":
        return "", ""
    base = normalize_base(body.api_base_url)
    key = body.api_key.get_secret_value().strip() if body.api_key else ""
    key = key or saved_key(base)
    if not key:
        raise ValueError("请填写 API Key；留空仅能保留该地址已保存的密钥")
    if any(ord(char) < 33 or ord(char) > 126 for char in key):
        raise ValueError("API Key 不能包含空白或非 ASCII 字符")
    return base, key


def save(body):
    base, key = connection_values(body)
    with db.LOCK:
        if body.mode == "external":
            conn = _credentials()
            try:
                with conn:
                    conn.execute("INSERT OR REPLACE INTO credentials VALUES(?,?)", (base, key))
            finally:
                conn.close()
        def change(state):
            state.update(mode=body.mode, model=body.model, model_configured=True,
                         model_connection_revision=state.get("model_connection_revision", 0) + 1)
            if body.mode == "external":
                state["api_base_url"] = base
            state["analysis"] = None
            db.trace(state, "模型连接已保存", label(state) + "；调用失败会报告错误")
        db.mutate(change)


def label(state):
    return {"demo": "演示模拟", "ollama": "Ollama", "external": "外部 API",
            "unconfigured": "尚未选择模型"}.get(state["mode"], "尚未选择模型")
