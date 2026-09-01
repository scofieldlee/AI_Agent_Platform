"""
Audit service: 落库、脱敏、查询编排、失败降级、非 HTTP 埋点入口。

- :func:`write_audit_entry`：异步落库（独立 session，不阻塞请求）；失败降级写文件。
- :func:`write_audit_fallback`：同步写本地日志文件（logs/audit-fallback.log）。
- :func:`record_audit`：非 HTTP 场景（Worker / 定时任务 / Service 层）的程序化埋点入口。
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from app.core.audit import sanitize_body, build_summary
from app.core.config import settings
from app.core.timeutils import now as now_tz

logger = logging.getLogger(__name__)

# 项目根目录（app/core/../../..）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FALLBACK_LOG_PATH = os.path.join(PROJECT_ROOT, "logs", "audit-fallback.log")

# 允许写入的字段白名单（防止脏数据污染表结构）
_ALLOWED_FIELDS = {
    "request_id", "user_id", "username", "action", "resource_type",
    "resource_id", "resource_name", "summary", "method", "path",
    "status_code", "success", "ip_address", "user_agent",
    "request_body", "changes", "duration_ms", "error_message", "tenant_id",
}


def _prepare_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """清洗字段 + 请求体强制脱敏，返回可入库 dict。"""
    clean: Dict[str, Any] = {}
    for key, value in entry.items():
        if key not in _ALLOWED_FIELDS:
            continue
        if value is None:
            continue
        clean[key] = value

    if "request_id" not in clean:
        # 非 HTTP 场景（Worker/定时任务）无 request_id，自动生成
        clean["request_id"] = uuid.uuid4().hex
    if "request_body" in clean and clean["request_body"] is not None:
        clean["request_body"] = sanitize_body(clean["request_body"])
    if "changes" in clean and clean["changes"] is not None:
        clean["changes"] = sanitize_body(clean["changes"])
    if "created_at" not in clean:
        clean["created_at"] = now_tz()
    if "summary" in clean and clean["summary"] is None and clean.get("action"):
        clean["summary"] = build_summary(
            clean.get("action", ""),
            clean.get("resource_type", ""),
            clean.get("resource_name"),
        )
    return clean


def write_audit_fallback(entry: Dict[str, Any]) -> None:
    """同步降级：把审计条目写入本地日志文件（日志丢失比接口报错更严重）。"""
    try:
        os.makedirs(os.path.dirname(FALLBACK_LOG_PATH), exist_ok=True)
        line = json.dumps(
            _prepare_entry(entry), ensure_ascii=False, default=str
        )
        with open(FALLBACK_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as e:  # noqa: BLE001
        logger.error(f"[audit] fallback write failed: {e}")


async def write_audit_entry(entry: Dict[str, Any]) -> bool:
    """异步落库（独立 session，与请求 session 生命周期解耦）。

    失败时降级写本地文件，绝不抛错影响业务。
    """
    try:
        from app.database.session import async_session_factory
        from app.models.audit_log import AuditLog

        clean = _prepare_entry(entry)
        async with async_session_factory() as db:
            db.add(AuditLog(**clean))
            await db.commit()
        return True
    except Exception as e:  # noqa: BLE001
        logger.error(f"[audit] async write failed, falling back to file: {e}")
        write_audit_fallback(entry)
        return False


async def record_audit(
    *,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    resource_name: Optional[str] = None,
    summary: Optional[str] = None,
    changes: Optional[Dict[str, Any]] = None,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    request_id: Optional[str] = None,
    **extra: Any,
) -> bool:
    """非 HTTP 场景的程序化埋点入口（Worker / 定时任务 / Service 层）。

    用法::

        await record_audit(
            action="execute", resource_type="task",
            resource_id=str(task_id), summary="定时任务执行完成",
        )
    """
    entry: Dict[str, Any] = {
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "resource_name": resource_name,
        "summary": summary,
        "changes": changes,
        "user_id": user_id,
        "username": username,
        "request_id": request_id,
        "success": True,
        **extra,
    }
    return await write_audit_entry(entry)
