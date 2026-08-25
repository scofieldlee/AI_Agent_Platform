"""Multimodal Knowledge Base — mm_assets model."""

from typing import Optional
from datetime import datetime
from sqlalchemy import String, BigInteger, Integer, ForeignKey, UniqueConstraint, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from app.database.base import Base


class MultimodalAsset(Base):
    """素材：一个真实存在的原始数字资产（图片/视频/音频/PPT/...）。

    状态机见 app/multimodal/constants.py AssetStatus。
    软删除：deleted_at 非空表示进入回收站。
    """
    __tablename__ = "mm_assets"
    __table_args__ = (
        UniqueConstraint("knowledge_base_id", "asset_code", name="uq_mm_asset_code_per_kb"),
    )

    knowledge_base_id: Mapped[int] = mapped_column(
        ForeignKey("mm_knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)

    asset_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # IMG-000001
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[Optional[str]] = mapped_column(String(500))
    file_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # image/video/audio/ppt/pdf/document/other
    mime_type: Mapped[Optional[str]] = mapped_column(String(100))
    file_size: Mapped[int] = mapped_column(BigInteger, default=0)  # 字节

    # 存储路径（相对 storage 根目录）
    storage_path: Mapped[Optional[str]] = mapped_column(String(1000))    # original 文件
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String(1000))  # 缩略图
    preview_path: Mapped[Optional[str]] = mapped_column(String(1000))    # Web 预览版

    status: Mapped[str] = mapped_column(String(20), default="uploaded", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    current_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("mm_asset_versions.id", ondelete="SET NULL", use_alter=True), nullable=True)

    # 附加属性（如用户自定义分类 category 等）
    attributes: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    def __repr__(self) -> str:
        return f"<MultimodalAsset id={self.id} code={self.asset_code} type={self.file_type} status={self.status}>"
