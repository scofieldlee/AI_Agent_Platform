"""Conversation QA sediment: AI answers -> human-edited knowledge entries.

Two-stage pipeline: AI drafts (pending) -> human edits & publishes ->
document + chunk + embedding in the target knowledge base (plan A:
"QA as a minimal document", source_type='conversation').
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, ForeignKey, DateTime, BigInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutils import now
from app.database.base import Base


class KnowledgeQaEntry(Base):
    """A human-curated QA knowledge entry sourced from a conversation.

    Lifecycle: pending -> published / rejected.
    Re-editing a published entry re-embeds and replaces its chunk in place.
    """

    __tablename__ = "knowledge_qa_entries"

    knowledge_base_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_bases.id"), nullable=False, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)   # edited question
    answer: Mapped[str] = mapped_column(Text, nullable=False)     # edited answer
    original_question: Mapped[Optional[str]] = mapped_column(Text)
    original_answer: Mapped[Optional[str]] = mapped_column(Text)
    conversation_id: Mapped[Optional[int]] = mapped_column(BigInteger, index=True)
    message_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    agent_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    # pending / published / rejected
    document_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    published_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    edit_note: Mapped[Optional[str]] = mapped_column(Text)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, onupdate=now, nullable=False)
