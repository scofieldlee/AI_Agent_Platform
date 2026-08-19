"""
AI Employee models: employee, agent bindings, tasks and steps.

Layer relationship:
  - Workflow manages Agent internals (intent -> knowledge -> tool -> llm -> human)
  - AI Employee manages Agent-to-Agent orchestration (DAG / Supervisor)
  - EmployeeRuntime never touches LangGraph; it calls AgentRuntime.execute_task().
"""

from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    String, Text, Integer, ForeignKey, Boolean, DateTime,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from app.database.base import Base


class AIEmployee(Base):
    """AI Employee: a multi-Agent collaborative role for business goals.

    Lifecycle: draft -> published -> disabled.
    """

    __tablename__ = "ai_employees"

    tenant_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    role: Mapped[Optional[str]] = mapped_column(String(100))
    goal: Mapped[Optional[str]] = mapped_column(Text)
    role_prompt: Mapped[Optional[str]] = mapped_column(Text)
    orchestration_mode: Mapped[str] = mapped_column(
        String(20), default="dag", index=True)  # dag / supervisor
    supervisor_agent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    # draft / published / disabled
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    # config: {
    #   "max_agent_calls": 20,
    #   "supervisor_max_rounds": 15,
    #   "step_timeout_seconds": 300,
    #   "max_retries": 1,
    #   "fail_fast": false,
    #   "summarize_with_llm": false,
    # }
    created_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    bindings: Mapped[List["AIEmployeeAgent"]] = relationship(
        back_populates="employee", lazy="selectin",
        cascade="all, delete-orphan", order_by="AIEmployeeAgent.priority",
    )


class AIEmployeeAgent(Base):
    """Employee-Agent binding with DAG dependency info."""

    __tablename__ = "ai_employee_agents"
    __table_args__ = (
        UniqueConstraint("employee_id", "agent_id", name="uq_employee_agent"),
    )

    tenant_id: Mapped[Optional[int]] = mapped_column(Integer)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("ai_employees.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id: Mapped[int] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[Optional[str]] = mapped_column(String(100))
    # team role: analyzer / researcher / generator / reviewer ...
    priority: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    depends_on: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    # list of agent_id that this binding depends on (DAG mode)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    # {"timeout_seconds": 300, "max_retries": 1}

    employee: Mapped["AIEmployee"] = relationship(back_populates="bindings")


class AIEmployeeTask(Base):
    """Task instance: a complete business job assigned to an AI Employee."""

    __tablename__ = "ai_employee_tasks"

    tenant_id: Mapped[Optional[int]] = mapped_column(Integer)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("ai_employees.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(300))
    input: Mapped[dict] = mapped_column(JSONB, default=dict)
    context: Mapped[dict] = mapped_column(JSONB, default=dict)
    employee_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    # snapshot: {mode, supervisor_agent_id, config, role_prompt,
    #           agents: [{agent_id, name, role, description, depends_on, config}]}
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    # pending / running / waiting_human / completed / failed / cancelled
    current_step_id: Mapped[Optional[int]] = mapped_column(Integer)
    result: Mapped[Optional[dict]] = mapped_column(JSONB)
    error: Mapped[Optional[dict]] = mapped_column(JSONB)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)

    steps: Mapped[List["AIEmployeeTaskStep"]] = relationship(
        back_populates="task", lazy="selectin",
        cascade="all, delete-orphan", order_by="AIEmployeeTaskStep.id",
    )


class AIEmployeeTaskStep(Base):
    """Task step: one Agent's complete execution within a Task."""

    __tablename__ = "ai_employee_task_steps"

    tenant_id: Mapped[Optional[int]] = mapped_column(Integer)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("ai_employee_tasks.id", ondelete="CASCADE"),
        nullable=False, index=True)
    agent_id: Mapped[int] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    step_key: Mapped[str] = mapped_column(String(100), nullable=False)
    # DAG: "agent_{agent_id}"; Supervisor: "round{N}_agent{agent_id}"
    role: Mapped[Optional[str]] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    # pending / running / completed / failed / skipped / cancelled
    input: Mapped[Optional[dict]] = mapped_column(JSONB)
    # {instruction: str, upstream: {step_key: AgentResult}}
    output: Mapped[Optional[dict]] = mapped_column(JSONB)
    # AgentResult: {success, summary, data, metadata}
    context_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB)
    depends_on: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    # list of step_key that this step depends on
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    trace_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    error: Mapped[Optional[dict]] = mapped_column(JSONB)

    task: Mapped["AIEmployeeTask"] = relationship(back_populates="steps")
