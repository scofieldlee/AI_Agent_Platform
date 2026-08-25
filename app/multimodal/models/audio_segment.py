"""Multimodal Knowledge Base — mm_audio_segments model."""

from typing import Optional
from sqlalchemy import String, Float, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from app.database.base import Base


class AudioSegment(Base):
    """音频分段详情表（KnowledgeUnit(unit_type=segment) 的扩展）。"""
    __tablename__ = "mm_audio_segments"

    unit_id: Mapped[int] = mapped_column(
        ForeignKey("mm_knowledge_units.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("mm_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[float] = mapped_column(Float, default=0.0)
    end_time: Mapped[float] = mapped_column(Float, default=0.0)
    transcript: Mapped[Optional[str]] = mapped_column(Text)          # ASR 转写文本
    speaker: Mapped[Optional[str]] = mapped_column(String(100))      # 说话人
    emotion: Mapped[Optional[str]] = mapped_column(String(50))       # 情绪
    segment_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    def __repr__(self) -> str:
        return f"<AudioSegment unit_id={self.unit_id} idx={self.segment_index} {self.start_time}-{self.end_time}s>"
