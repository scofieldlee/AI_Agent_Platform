"""知识单元 Repository."""

from typing import Optional, List, Dict, Any
from sqlalchemy import select, func, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.multimodal.models import (
    KnowledgeUnit, VideoShot, AudioSegment, PptSlide,
)


async def get_unit(db: AsyncSession, unit_id: int) -> Optional[KnowledgeUnit]:
    return await db.get(KnowledgeUnit, unit_id)


async def list_units_by_asset(db: AsyncSession, asset_id: int) -> List[KnowledgeUnit]:
    result = await db.execute(
        select(KnowledgeUnit).where(KnowledgeUnit.asset_id == asset_id)
        .order_by(KnowledgeUnit.unit_index.asc()))
    return list(result.scalars().all())


async def create_unit(db: AsyncSession, **kwargs) -> KnowledgeUnit:
    unit = KnowledgeUnit(**kwargs)
    db.add(unit)
    await db.flush()
    await db.refresh(unit)
    return unit


async def delete_units_by_asset(db: AsyncSession, asset_id: int) -> int:
    """删除素材全部知识单元（重新分析/重新生成前调用）。"""
    result = await db.execute(sa_delete(KnowledgeUnit).where(
        KnowledgeUnit.asset_id == asset_id))
    await db.flush()
    return result.rowcount or 0


async def count_units_by_asset(db: AsyncSession, asset_id: int) -> int:
    return (await db.execute(
        select(func.count(KnowledgeUnit.id))
        .where(KnowledgeUnit.asset_id == asset_id))).scalar() or 0


async def update_unit(db: AsyncSession, unit: KnowledgeUnit,
                      updates: Dict[str, Any]) -> KnowledgeUnit:
    for field in ("content", "description", "meta", "thumbnail_path",
                  "start_time", "end_time", "status"):
        if field in updates and updates[field] is not None:
            setattr(unit, field, updates[field])
    await db.flush()
    await db.refresh(unit)
    return unit


# ---------- 扩展详情表 ----------

async def create_video_shot(db: AsyncSession, **kwargs) -> VideoShot:
    shot = VideoShot(**kwargs)
    db.add(shot)
    await db.flush()
    await db.refresh(shot)
    return shot


async def create_audio_segment(db: AsyncSession, **kwargs) -> AudioSegment:
    seg = AudioSegment(**kwargs)
    db.add(seg)
    await db.flush()
    await db.refresh(seg)
    return seg


async def create_ppt_slide(db: AsyncSession, **kwargs) -> PptSlide:
    slide = PptSlide(**kwargs)
    db.add(slide)
    await db.flush()
    await db.refresh(slide)
    return slide


async def get_video_shot_by_unit(db: AsyncSession, unit_id: int) -> Optional[VideoShot]:
    result = await db.execute(select(VideoShot).where(VideoShot.unit_id == unit_id))
    return result.scalars().first()


async def get_audio_segment_by_unit(db: AsyncSession, unit_id: int) -> Optional[AudioSegment]:
    result = await db.execute(select(AudioSegment).where(AudioSegment.unit_id == unit_id))
    return result.scalars().first()


async def get_ppt_slide_by_unit(db: AsyncSession, unit_id: int) -> Optional[PptSlide]:
    result = await db.execute(select(PptSlide).where(PptSlide.unit_id == unit_id))
    return result.scalars().first()
