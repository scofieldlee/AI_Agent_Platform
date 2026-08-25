"""Multimodal Knowledge Base — mm_index_records model (pgvector 向量索引).

设计说明：为了支持跨模态检索（文本→图片），查询向量与索引向量必须处于同一
Embedding 空间，因此本表所有向量（无论 text/image/multimodal）统一使用
通义多模态 Embedding（multimodal-embedding-one-peace-v1, 1024 维），
通过 embedding_type 字段区分模态来源，metadata 字段支持检索时过滤。
"""

from typing import Optional
from sqlalchemy import String, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector

from app.core.config import settings
from app.database.base import Base


class IndexRecord(Base):
    """多模态向量索引记录。独立于文档知识库的 chunks.embedding，互不干扰。"""
    __tablename__ = "mm_index_records"
    __table_args__ = (
        Index("ix_mm_index_kb_vector", "knowledge_base_id",
              postgresql_using="ivfflat", postgresql_ops={"embedding": "vector_cosine_ops"}),
    )

    knowledge_base_id: Mapped[int] = mapped_column(
        ForeignKey("mm_knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("mm_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    knowledge_unit_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("mm_knowledge_units.id", ondelete="CASCADE"), nullable=True, index=True)

    embedding_type: Mapped[str] = mapped_column(String(20), default="multimodal")  # text / image / multimodal
    model_name: Mapped[Optional[str]] = mapped_column(String(100))
    embedding: Mapped[Optional[list]] = mapped_column(
        Vector(settings.multimodal_embedding_dimension))
    metadata: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)  # 检索过滤用

    def __repr__(self) -> str:
        return f"<IndexRecord id={self.id} kb={self.knowledge_base_id} asset={self.asset_id} type={self.embedding_type}>"
