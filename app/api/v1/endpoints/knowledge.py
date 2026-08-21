"""Knowledge base endpoints."""

import io
import logging
import os
import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.auth.dependencies import require_permission
from app.schemas.knowledge import (
    ChunkResponse, ChunkUpdate, DocumentContentUpdate, DocumentDetailResponse,
    DocumentResponse, DocumentUpdate, ExcelImportResponse, KnowledgeBaseCreate,
    KnowledgeBaseResponse,
)
from app.repositories.knowledge_repo import (
    create_knowledge_base, delete_chunk, delete_document, get_chunk, get_document,
    get_knowledge_base, list_chunks, list_documents, list_knowledge_bases,
    replace_document_chunks, update_document,
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
    """Create a new knowledge base.

    The `code` field is optional — auto-generated from kb_type + a random
    suffix when the client doesn't provide one (keeps the unique constraint).
    """
    payload = data.model_dump()
    if not payload.get("code") or not payload["code"].strip():
        payload["code"] = f"kb_{payload.get('kb_type', 'general')}_{uuid.uuid4().hex[:8]}"

    try:
        kb = await create_knowledge_base(db, payload)
        await db.commit()
        return kb
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"知识库编码已存在: {payload['code']}")


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


# ----------------------------------------------------------------------------
# Document / Chunk detail & edit endpoints
# ----------------------------------------------------------------------------

def _doc_to_detail(doc, chunks) -> DocumentDetailResponse:
    """Convert a Document ORM object + chunk list to a DocumentDetailResponse."""
    return DocumentDetailResponse(
        id=doc.id,
        title=doc.title,
        source_path=doc.source_path,
        source_type=doc.source_type,
        status=doc.status,
        chunk_count=doc.chunk_count,
        meta=doc.meta or {},
        created_at=doc.created_at.isoformat() if getattr(doc, "created_at", None) else None,
        updated_at=doc.updated_at.isoformat() if getattr(doc, "updated_at", None) else None,
        chunks=[ChunkResponse.model_validate(c) for c in chunks],
    )


async def _refresh_kb_counters(db: AsyncSession, kb_id: int) -> None:
    """Recompute document_count / chunk_count on the knowledge base from the DB."""
    from sqlalchemy import func, select
    from app.models.knowledge import Document as DocumentModel, Chunk as ChunkModel

    doc_count = await db.scalar(
        select(func.count(DocumentModel.id)).where(DocumentModel.knowledge_base_id == kb_id)
    ) or 0
    chunk_count = await db.scalar(
        select(func.count(ChunkModel.id))
        .join(DocumentModel, ChunkModel.document_id == DocumentModel.id)
        .where(DocumentModel.knowledge_base_id == kb_id)
    ) or 0
    kb = await get_knowledge_base(db, kb_id)
    if kb:
        kb.document_count = doc_count
        kb.chunk_count = chunk_count
        await db.flush()


@router.get("/{kb_id}/documents/{doc_id}", response_model=DocumentDetailResponse)
async def get_document_endpoint(
    kb_id: int, doc_id: int, db: AsyncSession = Depends(get_db)
):
    """Return document metadata plus all its chunks (embedding vectors omitted)."""
    doc = await get_document(db, kb_id, doc_id)
    if not doc or doc.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="Document not found")
    chunks = await list_chunks(db, doc_id)
    return _doc_to_detail(doc, chunks)


@router.patch(
    "/{kb_id}/documents/{doc_id}", response_model=DocumentResponse,
    dependencies=[Depends(require_permission("knowledge:manage"))],
)
async def update_document_endpoint(
    kb_id: int, doc_id: int, payload: DocumentUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Partially update a document (title, metadata)."""
    doc = await get_document(db, kb_id, doc_id)
    if not doc or doc.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="Document not found")
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        return doc
    updated = await update_document(db, doc, fields)
    await db.commit()
    return updated


@router.delete(
    "/{kb_id}/documents/{doc_id}", status_code=204,
    dependencies=[Depends(require_permission("knowledge:manage"))],
)
async def delete_document_endpoint(
    kb_id: int, doc_id: int, db: AsyncSession = Depends(get_db)
):
    """Delete a document and all of its chunks (cascades via FK)."""
    doc = await get_document(db, kb_id, doc_id)
    if not doc or doc.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="Document not found")
    await delete_document(db, doc)
    await _refresh_kb_counters(db, kb_id)
    await db.commit()
    return None


@router.patch(
    "/{kb_id}/documents/{doc_id}/chunks/{chunk_id}", response_model=ChunkResponse,
    dependencies=[Depends(require_permission("knowledge:manage"))],
)
async def update_chunk_endpoint(
    kb_id: int, doc_id: int, chunk_id: int, payload: ChunkUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Edit a chunk's content and/or section. When content changes, the embedding
    is regenerated automatically so retrieval keeps working."""
    doc = await get_document(db, kb_id, doc_id)
    if not doc or doc.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="Document not found")
    chunk = await get_chunk(db, chunk_id)
    if not chunk or chunk.document_id != doc_id:
        raise HTTPException(status_code=404, detail="Chunk not found")

    content_changed = "content" in payload.model_fields_set and payload.content is not None \
        and payload.content != chunk.content
    if "section" in payload.model_fields_set and payload.section is not None:
        chunk.section = payload.section
    if "content" in payload.model_fields_set and payload.content is not None:
        chunk.content = payload.content

    if content_changed:
        # Regenerate the embedding using the Model Center
        try:
            from app.models_center.service import ModelService
            embeddings = await ModelService().embed([chunk.content])
            if embeddings and embeddings[0] is not None:
                chunk.embedding = embeddings[0]
                chunk.token_count = len(chunk.content)
        except Exception as e:
            logger.warning(f"Failed to regenerate embedding for chunk {chunk_id}: {e}")
            # Content is saved; embedding regeneration can be retried by sync

    await db.flush()
    await db.refresh(chunk)
    await db.commit()
    return ChunkResponse.model_validate(chunk)


@router.delete(
    "/{kb_id}/documents/{doc_id}/chunks/{chunk_id}", status_code=204,
    dependencies=[Depends(require_permission("knowledge:manage"))],
)
async def delete_chunk_endpoint(
    kb_id: int, doc_id: int, chunk_id: int, db: AsyncSession = Depends(get_db)
):
    """Delete a single chunk from a document."""
    doc = await get_document(db, kb_id, doc_id)
    if not doc or doc.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="Document not found")
    chunk = await get_chunk(db, chunk_id)
    if not chunk or chunk.document_id != doc_id:
        raise HTTPException(status_code=404, detail="Chunk not found")
    await delete_chunk(db, chunk)
    # Update doc.chunk_count locally; refresh KB counters at the end
    doc.chunk_count = max(0, (doc.chunk_count or 1) - 1)
    await db.flush()
    await _refresh_kb_counters(db, kb_id)
    await db.commit()
    return None


@router.put(
    "/{kb_id}/documents/{doc_id}/content",
    response_model=DocumentDetailResponse,
    dependencies=[Depends(require_permission("knowledge:manage"))],
)
async def update_document_content_endpoint(
    kb_id: int,
    doc_id: int,
    payload: DocumentContentUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Replace the full Markdown content of a document.

    The content is re-split into chunks using the configured Markdown splitter,
    embeddings are regenerated, and old chunks are replaced. The document's
    content_hash is updated so subsequent Obsidian syncs can detect conflicts.
    """
    import hashlib

    import frontmatter

    doc = await get_document(db, kb_id, doc_id)
    if not doc or doc.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="Document not found")

    content = payload.content
    if not content or not content.strip():
        raise HTTPException(status_code=422, detail="内容不能为空")

    # Build raw markdown (body + frontmatter) for hash / future sync comparison
    meta = payload.meta if payload.meta is not None else (doc.meta or {})
    raw_content = frontmatter.dumps(frontmatter.Post(content, **meta))
    content_hash = hashlib.md5(raw_content.encode("utf-8")).hexdigest()

    # Split into chunks
    from app.knowledge.splitters.markdown_splitter import MarkdownSplitter
    splitter = MarkdownSplitter()
    chunks_data = splitter.split(
        content=content,
        metadata={
            **meta,
            "title": payload.title if payload.title is not None else doc.title,
            "source_path": doc.source_path or "",
        },
    )
    if not chunks_data:
        raise HTTPException(status_code=422, detail="内容过短，无法生成有效分块")

    # Generate embeddings
    from app.models_center.service import ModelService
    chunk_texts = [c["content"] for c in chunks_data]
    try:
        embeddings = await ModelService().embed(chunk_texts)
    except Exception as e:
        logger.error(f"Failed to regenerate embeddings for doc {doc_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Embedding 生成失败: {e}")

    # Replace chunks and update document
    await replace_document_chunks(
        db,
        doc,
        content,
        chunks_data,
        embeddings,
        content_hash,
        title=payload.title,
        meta=meta,
    )
    await _refresh_kb_counters(db, kb_id)
    await db.commit()

    # Return refreshed detail
    chunks = await list_chunks(db, doc_id)
    return _doc_to_detail(doc, chunks)
