"""
Conversation-related request/response schemas.
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class AttachmentMeta(BaseModel):
    """Metadata for a single attachment (used in chat and message history)."""
    filename: str
    mime_type: str = "application/octet-stream"
    size_bytes: int = 0
    category: str = "text"          # text, pdf, word, excel, image, video
    file_path: Optional[str] = None  # server-side path for stored file


class ChatRequest(BaseModel):
    """Request to chat with an agent.

    For text-only messages, use JSON body with `message` field.
    For messages with attachments, use the multipart `/chat-with-attachments` endpoint.
    """
    agent_id: int = Field(..., description="Agent to chat with")
    user_id: Optional[int] = Field(None, description="User ID")
    conversation_id: Optional[int] = Field(None, description="Existing conversation ID (for multi-turn)")
    message: str = Field(..., description="User message")
    attachments: Optional[List[AttachmentMeta]] = Field(None, description="Attachment metadata (for messages with files)")


class ChatResponse(BaseModel):
    """Response from agent chat."""
    conversation_id: int
    message_id: int
    reply: str
    intent: Optional[str] = None
    confidence: Optional[float] = None
    knowledge_sources: Optional[list] = None
    memories_used: Optional[list] = None
    need_human: bool = False
    ticket_number: Optional[str] = None
    trace_id: Optional[str] = None


class ConversationResponse(BaseModel):
    """Conversation list item."""
    id: int
    agent_id: Optional[int] = None
    title: Optional[str] = None
    status: str
    message_count: int
    is_transferred: Optional[bool] = False
    transfer_reason: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    """Single message in a conversation."""
    id: int
    sender_type: str
    content: str
    message_type: str
    meta: Optional[dict] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
