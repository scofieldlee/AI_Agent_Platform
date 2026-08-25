"""PPT 处理器 — 文本提取 / 页面转图 / 逐页分析（Phase 6）.

- python-pptx 提取每页文本（必须）
- LibreOffice headless 转 PNG（可选——服务器未装则纯文本单元）
- 通义千问 VL 分析每页截图（有截图时）
"""

import asyncio
import logging
import os
import shutil
from typing import Dict, Any, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.multimodal.constants import AssetStatus, UnitType, UnitStatus
from app.multimodal.repositories import asset_repo, knowledge_unit_repo
from app.multimodal.services import storage_service, analysis_service

logger = logging.getLogger(__name__)


def extract_slides_text(abs_path: str) -> List[Dict[str, Any]]:
    """python-pptx 提取每页文本。返回 [{index, title, text}]。"""
    from pptx import Presentation
    prs = Presentation(abs_path)
    slides = []
    for idx, slide in enumerate(prs.slides):
        texts = []
        title = None
        for shape in slide.shapes:
            if shape.has_text_frame:
                txt = "\n".join(p.text for p in shape.text_frame.paragraphs if p.text.strip())
                if txt.strip():
                    if title is None and shape == slide.shapes.title:
                        title = txt.strip()
                    texts.append(txt.strip())
        slides.append({
            "index": idx,
            "title": title or (texts[0][:100] if texts else f"Slide {idx + 1}"),
            "text": "\n".join(texts),
        })
    return slides


async def convert_slides_to_images(abs_path: str, output_dir: str) -> Optional[List[str]]:
    """LibreOffice headless: PPT → PNG 每页一张。未安装返回 None。"""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        logger.info("LibreOffice not installed; slides will be text-only units")
        return None

    os.makedirs(output_dir, exist_ok=True)
    proc = await asyncio.create_subprocess_exec(
        soffice, "--headless", "--convert-to", "png", "--outdir", output_dir, abs_path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        await asyncio.wait_for(proc.communicate(), timeout=300)
    except asyncio.TimeoutError:
        proc.kill()
        logger.warning("LibreOffice conversion timeout")
        return None

    # LibreOffice 单文件转换只输出第一页 png；用 pdf 中转实现全页
    # 转换为 PDF 再逐页转 PNG
    pngs = sorted(f for f in os.listdir(output_dir) if f.endswith(".png"))
    if len(pngs) <= 1:
        return await _convert_via_pdf(abs_path, output_dir)
    return [os.path.join(output_dir, f) for f in pngs]


async def _convert_via_pdf(abs_path: str, output_dir: str) -> Optional[List[str]]:
    """PPT → PDF → 每页 PNG（LibreOffice + pdftoppm）。"""
    import glob
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return None
    # 清理旧 png
    for f in glob.glob(os.path.join(output_dir, "*.png")):
        os.remove(f)

    proc = await asyncio.create_subprocess_exec(
        soffice, "--headless", "--convert-to", "pdf", "--outdir", output_dir, abs_path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        await asyncio.wait_for(proc.communicate(), timeout=300)
    except asyncio.TimeoutError:
        proc.kill()
        return None

    pdfs = glob.glob(os.path.join(output_dir, "*.pdf"))
    if not pdfs:
        return None

    pdftoppm = shutil.which("pdftoppm")
    if pdftoppm:
        proc = await asyncio.create_subprocess_exec(
            pdftoppm, "-png", "-r", "100", pdfs[0],
            os.path.join(output_dir, "slide"),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await proc.communicate()
    else:
        # Pillow 无法直接渲 PDF，降级：仅第一页（LibreOffice png）
        pass

    pngs = sorted(f for f in os.listdir(output_dir) if f.endswith(".png"))
    return [os.path.join(output_dir, f) for f in pngs] or None


async def process(db: AsyncSession, asset_id: int) -> Dict[str, Any]:
    """PPT 素材处理主流程: 文本提取 →（可选）转图 → 逐页分析 → units."""
    asset = await asset_repo.get_asset(db, asset_id)
    if not asset:
        return {"success": False, "error": f"Asset {asset_id} not found"}
    if not asset.storage_path:
        return {"success": False, "error": "Asset has no storage_path"}

    abs_path = storage_service.abs_file_path(asset.storage_path)
    kb_id, aid = asset.knowledge_base_id, asset.id

    # 1. 文本提取
    try:
        slides_text = extract_slides_text(abs_path)
    except Exception as e:
        return {"success": False, "error": f"PPT 解析失败: {e}"}
    if not slides_text:
        return {"success": False, "error": "PPT 无可提取内容"}

    # 2. 页面截图（可选）
    images_dir = storage_service.abs_file_path(
        storage_service.derived_file_path(kb_id, aid, "slides"))
    slide_images = await convert_slides_to_images(abs_path, images_dir)

    # 3. 逐页生成知识单元
    await knowledge_unit_repo.delete_units_by_asset(db, asset_id)
    analyzed = 0

    for i, slide in enumerate(slides_text):
        unit = await knowledge_unit_repo.create_unit(
            db, knowledge_base_id=kb_id, asset_id=aid,
            unit_type=UnitType.SLIDE, unit_index=i,
            content=slide["text"], description=slide["title"],
            status=UnitStatus.PENDING)

        # 截图归位到存储结构
        image_rel = None
        if slide_images and i < len(slide_images):
            src_abs = slide_images[i]
            image_rel = storage_service.derived_file_path(
                kb_id, aid, f"slide_{i:03d}.png")
            shutil.copy2(src_abs, storage_service.abs_file_path(image_rel))
            await knowledge_unit_repo.update_unit(db, unit, {"thumbnail_path": image_rel})

        await knowledge_unit_repo.create_ppt_slide(
            db, unit_id=unit.id, asset_id=aid, slide_index=i,
            title=slide["title"], text_content=slide["text"],
            image_path=image_rel)

        # 有截图时视觉分析增强
        if image_rel:
            try:
                await analysis_service.analyze_visual_unit(
                    db, asset_id, storage_service.abs_file_path(image_rel), unit,
                    frame_prompt_type="image")
                analyzed += 1
            except Exception as e:
                logger.warning(f"Slide {i} visual analysis failed: {e}")

    # 4. system + ai metadata
    system_meta = (await asset_repo.get_all_metadata(db, asset_id)).get("system", {})
    system_meta.update({"page_count": len(slides_text)})
    await asset_repo.upsert_metadata(db, asset_id, "system", system_meta)
    await asset_repo.upsert_metadata(db, asset_id, "ai", {
        "description": f"PPT 素材，共 {len(slides_text)} 页",
        "tags": ["PPT", "演示文稿"],
    })
    await asset_repo.replace_ai_tags(db, asset_id, ["PPT", "演示文稿"])

    # 5. 状态
    await asset_repo.update_asset(db, asset, {"status": AssetStatus.REVIEW_REQUIRED})
    return {"success": True, "slides": len(slides_text),
            "visual_analyzed": analyzed,
            "has_images": bool(slide_images)}
