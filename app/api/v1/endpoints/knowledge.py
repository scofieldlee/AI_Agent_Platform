"""Knowledge base endpoints."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.auth.dependencies import require_permission
from app.schemas.knowledge import KnowledgeBaseCreate, KnowledgeBaseResponse, DocumentResponse
from app.repositories.knowledge_repo import (
    list_knowledge_bases, get_knowledge_base, create_knowledge_base, list_documents,
)

router = APIRouter(dependencies=[Depends(require_permission("knowledge:view"))])


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
