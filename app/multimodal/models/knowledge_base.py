"""Multimodal Knowledge Base — mm_knowledge_bases model."""

from typing import Optional
from sqlalchemy import String, Integer, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from app.database.base import Base


class MultimodalKnowledgeBase(Base):
    """多模态知识库。与文档知识库 (knowledge_bases) 完全隔离。

    存储配置 / Embedding 配置 / 视觉模型配置均为 JSONB，
    便于后续切换存储后端（local → MinIO/OSS）或更换模型。
    """
    __tablename__ = "mm_knowledge_bases"

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(String(2000))
    kb_type: Mapped[str] = mapped_column(String(50), default="multimodal", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)  # active / archived

    # 配置 JSONB
    storage_config: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    embedding_config: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    vision_model_config: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    analysis_config: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    asset_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def __repr__(self) -> str:
        return f"<MultimodalKnowledgeBase id={self.id} name={self.name!r}>"
