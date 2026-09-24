"""Agent channel (IM integration) endpoints: CRUD + credential test."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_permission
from app.channels.registry import SUPPORTED_CHANNEL_TYPES, create_adapter
from app.core.timeutils import now
from app.database.session import get_db
from app.models.agent import Agent
from app.models.channel import AgentChannel
from app.repositories.channel_repo import (
    create_channel,
    delete_channel,
    get_channel,
    list_channels,
    update_channel,
)
from app.schemas.channel import (
    ChannelCreate,
    ChannelListResponse,
    ChannelResponse,
    ChannelTestResponse,
    ChannelUpdate,
)

router = APIRouter(dependencies=[Depends(require_permission("agent:view"))])


async def _validate_agent(db: AsyncSession, agent_id: int) -> None:
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")


async def _validate_target(db: AsyncSession, target_type: str,
                           agent_id: Optional[int], employee_id: Optional[int]) -> None:
    """Validate the binding target according to target_type."""
    if target_type == "agent":
        if not agent_id:
            raise HTTPException(status_code=400, detail="绑定 Agent 时必须提供 agent_id")
        await _validate_agent(db, agent_id)
    elif target_type == "employee":
        if not employee_id:
            raise HTTPException(status_code=400, detail="绑定 AI 员工时必须提供 employee_id")
        from app.models.ai_employee import AIEmployee
        employee = await db.get(AIEmployee, employee_id)
        if not employee:
            raise HTTPException(status_code=404, detail=f"AI 员工 {employee_id} not found")
        if employee.status != "published":
            raise HTTPException(status_code=400, detail=f"AI 员工「{employee.name}」未发布，请先发布")
    else:
        raise HTTPException(status_code=400, detail=f"不支持的绑定类型: {target_type}（支持: agent / employee）")


@router.get("/types")
async def list_channel_types():
    """Supported channel types (for the admin UI dropdown)."""
    return {"types": SUPPORTED_CHANNEL_TYPES}


@router.get("", response_model=ChannelListResponse)
async def list_channels_endpoint(
    agent_id: Optional[int] = None,
    channel_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    channels = await list_channels(db, agent_id=agent_id, channel_type=channel_type)
    return ChannelListResponse(items=[ChannelResponse.from_channel(c) for c in channels])


@router.post("", response_model=ChannelResponse)
async def create_channel_endpoint(payload: ChannelCreate, db: AsyncSession = Depends(get_db)):
    if payload.channel_type not in SUPPORTED_CHANNEL_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的渠道类型: {payload.channel_type}（支持: {SUPPORTED_CHANNEL_TYPES}）",
        )
    await _validate_target(db, payload.target_type, payload.agent_id, payload.employee_id)
    if not (payload.credentials or {}).get("app_id"):
        raise HTTPException(status_code=400, detail="credentials 缺少 app_id")

    channel = await create_channel(
        db,
        channel_type=payload.channel_type,
        name=payload.name,
        target_type=payload.target_type,
        agent_id=payload.agent_id,
        employee_id=payload.employee_id,
        credentials=payload.credentials,
        status=payload.status,
    )
    return ChannelResponse.from_channel(channel)


@router.put("/{channel_id}", response_model=ChannelResponse)
async def update_channel_endpoint(
    channel_id: int, payload: ChannelUpdate, db: AsyncSession = Depends(get_db)
):
    channel = await get_channel(db, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    fields = payload.model_dump(exclude_unset=True)

    # Validate binding target when it changes
    if "target_type" in fields or "agent_id" in fields or "employee_id" in fields:
        target_type = fields.get("target_type", channel.target_type)
        agent_id = fields.get("agent_id", channel.agent_id)
        employee_id = fields.get("employee_id", channel.employee_id)
        await _validate_target(db, target_type, agent_id, employee_id)
    elif fields.get("agent_id"):
        await _validate_agent(db, fields["agent_id"])

    # Merge credentials: keep existing values for masked ("***") secrets
    if "credentials" in fields and fields["credentials"] is not None:
        merged = dict(channel.credentials or {})
        for k, v in fields["credentials"].items():
            if v == "***":
                continue
            merged[k] = v
        fields["credentials"] = merged
        if not merged.get("app_id"):
            raise HTTPException(status_code=400, detail="credentials 缺少 app_id")

    # Credentials changed: reset connection state so the worker reconnects
    if "credentials" in fields:
        fields["last_connected_at"] = None
        fields["last_error"] = None

    channel = await update_channel(db, channel, **fields)
    return ChannelResponse.from_channel(channel)


@router.delete("/{channel_id}")
async def delete_channel_endpoint(channel_id: int, db: AsyncSession = Depends(get_db)):
    channel = await get_channel(db, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    await delete_channel(db, channel)
    return {"deleted": True}


@router.post("/{channel_id}/test", response_model=ChannelTestResponse)
async def test_channel_endpoint(channel_id: int, db: AsyncSession = Depends(get_db)):
    """Validate channel credentials against the IM platform."""
    channel = await get_channel(db, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    try:
        adapter = create_adapter(channel.id, channel.channel_type, channel.credentials)
        result = await adapter.test_credentials()
    except Exception as e:
        result = {"success": False, "detail": str(e)}

    if result.get("success"):
        await update_channel(db, channel, last_connected_at=now(), last_error=None)
    else:
        await update_channel(db, channel, last_error=result.get("detail"))

    return ChannelTestResponse(**result)
