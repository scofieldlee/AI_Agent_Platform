"""QA sediment endpoints: submit drafts from conversations, curate & publish
into knowledge bases."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_permission
from app.database.session import get_db
from app.models.user import User
from app.services import qa_sediment_service

router = APIRouter()


class SedimentSubmitRequest(BaseModel):
    knowledge_base_id: int
    question: str
    answer: str
    original_question: Optional[str] = None
    original_answer: Optional[str] = None
    conversation_id: Optional[int] = None
    message_id: Optional[int] = None
    agent_id: Optional[int] = None
    edit_note: Optional[str] = None


class SedimentUpdateRequest(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None
    knowledge_base_id: Optional[int] = None   # only honored for pending drafts
    edit_note: Optional[str] = None


def _entry_dict(e) -> dict:
    return {
        "id": e.id,
        "knowledge_base_id": e.knowledge_base_id,
        "question": e.question,
        "answer": e.answer,
        "original_question": e.original_question,
        "original_answer": e.original_answer,
        "conversation_id": e.conversation_id,
        "message_id": e.message_id,
        "agent_id": e.agent_id,
        "status": e.status,
        "document_id": e.document_id,
        "created_by": e.created_by,
        "published_by": e.published_by,
        "edit_note": e.edit_note,
        "published_at": e.published_at.isoformat() if e.published_at else None,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }


@router.post("/submit", dependencies=[Depends(require_permission("conversation:view"))])
async def submit_endpoint(
    payload: SedimentSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit a QA draft from a conversation answer (AI drafts, human curates)."""
    entry = await qa_sediment_service.submit_draft(
        db,
        knowledge_base_id=payload.knowledge_base_id,
        question=payload.question,
        answer=payload.answer,
        original_question=payload.original_question,
        original_answer=payload.original_answer,
        conversation_id=payload.conversation_id,
        message_id=payload.message_id,
        agent_id=payload.agent_id,
        created_by=current_user.id,
        edit_note=payload.edit_note,
    )
    await db.commit()
    return _entry_dict(entry)


@router.get("", dependencies=[Depends(require_permission("knowledge:view"))])
async def list_endpoint(
    status: Optional[str] = None,
    knowledge_base_id: Optional[int] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    entries = await qa_sediment_service.list_entries(
        db, status=status, knowledge_base_id=knowledge_base_id, limit=limit)
    return {"items": [_entry_dict(e) for e in entries]}


@router.get("/{entry_id}", dependencies=[Depends(require_permission("knowledge:view"))])
async def get_endpoint(entry_id: int, db: AsyncSession = Depends(get_db)):
    entry = await qa_sediment_service.get_entry(db, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="条目不存在")
    return _entry_dict(entry)


@router.put("/{entry_id}", dependencies=[Depends(require_permission("knowledge:manage"))])
async def update_endpoint(
    entry_id: int,
    payload: SedimentUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Edit a draft or a published entry (published entries re-embed on next publish)."""
    entry = await qa_sediment_service.get_entry(db, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="条目不存在")
    if entry.status == "rejected":
        raise HTTPException(status_code=400, detail="已拒绝的条目不可编辑")
    entry = await qa_sediment_service.update_entry(
        db, entry,
        question=payload.question, answer=payload.answer,
        knowledge_base_id=payload.knowledge_base_id, edit_note=payload.edit_note,
    )
    await db.commit()
    return _entry_dict(entry)


@router.post("/{entry_id}/publish", dependencies=[Depends(require_permission("knowledge:manage"))])
async def publish_endpoint(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Publish (or re-publish) a QA entry into the knowledge base index."""
    entry = await qa_sediment_service.get_entry(db, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="条目不存在")
    if entry.status == "rejected":
        raise HTTPException(status_code=400, detail="已拒绝的条目不可发布")
    try:
        entry = await qa_sediment_service.publish_entry(db, entry, current_user.id)
        await db.commit()
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    return _entry_dict(entry)


@router.post("/{entry_id}/reject", dependencies=[Depends(require_permission("knowledge:manage"))])
async def reject_endpoint(entry_id: int, db: AsyncSession = Depends(get_db)):
    """Reject a draft, or unpublish a published entry (removes its index)."""
    entry = await qa_sediment_service.get_entry(db, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="条目不存在")
    entry = await qa_sediment_service.reject_entry(db, entry)
    await db.commit()
    return _entry_dict(entry)


@router.delete("/{entry_id}", dependencies=[Depends(require_permission("knowledge:manage"))])
async def delete_endpoint(entry_id: int, db: AsyncSession = Depends(get_db)):
    """Delete entry (published ones also remove their backing document + chunks)."""
    entry = await qa_sediment_service.get_entry(db, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="条目不存在")
    await qa_sediment_service.delete_entry(db, entry)
    await db.commit()
    return {"deleted": True}
