"""Audit log endpoints: 查询与清理操作日志。

权限：仅 ``audit:view`` 可见（建议只给 superuser / 管理员角色）。
"""

from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.auth.dependencies import require_permission, get_current_user
from app.schemas.audit import AuditLogListItem, AuditLogDetail, AuditLogPage, AuditStats
from app.repositories import audit_repo
from app.core.timeutils import to_local, now as now_tz

router = APIRouter(
    prefix="/audit-logs",
    dependencies=[Depends(require_permission("audit:view"))],
)


def _to_list_item(log) -> AuditLogListItem:
    return AuditLogListItem.model_validate(log)


@router.get("", response_model=AuditLogPage, summary="分页查询操作日志")
async def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None, description="摘要/资源名/用户名/路径模糊搜索"),
    action: Optional[str] = Query(None, description="动作: create/update/delete/login/logout..."),
    resource_type: Optional[str] = Query(None, description="资源类型: asset/agent/user/role/workflow..."),
    username: Optional[str] = Query(None, description="操作人用户名"),
    success: Optional[bool] = Query(None, description="是否成功"),
    request_id: Optional[str] = Query(None, description="按 request_id 精确查询"),
    start_time: Optional[datetime] = Query(None, description="开始时间（本地时间）"),
    end_time: Optional[datetime] = Query(None, description="结束时间（本地时间）"),
    db: AsyncSession = Depends(get_db),
):
    """分页查询操作日志，支持时间/操作人/动作/资源/成功状态/关键词过滤。"""
    items, total = await audit_repo.list_audit_logs(
        db,
        page=page,
        page_size=page_size,
        keyword=keyword,
        action=action,
        resource_type=resource_type,
        username=username,
        success=success,
        request_id=request_id,
        start_time=to_local(start_time),
        end_time=to_local(end_time),
    )
    return AuditLogPage(
        items=[_to_list_item(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/stats/summary", response_model=AuditStats, summary="操作日志统计")
async def get_audit_stats(days: int = Query(30, ge=1, le=365), db: AsyncSession = Depends(get_db)):
    """概览统计：总数 / 成功失败 / 今日 / 动作分布。"""
    total = await audit_repo.count_audit_logs(db)
    today = now_tz().date()
    _, total_today = await audit_repo.list_audit_logs(
        db,
        page=1,
        page_size=1,
        start_time=today,
        end_time=today + _one_day(),
    )
    dist = await audit_repo.action_distribution(db, days=days)
    # 成功/失败计数
    _, success_count = await audit_repo.list_audit_logs(db, page=1, page_size=1, success=True)
    _, failed_count = await audit_repo.list_audit_logs(db, page=1, page_size=1, success=False)
    return AuditStats(
        total=total,
        success_count=success_count,
        failed_count=failed_count,
        today_count=total_today,
        action_distribution=dist,
    )


@router.get("/{log_id}", response_model=AuditLogDetail, summary="操作日志详情")
async def get_audit_log(log_id: int, db: AsyncSession = Depends(get_db)):
    """查看单条日志详情（含请求体与变更 diff）。"""
    log = await audit_repo.get_audit_log(db, log_id)
    if not log:
        raise HTTPException(status_code=404, detail="操作日志不存在")
    return AuditLogDetail.model_validate(log)


@router.get("/by-request/{request_id}", response_model=AuditLogDetail, summary="按 request_id 查日志")
async def get_audit_log_by_request(request_id: str, db: AsyncSession = Depends(get_db)):
    """按 request_id 精确查询一条日志（用于链路串联）。"""
    log = await audit_repo.get_audit_log_by_request_id(db, request_id)
    if not log:
        raise HTTPException(status_code=404, detail="操作日志不存在")
    return AuditLogDetail.model_validate(log)


def _one_day():
    from datetime import timedelta

    return timedelta(days=1)
