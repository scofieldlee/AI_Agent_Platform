"""
Channel repository: data access for agent_channels / channel_conversations.
"""

from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel import AgentChannel, ChannelConversation
from app.core.timeutils import now

# IM 会话上下文窗口：超过该分钟数未活跃则开启新会话
CHANNEL_SESSION_TTL_MINUTES = 30


async def list_channels(
    db: AsyncSession,
    agent_id: Optional[int] = None,
    channel_type: Optional[str] = None,
) -> List[AgentChannel]:
    stmt = select(AgentChannel).order_by(AgentChannel.id.desc())
    if agent_id:
        stmt = stmt.where(AgentChannel.agent_id == agent_id)
    if channel_type:
        stmt = stmt.where(AgentChannel.channel_type == channel_type)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_channel(db: AsyncSession, channel_id: int) -> Optional[AgentChannel]:
    return await db.get(AgentChannel, channel_id)


async def create_channel(db: AsyncSession, **fields) -> AgentChannel:
    channel = AgentChannel(**fields)
    db.add(channel)
    await db.commit()
    await db.refresh(channel)
    return channel


async def update_channel(db: AsyncSession, channel: AgentChannel, **fields) -> AgentChannel:
    for k, v in fields.items():
        setattr(channel, k, v)
    await db.commit()
    await db.refresh(channel)
    return channel


async def delete_channel(db: AsyncSession, channel: AgentChannel) -> None:
    await db.execute(
        delete(ChannelConversation).where(ChannelConversation.channel_id == channel.id)
    )
    await db.delete(channel)
    await db.commit()


async def list_active_channels(db: AsyncSession, channel_type: Optional[str] = None) -> List[AgentChannel]:
    """Channels that the message pump should connect to."""
    stmt = select(AgentChannel).where(AgentChannel.status == "active")
    if channel_type:
        stmt = stmt.where(AgentChannel.channel_type == channel_type)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def find_fresh_channel_conversation(
    db: AsyncSession,
    channel_id: int,
    external_user_id: str,
    external_chat_id: str,
) -> Optional[ChannelConversation]:
    """Return the session mapping when it is still inside the TTL window."""
    result = await db.execute(
        select(ChannelConversation)
        .where(
            ChannelConversation.channel_id == channel_id,
            ChannelConversation.external_user_id == external_user_id,
            ChannelConversation.external_chat_id == external_chat_id,
        )
        .order_by(ChannelConversation.last_active_at.desc().nullslast())
        .limit(1)
    )
    record = result.scalar_one_or_none()
    if (
        record
        and record.last_active_at
        and record.last_active_at >= now() - timedelta(minutes=CHANNEL_SESSION_TTL_MINUTES)
    ):
        record.last_active_at = now()
        await db.commit()
        return record
    return None


async def upsert_channel_conversation(
    db: AsyncSession,
    channel_id: int,
    external_user_id: str,
    external_chat_id: str,
    conversation_id: int,
) -> ChannelConversation:
    """Create or point the latest mapping at a (new) platform conversation."""
    result = await db.execute(
        select(ChannelConversation)
        .where(
            ChannelConversation.channel_id == channel_id,
            ChannelConversation.external_user_id == external_user_id,
            ChannelConversation.external_chat_id == external_chat_id,
        )
        .order_by(ChannelConversation.last_active_at.desc().nullslast())
        .limit(1)
    )
    record = result.scalar_one_or_none()
    if record:
        record.conversation_id = conversation_id
        record.last_active_at = now()
    else:
        record = ChannelConversation(
            channel_id=channel_id,
            external_user_id=external_user_id,
            external_chat_id=external_chat_id,
            conversation_id=conversation_id,
            last_active_at=now(),
        )
        db.add(record)
    await db.commit()
    await db.refresh(record)
    return record
