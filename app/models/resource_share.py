"""Resource share model: user/role level ACL for owned resources (agents,
AI employees, ...)."""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutils import now
from app.database.base import Base


class ResourceShare(Base):
    """A grant of permission over a resource to a user or a role.

    resource_type: 'agent' | 'employee' (extensible)
    principal_type: 'user' | 'role'
    permission: 'chat' | 'view' | 'manage'  (manage ⊃ view ⊃ chat)
    """

    __tablename__ = "resource_shares"

    resource_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    resource_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    principal_type: Mapped[str] = mapped_column(String(10), nullable=False)
    principal_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    permission: Mapped[str] = mapped_column(String(20), nullable=False)
    granted_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "resource_type", "resource_id", "principal_type", "principal_id",
            name="uq_resource_share_principal",
        ),
    )
