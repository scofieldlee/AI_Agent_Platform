"""人工审核服务 — AI 分析完成后的人工确认流程.

REVIEW_REQUIRED → 用户修正（metadata/标签）→ approve → 自动入队索引 → READY
"""

import logging
from typing import Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.multimodal.constants import AssetStatus, TagSource
from app.multimodal.repositories import asset_repo
from app.multimodal.services.task_queue_service import create_and_enqueue

logger = logging.getLogger(__name__)


async def update_user_metadata(db: AsyncSession, asset_id: int,
                               metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """更新用户 metadata（category/usage/copyright/remark 等）。"""
    asset = await asset_repo.get_asset(db, asset_id)
    if not asset:
        return None
    await asset_repo.upsert_metadata(db, asset_id, "user", metadata)
    return await asset_repo.get_all_metadata(db, asset_id)


async def approve_asset(db: AsyncSession, asset_id: int,
                        user_metadata: Optional[dict] = None,
                        user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """审核通过 → 覆盖 user metadata（可选）→ 入队索引任务。"""
    asset = await asset_repo.get_asset(db, asset_id)
    if not asset:
        return None
    if asset.status != AssetStatus.REVIEW_REQUIRED:
        return {"error": f"当前状态 {asset.status} 不可审核（需 review_required）"}

    if user_metadata:
        await asset_repo.upsert_metadata(db, asset_id, "user", user_metadata)

    await asset_repo.update_asset(db, asset, {"status": AssetStatus.INDEXING})
    task = await create_and_enqueue(
        db, asset_id=asset_id, kb_id=asset.knowledge_base_id,
        task_type="index", input_data={"approved_by": user_id})
    return {"asset_id": asset_id, "status": AssetStatus.INDEXING, "task_id": task.id}


async def update_user_tags_after_review(db: AsyncSession, asset_id: int,
                                        add_tags: list = None,
                                        remove_tag_ids: list = None,
                                        user_id: Optional[int] = None) -> None:
    """审核过程中的标签修正：增用户标签 / 删标签（含 AI 标签）。"""
    if add_tags:
        for name in add_tags:
            tag = await asset_repo.get_or_create_tag(db, name, TagSource.USER, user_id)
            await asset_repo.add_tag_to_asset(db, asset_id, tag.id, TagSource.USER)
    if remove_tag_ids:
        for tag_id in remove_tag_ids:
            await asset_repo.remove_tag_from_asset(db, asset_id, tag_id)
