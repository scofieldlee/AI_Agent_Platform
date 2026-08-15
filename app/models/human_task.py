"""
Human task (ticket) model for human-in-the-loop customer service.

When the AI agent cannot handle a request (low confidence, complaint, knowledge
missing, system error), a HumanTask is created and assigned to a human agent.
"""

from typing import Optional
from datetime import datetime, timezone
from sqlalchemy import String, Text, Integer, Float, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from app.database.base import Base


class HumanTask(Base):
    """A customer service ticket created when the AI agent transfers to human.

    Lifecycle: pending -> assigned -> resolved -> closed
    Priority:   low < normal < high < urgent
    """

    __tablename__ = "human_tasks"

    # --- Ticket Identity ---
    ticket_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    # Format: HT20260803001

    # --- Relations ---
    conversation_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    agent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    # No FK to users table since user may be anonymous

    trace_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    # --- Context (what triggered the transfer) ---
    user_message: Mapped[str] = mapped_column(Text, nullable=False)
    # The user's original message that triggered the transfer

    intent: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # product_info, order_query, complaint, etc.

    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Agent's confidence score (0.0-1.0)

    transfer_reason: Mapped[str] = mapped_column(String(50), nullable=False, default="low_confidence")
    # low_confidence, knowledge_missing, complaint, llm_error, system_error, user_request

    # --- Status ---
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    # pending, assigned, resolved, closed

    priority: Mapped[str] = mapped_column(String(10), nullable=False, default="normal", index=True)
    # low, normal, high, urgent

    # --- Assignment ---
    assigned_to: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Human agent/staff ID

    # --- Resolution ---
    resolution_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # What the human agent did to resolve the issue

    resolution_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # resolved, cannot_resolve, redirected, duplicate

    # --- Extra Context ---
    meta: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)
    # agent_answer (what the AI said before transfer), knowledge_sources, tool_results, etc.

    # --- Timestamps ---
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    assigned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    @property
    def is_open(self) -> bool:
        return self.status in ("pending", "assigned")

    @property
    def is_resolved(self) -> bool:
        return self.status in ("resolved", "closed")
