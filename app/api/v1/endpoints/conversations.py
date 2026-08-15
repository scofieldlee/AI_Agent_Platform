"""Conversation endpoints: chat with agent."""

import os
import uuid
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.auth.dependencies import require_permission
from app.schemas.conversation import ChatRequest, ChatResponse, ConversationResponse, MessageResponse, AttachmentMeta
from app.schemas.agent import get_input_config
from app.repositories.conversation_repo import (
    list_conversations, get_conversation, create_conversation,
    get_messages, get_recent_history, save_message, update_conversation_status,
)

logger = logging.getLogger(__name__)

# Upload directory (project root / uploads)
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

router = APIRouter()


async def resolve_chat_user(db: AsyncSession, user_id: Optional[int]) -> tuple[Optional[int], Optional[int]]:
    """Resolve a user_id passed by a third-party caller.

    The platform `users` table is for staff/admin accounts; conversational
    callers may pass their own user ids. If the id does not exist in the
    platform table, auto-create a lightweight external-user placeholder so
    that foreign-key relationships on `conversations`, `agent_traces` and
    `memories` remain valid.

    Returns: (platform_user_id, external_user_id)
    """
    if user_id is None:
        return None, None
    from sqlalchemy import select
    from app.models.user import User

    # 1) If it is a real platform user, use it directly.
    user = await db.get(User, user_id)
    if user is not None:
        return user_id, None

    # 2) Otherwise look for an existing placeholder for this external id.
    username = f"external_user_{user_id}"
    result = await db.execute(select(User).where(User.username == username))
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing.id, user_id

    # 3) Auto-create an external placeholder user. Several analytics/memory tables
    # reference users.id, so keeping a placeholder avoids FK violations while
    # still allowing third-party callers to pass their own user identifiers.
    logger.info(f"Creating external placeholder user for unknown user_id={user_id}")
    external_user = User(
        email=f"{username}@platform.local",
        username=username,
        hashed_password="!",
        full_name=f"External User {user_id}",
        is_active=True,
    )
    db.add(external_user)
    await db.flush()
    await db.refresh(external_user)
    return external_user.id, user_id


@router.get("", response_model=List[ConversationResponse], dependencies=[Depends(require_permission("conversation:view"))])
async def list_conversations_endpoint(db: AsyncSession = Depends(get_db)):
    """List all conversations."""
    return await list_conversations(db)


@router.get("/{conversation_id}/messages", response_model=List[MessageResponse], dependencies=[Depends(require_permission("conversation:view"))])
async def get_messages_endpoint(conversation_id: int, db: AsyncSession = Depends(get_db)):
    """Get all messages in a conversation."""
    return await get_messages(db, conversation_id)


async def parse_chat_request(request: Request) -> ChatRequest:
    """Parse chat request from JSON or multipart/form-data.

    Supports both `application/json` and `multipart/form-data` so that
    form-based clients (e.g. Postman defaulting to form-data) work without
    returning a confusing 422.
    """
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        try:
            data = {
                "agent_id": int(form.get("agent_id")),
                "message": form.get("message", ""),
            }
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="agent_id must be an integer")
        if form.get("user_id"):
            try:
                data["user_id"] = int(form.get("user_id"))
            except (TypeError, ValueError):
                raise HTTPException(status_code=422, detail="user_id must be an integer")
        if form.get("conversation_id"):
            try:
                data["conversation_id"] = int(form.get("conversation_id"))
            except (TypeError, ValueError):
                raise HTTPException(status_code=422, detail="conversation_id must be an integer")
        return ChatRequest.model_validate(data)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(
            status_code=422,
            detail="Request body must be valid JSON or multipart/form-data",
        )
    return ChatRequest.model_validate(body)


@router.post(
    "/chat",
    response_model=ChatResponse,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {
                        "title": "ChatRequest",
                        "type": "object",
                        "properties": {
                            "agent_id": {
                                "type": "integer",
                                "title": "Agent ID",
                                "description": "Agent to chat with",
                            },
                            "message": {
                                "type": "string",
                                "title": "Message",
                                "description": "User message",
                            },
                            "user_id": {
                                "anyOf": [{"type": "integer"}, {"type": "null"}],
                                "default": None,
                                "title": "User ID",
                                "description": "User ID",
                            },
                            "conversation_id": {
                                "anyOf": [{"type": "integer"}, {"type": "null"}],
                                "default": None,
                                "title": "Conversation ID",
                                "description": "Existing conversation ID (for multi-turn)",
                            },
                        },
                        "required": ["agent_id", "message"],
                    }
                },
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "agent_id": {"type": "integer", "title": "Agent ID"},
                            "message": {"type": "string", "title": "Message"},
                            "user_id": {"type": "integer", "title": "User ID"},
                            "conversation_id": {"type": "integer", "title": "Conversation ID"},
                        },
                        "required": ["agent_id", "message"],
                    }
                },
            },
        }
    },
)
async def chat(request: Request, db: AsyncSession = Depends(get_db)):
    """Send a message to an agent and get a response.

    Accepts either:
    - `application/json`: `{ "agent_id": int, "message": str, "user_id"?: int, "conversation_id"?: int }`
    - `multipart/form-data`: same fields as form-data fields (for compatibility with form-based clients)

    This is the main entry point for agent interaction.
    Flow: user message -> AgentRuntime -> LangGraph Workflow -> response.
    """
    from app.runtime.executor import AgentRuntime
    from app.runtime.context import AgentContext

    chat_request = await parse_chat_request(request)

    # Validate agent exists and is active (prevent 500 on invalid agent_id)
    from app.models.agent import Agent
    agent = await db.get(Agent, chat_request.agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {chat_request.agent_id} not found")
    if not agent.is_active or agent.status == "archived":
        raise HTTPException(
            status_code=403,
            detail=f"Agent '{agent.name}' is not active (status: {agent.status}). Please activate it first.",
        )

    # Resolve third-party user_id: if it does not exist in the platform users
    # table, store it as external_user_id and treat the conversation as anonymous.
    platform_user_id, external_user_id = await resolve_chat_user(db, chat_request.user_id)
    conversation_meta = {"external_user_id": external_user_id} if external_user_id else {}

    # Get or create conversation
    if chat_request.conversation_id:
        conv = await get_conversation(db, chat_request.conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        conv = await create_conversation(
            db,
            user_id=platform_user_id,
            agent_id=chat_request.agent_id,
            title=chat_request.message[:50] if chat_request.message else "New Conversation",
            meta=conversation_meta,
        )

    # Save user message
    user_msg = await save_message(
        db, conv.id, "user", platform_user_id or external_user_id, chat_request.message
    )

    # Load conversation history (previous messages, excluding the one just saved)
    history_msgs = await get_recent_history(db, conv.id, before_msg_id=user_msg.id, limit=10)

    # Convert to LLM format: [{role, content}]
    conversation_history = [
        {"role": "user" if msg.sender_type == "user" else "assistant", "content": msg.content}
        for msg in history_msgs
    ]

    # Commit conversation + user message before runtime,
    # so tool executor can record execution logs with valid FK references.
    await db.commit()

    # Run agent
    context = AgentContext(
        user_id=platform_user_id or external_user_id,
        conversation_id=conv.id,
        agent_id=chat_request.agent_id,
    )

    runtime = AgentRuntime()
    result = await runtime.run(
        chat_request.message,
        context,
        conversation_history=conversation_history,
    )

    # Save agent response
    agent_msg = await save_message(
        db,
        conv.id,
        "agent",
        chat_request.agent_id,
        result.get("answer", "I'm sorry, I couldn't process your request."),
        meta={
            "intent": result.get("intent"),
            "confidence": result.get("confidence"),
            "knowledge_sources": result.get("knowledge_sources"),
            "memories_used": result.get("memories_used"),
            "trace_id": result.get("trace_id"),
            "ticket_number": result.get("ticket_number"),
            "need_human": result.get("need_human", False),
        },
    )

    # Update conversation status
    await update_conversation_status(
        db,
        conv,
        message_count_delta=2,
        is_transferred=result.get("need_human", False) or None,
        transfer_reason=result.get("transfer_reason"),
    )

    await db.commit()

    return ChatResponse(
        conversation_id=conv.id,
        message_id=agent_msg.id,
        reply=agent_msg.content,
        intent=result.get("intent"),
        confidence=result.get("confidence"),
        knowledge_sources=result.get("knowledge_sources"),
        memories_used=result.get("memories_used"),
        need_human=result.get("need_human", False),
        ticket_number=result.get("ticket_number"),
        trace_id=result.get("trace_id"),
    )


# --- File extension to input type mapping ---
_EXT_TO_INPUT = {
    ".txt": "text", ".md": "text", ".csv": "text",
    ".pdf": "pdf",
    ".docx": "word", ".doc": "word",
    ".xlsx": "excel", ".xls": "excel",
    ".jpg": "image", ".jpeg": "image", ".png": "image", ".gif": "image", ".webp": "image", ".bmp": "image",
    ".mp4": "video", ".avi": "video", ".mov": "video", ".mkv": "video",
}


def _ext_to_input_type(filename: str) -> Optional[str]:
    ext = os.path.splitext(filename)[1].lower()
    return _EXT_TO_INPUT.get(ext)


@router.post("/chat-with-attachments", response_model=ChatResponse)
async def chat_with_attachments(
    agent_id: int = Form(...),
    message: str = Form(""),
    user_id: Optional[int] = Form(None),
    conversation_id: Optional[int] = Form(None),
    files: List[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_db),
):
    """Send a message with file attachments to an agent.

    Accepts multipart/form-data with:
    - agent_id: Agent ID (required)
    - message: User's text message (optional if files present)
    - user_id: Optional user ID
    - conversation_id: Optional existing conversation ID
    - files: One or more file uploads
    """
    from app.runtime.executor import AgentRuntime
    from app.runtime.context import AgentContext
    from app.models.agent import Agent
    from app.knowledge.parsers.file_parser import parse_file, format_attachment_for_prompt, get_mime_type

    # Validate agent
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    if not agent.is_active or agent.status == "archived":
        raise HTTPException(
            status_code=403,
            detail=f"Agent '{agent.name}' is not active (status: {agent.status}).",
        )

    # Resolve third-party user_id (same logic as /chat)
    platform_user_id, external_user_id = await resolve_chat_user(db, user_id)
    conversation_meta = {"external_user_id": external_user_id} if external_user_id else {}

    # Get input config from agent
    input_config = get_input_config(agent.config or {})
    allowed_types = input_config["allowed_input_types"]
    max_size_mb = input_config["max_file_size_mb"]
    max_files = input_config["max_files_per_message"]

    if len(files) > max_files:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files. Maximum {max_files} files per message, got {len(files)}.",
        )

    # Validate and save files
    attachment_metas: List[AttachmentMeta] = []
    parsed_attachments: List[dict] = []

    for upload in files:
        if not upload.filename:
            continue

        input_type = _ext_to_input_type(upload.filename)
        if not input_type:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {upload.filename}",
            )
        if input_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"File type '{input_type}' not allowed for this agent. Allowed: {', '.join(allowed_types)}",
            )

        # Read file content
        file_bytes = await upload.read()
        size_mb = len(file_bytes) / (1024 * 1024)
        if size_mb > max_size_mb:
            raise HTTPException(
                status_code=400,
                detail=f"File '{upload.filename}' too large: {size_mb:.1f}MB (max {max_size_mb}MB).",
            )

        # Save to disk
        safe_name = f"{uuid.uuid4().hex}_{upload.filename}"
        file_path = os.path.join(UPLOAD_DIR, safe_name)
        with open(file_path, "wb") as f:
            f.write(file_bytes)

        # Parse file
        parsed = await parse_file(file_path, upload.filename, content=file_bytes)
        parsed_attachments.append(parsed)

        attachment_metas.append(AttachmentMeta(
            filename=upload.filename,
            mime_type=get_mime_type(upload.filename),
            size_bytes=len(file_bytes),
            category=input_type,
            file_path=file_path,
        ))

        logger.info(f"Attachment saved: {upload.filename} → {file_path} (type={input_type}, {size_mb:.1f}MB)")

    # Build the full message text (user text + extracted attachment text)
    text_parts = [message] if message else []
    image_attachments: List[dict] = []
    video_attachments: List[dict] = []

    for parsed in parsed_attachments:
        if parsed["type"] == "text":
            formatted = format_attachment_for_prompt(parsed)
            if formatted:
                text_parts.append(formatted)
        elif parsed["type"] == "image":
            image_attachments.append(parsed)
        elif parsed["type"] == "video":
            video_info = format_attachment_for_prompt(parsed)
            if video_info:
                text_parts.append(video_info)

    full_message = "\n\n".join(text_parts) if text_parts else "(仅附件，无文字消息)"

    # Get or create conversation
    if conversation_id:
        conv = await get_conversation(db, conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        conv = await create_conversation(
            db,
            user_id=platform_user_id,
            agent_id=agent_id,
            title=(message[:50] if message else f"附件对话 ({len(attachment_metas)} 个文件)"),
            meta=conversation_meta,
        )

    # Save user message with attachment metadata
    attachment_meta_dicts = [a.model_dump() for a in attachment_metas]
    user_msg = await save_message(
        db, conv.id, "user", platform_user_id or external_user_id, full_message,
        meta={"attachments": attachment_meta_dicts} if attachment_meta_dicts else None,
    )

    # Load history
    history_msgs = await get_recent_history(db, conv.id, before_msg_id=user_msg.id, limit=10)
    conversation_history = [
        {"role": "user" if msg.sender_type == "user" else "assistant", "content": msg.content}
        for msg in history_msgs
    ]

    await db.commit()

    # Run agent with attachment context
    context = AgentContext(
        user_id=platform_user_id or external_user_id,
        conversation_id=conv.id,
        agent_id=agent_id,
    )

    runtime = AgentRuntime()
    result = await runtime.run(
        full_message,
        context,
        conversation_history=conversation_history,
        attachments=parsed_attachments if parsed_attachments else None,
    )

    # Save agent response
    agent_msg = await save_message(
        db, conv.id, "agent", agent_id,
        result.get("answer", "I'm sorry, I couldn't process your request."),
        meta={
            "intent": result.get("intent"),
            "confidence": result.get("confidence"),
            "knowledge_sources": result.get("knowledge_sources"),
            "memories_used": result.get("memories_used"),
            "trace_id": result.get("trace_id"),
            "ticket_number": result.get("ticket_number"),
            "need_human": result.get("need_human", False),
        },
    )

    await update_conversation_status(
        db, conv,
        message_count_delta=2,
        is_transferred=result.get("need_human", False) or None,
        transfer_reason=result.get("transfer_reason"),
    )

    await db.commit()

    return ChatResponse(
        conversation_id=conv.id,
        message_id=agent_msg.id,
        reply=agent_msg.content,
        intent=result.get("intent"),
        confidence=result.get("confidence"),
        knowledge_sources=result.get("knowledge_sources"),
        memories_used=result.get("memories_used"),
        need_human=result.get("need_human", False),
        ticket_number=result.get("ticket_number"),
        trace_id=result.get("trace_id"),
    )
