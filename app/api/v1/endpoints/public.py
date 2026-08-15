"""Public endpoints for the customer-facing chat widget.

These endpoints are intentionally unauthenticated so that anonymous
end-users can interact with the customer-service agent embedded on
public pages or standalone at /chat.
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.models.agent import Agent, AgentKnowledgeBinding
from app.models.knowledge import KnowledgeBase
from app.models.conversation import Conversation, Message
from app.schemas.conversation import MessageResponse
from app.schemas.agent import get_input_config

router = APIRouter()


@router.get("/chat-config")
async def chat_config(
    token: Optional[str] = Query(None, description="Agent chat token from URL: /chat?token=xxx"),
    db: AsyncSession = Depends(get_db),
):
    """Return the agent configuration for the chat widget.

    If a token is provided, resolve the specific agent by its chat_token.
    If no token, fall back to the first published active agent (backward compatible).
    Only published + active agents are accessible.
    """
    if token:
        result = await db.execute(
            select(Agent)
            .where(Agent.chat_token == token)
            .where(Agent.is_active.is_(True))
            .where(Agent.status == "published")
        )
        agent = result.scalar_one_or_none()

        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found or not published")
    else:
        # Backward compatible: pick first published active agent
        result = await db.execute(
            select(Agent)
            .where(Agent.is_active.is_(True))
            .where(Agent.status == "published")
            .order_by(Agent.id.asc())
            .limit(1)
        )
        agent = result.scalar_one_or_none()

    if not agent:
        return {
            "agent_id": None,
            "agent_name": None,
            "agent_status": "unavailable",
            "kb_synced": False,
            "kb_documents": 0,
            "kb_chunks": 0,
            "kb_name": None,
            "welcome_message": None,
            "suggested_questions": [],
            "allowed_input_types": ["text"],
            "max_file_size_mb": 10,
            "max_files_per_message": 5,
        }

    # Load the first bound knowledge base for status display
    kb_result = await db.execute(
        select(KnowledgeBase)
        .join(AgentKnowledgeBinding, AgentKnowledgeBinding.knowledge_base_id == KnowledgeBase.id)
        .where(AgentKnowledgeBinding.agent_id == agent.id)
        .limit(1)
    )
    kb = kb_result.scalar_one_or_none()

    # Compute actual chunk count from the chunks table
    actual_chunk_count = 0
    if kb:
        from sqlalchemy import func
        from app.models.knowledge import Chunk, Document
        count_result = await db.execute(
            select(func.count(Chunk.id))
            .join(Document, Document.id == Chunk.document_id)
            .where(Document.knowledge_base_id == kb.id)
        )
        actual_chunk_count = count_result.scalar() or 0

    kb_synced = bool(kb and actual_chunk_count > 0)

    # Extract chat UI config from agent config JSONB
    config = agent.config or {}
    input_cfg = get_input_config(config)

    return {
        "agent_id": agent.id,
        "agent_name": agent.name,
        "agent_description": agent.description,
        "agent_status": agent.status,
        "kb_synced": kb_synced,
        "kb_documents": kb.document_count if kb else 0,
        "kb_chunks": actual_chunk_count,
        "kb_name": kb.name if kb else None,
        "welcome_message": config.get("welcome_message", ""),
        "suggested_questions": config.get("suggested_questions", []),
        "avatar_emoji": config.get("avatar_emoji", ""),
        "allowed_input_types": input_cfg["allowed_input_types"],
        "max_file_size_mb": input_cfg["max_file_size_mb"],
        "max_files_per_message": input_cfg["max_files_per_message"],
    }


@router.get("/conversations/{conversation_id}/messages", response_model=List[MessageResponse])
async def get_public_conversation_messages(conversation_id: int, db: AsyncSession = Depends(get_db)):
    """Return all messages for a conversation without authentication.

    Used by the public /chat widget so anonymous users can view the
    history of the current conversation. Only active conversations
    are exposed.
    """
    conv = await db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv.status != "active":
        raise HTTPException(status_code=403, detail="Conversation is not accessible")

    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.id)
    )
    return list(result.scalars().all())
