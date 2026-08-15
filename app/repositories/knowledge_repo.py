"""
Knowledge base repository: data access for knowledge bases and documents.
"""

from typing import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeBase, Document


async def list_knowledge_bases(db: AsyncSession) -> List[KnowledgeBase]:
    """List all knowledge bases ordered by most recent."""
    result = await db.execute(select(KnowledgeBase).order_by(KnowledgeBase.id.desc()))
    return list(result.scalars().all())


async def get_knowledge_base(db: AsyncSession, kb_id: int) -> KnowledgeBase:
    """Get a knowledge base by ID."""
    return await db.get(KnowledgeBase, kb_id)


async def create_knowledge_base(db: AsyncSession, data: dict) -> KnowledgeBase:
    """Create a new knowledge base."""
    kb = KnowledgeBase(**data)
    db.add(kb)
    await db.flush()
    await db.refresh(kb)
    return kb


async def list_documents(db: AsyncSession, kb_id: int) -> List[Document]:
    """List documents in a knowledge base."""
    result = await db.execute(
        select(Document).where(Document.knowledge_base_id == kb_id).order_by(Document.id.desc())
    )
    return list(result.scalars().all())
