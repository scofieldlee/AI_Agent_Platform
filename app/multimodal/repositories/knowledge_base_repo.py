"""多模态知识库 Repository."""

from typing import Optional, List, Dict, Any
from sqlalchemy import select, func, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.multimodal.models import (
    MultimodalKnowledgeBase, MultimodalAsset,
    AssetMetadata, KnowledgeUnit, IndexRecord,
)
from app.multimodal.constants import AssetStatus


async def get_kb(db: AsyncSession, kb_id: int) -> Optional[MultimodalKnowledgeBase]:
    return await db.get(MultimodalKnowledgeBase, kb_id)


async def get_kb_by_code(db: AsyncSession, code: str) -> Optional[MultimodalKnowledgeBase]:
    result = await db.execute(
        select(MultimodalKnowledgeBase).where(MultimodalKnowledgeBase.code == code))
    return result.scalars().first()


async def generate_kb_code(db: AsyncSession, name: str) -> str:
    """自动生成知识库 code: mkb_{slug}_{random}。"""
    import uuid
    slug = "".join(c if c.isalnum() else "-" for c in name.lower())[:30].strip("-") or "kb"
    return f"mkb_{slug}_{uuid.uuid4().hex[:6]}"


async def list_kbs(db: AsyncSession, include_archived: bool = False) -> List[MultimodalKnowledgeBase]:
    stmt = select(MultimodalKnowledgeBase).order_by(MultimodalKnowledgeBase.created_at.desc())
    if not include_archived:
        stmt = stmt.where(MultimodalKnowledgeBase.status == "active")
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def create_kb(db: AsyncSession, **kwargs) -> MultimodalKnowledgeBase:
    if not kwargs.get("code"):
        kwargs["code"] = await generate_kb_code(db, kwargs.get("name", ""))
    kb = MultimodalKnowledgeBase(**kwargs)
    db.add(kb)
    await db.flush()
    await db.refresh(kb)
    return kb


async def update_kb(db: AsyncSession, kb: MultimodalKnowledgeBase,
                    updates: Dict[str, Any]) -> MultimodalKnowledgeBase:
    for field in ("name", "description", "status", "storage_config", "embedding_config",
                  "vision_model_config", "analysis_config", "is_active"):
        if field in updates and updates[field] is not None:
            setattr(kb, field, updates[field])
    await db.flush()
    await db.refresh(kb)
    return kb


async def count_assets(db: AsyncSession, kb_id: int, include_deleted: bool = False) -> int:
    stmt = select(func.count(MultimodalAsset.id)).where(
        MultimodalAsset.knowledge_base_id == kb_id)
    if not include_deleted:
        stmt = stmt.where(MultimodalAsset.deleted_at.is_(None))
    result = await db.execute(stmt)
    return result.scalar() or 0


async def get_kb_stats(db: AsyncSession, kb_id: int) -> Dict[str, Any]:
    """知识库统计：素材数/类型分布/状态分布/知识单元数/已索引数."""
    # 类型分布（不含回收站）
    type_rows = await db.execute(
        select(MultimodalAsset.file_type, func.count(MultimodalAsset.id))
        .where(MultimodalAsset.knowledge_base_id == kb_id,
               MultimodalAsset.deleted_at.is_(None))
        .group_by(MultimodalAsset.file_type))
    type_stats = {row[0]: row[1] for row in type_rows}

    # 状态分布
    status_rows = await db.execute(
        select(MultimodalAsset.status, func.count(MultimodalAsset.id))
        .where(MultimodalAsset.knowledge_base_id == kb_id,
               MultimodalAsset.deleted_at.is_(None))
        .group_by(MultimodalAsset.status))
    status_stats = {row[0]: row[1] for row in status_rows}

    # 知识单元 / 索引
    units_count = (await db.execute(
        select(func.count(KnowledgeUnit.id))
        .where(KnowledgeUnit.knowledge_base_id == kb_id))).scalar() or 0
    indexed_count = (await db.execute(
        select(func.count(IndexRecord.id))
        .where(IndexRecord.knowledge_base_id == kb_id))).scalar() or 0

    total = sum(type_stats.values())
    return {
        "total_assets": total,
        "total_units": units_count,
        "total_indexed": indexed_count,
        "type_stats": type_stats,
        "status_stats": status_stats,
    }


async def refresh_asset_count(db: AsyncSession, kb_id: int) -> int:
    """重算并更新 kb.asset_count（不含回收站）。"""
    count = await count_assets(db, kb_id, include_deleted=False)
    kb = await get_kb(db, kb_id)
    if kb:
        kb.asset_count = count
        await db.flush()
    return count


async def delete_kb(db: AsyncSession, kb: MultimodalKnowledgeBase) -> None:
    """物理删除知识库（前置条件：无素材，由 service 校验）。"""
    await db.delete(kb)
    await db.flush()
