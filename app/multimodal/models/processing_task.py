"""Multimodal Knowledge Base — mm_processing_tasks model."""

from typing import Optional
from datetime import datetime
from sqlalchemy import String, Integer, ForeignKey, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from app.database.base import Base


class ProcessingTask(Base):
    """异步处理任务记录（上传/缩略图/分析/ASR/Embedding/索引等）。

    用于调试、失败重试、成本统计、性能分析。
    """
    __tablename__ = "mm_processing_tasks"

    asset_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("mm_assets.id", ondelete="CASCADE"), nullable=True, index=True)
    knowledge_base_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("mm_knowledge_bases.id", ondelete="CASCADE"), nullable=True, index=True)
    task_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)

    model: Mapped[Optional[str]] = mapped_column(String(100))  # 使用的模型名
    input: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    output: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    error: Mapped[Optional[str]] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<ProcessingTask id={self.id} type={self.task_type} status={self.status}>"
