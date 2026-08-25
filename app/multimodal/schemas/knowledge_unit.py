"""Multimodal Knowledge Base schemas — 知识单元."""

from typing import Optional, List, Dict
from datetime import datetime
from pydantic import BaseModel, Field


class KnowledgeUnitResponse(BaseModel):
    """知识单元."""
    id: int
    asset_id: int
    knowledge_base_id: int
    unit_type: str          # image / shot / segment / slide
    unit_index: Optional[int] = None
    content: Optional[str] = None
    description: Optional[str] = None
    metadata: Optional[dict] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    thumbnail_path: Optional[str] = None
    frame_index: Optional[int] = None
    status: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class VideoShotResponse(KnowledgeUnitResponse):
    """视频镜头（含扩展详情）."""
    keyframe_path: Optional[str] = None
    duration: Optional[float] = None
    shot_metadata: Optional[dict] = None


class AudioSegmentResponse(KnowledgeUnitResponse):
    """音频分段（含扩展详情）."""
    transcript: Optional[str] = None
    speaker: Optional[str] = None
    emotion: Optional[str] = None


class PptSlideResponse(KnowledgeUnitResponse):
    """PPT 页（含扩展详情）."""
    title: Optional[str] = None
    image_path: Optional[str] = None
    text_content: Optional[str] = None


class UnitListResponse(BaseModel):
    """知识单元列表."""
    total: int
    items: List[KnowledgeUnitResponse] = Field(default_factory=list)
