"""异步任务队列 — Redis BLPOP 轻量队列（不引入 Celery，与现有架构一致）.

流程:
API → ProcessingTask(status=pending) → Redis LPUSH mm:task:queue
Worker (systemd) → BLPOP mm:task:queue → status=processing → 执行 Processor
    → 成功: status=success, 更新 Asset 状态
    → 失败: status=failed, retry_count++, 记录 error
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.redis_client import redis_client
from app.multimodal.repositories import processing_repo
from app.multimodal.constants import TaskStatus

logger = logging.getLogger(__name__)

TASK_QUEUE_KEY = "mm:task:queue"


async def enqueue(task_id: int) -> None:
    """任务入队。"""
    await redis_client.lpush(TASK_QUEUE_KEY, json.dumps({"task_id": task_id}))
    logger.info(f"Multimodal task enqueued: #{task_id}")


async def dequeue(timeout: int = 5) -> Optional[int]:
    """任务出队（Worker 用）。返回 task_id 或 None（超时）。"""
    result = await redis_client.blpop(TASK_QUEUE_KEY, timeout=timeout)
    if result is None:
        return None
    _, value = result
    try:
        return json.loads(value)["task_id"]
    except (json.JSONDecodeError, KeyError):
        logger.warning(f"Invalid queue message: {value}")
        return None


async def create_and_enqueue(db: AsyncSession, asset_id: Optional[int],
                             kb_id: Optional[int], task_type: str,
                             input_data: Optional[dict] = None,
                             model: Optional[str] = None):
    """创建任务记录并入队。"""
    task = await processing_repo.create_task(
        db, asset_id=asset_id, knowledge_base_id=kb_id, task_type=task_type,
        status=TaskStatus.PENDING, input=input_data or {}, model=model)
    await enqueue(task.id)
    return task


async def mark_processing(db: AsyncSession, task_id: int):
    task = await processing_repo.get_task(db, task_id)
    if task:
        return await processing_repo.update_task(
            db, task, status=TaskStatus.PROCESSING, started_at=datetime.now(timezone.utc))
    return task


async def mark_success(db: AsyncSession, task_id: int, output: Optional[dict] = None):
    task = await processing_repo.get_task(db, task_id)
    if task:
        return await processing_repo.update_task(
            db, task, status=TaskStatus.SUCCESS, output=output or {},
            completed_at=datetime.now(timezone.utc))
    return task


async def mark_failed(db: AsyncSession, task_id: int, error: str):
    task = await processing_repo.get_task(db, task_id)
    if task:
        return await processing_repo.update_task(
            db, task, status=TaskStatus.FAILED, error=error[:5000],
            retry_count=task.retry_count + 1,
            completed_at=datetime.now(timezone.utc))
    return task


async def get_queue_depth() -> int:
    """队列中等待任务数。"""
    try:
        return await redis_client.llen(TASK_QUEUE_KEY)
    except Exception:
        return -1
