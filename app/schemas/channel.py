"""
Channel schemas (IM integrations).
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class ChannelCreate(BaseModel):
    channel_type: str = Field(..., description="feishu / dingtalk / wecom")
    name: str
    agent_id: int
    credentials: Dict[str, Any] = {}
    status: str = "active"


class ChannelUpdate(BaseModel):
    name: Optional[str] = None
    agent_id: Optional[int] = None
    credentials: Optional[Dict[str, Any]] = None
    status: Optional[str] = None


class ChannelResponse(BaseModel):
    id: int
    channel_type: str
    name: str
    agent_id: int
    status: str
    credentials: Optional[Dict[str, Any]] = None
    last_connected_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_channel(cls, ch, mask_secret: bool = True) -> "ChannelResponse":
        creds = dict(ch.credentials or {})
        if mask_secret and creds.get("app_secret"):
            creds["app_secret"] = "***"
            creds["app_secret_masked"] = True
        return cls(
            id=ch.id,
            channel_type=ch.channel_type,
            name=ch.name,
            agent_id=ch.agent_id,
            status=ch.status,
            credentials=creds,
            last_connected_at=ch.last_connected_at,
            last_error=ch.last_error,
            created_at=ch.created_at,
        )


class ChannelListResponse(BaseModel):
    items: List[ChannelResponse]


class ChannelTestResponse(BaseModel):
    success: bool
    detail: str
