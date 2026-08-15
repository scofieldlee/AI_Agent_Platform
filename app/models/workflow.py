"""
Workflow models: workflow definitions, nodes, edges, and run records.
"""

from typing import Optional, List
from sqlalchemy import String, Text, Integer, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from app.database.base import Base


class Workflow(Base):
    """LangGraph workflow definition.

    Types: static (fixed), dynamic (planner-generated), hybrid (default).
    """

    __tablename__ = "workflows"

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    workflow_type: Mapped[str] = mapped_column(String(20), default="hybrid")  # static, dynamic, hybrid
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    version: Mapped[str] = mapped_column(String(20), default="0.1.0")
    graph_config: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    # graph_config: nodes, edges, entry_point, conditional_edges
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    nodes: Mapped[List["WorkflowNode"]] = relationship(
        back_populates="workflow", lazy="selectin", cascade="all, delete-orphan"
    )


class WorkflowNode(Base):
    """Workflow node definition (intent, knowledge_search, tool, llm, human, etc.)."""

    __tablename__ = "workflow_nodes"

    workflow_id: Mapped[int] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True)
    node_id: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g., "intent", "knowledge_search"
    node_type: Mapped[str] = mapped_column(String(50), nullable=False)  # intent, knowledge, tool, llm, human, router, start, end
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    config: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    # config: node-specific settings (prompt template, model policy, tool_id, etc.)

    workflow: Mapped["Workflow"] = relationship(back_populates="nodes")


class WorkflowRun(Base):
    """Workflow execution record (for analytics and debugging)."""

    __tablename__ = "workflow_runs"

    workflow_id: Mapped[int] = mapped_column(ForeignKey("workflows.id"), nullable=False, index=True)
    conversation_id: Mapped[Optional[int]] = mapped_column(ForeignKey("conversations.id"), nullable=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running, completed, failed, interrupted
    input_data: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    output_data: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    error: Mapped[Optional[str]] = mapped_column(Text)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
