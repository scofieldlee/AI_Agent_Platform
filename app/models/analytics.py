"""
Analytics models: traces and spans.

Trace = one complete agent execution (one user request).
Span  = one step within a trace (one node execution).

Note: ModelUsageLog is defined in app/models/model_config.py
(model_usage_logs table) — already has trace_id; span_id added there.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, Float, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from app.database.base import Base


class AgentTrace(Base):
    """Complete agent execution trace.

    One user request -> one Trace.
    Status: running -> success | failed | human_transfer.
    """

    __tablename__ = "agent_traces"

    trace_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    agent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("agents.id"), nullable=True, index=True)
    conversation_id: Mapped[Optional[int]] = mapped_column(ForeignKey("conversations.id"), nullable=True, index=True)
    workflow_id: Mapped[Optional[int]] = mapped_column(ForeignKey("workflows.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="running", index=True)
    input_data: Mapped[Optional[dict]] = mapped_column("input", JSONB, default=dict)
    output_data: Mapped[Optional[dict]] = mapped_column("output", JSONB, default=dict)
    intent: Mapped[Optional[str]] = mapped_column(String(50))
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    total_tokens: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    total_cost: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)


class AgentSpan(Base):
    """One execution step within a trace.

    One node execution (intent, knowledge, tool, llm, human) = one Span.
    """

    __tablename__ = "agent_spans"

    trace_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    span_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    parent_span_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    node_name: Mapped[str] = mapped_column(String(100), nullable=False)
    node_type: Mapped[str] = mapped_column(String(50), default="workflow")
    status: Mapped[str] = mapped_column(String(30), default="running")
    input_data: Mapped[Optional[dict]] = mapped_column("input", JSONB, default=dict)
    output_data: Mapped[Optional[dict]] = mapped_column("output", JSONB, default=dict)
    token_usage: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    error: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
