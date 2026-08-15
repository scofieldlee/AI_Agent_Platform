"""
Conversation and message models.
"""

from typing import Optional, List
from sqlalchemy import String, Text, Integer, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from app.database.base import Base


class Conversation(Base):
    """A conversation session between user and agent."""

    __tablename__ = "conversations"

    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    agent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("agents.id"), nullable=True, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="active")  # active, closed, transferred
    meta: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)
    # metadata: user_agent, ip, source (web/api), etc.
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    is_transferred: Mapped[bool] = mapped_column(Boolean, default=False)
    transfer_reason: Mapped[Optional[str]] = mapped_column(String(100))  # knowledge_missing, low_confidence, etc.

    messages: Mapped[List["Message"]] = relationship(
        back_populates="conversation", lazy="selectin", cascade="all, delete-orphan",
        order_by="Message.id"
    )


class Message(Base):
    """A single message in a conversation.

    sender_type: user, agent, human (customer service), system.
    """

    __tablename__ = "messages"

    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_type: Mapped[str] = mapped_column(String(20), nullable=False)  # user, agent, human, system
    sender_id: Mapped[Optional[int]] = mapped_column(Integer)  # user_id or agent_id or human_id
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[str] = mapped_column(String(20), default="text")  # text, image, card, action
    meta: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)
    # metadata: intent, confidence, knowledge_sources, tool_results, trace_id, etc.
    feedback: Mapped[Optional[str]] = mapped_column(String(20))  # like, dislike, null
    feedback_note: Mapped[Optional[str]] = mapped_column(Text)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
