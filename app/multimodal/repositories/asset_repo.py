"""素材 Repository — CRUD / 列表过滤 / Metadata / 标签 / 版本 / 关联."""

import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy import select, func, and_, or_, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.multimodal.models import (
    MultimodalAsset, AssetMetadata, AssetTag, AssetTagRelation,
    AssetRelation, AssetVersion, KnowledgeUnit,
)
from app.multimodal.constants import (AssetStatus, FileType, TagSource,
                                      ASSET_CODE_PREFIX)


# ---------- CRUD ----------

async def get_asset(db: AsyncSession, asset_id: int) -> Optional[MultimodalAsset]:
    return await db.get(MultimodalAsset, asset_id)


async def generate_asset_code(db: AsyncSession, kb_id: int, file_type: str) -> str:
    """生成素材编码: {PREFIX}-{6位序号}（知识库内自增）。"""
    prefix = ASSET_CODE_PREFIX.get(file_type, "FILE")
    # 当前 KB 内同前缀最大序号 + 1
    stmt = select(func.count(MultimodalAsset.id)).where(
        MultimodalAsset.knowledge_base_id == kb_id,
        MultimodalAsset.asset_code.like(f"{prefix}-%"))
    count = (await db.execute(stmt)).scalar() or 0
    # 防并发冲突：循环检测唯一约束
    for _ in range(5):
        code = f"{prefix}-{count + 1:06d}"
        exists = await db.execute(
            select(func.count(MultimodalAsset.id)).where(
                MultimodalAsset.knowledge_base_id == kb_id,
                MultimodalAsset.asset_code == code))
        if (exists.scalar() or 0) == 0:
            return code
        count += 1
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


async def create_asset(db: AsyncSession, **kwargs) -> MultimodalAsset:
    asset = MultimodalAsset(**kwargs)
    db.add(asset)
    await db.flush()
    await db.refresh(asset)
    return asset


async def update_asset(db: AsyncSession, asset: MultimodalAsset,
                       updates: Dict[str, Any]) -> MultimodalAsset:
    for field in ("name", "status", "storage_path", "thumbnail_path", "preview_path",
                  "attributes", "version", "current_version_id"):
        if field in updates and updates[field] is not None:
            setattr(asset, field, updates[field])
    await db.flush()
    await db.refresh(asset)
    return asset


# ---------- 列表查询 ----------

async def list_assets(db: AsyncSession, kb_id: int,
                      file_type: Optional[str] = None,
                      status: Optional[str] = None,
                      tag: Optional[str] = None,
                      keyword: Optional[str] = None,
                      include_deleted: bool = False,
                      page: int = 1, page_size: int = 20) -> Tuple[int, List[MultimodalAsset]]:
    """分页列表。include_deleted=True 查回收站；否则仅正常素材。"""
    conditions = [MultimodalAsset.knowledge_base_id == kb_id]
    if include_deleted:
        conditions.append(MultimodalAsset.deleted_at.isnot(None))
        conditions.append(MultimodalAsset.status == AssetStatus.DELETED)
    else:
        conditions.append(MultimodalAsset.deleted_at.is_(None))

    if file_type:
        conditions.append(MultimodalAsset.file_type == file_type)
    if status:
        conditions.append(MultimodalAsset.status == status)
    if keyword:
        like = f"%{keyword}%"
        conditions.append(or_(MultimodalAsset.name.ilike(like),
                              MultimodalAsset.asset_code.ilike(like)))

    base = select(MultimodalAsset).where(and_(*conditions))
    if tag:
        base = base.join(AssetTagRelation, AssetTagRelation.asset_id == MultimodalAsset.id) \
                   .join(AssetTag, AssetTag.id == AssetTagRelation.tag_id) \
                   .where(AssetTag.name == tag)

    total = (await db.execute(
        select(func.count()).select_from(base.subquery()))).scalar() or 0
    result = await db.execute(
        base.order_by(MultimodalAsset.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size))
    return total, list(result.scalars().all())


async def get_asset_tags(db: AsyncSession, asset_id: int) -> List[Dict]:
    """素材标签列表 [{id, name, source}]。"""
    stmt = (select(AssetTag, AssetTagRelation.source)
            .join(AssetTagRelation, AssetTagRelation.tag_id == AssetTag.id)
            .where(AssetTagRelation.asset_id == asset_id))
    result = await db.execute(stmt)
    return [{"id": tag.id, "name": tag.name, "source": source}
            for tag, source in result.all()]


async def get_assets_tags_map(db: AsyncSession, asset_ids: List[int]) -> Dict[int, List[Dict]]:
    """批量获取素材标签（列表页性能优化）。"""
    if not asset_ids:
        return {}
    stmt = (select(AssetTagRelation.asset_id, AssetTag.id, AssetTag.name,
                   AssetTagRelation.source)
            .join(AssetTag, AssetTag.id == AssetTagRelation.tag_id)
            .where(AssetTagRelation.asset_id.in_(asset_ids)))
    result = await db.execute(stmt)
    tags_map: Dict[int, List[Dict]] = {}
    for asset_id, tag_id, name, source in result.all():
        tags_map.setdefault(asset_id, []).append(
            {"id": tag_id, "name": name, "source": source})
    return tags_map


# ---------- Metadata ----------

async def upsert_metadata(db: AsyncSession, asset_id: int,
                          metadata_type: str, metadata: dict) -> AssetMetadata:
    """写入/覆盖某来源 metadata。"""
    result = await db.execute(
        select(AssetMetadata).where(AssetMetadata.asset_id == asset_id,
                                    AssetMetadata.metadata_type == metadata_type))
    record = result.scalars().first()
    if record:
        record.meta = metadata
    else:
        record = AssetMetadata(asset_id=asset_id, metadata_type=metadata_type,
                               meta=metadata)
        db.add(record)
    await db.flush()
    await db.refresh(record)
    return record


async def get_all_metadata(db: AsyncSession, asset_id: int) -> Dict[str, dict]:
    """获取素材全部 metadata {system: {...}, ai: {...}, user: {...}}。"""
    result = await db.execute(
        select(AssetMetadata).where(AssetMetadata.asset_id == asset_id))
    return {r.metadata_type: (r.meta or {}) for r in result.scalars().all()}


# ---------- 标签 ----------

async def get_or_create_tag(db: AsyncSession, name: str, source: str,
                            created_by: Optional[int] = None) -> AssetTag:
    """获取或创建标签（按 name+source 唯一）。"""
    name = name.strip()
    result = await db.execute(
        select(AssetTag).where(AssetTag.name == name, AssetTag.source == source))
    tag = result.scalars().first()
    if not tag:
        tag = AssetTag(name=name, source=source, created_by=created_by)
        db.add(tag)
        await db.flush()
        await db.refresh(tag)
    return tag


async def add_tag_to_asset(db: AsyncSession, asset_id: int, tag_id: int, source: str) -> None:
    """挂载标签到素材（幂等）。"""
    exists = await db.execute(
        select(func.count(AssetTagRelation.id)).where(
            AssetTagRelation.asset_id == asset_id,
            AssetTagRelation.tag_id == tag_id,
            AssetTagRelation.source == source))
    if (exists.scalar() or 0) == 0:
        db.add(AssetTagRelation(asset_id=asset_id, tag_id=tag_id, source=source))
        await db.flush()


async def remove_tag_from_asset(db: AsyncSession, asset_id: int, tag_id: int) -> bool:
    """移除素材标签（用户删除 AI 标签后，标记为用户删除——记录到 asset.attributes['removed_ai_tags']）."""
    result = await db.execute(sa_delete(AssetTagRelation).where(
        AssetTagRelation.asset_id == asset_id,
        AssetTagRelation.tag_id == tag_id))
    await db.flush()
    return bool(result.rowcount)


async def replace_ai_tags(db: AsyncSession, asset_id: int, tag_names: List[str]) -> None:
    """AI 重新分析时整体替换 AI 标签（不触碰 user 标签）。"""
    await db.execute(sa_delete(AssetTagRelation).where(
        AssetTagRelation.asset_id == asset_id,
        AssetTagRelation.source == TagSource.AI))
    for name in tag_names:
        if not name or not name.strip():
            continue
        tag = await get_or_create_tag(db, name.strip(), TagSource.AI)
        await add_tag_to_asset(db, asset_id, tag.id, TagSource.AI)


async def list_all_tags(db: AsyncSession, kb_id: Optional[int] = None) -> List[Dict]:
    """标签字典（含使用计数）。"""
    stmt = (select(AssetTag.id, AssetTag.name, AssetTag.source,
                   func.count(AssetTagRelation.id).label("usage"))
            .outerjoin(AssetTagRelation, AssetTagRelation.tag_id == AssetTag.id)
            .group_by(AssetTag.id, AssetTag.name, AssetTag.source)
            .order_by(func.count(AssetTagRelation.id).desc()))
    result = await db.execute(stmt)
    return [{"id": r.id, "name": r.name, "source": r.source, "usage": r.usage}
            for r in result.all()]


# ---------- 版本 ----------

async def create_version_snapshot(db: AsyncSession, asset: MultimodalAsset,
                                  created_by: Optional[int] = None) -> AssetVersion:
    """为当前素材创建版本快照。"""
    version = AssetVersion(
        asset_id=asset.id,
        version=asset.version,
        storage_path=asset.storage_path,
        file_size=asset.file_size,
        meta={"status": asset.status},
        created_by=created_by)
    db.add(version)
    await db.flush()
    await db.refresh(version)
    return version


async def list_versions(db: AsyncSession, asset_id: int) -> List[AssetVersion]:
    result = await db.execute(
        select(AssetVersion).where(AssetVersion.asset_id == asset_id)
        .order_by(AssetVersion.version.desc()))
    return list(result.scalars().all())


# ---------- 关联 ----------

async def create_relation(db: AsyncSession, source_asset_id: int, target_asset_id: int,
                          relation_type: str, metadata: Optional[dict] = None,
                          created_by: Optional[int] = None) -> AssetRelation:
    rel = AssetRelation(source_asset_id=source_asset_id, target_asset_id=target_asset_id,
                        relation_type=relation_type, meta=metadata or {},
                        created_by=created_by)
    db.add(rel)
    await db.flush()
    await db.refresh(rel)
    return rel


async def list_relations(db: AsyncSession, asset_id: int) -> List[Dict]:
    """双向关联列表（含对方素材概要）。"""
    stmt = (select(AssetRelation, MultimodalAsset)
            .join(MultimodalAsset,
                  or_(MultimodalAsset.id == AssetRelation.target_asset_id,
                      MultimodalAsset.id == AssetRelation.source_asset_id))
            .where(or_(AssetRelation.source_asset_id == asset_id,
                       AssetRelation.target_asset_id == asset_id),
                   MultimodalAsset.id != asset_id))
    result = await db.execute(stmt)
    relations = []
    seen = set()
    for rel, other in result.all():
        key = (rel.id, other.id)
        if key in seen:
            continue
        seen.add(key)
        relations.append({
            "relation_id": rel.id,
            "relation_type": rel.relation_type,
            "direction": "outgoing" if rel.source_asset_id == asset_id else "incoming",
            "asset": {
                "id": other.id,
                "asset_code": other.asset_code,
                "name": other.name,
                "file_type": other.file_type,
                "thumbnail_path": other.thumbnail_path,
                "status": other.status,
            },
        })
    return relations


async def delete_relation(db: AsyncSession, relation_id: int) -> bool:
    result = await db.execute(sa_delete(AssetRelation).where(AssetRelation.id == relation_id))
    await db.flush()
    return bool(result.rowcount)


# ---------- 删除/恢复 ----------

async def soft_delete_asset(db: AsyncSession, asset: MultimodalAsset) -> MultimodalAsset:
    """软删除 → 回收站。"""
    asset.deleted_at = datetime.now(timezone.utc)
    asset.status = AssetStatus.DELETED
    await db.flush()
    await db.refresh(asset)
    return asset


async def restore_asset(db: AsyncSession, asset: MultimodalAsset) -> MultimodalAsset:
    """从回收站恢复（恢复到审核或就绪状态）。"""
    asset.deleted_at = None
    if asset.status == AssetStatus.DELETED:
        # 依据是否已有 AI metadata 决定恢复状态
        ai_meta = await db.execute(
            select(func.count(AssetMetadata.id)).where(
                AssetMetadata.asset_id == asset.id,
                AssetMetadata.metadata_type == "ai"))
        asset.status = (AssetStatus.REVIEW_REQUIRED
                        if (ai_meta.scalar() or 0) > 0 else AssetStatus.UPLOADED)
    await db.flush()
    await db.refresh(asset)
    return asset


async def permanent_delete_asset(db: AsyncSession, asset: MultimodalAsset) -> None:
    """永久删除（DB 级联清理 units/index/metadata/relations）。"""
    await db.delete(asset)
    await db.flush()


async def count_assets_in_kb(db: AsyncSession, kb_id: int, include_trash: bool = False) -> int:
    conditions = [MultimodalAsset.knowledge_base_id == kb_id]
    if not include_trash:
        conditions.append(MultimodalAsset.deleted_at.is_(None))
    result = await db.execute(
        select(func.count(MultimodalAsset.id)).where(and_(*conditions)))
    return result.scalar() or 0


async def count_kb_processing(db: AsyncSession, kb_id: int) -> Dict[str, int]:
    """统计知识库各状态素材数（用于删除保护判断）。"""
    rows = await db.execute(
        select(MultimodalAsset.status, func.count(MultimodalAsset.id))
        .where(MultimodalAsset.knowledge_base_id == kb_id,
               MultimodalAsset.deleted_at.is_(None))
        .group_by(MultimodalAsset.status))
    return {row[0]: row[1] for row in rows.all()}
