"""
Agent models: agent definitions, versions, and bindings.
"""

import secrets
import string
from typing import Optional, List
from sqlalchemy import String, Text, Integer, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from app.database.base import Base


def _generate_chat_token(length: int = 8) -> str:
    """Generate a random alphanumeric chat token."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


class Agent(Base):
    """AI Agent definition.

    Lifecycle: draft -> testing -> published -> running -> suspended -> archived.
    """

    __tablename__ = "agents"

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    agent_type: Mapped[str] = mapped_column(String(50), default="config")  # system, config, composite
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)  # draft, testing, published, running, suspended, archived
    version: Mapped[str] = mapped_column(String(20), default="0.1.0")
    config: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    # config includes: system_prompt, model_policy, memory_config, etc.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    chat_token: Mapped[Optional[str]] = mapped_column(
        String(16), unique=True, nullable=True, index=True,
        comment="Random token for public chat URL: /chat?token=xxx"
    )

    # Relationships
    versions: Mapped[List["AgentVersion"]] = relationship(
        back_populates="agent", lazy="selectin"
    )
    workflows: Mapped[List["AgentWorkflowBinding"]] = relationship(
        back_populates="agent", lazy="selectin"
    )
    knowledge_bindings: Mapped[List["AgentKnowledgeBinding"]] = relationship(
        back_populates="agent", lazy="selectin"
    )
    tool_bindings: Mapped[List["AgentToolBinding"]] = relationship(
        back_populates="agent", lazy="selectin"
    )


class AgentVersion(Base):
    """Agent version history for rollback and audit."""

    __tablename__ = "agent_versions"

    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    config: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    changelog: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft, review, published, archived
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    agent: Mapped["Agent"] = relationship(back_populates="versions")


class AgentWorkflowBinding(Base):
    """Agent <-> Workflow binding."""

    __tablename__ = "agent_workflow_bindings"

    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    workflow_id: Mapped[int] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    agent: Mapped["Agent"] = relationship(back_populates="workflows")


class AgentKnowledgeBinding(Base):
    """Agent <-> KnowledgeBase binding."""

    __tablename__ = "agent_knowledge_bindings"

    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    knowledge_base_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)

    agent: Mapped["Agent"] = relationship(back_populates="knowledge_bindings")


class AgentToolBinding(Base):
    """Agent <-> Tool binding."""

    __tablename__ = "agent_tool_bindings"

    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    tool_id: Mapped[int] = mapped_column(ForeignKey("tools.id", ondelete="CASCADE"), nullable=False, index=True)
    permission: Mapped[str] = mapped_column(String(20), default="allow")  # allow, deny

    agent: Mapped["Agent"] = relationship(back_populates="tool_bindings")
