"""
Tool models: tool definitions, versions, schemas.
"""

from typing import Optional
from datetime import datetime
from sqlalchemy import String, Text, Integer, ForeignKey, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from app.core.timeutils import now
from app.database.base import Base


class Tool(Base):
    """Tool definition (Internal, Business, API, Database, MCP, Agent).

    One tool = one clear capability.
    Must have: input_schema, output_schema, permission check.
    """

    __tablename__ = "tools"

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)  # important for LLM tool selection
    tool_type: Mapped[str] = mapped_column(String(50), default="internal")  # internal, business, api, database, mcp, agent
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    version: Mapped[str] = mapped_column(String(20), default="1.0.0")
    input_schema: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    output_schema: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    config: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    # config: endpoint, method, headers, timeout, retry_policy, etc.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Approval gate: write-effect tools require human approval before execution
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    approval_timeout_minutes: Mapped[int] = mapped_column(Integer, default=30)


class ToolApproval(Base):
    """Human approval request for a sensitive tool execution.

    Lifecycle: pending -> approved / rejected; pending past its timeout
    becomes expired (treated as rejected).
    """

    __tablename__ = "tool_approvals"

    tool_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    agent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("agents.id"), nullable=True, index=True)
    conversation_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("conversations.id"), nullable=True, index=True)
    trace_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    params: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    # pending / approved / rejected / expired
    requester: Mapped[Optional[str]] = mapped_column(String(200))  # external user id if IM
    reviewer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    comment: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, nullable=False)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ToolExecution(Base):
    """Tool execution log for analytics and debugging."""

    __tablename__ = "tool_executions"

    tool_id: Mapped[int] = mapped_column(ForeignKey("tools.id"), nullable=False, index=True)
    agent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("agents.id"), nullable=True, index=True)
    conversation_id: Mapped[Optional[int]] = mapped_column(ForeignKey("conversations.id"), nullable=True, index=True)
    input_data: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    output_data: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="success")  # success, error, timeout
    error: Mapped[Optional[str]] = mapped_column(Text)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    trace_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
