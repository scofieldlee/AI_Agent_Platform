"""素材服务 — 上传校验 / 缩略图 / CRUD 编排."""

import io
import logging
import uuid
from typing import Optional, List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.multimodal.constants import (AssetStatus, FileType, detect_file_type,
                                      MAX_FILE_SIZE_MB, allowed_file_types)
from app.multimodal.repositories import asset_repo, knowledge_base_repo, knowledge_unit_repo
from app.multimodal.services import storage_service
from app.multimodal.services.task_queue_service import create_and_enqueue

logger = logging.getLogger(__name__)

MB = 1024 * 1024


# ---------- 上传 ----------

async def validate_upload(filename: str, file_size: int) -> tuple:
    """校验文件名/类型/大小。返回 (file_type, error)。"""
    file_type = detect_file_type(filename)
    if file_type == FileType.OTHER:
        return None, f"不支持的文件类型: {filename}（支持图片/视频/音频/PPT/PDF/文档）"
    limit_mb = MAX_FILE_SIZE_MB.get(file_type, 100)
    if file_size > limit_mb * MB:
        return None, f"文件超过大小限制: {file_size / MB:.1f}MB > {limit_mb}MB"
    return file_type, None


def generate_image_thumbnail(file_data: bytes, max_size: int = 320) -> Optional[bytes]:
    """图片缩略图生成（Pillow，同步调用——上传路径上耗时可接受）。"""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(file_data))
        img.thumbnail((max_size, max_size))
        # 统一转 RGB（PNG 透明通道 → JPEG 白底）
        if img.mode in ("RGBA", "P", "LA"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except Exception as e:
        logger.warning(f"Thumbnail generation failed: {e}")
        return None


def extract_image_system_metadata(file_data: bytes) -> dict:
    """提取图片系统 metadata（分辨率/格式）。"""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(file_data))
        return {
            "resolution": f"{img.width}x{img.height}",
            "width": img.width,
            "height": img.height,
            "format": img.format or "UNKNOWN",
        }
    except Exception:
        return {}


async def upload_asset(db: AsyncSession, kb_id: int, filename: str,
                       file_data: bytes, created_by: Optional[int] = None) -> Dict[str, Any]:
    """上传单个素材。返回 {success, asset_id, asset_code, error}。

    流程: 校验 → 建记录 → 存原文件 → 图片即时生成缩略图 → 入队 AI 分析任务。
    """
    file_type, error = await validate_upload(filename, len(file_data))
    if error:
        return {"success": False, "error": error, "filename": filename}

    kb = await knowledge_base_repo.get_kb(db, kb_id)
    if not kb:
        return {"success": False, "error": f"知识库不存在: {kb_id}", "filename": filename}

    # 1. 创建素材记录
    asset_code = await asset_repo.generate_asset_code(db, kb_id, file_type)
    asset = await asset_repo.create_asset(
        db, knowledge_base_id=kb_id, asset_code=asset_code,
        name=filename.rsplit(".", 1)[0] if "." in filename else filename,
        original_filename=filename, file_type=file_type,
        mime_type=storage_service.guess_mime(filename),
        file_size=len(file_data), status=AssetStatus.UPLOADED, created_by=created_by)

    # 2. 存储原始文件
    await storage_service.ensure_asset_dirs(kb_id, asset.id)
    storage_path = await storage_service.save_original(kb_id, asset.id, file_data, filename)
    updates: Dict[str, Any] = {"storage_path": storage_path}

    # 3. 图片：即时生成缩略图 + 系统 metadata
    system_meta: Dict[str, Any] = {"file_type": file_type, "size": len(file_data),
                                   "filename": filename}
    if file_type == FileType.IMAGE:
        thumb = generate_image_thumbnail(file_data)
        if thumb:
            updates["thumbnail_path"] = await storage_service.save_thumbnail(
                kb_id, asset.id, thumb)
        system_meta.update(extract_image_system_metadata(file_data))

    await asset_repo.upsert_metadata(db, asset.id, "system", system_meta)
    asset = await asset_repo.update_asset(db, asset, updates)

    # 4. 创建初始版本快照
    await asset_repo.create_version_snapshot(db, asset, created_by)

    # 5. 更新知识库计数 & 入队 AI 分析
    await knowledge_base_repo.refresh_asset_count(db, kb_id)
    await create_and_enqueue(
        db, asset_id=asset.id, kb_id=kb_id, task_type="analysis",
        input_data={"file_type": file_type, "auto": True})

    return {"success": True, "asset_id": asset.id, "asset_code": asset.asset_code,
            "file_type": file_type, "filename": filename, "error": None}


# ---------- 查询 ----------

async def list_assets(db: AsyncSession, params) -> Dict[str, Any]:
    """素材列表（分页 + 过滤 + 标签批量装配）。"""
    total, assets = await asset_repo.list_assets(
        db, kb_id=params.knowledge_base_id, file_type=params.file_type,
        status=params.status, tag=params.tag, keyword=params.keyword,
        include_deleted=params.include_deleted,
        page=params.page, page_size=params.page_size)
    tags_map = await asset_repo.get_assets_tags_map(db, [a.id for a in assets])
    items = []
    for a in assets:
        item = {c.name: getattr(a, c.name) for c in a.__table__.columns}
        item["tags"] = tags_map.get(a.id, [])
        items.append(item)
    return {"total": total, "page": params.page, "page_size": params.page_size, "items": items}


async def get_asset_detail(db: AsyncSession, asset_id: int) -> Optional[Dict[str, Any]]:
    """素材详情：基础信息 + 全部 metadata + units + relations + 处理汇总。"""
    asset = await asset_repo.get_asset(db, asset_id)
    if not asset:
        return None

    detail = {c.name: getattr(asset, c.name) for c in asset.__table__.columns}
    detail["tags"] = await asset_repo.get_asset_tags(db, asset_id)
    detail["metadata"] = await asset_repo.get_all_metadata(db, asset_id)
    ai_meta = detail["metadata"].get("ai", {})
    detail["ai_tags"] = ai_meta.get("tags", [])

    units = await knowledge_unit_repo.list_units_by_asset(db, asset_id)
    detail["units_count"] = len(units)
    detail["units"] = [{
        "id": u.id, "unit_type": u.unit_type, "unit_index": u.unit_index,
        "description": (u.description or "")[:200], "status": u.status,
        "start_time": u.start_time, "end_time": u.end_time,
        "thumbnail_url": storage_service.file_url(u.thumbnail_path),
    } for u in units]

    detail["relations"] = await asset_repo.list_relations(db, asset_id)

    from app.multimodal.repositories import processing_repo
    detail["processing_summary"] = await processing_repo.get_asset_processing_summary(
        db, asset_id)
    return detail


# ---------- 删除/恢复 ----------

async def soft_delete_asset(db: AsyncSession, asset_id: int) -> Optional[Any]:
    asset = await asset_repo.get_asset(db, asset_id)
    if not asset or asset.deleted_at is not None:
        return None
    asset = await asset_repo.soft_delete_asset(db, asset)
    await knowledge_base_repo.refresh_asset_count(db, asset.knowledge_base_id)
    return asset


async def restore_asset(db: AsyncSession, asset_id: int) -> Optional[Any]:
    asset = await asset_repo.get_asset(db, asset_id)
    if not asset or asset.deleted_at is None:
        return None
    asset = await asset_repo.restore_asset(db, asset)
    await knowledge_base_repo.refresh_asset_count(db, asset.knowledge_base_id)
    return asset


async def permanent_delete_asset(db: AsyncSession, asset_id: int) -> Optional[Dict]:
    """永久删除：DB 记录（级联 units/index/metadata）+ 文件目录。"""
    from app.multimodal.repositories import index_repo
    asset = await asset_repo.get_asset(db, asset_id)
    if not asset:
        return None
    kb_id = asset.knowledge_base_id
    files_removed = await storage_service.delete_asset_files(kb_id, asset_id)
    await index_repo.delete_index_by_asset(db, asset_id)
    await asset_repo.permanent_delete_asset(db, asset)
    await knowledge_base_repo.refresh_asset_count(db, kb_id)
    return {"asset_id": asset_id, "files_removed": files_removed}


# ---------- 标签 ----------

async def add_tags(db: AsyncSession, asset_id: int, tag_names: List[str],
                   source: str, user_id: Optional[int] = None) -> List[Dict]:
    for name in tag_names:
        tag = await asset_repo.get_or_create_tag(db, name, source, user_id)
        await asset_repo.add_tag_to_asset(db, asset_id, tag.id, source)
    return await asset_repo.get_asset_tags(db, asset_id)


async def remove_tag(db: AsyncSession, asset_id: int, tag_id: int) -> bool:
    return await asset_repo.remove_tag_from_asset(db, asset_id, tag_id)


# ---------- 触发处理 ----------

async def trigger_analysis(db: AsyncSession, asset_id: int) -> Optional[Any]:
    """触发/重新触发 AI 分析（异步）。"""
    from app.multimodal.repositories import processing_repo
    asset = await asset_repo.get_asset(db, asset_id)
    if not asset:
        return None
    if asset.status in (AssetStatus.PROCESSING, AssetStatus.ANALYZING):
        return {"error": "素材正在处理中，请稍候"}
    await asset_repo.update_asset(db, asset, {"status": AssetStatus.ANALYZING})
    task = await create_and_enqueue(
        db, asset_id=asset_id, kb_id=asset.knowledge_base_id,
        task_type="analysis", input_data={"file_type": asset.file_type})
    return task


async def trigger_index(db: AsyncSession, asset_id: int) -> Optional[Any]:
    """触发/重新触发向量化索引（异步）。"""
    asset = await asset_repo.get_asset(db, asset_id)
    if not asset:
        return None
    if asset.status == AssetStatus.INDEXING:
        return {"error": "素材正在索引中，请稍候"}
    await asset_repo.update_asset(db, asset, {"status": AssetStatus.INDEXING})
    task = await create_and_enqueue(
        db, asset_id=asset_id, kb_id=asset.knowledge_base_id,
        task_type="index", input_data={"file_type": asset.file_type})
    return task


async def batch_analyze(db: AsyncSession, asset_ids: List[int]) -> List[Dict]:
    """批量触发分析。"""
    results = []
    for aid in asset_ids:
        task = await trigger_analysis(db, aid)
        if task is None:
            results.append({"asset_id": aid, "error": "素材不存在"})
        elif isinstance(task, dict) and "error" in task:
            results.append({"asset_id": aid, "error": task["error"]})
        else:
            results.append({"asset_id": aid, "task_id": task.id, "status": "queued"})
    return results
