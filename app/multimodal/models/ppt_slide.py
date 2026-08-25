"""Multimodal Knowledge Base — mm_ppt_slides model."""

from typing import Optional
from sqlalchemy import String, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from app.database.base import Base


class PptSlide(Base):
    """PPT 页详情表（KnowledgeUnit(unit_type=slide) 的扩展）。"""
    __tablename__ = "mm_ppt_slides"

    unit_id: Mapped[int] = mapped_column(
        ForeignKey("mm_knowledge_units.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("mm_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    slide_index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(500))
    image_path: Mapped[Optional[str]] = mapped_column(String(1000))  # 页面截图
    text_content: Mapped[Optional[str]] = mapped_column(Text)        # 页面文本
    slide_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    def __repr__(self) -> str:
        return f"<PptSlide unit_id={self.unit_id} idx={self.slide_index} title={self.title!r}>"
