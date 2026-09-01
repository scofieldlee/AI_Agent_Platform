"""
审计日志模型（audit_logs）。

记录系统操作日志：谁在什么时间对什么资源做了什么操作。
设计要点（与 docs/操作日志方案设计.md 对齐）：
- 存 username / resource_name 快照，用户或资源被删除后仍可追溯；
- request_id 贯穿请求链路（应用日志、Agent trace 均可串联）；
- request_body / changes 用 JSONB，入库前强制脱敏；
- tenant_id 预留多租户。
"""

from typing import Optional
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class AuditLog(Base):
    """系统操作日志（审计日志）一行。"""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_created_at", "created_at"),
        Index("ix_audit_logs_user_created", "user_id", "created_at"),
        Index("ix_audit_logs_resource", "resource_type", "resource_id"),
        Index("ix_audit_logs_action", "action"),
    )

    request_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True,
        comment="请求唯一 ID，串联应用日志",
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True,
        comment="操作人（可空：匿名接口）",
    )
    username: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
        comment="用户名快照（用户被删后仍可追溯）",
    )
    action: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
        comment="动作: create/update/delete/login/logout/approve/export/execute",
    )
    resource_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
        comment="资源: asset/agent/user/role/workflow/knowledge...",
    )
    resource_id: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
        comment="资源 ID",
    )
    resource_name: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True,
        comment="资源名称快照（如素材名），删除后仍可读",
    )
    summary: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="人类可读描述，如：删除了素材 ruko-f11mini",
    )
    method: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45), nullable=True,
        comment="客户端 IP（兼容 IPv6）",
    )
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    request_body: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True,
        comment="请求体（已脱敏，可配置为不存）",
    )
    changes: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True,
        comment="字段级变更: {\"field\": {\"before\": x, \"after\": y}}",
    )
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tenant_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    # created_at 由 Base 提供（DateTime(timezone=True)），操作时间用 timeutils.now() 写入
    # 这里覆盖默认 server_default，仍保留 server_default=func.now()，语义一致。
