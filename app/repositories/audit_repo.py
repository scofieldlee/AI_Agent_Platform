"""
Audit repository: data access for audit_logs.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from sqlalchemy import select, func, desc, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


async def list_audit_logs(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    username: Optional[str] = None,
    user_id: Optional[int] = None,
    success: Optional[bool] = None,
    request_id: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> tuple[List[AuditLog], int]:
    """分页查询审计日志，返回 (items, total)。"""
    conditions = []
    if keyword:
        like = f"%{keyword}%"
        conditions.append(
            (AuditLog.summary.ilike(like))
            | (AuditLog.resource_name.ilike(like))
            | (AuditLog.username.ilike(like))
            | (AuditLog.path.ilike(like))
        )
    if action:
        conditions.append(AuditLog.action == action)
    if resource_type:
        conditions.append(AuditLog.resource_type == resource_type)
    if username:
        conditions.append(AuditLog.username == username)
    if user_id is not None:
        conditions.append(AuditLog.user_id == user_id)
    if success is not None:
        conditions.append(AuditLog.success == success)
    if request_id:
        conditions.append(AuditLog.request_id == request_id)
    if start_time is not None:
        conditions.append(AuditLog.created_at >= start_time)
    if end_time is not None:
        conditions.append(AuditLog.created_at <= end_time)

    base = select(AuditLog)
    if conditions:
        base = base.where(*conditions)

    total_result = await db.execute(
        select(func.count()).select_from(base.subquery())
    )
    total = total_result.scalar() or 0

    result = await db.execute(
        base.order_by(desc(AuditLog.created_at), desc(AuditLog.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), total


async def get_audit_log(db: AsyncSession, log_id: int) -> Optional[AuditLog]:
    """按主键取单条日志。"""
    result = await db.execute(select(AuditLog).where(AuditLog.id == log_id))
    return result.scalar_one_or_none()


async def get_audit_log_by_request_id(db: AsyncSession, request_id: str) -> Optional[AuditLog]:
    """按 request_id 取单条日志。"""
    result = await db.execute(
        select(AuditLog).where(AuditLog.request_id == request_id).order_by(desc(AuditLog.id)).limit(1)
    )
    return result.scalar_one_or_none()


async def count_audit_logs(db: AsyncSession) -> int:
    """日志总数。"""
    result = await db.execute(select(func.count(AuditLog.id)))
    return result.scalar() or 0


async def action_distribution(db: AsyncSession, days: int = 30) -> Dict[str, int]:
    """近 N 天动作分布。"""
    since = datetime.now().astimezone() - timedelta(days=days)
    result = await db.execute(
        select(AuditLog.action, func.count(AuditLog.id))
        .where(AuditLog.created_at >= since)
        .group_by(AuditLog.action)
    )
    return {action or "unknown": count for action, count in result.fetchall()}


async def delete_older_than(db: AsyncSession, days: int) -> int:
    """删除超过保留期的日志，返回删除条数。"""
    cutoff = datetime.now().astimezone() - timedelta(days=days)
    result = await db.execute(
        delete(AuditLog).where(AuditLog.created_at < cutoff)
    )
    await db.commit()
    return result.rowcount or 0
