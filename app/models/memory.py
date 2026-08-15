"""
Memory models: long-term memories with embeddings.
Short-term memory uses Redis (not persisted in PostgreSQL).
"""

from typing import Optional
from sqlalchemy import String, Text, Float, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from pgvector.sqlalchemy import Vector

from app.core.config import settings
from app.database.base import Base


class Memory(Base):
    """Long-term memory entry.

    Types: preference, fact, behavior, history, skill.
    Lifecycle: active -> expired -> archived.
    """

    __tablename__ = "memories"

    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    agent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("agents.id"), nullable=True, index=True)
    memory_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # preference, fact, behavior, history, skill
    content: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[float] = mapped_column(Float, default=0.5)  # 0.0-1.0
    embedding: Mapped[Optional[list]] = mapped_column(Vector(settings.embedding_dimension))
    meta: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)  # active, expired, archived
    access_count: Mapped[int] = mapped_column(Integer, default=0)
    last_accessed_at: Mapped[Optional[str]] = mapped_column(String(50))
