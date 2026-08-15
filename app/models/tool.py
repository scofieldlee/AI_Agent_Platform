"""
Tool models: tool definitions, versions, schemas.
"""

from typing import Optional
from sqlalchemy import String, Text, Integer, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

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
