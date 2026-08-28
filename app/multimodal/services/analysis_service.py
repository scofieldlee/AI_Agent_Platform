"""AI 分析编排服务 — 调用 Vision Adapter，落库 Metadata + 标签 + KnowledgeUnit.

被 Worker 的 Processor 调用（独立 DB session）。
"""

import logging
from typing import Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.multimodal.adapters import get_vision_adapter
from app.multimodal.constants import (AssetStatus, FileType, UnitType, UnitStatus,
                                      TagSource)
from app.multimodal.repositories import (asset_repo, knowledge_unit_repo)
from app.multimodal.services import storage_service

logger = logging.getLogger(__name__)


def build_unit_content(description: str, ai_metadata: dict) -> str:
    """把 AI 分析结果文本化，作为 KnowledgeUnit.content（Embedding 输入）。"""
    parts = [description or ""]
    for key in ("detail", "objects", "scene", "style", "color", "usage"):
        val = ai_metadata.get(key)
        if isinstance(val, list) and val:
            parts.append(f"{key}: {', '.join(str(v) for v in val)}")
        elif isinstance(val, str) and val:
            parts.append(f"{key}: {val}")
    if ai_metadata.get("ocr"):
        ocr = ai_metadata["ocr"]
        if isinstance(ocr, list):
            parts.append("ocr: " + "; ".join(str(o) for o in ocr))
    return "\n".join(p for p in parts if p.strip())


async def analyze_image_asset(db: AsyncSession, asset_id: int) -> Dict[str, Any]:
    """图片素材 AI 分析主流程:
    Vision 分析 → ai metadata 落库 → AI 标签替换 → 生成/更新 ImageUnit → REVIEW_REQUIRED
    """
    asset = await asset_repo.get_asset(db, asset_id)
    if not asset:
        return {"success": False, "error": f"Asset {asset_id} not found"}
    if not asset.storage_path:
        return {"success": False, "error": "Asset has no storage_path"}

    vision = get_vision_adapter()
    image_abs = storage_service.abs_file_path(asset.storage_path)

    # 1. AI 分析
    result = await vision.analyze_image(image_abs)
    model_used = vision.model_name

    # 2. AI metadata 落库（覆盖旧结果）
    await asset_repo.upsert_metadata(db, asset_id, "ai", result)

    # 3. AI 标签整体替换
    ai_tags = [t for t in result.get("tags", []) if t]
    await asset_repo.replace_ai_tags(db, asset_id, ai_tags)

    # 4. 生成/更新 ImageUnit
    content = build_unit_content(result.get("description", ""), result)
    units = await knowledge_unit_repo.list_units_by_asset(db, asset_id)
    if units:
        unit = units[0]
        await knowledge_unit_repo.update_unit(db, unit, {
            "content": content, "description": result.get("description"),
            "meta": result, "thumbnail_path": asset.thumbnail_path,
            "status": UnitStatus.PENDING})
        unit_id = unit.id
    else:
        unit = await knowledge_unit_repo.create_unit(
            db, knowledge_base_id=asset.knowledge_base_id, asset_id=asset_id,
            unit_type=UnitType.IMAGE, unit_index=0, content=content,
            description=result.get("description"), meta=result,
            thumbnail_path=asset.thumbnail_path, status=UnitStatus.PENDING)
        unit_id = unit.id

    # 5. 状态 → REVIEW_REQUIRED（等待人工审核后进入索引）
    await asset_repo.update_asset(db, asset, {"status": AssetStatus.REVIEW_REQUIRED})

    return {"success": True, "unit_id": unit_id, "model": model_used,
            "tags": ai_tags, "description": result.get("description", "")}


async def analyze_visual_unit(db: AsyncSession, asset_id: int,
                              frame_abs_path: str, unit: Any,
                              frame_prompt_type: str = "frame") -> Dict[str, Any]:
    """分析单个视觉知识单元（视频关键帧 / PPT 页截图）.

    返回分析结果并更新 unit 的 content/description/metadata。
    """
    vision = get_vision_adapter()
    if frame_prompt_type == "frame":
        result = await vision.analyze_video_frame(frame_abs_path)
    else:
        result = await vision.analyze_image(frame_abs_path)

    content = build_unit_content(result.get("description", ""), result)
    await knowledge_unit_repo.update_unit(db, unit, {
        "content": content,
        "description": result.get("description"),
        "meta": result,
        "status": UnitStatus.PENDING})
    return {"success": True, "analysis": result, "model": vision.model_name}


async def analyze_audio_unit(db: AsyncSession, asset_id: int, unit: Any,
                             transcript: str,
                             segment_meta: Optional[dict] = None) -> Dict[str, Any]:
    """音频分段：转写文本即内容（无需视觉模型）。"""
    content = f"transcript: {transcript}" if transcript else ""
    await knowledge_unit_repo.update_unit(db, unit, {
        "content": content, "description": transcript[:200] if transcript else None,
        "meta": segment_meta or {}, "status": UnitStatus.PENDING})
    return {"success": True}


async def analyze_asset_dispatch(db: AsyncSession, asset_id: int,
                                 file_type: str) -> Dict[str, Any]:
    """按素材类型分发分析流程（Worker 入口）。"""
    from app.multimodal.processors import (video_processor, audio_processor,
                                           ppt_processor, document_processor)
    if file_type == FileType.IMAGE:
        return await analyze_image_asset(db, asset_id)
    # video / audio / ppt / document 的分解 + 逐单元分析在各自 Processor 中完成
    if file_type == FileType.VIDEO:
        return await video_processor.process(db, asset_id)
    if file_type == FileType.AUDIO:
        return await audio_processor.process(db, asset_id)
    if file_type == FileType.PPT:
        return await ppt_processor.process(db, asset_id)
    if file_type in (FileType.PDF, FileType.DOCUMENT):
        return await document_processor.process(db, asset_id)
    return {"success": False, "error": f"暂不支持的分析类型: {file_type}"}
