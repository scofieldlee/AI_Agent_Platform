"""Multimodal Knowledge Base — mm_asset_versions model (V1 简版)."""

from typing import Optional
from sqlalchemy import String, BigInteger, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from app.database.base import Base


class AssetVersion(Base):
    """素材版本历史（V1 简版：仅记录快照，不做 Git 式管理）。"""
    __tablename__ = "mm_asset_versions"
    __table_args__ = (
        UniqueConstraint("asset_id", "version", name="uq_mm_asset_version"),
    )

    asset_id: Mapped[int] = mapped_column(
        ForeignKey("mm_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[Optional[str]] = mapped_column(String(1000))
    file_size: Mapped[int] = mapped_column(BigInteger, default=0)
    metadata: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    def __repr__(self) -> str:
        return f"<AssetVersion asset_id={self.asset_id} v{self.version}>"
