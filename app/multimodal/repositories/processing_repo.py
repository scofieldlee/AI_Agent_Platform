"""处理任务 Repository."""

from typing import Optional, List
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.multimodal.models import ProcessingTask
from app.multimodal.constants import TaskStatus


async def get_task(db: AsyncSession, task_id: int) -> Optional[ProcessingTask]:
    return await db.get(ProcessingTask, task_id)


async def create_task(db: AsyncSession, **kwargs) -> ProcessingTask:
    task = ProcessingTask(**kwargs)
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return task


async def update_task(db: AsyncSession, task: ProcessingTask, **kwargs) -> ProcessingTask:
    for field in ("status", "model", "output", "error", "retry_count",
                  "started_at", "completed_at"):
        if field in kwargs and kwargs[field] is not None:
            setattr(task, field, kwargs[field])
    await db.flush()
    await db.refresh(task)
    return task


async def list_tasks(db: AsyncSession, asset_id: Optional[int] = None,
                     kb_id: Optional[int] = None,
                     task_type: Optional[str] = None,
                     status: Optional[str] = None,
                     page: int = 1, page_size: int = 20) -> tuple:
    """任务列表（分页）。"""
    conditions = []
    if asset_id:
        conditions.append(ProcessingTask.asset_id == asset_id)
    if kb_id:
        conditions.append(ProcessingTask.knowledge_base_id == kb_id)
    if task_type:
        conditions.append(ProcessingTask.task_type == task_type)
    if status:
        conditions.append(ProcessingTask.status == status)

    stmt = select(ProcessingTask)
    if conditions:
        from sqlalchemy import and_
        stmt = stmt.where(and_(*conditions))

    total = (await db.execute(
        select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    result = await db.execute(
        stmt.order_by(ProcessingTask.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size))
    return total, list(result.scalars().all())


async def get_asset_processing_summary(db: AsyncSession, asset_id: int) -> dict:
    """素材处理任务状态汇总 {success: n, failed: n, ...}."""
    rows = await db.execute(
        select(ProcessingTask.status, func.count(ProcessingTask.id))
        .where(ProcessingTask.asset_id == asset_id)
        .group_by(ProcessingTask.status))
    return {row[0]: row[1] for row in rows.all()}


async def find_retryable_failed_tasks(db: AsyncSession, limit: int = 20) -> List[ProcessingTask]:
    """查找可重试的失败任务（retry_count < 3）。"""
    result = await db.execute(
        select(ProcessingTask)
        .where(ProcessingTask.status == TaskStatus.FAILED,
               ProcessingTask.retry_count < 3)
        .order_by(ProcessingTask.created_at.asc()).limit(limit))
    return list(result.scalars().all())
