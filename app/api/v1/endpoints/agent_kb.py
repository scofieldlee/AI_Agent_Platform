"""Agent private knowledge base endpoints.

An agent-owned KB (``visibility='agent_private'``, ``owner_agent_id=agent_id``):
- is created / managed inside the Agent config page (one-stop, no jump to the
  global knowledge center);
- is hidden from the global knowledge list for non-admin users (admin sees a
  "专属" badge, audit only);
- has its permission follow the agent: ``agent:manage`` on THIS agent is the
  only gate (no separate KB ACL);
- is auto-bound to its owning agent via ``agent_knowledge_bindings`` so the
  RAG pipeline picks it up.
"""

import logging
import os
import uuid
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_permission
from app.core.audit import audit
from app.database.session import get_db
from app.models.agent import AgentKnowledgeBinding
from app.models.knowledge import KnowledgeBase
from app.models.user import User
from app.repositories.knowledge_repo import (
    create_knowledge_base, delete_document, get_document, get_knowledge_base,
    list_documents,
)
from app.schemas.knowledge import (
    AgentPrivateKBCreate, DocumentResponse, ExcelImportResponse,
    KnowledgeBaseResponse,
)

from .agents import _check_agent_visibility

router = APIRouter(dependencies=[Depends(require_permission("agent:manage"))])

logger = logging.getLogger(__name__)

# Same archive convention as knowledge.py
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))


async def _get_owned_kb(db: AsyncSession, agent_id: int, kb_id: int) -> KnowledgeBase:
    """Fetch the KB and verify it belongs to this agent (404 hides existence)."""
    kb = await get_knowledge_base(db, kb_id)
    if (
        not kb
        or kb.visibility != "agent_private"
        or kb.owner_agent_id != agent_id
    ):
        raise HTTPException(status_code=404, detail="专属知识库不存在")
    return kb


async def _bind_agent_kb(db: AsyncSession, agent_id: int, kb_id: int) -> None:
    exists = await db.execute(
        select(AgentKnowledgeBinding).where(
            AgentKnowledgeBinding.agent_id == agent_id,
            AgentKnowledgeBinding.knowledge_base_id == kb_id,
        )
    )
    if exists.scalars().first() is None:
        db.add(AgentKnowledgeBinding(agent_id=agent_id, knowledge_base_id=kb_id))
    await db.flush()


async def _gen_private_code(db: AsyncSession, agent_code: str) -> str:
    """agent_{code}_kb, agent_{code}_kb_2, ... until unique."""
    base = f"agent_{agent_code}_kb"
    code, n = base, 1
    while True:
        dup = await db.execute(
            select(KnowledgeBase.id).where(KnowledgeBase.code == code)
        )
        if dup.scalars().first() is None:
            return code
        n += 1
        code = f"{base}_{n}"


@router.get("/{agent_id}/kb", response_model=List[KnowledgeBaseResponse])
async def list_agent_private_kbs(
    agent_id: int, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List the agent's private knowledge bases (requires agent manage)."""
    await _check_agent_visibility(db, current_user, agent_id, need="manage")
    result = await db.execute(
        select(KnowledgeBase)
        .where(KnowledgeBase.owner_agent_id == agent_id,
               KnowledgeBase.visibility == "agent_private")
        .order_by(KnowledgeBase.id)
    )
    return result.scalars().all()


@router.post("/{agent_id}/kb", response_model=KnowledgeBaseResponse, status_code=201)
@audit(action="create", resource_type="knowledge",
       resource_name=lambda ctx: getattr(ctx.get("data"), "name", None))
async def create_agent_private_kb(
    agent_id: int, data: AgentPrivateKBCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a private KB owned by this agent and auto-bind it."""
    agent = await _check_agent_visibility(db, current_user, agent_id, need="manage")

    code = await _gen_private_code(db, agent.code)
    kb = await create_knowledge_base(db, {
        "name": data.name.strip() or f"{agent.name} 专属知识库",
        "code": code,
        "description": data.description,
        "kb_type": "manual",
        "source_type": "manual",
        "visibility": "agent_private",
        "owner_agent_id": agent_id,
    })
    kb.created_by = current_user.id
    await _bind_agent_kb(db, agent_id, kb.id)
    await db.commit()
    await db.refresh(kb)
    return kb


@router.delete("/{agent_id}/kb/{kb_id}", status_code=204)
@audit(action="delete", resource_type="knowledge",
       get_resource=lambda db, agent_id, kb_id: get_knowledge_base(db, kb_id),
       resource_name_attr="name")
async def delete_agent_private_kb(
    agent_id: int, kb_id: int, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a private KB of this agent (documents/chunks cascade via FK)."""
    await _check_agent_visibility(db, current_user, agent_id, need="manage")
    kb = await _get_owned_kb(db, agent_id, kb_id)
    await db.delete(kb)
    await db.commit()
    return None


@router.post("/{agent_id}/kb/{kb_id}/promote", response_model=KnowledgeBaseResponse)
@audit(action="update", resource_type="knowledge",
       get_resource=lambda db, agent_id, kb_id: get_knowledge_base(db, kb_id),
       resource_name_attr="name")
async def promote_agent_private_kb(
    agent_id: int, kb_id: int, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Promote a private KB to the global knowledge center.

    Keeps the agent binding (the agent keeps using it); the KB becomes visible
    in the knowledge center and its permission switches to the normal KB ACL.
    """
    await _check_agent_visibility(db, current_user, agent_id, need="manage")
    kb = await _get_owned_kb(db, agent_id, kb_id)
    kb.visibility = "global"
    kb.owner_agent_id = None
    await db.commit()
    await db.refresh(kb)
    return kb


@router.get("/{agent_id}/kb/{kb_id}/documents", response_model=List[DocumentResponse])
async def list_agent_kb_documents(
    agent_id: int, kb_id: int, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _check_agent_visibility(db, current_user, agent_id, need="manage")
    await _get_owned_kb(db, agent_id, kb_id)
    return await list_documents(db, kb_id)


@router.post("/{agent_id}/kb/{kb_id}/import", response_model=ExcelImportResponse)
async def import_agent_kb_document(
    agent_id: int, kb_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Import an Excel/CSV/MD/TXT file into the agent's private KB."""
    await _check_agent_visibility(db, current_user, agent_id, need="manage")
    await _get_owned_kb(db, agent_id, kb_id)

    from app.knowledge.loaders.excel_loader import ALLOWED_EXTENSIONS, MAX_FILE_SIZE_MB

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

    # Archive the original file (best-effort, same as knowledge.py)
    saved_path = None
    try:
        archive_dir = os.path.join(PROJECT_ROOT, "uploads", "knowledge")
        os.makedirs(archive_dir, exist_ok=True)
        safe_name = f"{uuid.uuid4().hex[:12]}_{os.path.basename(filename)}"
        with open(os.path.join(archive_dir, safe_name), "wb") as f:
            f.write(content)
        saved_path = os.path.join("uploads", "knowledge", safe_name)
    except OSError as e:
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


@router.delete("/{agent_id}/kb/{kb_id}/documents/{doc_id}", status_code=204)
async def delete_agent_kb_document(
    agent_id: int, kb_id: int, doc_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _check_agent_visibility(db, current_user, agent_id, need="manage")
    await _get_owned_kb(db, agent_id, kb_id)
    doc = await get_document(db, kb_id, doc_id)
    if not doc or doc.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="Document not found")
    await delete_document(db, doc)
    from app.api.v1.endpoints.knowledge import _refresh_kb_counters
    await _refresh_kb_counters(db, kb_id)
    await db.commit()
    return None
