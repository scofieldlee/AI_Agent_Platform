"""异步任务 Worker 主循环（systemd 守护: ai-agent-multimodal-worker）.

启动: python -m app.multimodal.workers.task_worker
流程: BLPOP mm:task:queue → mark_processing → 按 task_type 分发 → success/failed
失败重试: retry_count < 3 时自动重新入队。
"""

import asyncio
import logging
import signal
from typing import Optional

from app.database.session import async_session_factory
import app.models  # noqa: F401  # 确保 User 等业务表进入 Base.metadata（mm_asset_tags.created_by 外键解析）
from app.multimodal.constants import TaskStatus, TaskType, FileType
from app.multimodal.services import task_queue_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("mm.worker")

# 优雅退出
_shutdown = asyncio.Event()

MAX_RETRY = 3


async def execute_task(task_id: int) -> None:
    """执行单个任务。"""
    async with async_session_factory() as db:
        try:
            task = await task_queue_service.mark_processing(db, task_id)
            if not task:
                logger.warning(f"Task {task_id} not found, skip")
                return
            await db.commit()

            task_type = task.task_type
            asset_id = task.asset_id
            input_data = task.input or {}

            # ---- 分发 ----
            output = None
            if task_type == TaskType.ANALYSIS:
                from app.multimodal.services import analysis_service
                file_type = input_data.get("file_type") or await _get_file_type(db, asset_id)
                output = await analysis_service.analyze_asset_dispatch(db, asset_id, file_type)

            elif task_type == TaskType.INDEX:
                from app.multimodal.services import index_service
                output = await index_service.index_asset(db, asset_id)

            else:
                output = {"success": False, "error": f"未知任务类型: {task_type}"}

            # ---- 结果 ----
            if isinstance(output, dict) and output.get("success") is False:
                error = output.get("error", "unknown error")
                task = await task_queue_service.mark_failed(db, task_id, error)
                await db.commit()
                logger.error(f"Task {task_id} ({task_type}) failed: {error}")
                # 失败重试；重试耗尽则回退素材状态，避免永久锁死
                if task and task.retry_count < MAX_RETRY:
                    await _retry_later(task_id)
                else:
                    await _abandon_asset(db, task_id)
            else:
                await task_queue_service.mark_success(db, task_id, output or {})
                await db.commit()
                logger.info(f"Task {task_id} ({task_type}) success: "
                            f"{str(output)[:200]}")

        except Exception as e:
            logger.error(f"Task {task_id} crashed: {e}", exc_info=True)
            try:
                # 崩溃后 session 可能处于失败状态，先回滚再标记失败
                await db.rollback()
                await task_queue_service.mark_failed(db, task_id, f"{type(e).__name__}: {e}")
                await db.commit()
                # 查询 retry 信息决定是否重试
                from app.multimodal.repositories import processing_repo
                t = await processing_repo.get_task(db, task_id)
                if t and t.retry_count <= MAX_RETRY:
                    await _retry_later(task_id)
                else:
                    await _abandon_asset(db, task_id)
            except Exception as retry_err:
                logger.error(f"Task {task_id} mark_failed also failed: {retry_err}")


async def _retry_later(task_id: int, delay_key: str = "retry") -> None:
    """失败任务重新入队。"""
    await task_queue_service.enqueue(task_id)
    logger.info(f"Task {task_id} re-enqueued for retry")


async def _abandon_asset(db, task_id: int) -> None:
    """任务重试耗尽后回退素材状态。

    ⚠️ 历史坑位：素材在进入分析/索引前会被置为 `analyzing` / `indexing`，
    若任务最终失败且未回退，素材会永久卡在中间态，造成两个后果：
      1. 前端一直显示"处理中"，看不到失败原因
      2. `trigger_analysis` 判定 status in (processing, analyzing) → 返回
         409「素材正在处理中，请稍候」→ 用户再也点不动"重新分析"

    这里的回退策略：
      - 分析任务失败 → FAILED（需重新上传或人工排查后重跑）
      - 索引任务失败 → 退回 REVIEW_REQUIRED（分析结果仍在，可重新索引/审核）
      - 仅当素材当前确实处于对应的中间态时才回退，不覆盖其它状态
    """
    from app.multimodal.repositories import processing_repo, asset_repo
    from app.multimodal.constants import AssetStatus, TaskType

    try:
        task = await processing_repo.get_task(db, task_id)
        if not task or not task.asset_id:
            return
        asset = await asset_repo.get_asset(db, task.asset_id)
        if not asset:
            return

        if task.task_type == TaskType.INDEX:
            if asset.status != AssetStatus.INDEXING:
                return
            target = AssetStatus.REVIEW_REQUIRED
        else:
            if asset.status not in (AssetStatus.ANALYZING, AssetStatus.PROCESSING):
                return
            target = AssetStatus.FAILED

        await asset_repo.update_asset(db, asset, {"status": target})
        await db.commit()
        logger.warning(
            f"Task {task_id} exhausted retries, asset #{asset.id} "
            f"{asset.status} -> {target}")
    except Exception as e:
        logger.error(f"Failed to roll back asset status for task {task_id}: {e}")


async def _get_file_type(db, asset_id: Optional[int]) -> Optional[str]:
    if not asset_id:
        return None
    from app.multimodal.repositories import asset_repo
    asset = await asset_repo.get_asset(db, asset_id)
    return asset.file_type if asset else None


async def recover_orphan_tasks() -> int:
    """启动时恢复中断任务（status=processing 的改回 pending 并入队）。"""
    from sqlalchemy import select, update
    from app.multimodal.models import ProcessingTask
    from app.multimodal.constants import TaskStatus as TS
    async with async_session_factory() as db:
        result = await db.execute(
            select(ProcessingTask).where(ProcessingTask.status == TS.PROCESSING))
        orphans = list(result.scalars().all())
        for t in orphans:
            t.status = TS.PENDING
        await db.commit()
        for t in orphans:
            await task_queue_service.enqueue(t.id)
    if orphans:
        logger.info(f"Recovered {len(orphans)} orphan tasks")
    return len(orphans)


async def recover_stuck_assets() -> int:
    """启动时回收卡死的素材状态（Worker 被 kill / 崩溃重启的善后）。

    素材进入分析/索引前被置为 analyzing / processing / indexing。若 Worker 在任务
    完成前被杀掉，且该素材已无 pending/processing 的任务，状态就永远不会变化：
    前端显示"处理中"，重新触发又被 409 拦下。这里按"最终失败"规则回退，
    让用户能立刻点"重新分析"。
    """
    from sqlalchemy import select
    from app.multimodal.models import MultimodalAsset, ProcessingTask
    from app.multimodal.constants import AssetStatus, TaskStatus

    in_flight = [AssetStatus.PROCESSING, AssetStatus.ANALYZING, AssetStatus.INDEXING]
    fixed = 0
    async with async_session_factory() as db:
        result = await db.execute(
            select(MultimodalAsset).where(MultimodalAsset.status.in_(in_flight)))
        stuck = list(result.scalars().all())
        for a in stuck:
            active = (await db.execute(
                select(ProcessingTask.id).where(
                    ProcessingTask.asset_id == a.id,
                    ProcessingTask.status.in_(
                        [TaskStatus.PENDING, TaskStatus.PROCESSING])))).first()
            if active:  # 仍有未完成任务，交给任务流程处理
                continue
            a.status = (AssetStatus.REVIEW_REQUIRED
                        if a.status == AssetStatus.INDEXING else AssetStatus.FAILED)
            fixed += 1
        if fixed:
            await db.commit()
            logger.info(f"Recovered {fixed} stuck assets -> failed/review_required")
    return fixed


async def main():
    """Worker 主循环。"""
    logger.info("Multimodal worker starting...")
    await recover_orphan_tasks()
    await recover_stuck_assets()

    while not _shutdown.is_set():
        try:
            task_id = await task_queue_service.dequeue(timeout=5)
        except Exception as e:
            logger.error(f"Queue dequeue error: {e}")
            await asyncio.sleep(5)
            continue

        if task_id is None:
            continue

        logger.info(f"Processing task #{task_id}")
        try:
            await execute_task(task_id)
        except Exception as e:
            # execute_task 内部已兜底，此处双保险
            logger.error(f"Unhandled task error #{task_id}: {e}", exc_info=True)


def _handle_signal(sig, frame):
    logger.info(f"Received signal {sig}, shutting down...")
    _shutdown.set()


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    asyncio.run(main())
