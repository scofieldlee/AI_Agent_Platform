"""
Channel models: IM integrations (Feishu / DingTalk / WeCom) that let users
chat with agents without opening the admin web UI.

One channel (bot app) binds to exactly one Agent. Inbound IM messages are
routed through the standard conversation pipeline (knowledge / tools / LLM).
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, ForeignKey, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from app.database.base import Base


class AgentChannel(Base):
    """An IM channel (bot app) bound to one Agent.

    credentials JSONB holds provider-specific secrets, e.g. for Feishu:
        {"app_id": "cli_xxx", "app_secret": "xxx"}
    """

    __tablename__ = "agent_channels"

    channel_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # feishu, dingtalk, wecom
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    credentials: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)  # active, disabled
    last_connected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    @property
    def is_active(self) -> bool:
        return self.status == "active"


class ChannelConversation(Base):
    """Maps an external IM user/chat pair to a platform conversation.

    Session window: when last_active_at is older than CHANNEL_SESSION_TTL
    minutes, a fresh platform conversation is started so IM users get
    multi-turn context without it growing forever.
    """

    __tablename__ = "channel_conversations"

    channel_id: Mapped[int] = mapped_column(ForeignKey("agent_channels.id"), nullable=False, index=True)
    external_user_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)  # e.g. feishu open_id
    external_chat_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)  # p2p chat_id or group chat_id
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), nullable=False, index=True)
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
