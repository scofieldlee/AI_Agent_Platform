"""Multimodal Knowledge Base — mm_asset_tags + mm_asset_tag_relations models."""

from typing import Optional
from sqlalchemy import String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class AssetTag(Base):
    """标签字典表（独立管理，支持 ai/user 两种来源）。"""
    __tablename__ = "mm_asset_tags"
    __table_args__ = (
        UniqueConstraint("name", "source", name="uq_mm_tag_name_source"),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(10), default="user")  # ai / user
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    def __repr__(self) -> str:
        return f"<AssetTag id={self.id} name={self.name!r} source={self.source}>"


class AssetTagRelation(Base):
    """素材 ↔ 标签 关联。source 区分标签挂载来源。"""
    __tablename__ = "mm_asset_tag_relations"
    __table_args__ = (
        UniqueConstraint("asset_id", "tag_id", "source", name="uq_mm_asset_tag_relation"),
    )

    asset_id: Mapped[int] = mapped_column(
        ForeignKey("mm_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("mm_asset_tags.id", ondelete="CASCADE"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(10), default="user")  # ai / user

    def __repr__(self) -> str:
        return f"<AssetTagRelation asset_id={self.asset_id} tag_id={self.tag_id} source={self.source}>"
