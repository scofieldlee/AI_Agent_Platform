"""Multimodal Knowledge Base — mm_asset_relations model."""

from typing import Optional
from sqlalchemy import String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from app.database.base import Base


class AssetRelation(Base):
    """素材之间的关联关系。
    relation_type: related / reference / derived_from / belongs_to / similar / alternative
    """
    __tablename__ = "mm_asset_relations"
    __table_args__ = (
        UniqueConstraint("source_asset_id", "target_asset_id", "relation_type",
                         name="uq_mm_asset_relation"),
    )

    source_asset_id: Mapped[int] = mapped_column(
        ForeignKey("mm_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    target_asset_id: Mapped[int] = mapped_column(
        ForeignKey("mm_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    relation_type: Mapped[str] = mapped_column(String(30), default="related")
    metadata: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    def __repr__(self) -> str:
        return (f"<AssetRelation {self.source_asset_id} -[{self.relation_type}]-> "
                f"{self.target_asset_id}>")
