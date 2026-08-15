"""
SQLAlchemy 2.0 Base Model.
All models inherit from Base, getting id/created_at/updated_at for free.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, BigInteger, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """
    Base model for all database tables.

    Provides:
    - id: BIGSERIAL primary key
    - created_at: auto-set on insert
    - updated_at: auto-updated on update
    - tenant_id: multi-tenant isolation (reserved, nullable for MVP)
    """

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    """Mixin for soft-delete support via status or deleted_at."""

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
