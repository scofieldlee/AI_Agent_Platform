"""审计 ASGI 中间件 — 操作日志的"保底采集"层。

设计（与 docs/操作日志方案设计.md 对齐）
---------------------------------------
- 纯 ASGI，与 ``LocalTimezoneMiddleware`` 同机制；只缓冲需要采集的请求体，
  响应体不缓冲（不破坏流式响应/文件下载）。
- 采集范围：
  * POST / PUT / PATCH / DELETE 全部记录；
  * GET 仅白名单（登录/权限查询/监控/素材下载等敏感读），否则不记录避免灌爆表；
  * 排除：健康检查、/docs、/openapi.json、静态文件、多模态文件服务。
- 每个请求生成 request_id 写入 contextvars（应用日志/Agent trace 可串联）；
  从 JWT 中解析当前用户写入 contextvars（供 @audit 装饰器 / Service 使用）。
- 响应结束时：把基础信息 + @audit 装饰器写入的富化信息合并，
  通过 ``asyncio.create_task`` 异步落库，失败降级写本地日志文件（logs/audit-fallback.log）。
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Optional

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.audit import sanitize_body
from app.core.config import settings
from app.core.request_context import (
    audit_enrichment_var,
    current_user_var,
    current_username_var,
    request_id_var,
)
from app.services import audit_service

logger = logging.getLogger(__name__)

__all__ = ["AuditMiddleware"]

# 请求体最大采集字节数（防超大 body 拖垮内存/性能）
_MAX_BODY_BYTES = 512 * 1024  # 512KB

# 不做采集的路径（前缀匹配）
_EXCLUDED_PREFIXES = (
    "/api/v1/health",
    "/api/v1/monitoring/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/static",
    "/chat",
    "/api/v1/multimodal/files/",  # 素材预览/缩略图文件服务
    "/favicon",
)

# 写方法
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _build_get_whitelist() -> tuple:
    """解析配置的 GET 白名单（逗号分隔前缀）。"""
    raw = (settings.audit_get_whitelist or "").strip()
    return tuple(p.strip() for p in raw.split(",") if p.strip())


def _should_record(method: str, path: str) -> bool:
    """判断该请求是否需要记录。"""
    if path.startswith(_EXCLUDED_PREFIXES):
        return False
    if method in _WRITE_METHODS:
        return True
    if method == "GET":
        return path.startswith(_build_get_whitelist())
    # OPTIONS / HEAD / TRACE 等不记录
    return False


def _client_ip(scope: Scope, headers: dict) -> Optional[str]:
    """优先取 X-Forwarded-For / X-Real-IP，回退到 ASGI client。"""
    fwd = headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()[:45]
    real = headers.get("x-real-ip")
    if real:
        return real.strip()[:45]
    client = scope.get("client")
    if client:
        return str(client[0])[:45]
    return None


def _extract_user(auth_header: str) -> tuple[Optional[int], Optional[str]]:
    """从 Authorization Bearer JWT 解析 user_id / username（不查库）。

    解析失败返回 (None, None)，匿名接口/无效 token 时日志里 user 为空。
    """
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return None, None
    token = auth_header.split(" ", 1)[1].strip()
    try:
        from app.auth.service import decode_token

        payload = decode_token(token)
        if not payload:
            return None, None
        uid = payload.get("sub")
        if uid is None:
            return None, None
        return int(uid), str(payload.get("username") or "")
    except Exception:  # noqa: BLE001
        return None, None


async def _read_json_body(receive: Receive) -> Optional[dict]:
    """读取并解析 JSON 请求体（超过上限或非 JSON 返回 None）。"""
    chunks: list[bytes] = []
    total = 0
    more = True
    while more:
        message = await receive()
        if message["type"] != "http.request":
            continue
        body = message.get("body", b"") or b""
        chunks.append(body)
        total += len(body)
        more = message.get("more_body", False)
        if total > _MAX_BODY_BYTES:
            return None
    raw = b"".join(chunks)
    if not raw:
        return None
    try:
        import json

        data = json.loads(raw)
        return data if isinstance(data, dict) else {"_body": data}
    except Exception:  # noqa: BLE001 非 JSON / 解析失败 → 不记录 body
        return None


class AuditMiddleware:
    """纯 ASGI 审计中间件。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http" or not settings.audit_enabled:
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        path = scope.get("path", "")
        if not _should_record(method, path):
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex
        rid_token = request_id_var.set(request_id)

        try:
            headers = {
                k.decode("latin-1").lower(): v.decode("latin-1")
                for k, v in scope.get("headers", [])
            }
        except Exception:  # noqa: BLE001
            headers = {}

        user_id, username = _extract_user(headers.get("authorization", ""))
        uid_token = current_user_var.set(user_id)
        uname_token = current_username_var.set(username)

        content_type = headers.get("content-type", "")
        want_body = settings.audit_store_request_body and (
            "application/json" in content_type or "multipart/form-data" in content_type
        )
        request_body: Optional[dict] = None
        buffered: Optional[bytearray] = bytearray() if want_body else None

        async def receive_wrapper() -> Message:
            message = await receive()
            if buffered is not None and message["type"] == "http.request":
                buffered.extend(message.get("body", b"") or b"")
            return message

        start = time.perf_counter()
        status_code: int = 500
        state: dict = {"status_set": False}

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 500)
                state["status_set"] = True
            await send(message)

        try:
            await self.app(scope, receive_wrapper if buffered is not None else receive, send_wrapper)
        except Exception:
            if not state["status_set"]:
                status_code = 500
            raise
        finally:
            duration_ms = int((time.perf_counter() - start) * 1000)

            if buffered is not None and len(buffered) <= _MAX_BODY_BYTES:
                request_body = await _read_json_body_from_bytes(bytes(buffered))

            # 合并 @audit 装饰器写入的富化信息
            enrichment = audit_enrichment_var.get() or {}

            entry = {
                "request_id": request_id,
                "user_id": user_id,
                "username": username,
                "method": method,
                "path": path,
                "status_code": status_code,
                "success": status_code < 400,
                "ip_address": _client_ip(scope, headers),
                "user_agent": (headers.get("user-agent") or "")[:500],
                "duration_ms": duration_ms,
                "action": enrichment.get("action"),
                "resource_type": enrichment.get("resource_type"),
                "resource_id": enrichment.get("resource_id"),
                "resource_name": enrichment.get("resource_name"),
                "summary": enrichment.get("summary"),
                "changes": enrichment.get("changes") or None,
            }

            # 装饰器显式覆盖 username（如登录场景，请求尚无 Authorization 头）
            if enrichment.get("username"):
                entry["username"] = enrichment["username"]

            # 请求体脱敏后入库（仅 JSON / multipart 表单场景）
            if request_body is not None:
                entry["request_body"] = sanitize_body(request_body)
                # 失败操作无装饰器富化时，从请求体补身份（如登录失败的尝试用户名）
                if entry["username"] is None and isinstance(request_body, dict):
                    body_user = request_body.get("username")
                    if body_user:
                        entry["username"] = str(body_user)[:100]

            if not state["status_set"]:
                entry["error_message"] = "response did not complete (client disconnected or exception)"

            # 异步落库 + 失败降级
            try:
                asyncio.create_task(audit_service.write_audit_entry(entry))
            except RuntimeError:
                # 事件循环已关闭（如测试/关闭场景）→ 同步降级写文件
                audit_service.write_audit_fallback(entry)

            request_id_var.reset(rid_token)
            current_user_var.reset(uid_token)
            current_username_var.reset(uname_token)


async def _read_json_body_from_bytes(raw: bytes) -> Optional[dict]:
    """从已缓冲的字节解析 JSON body（供响应结束后使用）。"""
    if not raw:
        return None
    try:
        import json

        data = json.loads(raw)
        return data if isinstance(data, dict) else {"_body": data}
    except Exception:  # noqa: BLE001
        return None
