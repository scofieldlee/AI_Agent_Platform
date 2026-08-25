"""Multimodal Knowledge Base — mm_knowledge_units model (统一知识单元)."""

from typing import Optional
from sqlalchemy import String, Text, Integer, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from app.database.base import Base


class KnowledgeUnit(Base):
    """统一知识单元：多模态检索的基本单位。

    - 图片 → 1 个 image unit
    - 视频 → N 个 shot units（每个镜头一个）
    - 音频 → N 个 segment units（每段一个）
    - PPT  → N 个 slide units（每页一个）

    content 为文本化描述（拼接 description + 关键 metadata），用于 Embedding。
    扩展详情表（mm_video_shots / mm_audio_segments / mm_ppt_slides）通过 unit_id 关联。
    """
    __tablename__ = "mm_knowledge_units"
    __table_args__ = (
        UniqueConstraint("asset_id", "unit_type", "unit_index",
                         name="uq_mm_unit_per_asset"),
    )

    knowledge_base_id: Mapped[int] = mapped_column(
        ForeignKey("mm_knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("mm_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    unit_type: Mapped[str] = mapped_column(String(20), nullable=False)  # image / shot / segment / slide
    unit_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 同 asset 内序号

    content: Mapped[Optional[str]] = mapped_column(Text)        # 文本化描述（用于 Embedding）
    description: Mapped[Optional[str]] = mapped_column(Text)    # AI 生成描述
    meta: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    # 视频/音频时间轴
    start_time: Mapped[Optional[float]] = mapped_column(Float)
    end_time: Mapped[Optional[float]] = mapped_column(Float)

    # 视觉素材
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String(1000))
    frame_index: Mapped[Optional[int]] = mapped_column(Integer)

    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending / indexed / error

    def __repr__(self) -> str:
        return f"<KnowledgeUnit id={self.id} asset_id={self.asset_id} type={self.unit_type} idx={self.unit_index}>"
