"""索引服务 — Embedding + 向量索引（mm_index_records）.

被 Worker 调用（index 任务）或审核通过后自动触发。
"""

import logging
from typing import Dict, Any, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.multimodal.adapters import get_embedding_adapter
from app.multimodal.constants import AssetStatus, EmbeddingType, UnitStatus
from app.multimodal.repositories import (asset_repo, knowledge_unit_repo, index_repo)
from app.multimodal.services import storage_service

logger = logging.getLogger(__name__)


async def embed_and_index_unit(db: AsyncSession, unit: Any,
                               image_path: Optional[str] = None) -> bool:
    """单个知识单元 Embedding + 索引。

    策略:
    - 有视觉素材（image/shot/slide 且有缩略图/关键帧）→ 图片 Embedding
    - 纯文本（segment）→ 文本 Embedding
    """
    embedding_adapter = get_embedding_adapter()
    embedding_type = EmbeddingType.MULTIMODAL

    try:
        if image_path:
            abs_path = storage_service.abs_file_path(image_path)
            embedding = await embedding_adapter.embed_image(abs_path)
        elif unit.content:
            # 长文本截断，避免超出 Embedding 模型上下文
            embedding = await embedding_adapter.embed_text(unit.content[:4000])
        else:
            logger.warning(f"Unit {unit.id} has neither image nor content, skip")
            return False
    except RuntimeError as e:
        # DASHSCOPE_API_KEY 未配置等——显式抛出让 Worker 标记任务失败
        raise
    except Exception as e:
        logger.error(f"Embed unit {unit.id} failed: {e}")
        await knowledge_unit_repo.update_unit(db, unit, {"status": UnitStatus.ERROR})
        return False

    # 删除该 unit 的旧记录（重新索引场景）
    from sqlalchemy import delete as sa_delete
    from app.multimodal.models import IndexRecord
    await db.execute(sa_delete(IndexRecord).where(
        IndexRecord.knowledge_unit_id == unit.id))
    await db.flush()

    asset = await asset_repo.get_asset(db, unit.asset_id)
    metadata = {
        "unit_type": unit.unit_type,
        "asset_id": unit.asset_id,
        "file_type": asset.file_type if asset else None,
    }

    await index_repo.create_index_record(
        db, knowledge_base_id=unit.knowledge_base_id, asset_id=unit.asset_id,
        knowledge_unit_id=unit.id, embedding=embedding,
        embedding_type=embedding_type, model_name=embedding_adapter.model_name,
        metadata=metadata)

    await knowledge_unit_repo.update_unit(db, unit, {"status": UnitStatus.INDEXED})
    return True


async def index_asset(db: AsyncSession, asset_id: int) -> Dict[str, Any]:
    """素材全量索引: 全部 KnowledgeUnit → Embedding → IndexRecord → Asset READY."""
    asset = await asset_repo.get_asset(db, asset_id)
    if not asset:
        return {"success": False, "error": f"Asset {asset_id} not found"}

    units = await knowledge_unit_repo.list_units_by_asset(db, asset_id)
    if not units:
        return {"success": False, "error": "素材没有知识单元（先完成 AI 分析）"}

    indexed, failed = 0, 0
    import os
    # 仅图片素材允许回退到原图做图片 Embedding；
    # 其它类型（pdf/文档/音频/ppt）的单元一律走文本 Embedding，
    # 避免把 PDF/PPT 原始文件路径误传给图片 Embedding。
    allow_image_fallback = (asset.file_type == "image")
    for unit in units:
        # 视觉单元优先图片 Embedding
        image_path = unit.thumbnail_path
        if unit.unit_type == "shot":
            shot = await knowledge_unit_repo.get_video_shot_by_unit(db, unit.id)
            image_path = (shot.keyframe_path if shot else None) or unit.thumbnail_path
        # 缩略图/关键帧文件缺失时的回退策略
        if image_path and not os.path.exists(storage_service.abs_file_path(image_path)):
            if allow_image_fallback:
                logger.warning(
                    f"Unit {unit.id} image file missing ({image_path}), "
                    f"falling back to asset original/thumbnail")
                fallback = asset.storage_path or asset.thumbnail_path
                image_path = fallback if (
                    fallback and os.path.exists(storage_service.abs_file_path(fallback))
                ) else None
            else:
                logger.warning(
                    f"Unit {unit.id} image file missing ({image_path}), "
                    f"degrade to text embedding")
                image_path = None
        ok = await embed_and_index_unit(db, unit, image_path)
        indexed += 1 if ok else 0
        failed += 0 if ok else 1

    if indexed == 0:
        await asset_repo.update_asset(db, asset, {"status": AssetStatus.FAILED})
        return {"success": False, "error": f"全部 {failed} 个单元索引失败"}

    await asset_repo.update_asset(db, asset, {"status": AssetStatus.READY})
    return {"success": True, "indexed": indexed, "failed": failed}


async def reindex_kb(db: AsyncSession, kb_id: int) -> Dict[str, Any]:
    """重建整个知识库索引（更换 Embedding 模型后）。"""
    from app.multimodal.repositories import knowledge_base_repo
    await index_repo.delete_index_by_kb(db, kb_id)
    # 找到全部 ready 素材并重新入队
    _, assets = await asset_repo.list_assets(db, kb_id=kb_id, page=1, page_size=10000)
    queued = 0
    from app.multimodal.services.task_queue_service import create_and_enqueue
    for a in assets:
        if a.status == AssetStatus.READY:
            await create_and_enqueue(db, asset_id=a.id, kb_id=kb_id, task_type="index",
                                     input_data={"file_type": a.file_type, "reindex": True})
            queued += 1
    return {"success": True, "queued": queued}
