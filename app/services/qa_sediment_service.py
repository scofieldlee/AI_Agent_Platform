"""QA sediment service: conversation answers -> human-edited knowledge entries.

Publish path (plan A "QA as a minimal document"):
  1. create a Document in the target KB (source_type='conversation')
  2. create ONE Chunk (content = Q+A joined), embedding via Model Center (bge 512d)
  3. link qa_entry.document_id; re-publishing replaces content + re-embeds in place
"""

import hashlib
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import now
from app.models.knowledge import Chunk, Document, KnowledgeBase
from app.models.knowledge_qa import KnowledgeQaEntry


def _chunk_content(question: str, answer: str) -> str:
    q = (question or "").strip()
    a = (answer or "").strip()
    return f"问：{q}\n答：{a}"


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


async def submit_draft(
    db: AsyncSession,
    knowledge_base_id: int,
    question: str,
    answer: str,
    original_question: Optional[str] = None,
    original_answer: Optional[str] = None,
    conversation_id: Optional[int] = None,
    message_id: Optional[int] = None,
    agent_id: Optional[int] = None,
    created_by: Optional[int] = None,
    edit_note: Optional[str] = None,
) -> KnowledgeQaEntry:
    entry = KnowledgeQaEntry(
        knowledge_base_id=knowledge_base_id,
        question=question.strip(),
        answer=answer.strip(),
        original_question=original_question,
        original_answer=original_answer,
        conversation_id=conversation_id,
        message_id=message_id,
        agent_id=agent_id,
        status="pending",
        created_by=created_by,
        edit_note=edit_note,
    )
    db.add(entry)
    await db.flush()
    return entry


async def get_entry(db: AsyncSession, entry_id: int) -> Optional[KnowledgeQaEntry]:
    return await db.get(KnowledgeQaEntry, entry_id)


async def list_entries(
    db: AsyncSession,
    status: Optional[str] = None,
    knowledge_base_id: Optional[int] = None,
    limit: int = 100,
) -> List[KnowledgeQaEntry]:
    stmt = select(KnowledgeQaEntry).order_by(KnowledgeQaEntry.id.desc()).limit(limit)
    if status:
        stmt = stmt.where(KnowledgeQaEntry.status == status)
    if knowledge_base_id:
        stmt = stmt.where(KnowledgeQaEntry.knowledge_base_id == knowledge_base_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_entry(
    db: AsyncSession, entry: KnowledgeQaEntry,
    question: Optional[str] = None, answer: Optional[str] = None,
    knowledge_base_id: Optional[int] = None, edit_note: Optional[str] = None,
) -> KnowledgeQaEntry:
    """Update draft fields. Pending entries may switch KB; published entries
    keep their KB (they already have a document + chunk there)."""
    if entry.status == "pending":
        if knowledge_base_id:
            entry.knowledge_base_id = knowledge_base_id
    if question is not None and question.strip():
        entry.question = question.strip()
    if answer is not None and answer.strip():
        entry.answer = answer.strip()
    if edit_note is not None:
        entry.edit_note = edit_note
    await db.flush()
    return entry


async def publish_entry(db: AsyncSession, entry: KnowledgeQaEntry, publisher_id: int) -> KnowledgeQaEntry:
    """Create/update the backing document + chunk and embed it.

    - First publish: create document + chunk, embed, link back.
    - Re-publish (after edit): replace chunk content + re-embed in place.
    """
    kb = await db.get(KnowledgeBase, entry.knowledge_base_id)
    if not kb:
        raise ValueError(f"目标知识库不存在 (id={entry.knowledge_base_id})")

    content = _chunk_content(entry.question, entry.answer)

    if entry.status == "published" and entry.document_id:
        # Re-publish: update existing document + chunk in place
        doc = await db.get(Document, entry.document_id)
        if doc is None:
            # Document was deleted externally; fall through to create anew
            entry.document_id = None
        else:
            doc.title = entry.question[:500]
            doc.content_hash = _content_hash(content)
            doc.updated_at = now()
            chunk_result = await db.execute(
                select(Chunk).where(Chunk.document_id == doc.id)
            )
            chunk = chunk_result.scalars().first()
            if chunk:
                from app.models_center.service import ModelService
                embeddings = await ModelService().embed([content])
                chunk.content = content
                chunk.section = entry.question[:500]
                chunk.meta = {
                    "origin": "qa_sediment", "qa_entry_id": entry.id,
                    "title": entry.question[:200],
                }
                chunk.token_count = len(content)
                chunk.embedding = embeddings[0] if embeddings and embeddings[0] else None
            entry.published_by = publisher_id
            entry.published_at = now()
            await db.flush()
            return entry

    # First publish: create document + chunk
    doc = Document(
        knowledge_base_id=entry.knowledge_base_id,
        title=entry.question[:500],
        source_type="conversation",
        content_hash=_content_hash(content),
        meta={
            "origin": "qa_sediment",
            "qa_entry_id": entry.id,
            "original_question": entry.original_question,
            "original_answer": entry.original_answer,
            "conversation_id": entry.conversation_id,
            "message_id": entry.message_id,
            "agent_id": entry.agent_id,
            "edited_by": entry.created_by,
            "edit_note": entry.edit_note,
        },
        status="ready",
        chunk_count=1,
    )
    db.add(doc)
    await db.flush()  # get doc.id

    from app.models_center.service import ModelService
    embeddings = await ModelService().embed([content])
    embedding = embeddings[0] if embeddings and embeddings[0] else None

    chunk = Chunk(
        document_id=doc.id,
        chunk_index=0,
        content=content,
        section=entry.question[:500],
        token_count=len(content),
        meta={"origin": "qa_sediment", "qa_entry_id": entry.id, "title": entry.question[:200]},
        embedding=embedding,
    )
    db.add(chunk)

    # Update KB counters
    kb.document_count = (kb.document_count or 0) + 1
    kb.chunk_count = (kb.chunk_count or 0) + 1

    entry.document_id = doc.id
    entry.status = "published"
    entry.published_by = publisher_id
    entry.published_at = now()
    await db.flush()
    return entry


async def reject_entry(db: AsyncSession, entry: KnowledgeQaEntry) -> KnowledgeQaEntry:
    """Reject a pending draft (or unpublish+remove a published one's index)."""
    if entry.status == "published" and entry.document_id:
        # Remove document (chunks cascade) and decrement KB counters
        doc = await db.get(Document, entry.document_id)
        if doc:
            kb = await db.get(KnowledgeBase, entry.knowledge_base_id)
            if kb:
                kb.document_count = max(0, (kb.document_count or 0) - 1)
                kb.chunk_count = max(0, (kb.chunk_count or 0) - doc.chunk_count)
            await db.delete(doc)
        entry.document_id = None
    entry.status = "rejected"
    await db.flush()
    return entry


async def delete_entry(db: AsyncSession, entry: KnowledgeQaEntry) -> None:
    """Delete entry; published ones also remove their backing document."""
    if entry.status == "published" and entry.document_id:
        doc = await db.get(Document, entry.document_id)
        if doc:
            kb = await db.get(KnowledgeBase, entry.knowledge_base_id)
            if kb:
                kb.document_count = max(0, (kb.document_count or 0) - 1)
                kb.chunk_count = max(0, (kb.chunk_count or 0) - doc.chunk_count)
            await db.delete(doc)
    await db.delete(entry)
    await db.flush()
