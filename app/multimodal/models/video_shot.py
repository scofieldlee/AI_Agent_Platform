"""Multimodal Knowledge Base — mm_video_shots model."""

from typing import Optional
from sqlalchemy import String, Float, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from app.database.base import Base


class VideoShot(Base):
    """视频镜头详情表（KnowledgeUnit(unit_type=shot) 的扩展）。"""
    __tablename__ = "mm_video_shots"

    unit_id: Mapped[int] = mapped_column(
        ForeignKey("mm_knowledge_units.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("mm_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    shot_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[float] = mapped_column(Float, default=0.0)
    end_time: Mapped[float] = mapped_column(Float, default=0.0)
    duration: Mapped[float] = mapped_column(Float, default=0.0)
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String(1000))
    keyframe_path: Mapped[Optional[str]] = mapped_column(String(1000))
    shot_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    def __repr__(self) -> str:
        return f"<VideoShot unit_id={self.unit_id} idx={self.shot_index} {self.start_time}-{self.end_time}s>"
