"""
Knowledge base repository: data access for knowledge bases and documents.
"""

from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeBase, Document, Chunk


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


async def get_document(db: AsyncSession, kb_id: int, doc_id: int) -> Optional[Document]:
    """Get a single document by ID, scoped to a knowledge base."""
    return await db.get(Document, doc_id)


async def list_chunks(db: AsyncSession, doc_id: int) -> List[Chunk]:
    """List all chunks of a document, ordered by chunk_index."""
    result = await db.execute(
        select(Chunk).where(Chunk.document_id == doc_id).order_by(Chunk.chunk_index.asc())
    )
    return list(result.scalars().all())


async def get_chunk(db: AsyncSession, chunk_id: int) -> Optional[Chunk]:
    """Get a single chunk by ID."""
    return await db.get(Chunk, chunk_id)


async def update_document(db: AsyncSession, doc: Document, fields: dict) -> Document:
    """Apply a partial update to a document and persist it."""
    for key, value in fields.items():
        if value is not None:
            setattr(doc, key, value)
    await db.flush()
    await db.refresh(doc)
    return doc


async def delete_document(db: AsyncSession, doc: Document) -> None:
    """Delete a document (chunks cascade via FK)."""
    await db.delete(doc)
    await db.flush()


async def delete_chunk(db: AsyncSession, chunk: Chunk) -> None:
    """Delete a single chunk."""
    await db.delete(chunk)
    await db.flush()


async def replace_document_chunks(
    db: AsyncSession,
    doc: Document,
    content: str,
    chunks_data: List[dict],
    embeddings: List[Optional[List[float]]],
    content_hash: str,
    title: Optional[str] = None,
    meta: Optional[dict] = None,
) -> Document:
    """Replace all chunks of a document with newly split + embedded chunks.

    Deletes existing chunks (cascade handled at ORM level), creates new ones,
    and updates document metadata.
    """
    # Delete existing chunks
    for old in list(doc.chunks):
        await db.delete(old)
    await db.flush()

    # Create new chunks
    for chunk_data, embedding in zip(chunks_data, embeddings):
        chunk = Chunk(
            document_id=doc.id,
            chunk_index=chunk_data["chunk_index"],
            content=chunk_data["content"],
            section=chunk_data.get("section"),
            token_count=chunk_data.get("token_count"),
            meta=chunk_data.get("metadata", {}),
            embedding=embedding,
        )
        db.add(chunk)

    # Update document fields
    doc.content_hash = content_hash
    doc.chunk_count = len(chunks_data)
    doc.status = "ready"
    if title is not None:
        doc.title = title
    if meta is not None:
        doc.meta = meta

    await db.flush()
    await db.refresh(doc)
    return doc
