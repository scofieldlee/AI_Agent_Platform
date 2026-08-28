"""响应时区中间件 — 把接口输出里的时间统一换算成系统时区（默认北京时间）。

为什么需要它
------------
数据库列是 ``timestamptz``，存的是正确瞬时值；但 asyncpg 读回的 datetime 一律带
UTC 时区，Pydantic 序列化后变成 ``2026-08-28T18:38:36.031102Z``。
前端（处理任务列表、素材详情等）直接截断字符串显示，于是界面上比北京时间慢 8 小时。

与其逐个 schema 加序列化器，不如在 HTTP 出口做一次统一改写，
这样「有 response_model 的接口」和「直接返回 dict 的接口」都被覆盖。

改写规则
--------
只匹配 **完整的 JSON 字符串值** 且内容是 ISO-8601 时间、并带 **UTC 标识**
（``Z`` / ``+00:00`` / ``+0000``）的条目，换算到系统时区后输出为
不带偏移的本地墙钟时间 ``2026-08-29T02:38:36.031102``。

- 因为正则要求从 ``"`` 开始到 ``"`` 结束，不会命中嵌入在长文本里的时间片段。
- 只处理 UTC 标识，已经是本地时间（``+08:00``）或其它偏移的不会被二次换算。
- 日期（``2026-08-29``）不含 ``T``，不受影响。
- 流式响应（SSE / 文件下载，无 content-length）直接放行，不做缓冲。
"""

from __future__ import annotations

import re
from datetime import datetime

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.timeutils import APP_TZ

__all__ = ["LocalTimezoneMiddleware", "rewrite_iso_datetimes"]

# 完整 JSON 字符串值 + ISO-8601 时间 + UTC 标识
_UTC_ISO_RE = re.compile(
    rb'"(\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:[Zz]|[+-]00:?00))"'
)


def _to_local_iso(raw: bytes) -> bytes:
    """把 UTC 时间字符串换算为系统时区的本地时间字符串。"""
    text = raw.decode("utf-8", errors="ignore")
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        return raw
    if dt.tzinfo is None:
        # 无偏移的按 UTC 解释（Pydantic 不会这么输出，防御性处理）
        dt = dt.replace(tzinfo=APP_TZ)
    local = dt.astimezone(APP_TZ).replace(tzinfo=None)
    return local.isoformat().encode("utf-8")


def rewrite_iso_datetimes(body: bytes) -> bytes:
    """批量改写 JSON 响应体中的 UTC 时间字符串。"""
    if b"T" not in body and b"t" not in body:
        return body
    return _UTC_ISO_RE.sub(lambda m: b'"' + _to_local_iso(m.group(1)) + b'"', body)


class LocalTimezoneMiddleware:
    """纯 ASGI 中间件：改写非流式 JSON 响应中的时间为系统时区。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        state: dict = {"eligible": False, "start": None, "body": bytearray()}

        async def send_wrapper(message: Message) -> None:
            mtype = message["type"]

            if mtype == "http.response.start":
                headers = {
                    k.decode("latin-1").lower(): v.decode("latin-1")
                    for k, v in message.get("headers", [])
                }
                content_type = headers.get("content-type", "")
                try:
                    length = int(headers.get("content-length", "0"))
                except (TypeError, ValueError):
                    length = 0
                # 仅处理：JSON + 非流式（有 content-length）+ 非空
                state["eligible"] = (
                    "application/json" in content_type and length > 0
                )
                if state["eligible"]:
                    state["start"] = message
                else:
                    await send(message)
                return

            if mtype == "http.response.body":
                if not state["eligible"]:
                    await send(message)
                    return

                state["body"].extend(message.get("body", b"") or b"")
                if message.get("more_body"):
                    return

                new_body = rewrite_iso_datetimes(bytes(state["body"]))
                if new_body != bytes(state["body"]):
                    start = state["start"]
                    start["headers"] = [
                        (k, v)
                        for k, v in start.get("headers", [])
                        if k.decode("latin-1").lower() != "content-length"
                    ] + [(b"content-length", str(len(new_body)).encode("latin-1"))]
                await send(state["start"])
                await send({
                    "type": "http.response.body",
                    "body": new_body,
                    "more_body": False,
                })
                return

            await send(message)

        await self.app(scope, receive, send_wrapper)
