"""请求级上下文（contextvars）。

让审计日志、应用日志、Agent trace 能串联同一个 request_id，
并在不传递参数的场景下拿到当前用户信息（供 Service 层/装饰器使用）。

用法
----
- 中间件在请求进入时设置 ``request_id_var`` / ``current_user_var``；
- 装饰器 / 业务代码通过 :func:`get_request_id` / :func:`get_current_audit_user`
  读取，无需显式传参；
- 请求结束后自动还原（contextvars 随 asyncio task 隔离，无需手动清理）。
"""

from __future__ import annotations

import contextvars
from typing import Optional

__all__ = [
    "request_id_var",
    "current_user_var",
    "current_username_var",
    "audit_enrichment_var",
    "get_request_id",
    "get_current_audit_user",
    "get_current_audit_username",
]

# 当前请求的唯一 ID（默认 "-" 表示非 HTTP 上下文，如 Worker/定时任务）
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)
# 当前请求的操作人（可空：匿名接口 / 未认证）
current_user_var: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar(
    "current_user_id", default=None
)
# 当前请求的操作人姓名快照
current_username_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_username", default=None
)
# @audit 装饰器写入的业务语义富化信息，由审计中间件在响应结束时合并落库
audit_enrichment_var: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar(
    "audit_enrichment", default=None
)


def get_request_id() -> str:
    """当前请求的 request_id（非 HTTP 上下文返回 "-"）。"""
    return request_id_var.get()


def get_current_audit_user() -> Optional[int]:
    """当前请求的操作人 ID（可空）。"""
    return current_user_var.get()


def get_current_audit_username() -> Optional[str]:
    """当前请求的操作人用户名快照（可空）。"""
    return current_username_var.get()
