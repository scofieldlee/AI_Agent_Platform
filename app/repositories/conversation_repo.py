"""
Conversation repository: data access for conversations and messages.
"""

from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, Message


async def list_conversations(db: AsyncSession) -> List[Conversation]:
    """List all conversations ordered by most recent."""
    result = await db.execute(select(Conversation).order_by(Conversation.id.desc()))
    return list(result.scalars().all())


async def get_conversation(db: AsyncSession, conv_id: int) -> Optional[Conversation]:
    """Get a conversation by ID."""
    return await db.get(Conversation, conv_id)


async def create_conversation(
    db: AsyncSession,
    user_id: Optional[int],
    agent_id: int,
    title: str,
    meta: Optional[dict] = None,
) -> Conversation:
    """Create a new conversation.

    `meta` may include `external_user_id` when the caller is a third-party
    system whose user id does not exist in the platform users table.
    """
    conv = Conversation(user_id=user_id, agent_id=agent_id, title=title, meta=meta or {})
    db.add(conv)
    await db.flush()
    return conv


async def get_messages(db: AsyncSession, conv_id: int) -> List[Message]:
    """Get all messages in a conversation ordered by ID."""
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conv_id)
        .order_by(Message.id)
    )
    return list(result.scalars().all())


async def get_recent_history(db: AsyncSession, conv_id: int, before_msg_id: int, limit: int = 10) -> List[Message]:
    """Get recent conversation history before a given message ID."""
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conv_id)
        .where(Message.id < before_msg_id)
        .order_by(Message.id.desc())
        .limit(limit)
    )
    return list(reversed(result.scalars().all()))


async def save_message(
    db: AsyncSession,
    conv_id: int,
    sender_type: str,
    sender_id: Optional[int],
    content: str,
    meta: Optional[dict] = None,
) -> Message:
    """Save a message and return it."""
    msg = Message(
        conversation_id=conv_id,
        sender_type=sender_type,
        sender_id=sender_id,
        content=content,
        meta=meta or {},
    )
    db.add(msg)
    await db.flush()
    return msg


async def update_conversation_status(
    db: AsyncSession,
    conv: Conversation,
    message_count_delta: int = 0,
    is_transferred: Optional[bool] = None,
    transfer_reason: Optional[str] = None,
):
    """Update conversation message count and transfer status."""
    conv.message_count += message_count_delta
    if is_transferred is not None:
        conv.is_transferred = is_transferred
    if transfer_reason is not None:
        conv.transfer_reason = transfer_reason
