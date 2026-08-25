"""Multimodal Knowledge Base — mm_asset_metadata model."""

from typing import Optional
from sqlalchemy import String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from app.database.base import Base


class AssetMetadata(Base):
    """素材元数据。三来源：
    - system: file_type/size/resolution/duration/fps/page_count（程序提取）
    - ai: description/style/scene/objects/composition/lighting/tags/ocr/usage（模型生成）
    - user: category/tags/usage/copyright/remark（人工维护）
    """
    __tablename__ = "mm_asset_metadata"
    __table_args__ = (
        UniqueConstraint("asset_id", "metadata_type", name="uq_mm_metadata_per_asset_type"),
    )

    asset_id: Mapped[int] = mapped_column(
        ForeignKey("mm_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    metadata_type: Mapped[str] = mapped_column(String(20), nullable=False)  # system / ai / user
    meta: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    def __repr__(self) -> str:
        return f"<AssetMetadata asset_id={self.asset_id} type={self.metadata_type}>"
