"""Knowledge base endpoints."""

import io
import logging
import os
import uuid
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.auth.dependencies import require_permission
from app.schemas.knowledge import (
    KnowledgeBaseCreate, KnowledgeBaseResponse, DocumentResponse, ExcelImportResponse,
)
from app.repositories.knowledge_repo import (
    list_knowledge_bases, get_knowledge_base, create_knowledge_base, list_documents,
)

router = APIRouter(dependencies=[Depends(require_permission("knowledge:view"))])

logger = logging.getLogger(__name__)

# Project root / uploads (same convention as conversations.py)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

# Pre-defined column templates for each knowledge base type.
# Each data row becomes one retrieval chunk with "column: value" format.
_EXCEL_TEMPLATES = {
    "product": {
        "sheet": "商品信息",
        "headers": ["商品名称", "品牌", "型号", "规格参数", "核心卖点", "适用场景", "价格（元）"],
        "rows": [
            ["无人机 X1", "SkyTech", "X1-2025", "4K 摄像头 / 30分钟续航 / 图传5公里", "三轴云台防抖、智能跟随、一键返航", "航拍入门 / 旅行记录", "2999"],
            ["遥控车 GT", "Ruko", "GT-Pro", "1:10 比例 / 四驱 / 最高速40km/h", "全地形轮胎、金属底盘、可改装升级", "儿童玩具 / 模型爱好者", "699"],
        ],
    },
    "qa": {
        "sheet": "问答对",
        "headers": ["问题", "答案", "分类", "关联商品"],
        "rows": [
            ["这款手表防水吗？", "支持 5ATM 防水，可佩戴游泳，但不建议热水浴或潜水。", "产品功能", "智能手表Pro"],
            ["退换货期限是多久？", "签收后 7 天内无理由退货，15 天内质量问题可换货。", "售后政策", "通用"],
        ],
    },
    "faq": {
        "sheet": "问答对",
        "headers": ["问题", "答案", "分类", "关联商品"],
        "rows": [
            ["这款产品支持哪些支付方式？", "支持微信支付、支付宝、银联卡及花呗分期。", "支付相关", "通用"],
            ["发货后多久能到？", "国内一线城市一般 1-3 天，偏远地区 3-7 天。", "物流配送", "通用"],
        ],
    },
    "parameter": {
        "sheet": "参数表",
        "headers": ["商品名称", "参数项", "参数值", "单位"],
        "rows": [
            ["智能手表Pro", "屏幕尺寸", "1.43", "英寸"],
            ["智能手表Pro", "电池容量", "450", "mAh"],
            ["智能手表Pro", "防水等级", "5ATM", "-"],
        ],
    },
    "manual": {
        "sheet": "使用说明",
        "headers": ["步骤", "操作说明", "注意事项"],
        "rows": [
            ["1", "长按电源键 3 秒开机，等待 logo 出现后松开。", "首次使用请先充满电。"],
            ["2", "打开手机蓝牙，在 App 中点击「添加设备」完成配对。", "确保手机系统为 Android 8 / iOS 12 以上。"],
        ],
    },
    "after_sale": {
        "sheet": "售后政策",
        "headers": ["政策类型", "适用条件", "处理说明"],
        "rows": [
            ["7天无理由退货", "商品未使用、包装完整、配件齐全", "签收后 7 天内可申请，运费由买家承担。"],
            ["质量问题换货", "经官方检测确认非人为损坏", "15 天内免费换货，运费由商家承担。"],
        ],
    },
    "general": {
        "sheet": "知识条目",
        "headers": ["标题", "内容", "分类", "备注"],
        "rows": [
            ["公司介绍", "我们是一家专注于智能硬件研发与销售的高科技企业。", "品牌", ""],
            ["会员权益", "会员可享受积分兑换、生日礼券、专属客服等权益。", "服务", ""],
        ],
    },
}


def _build_excel_template(kb) -> bytes:
    """Build an example .xlsx template for the given knowledge base type."""
    from openpyxl import Workbook

    template = _EXCEL_TEMPLATES.get(kb.kb_type) or _EXCEL_TEMPLATES["general"]
    wb = Workbook()
    ws = wb.active
    ws.title = template["sheet"]
    ws.append(template["headers"])
    for row in template["rows"]:
        ws.append(row)

    # Set reasonable column widths for readability
    for col_idx, header in enumerate(template["headers"], start=1):
        width = min(max(len(str(header)) * 2, 12), 50)
        ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = width

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


def _template_filename(kb) -> str:
    safe_code = "".join(c if c.isalnum() or c in "-_" else "_" for c in (kb.code or "kb"))
    return f"{safe_code}_import_template.xlsx"


@router.get("", response_model=List[KnowledgeBaseResponse])
async def list_knowledge_bases_endpoint(db: AsyncSession = Depends(get_db)):
    """List all knowledge bases."""
    return await list_knowledge_bases(db)


@router.post("", response_model=KnowledgeBaseResponse, status_code=201)
async def create_knowledge_base_endpoint(data: KnowledgeBaseCreate, db: AsyncSession = Depends(get_db)):
    """Create a new knowledge base."""
    kb = await create_knowledge_base(db, data.model_dump())
    await db.commit()
    return kb


@router.get("/{kb_id}/documents", response_model=List[DocumentResponse])
async def list_documents_endpoint(kb_id: int, db: AsyncSession = Depends(get_db)):
    """List documents in a knowledge base."""
    return await list_documents(db, kb_id)


@router.post("/{kb_id}/sync")
async def sync_knowledge_base_endpoint(kb_id: int, force: bool = False, db: AsyncSession = Depends(get_db)):
    """Sync knowledge base from source (e.g., Obsidian vault).

    Scans the source directory, parses Markdown files, chunks them,
    generates embeddings, and stores in the vector database.
    """
    kb = await get_knowledge_base(db, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    from app.knowledge.services.sync_service import KnowledgeSyncService
    service = KnowledgeSyncService()
    try:
        stats = await service.sync_knowledge_base(kb_id, force=force)
        return {
            "status": "completed",
            "knowledge_base_id": kb_id,
            "stats": stats,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{kb_id}/import", response_model=ExcelImportResponse)
async def import_document_endpoint(
    kb_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("knowledge:manage")),
):
    """Import an Excel/CSV file into a knowledge base.

    First row of each sheet is treated as column headers; each data row becomes
    one retrieval chunk ("column: value" format), embedded and stored in pgvector.
    Re-importing an unchanged file is skipped; a changed file updates the document.
    """
    from app.knowledge.loaders.excel_loader import ALLOWED_EXTENSIONS, MAX_FILE_SIZE_MB

    kb = await get_knowledge_base(db, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    filename = file.filename or "upload.xlsx"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"不支持的文件类型 {ext}，仅支持 {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="文件内容为空")
    if len(content) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=422, detail=f"文件超过 {MAX_FILE_SIZE_MB}MB 限制")
    await file.close()

    # Archive the original file for audit / future re-index
    saved_path = None
    try:
        archive_dir = os.path.join(PROJECT_ROOT, "uploads", "knowledge")
        os.makedirs(archive_dir, exist_ok=True)
        safe_name = f"{uuid.uuid4().hex[:12]}_{os.path.basename(filename)}"
        with open(os.path.join(archive_dir, safe_name), "wb") as f:
            f.write(content)
        saved_path = os.path.join("uploads", "knowledge", safe_name)
    except OSError as e:
        # Archiving is best-effort; indexing continues even if disk write fails
        logger.warning(f"Failed to archive imported file: {e}")

    from app.knowledge.services.import_service import KnowledgeImportService
    service = KnowledgeImportService()
    try:
        stats = await service.import_spreadsheet(kb_id, filename, content, saved_path=saved_path)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导入失败: {e}")

    return ExcelImportResponse(
        status="skipped" if stats.get("skipped") else "completed",
        knowledge_base_id=kb_id,
        document_id=stats["document_id"],
        filename=stats["filename"],
        action=stats.get("action", "skipped"),
        sheets=stats.get("sheets", []),
        rows=stats.get("rows", 0),
        chunks=stats.get("chunks", 0),
    )


@router.get("/{kb_id}/import-template")
async def download_import_template_endpoint(kb_id: int, db: AsyncSession = Depends(get_db)):
    """Download an Excel template matching the knowledge base type.

    The template contains recommended column headers and a few example rows.
    Users can fill in their own data and upload it via POST /knowledge/{kb_id}/import.
    """
    kb = await get_knowledge_base(db, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    content = _build_excel_template(kb)
    filename = _template_filename(kb)

    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )
