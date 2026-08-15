"""
Knowledge models: knowledge bases, documents, chunks, embeddings.
Supports Obsidian Markdown -> RAG pipeline.
"""

from typing import Optional, List
from sqlalchemy import String, Text, Integer, Float, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from pgvector.sqlalchemy import Vector

from app.core.config import settings
from app.database.base import Base


class KnowledgeBase(Base):
    """Knowledge base (e.g., product knowledge, FAQ, after-sales)."""

    __tablename__ = "knowledge_bases"

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    kb_type: Mapped[str] = mapped_column(String(50), default="product")  # product, faq, manual, after_sale
    source_type: Mapped[str] = mapped_column(String(50), default="obsidian")  # obsidian, file, api, manual
    source_path: Mapped[Optional[str]] = mapped_column(String(500))  # e.g., Obsidian vault path
    config: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    # config: chunk_size, chunk_overlap, embedding_model, etc.
    document_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    documents: Mapped[List["Document"]] = relationship(
        back_populates="knowledge_base", lazy="selectin"
    )


class Document(Base):
    """Source document (e.g., one Obsidian .md file)."""

    __tablename__ = "documents"

    knowledge_base_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source_path: Mapped[Optional[str]] = mapped_column(String(1000))  # file path or URL
    source_type: Mapped[str] = mapped_column(String(50), default="markdown")  # markdown, pdf, html, text
    content_hash: Mapped[Optional[str]] = mapped_column(String(64))  # for change detection
    meta: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)
    # metadata: frontmatter fields (product_name, brand, category, price, etc.)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, processing, ready, error
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)

    knowledge_base: Mapped["KnowledgeBase"] = relationship(back_populates="documents")
    chunks: Mapped[List["Chunk"]] = relationship(
        back_populates="document", lazy="selectin", cascade="all, delete-orphan"
    )


class Chunk(Base):
    """Document chunk with embedding vector.

    Chunk strategy: Markdown Header Splitter + Recursive Splitter.
    """

    __tablename__ = "chunks"

    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)  # order within document
    content: Mapped[str] = mapped_column(Text, nullable=False)
    section: Mapped[Optional[str]] = mapped_column(String(500))  # e.g., "商品基础信息", "产品参数"
    token_count: Mapped[Optional[int]] = mapped_column(Integer)
    meta: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)
    # metadata: document_id, title, section, source, product_name, brand, category
    embedding: Mapped[Optional[list]] = mapped_column(Vector(settings.embedding_dimension))

    document: Mapped["Document"] = relationship(back_populates="chunks")
