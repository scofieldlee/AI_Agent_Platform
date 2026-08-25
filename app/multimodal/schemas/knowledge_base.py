"""Multimodal Knowledge Base schemas — 知识库."""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class MultimodalKBCreate(BaseModel):
    """创建多模态知识库."""
    name: str = Field(..., min_length=1, max_length=200)
    code: Optional[str] = Field(None, max_length=100)  # 不填自动生成
    description: Optional[str] = None
    storage_config: dict = Field(default_factory=dict)
    embedding_config: dict = Field(default_factory=dict)
    vision_model_config: dict = Field(default_factory=dict)
    analysis_config: dict = Field(default_factory=dict)


class MultimodalKBUpdate(BaseModel):
    """更新知识库配置（全可选）."""
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    storage_config: Optional[dict] = None
    embedding_config: Optional[dict] = None
    vision_model_config: Optional[dict] = None
    analysis_config: Optional[dict] = None
    is_active: Optional[bool] = None


class MultimodalKBResponse(BaseModel):
    """知识库列表项."""
    id: int
    name: str
    code: str
    description: Optional[str] = None
    kb_type: str
    status: str
    storage_config: Optional[dict] = None
    embedding_config: Optional[dict] = None
    vision_model_config: Optional[dict] = None
    analysis_config: Optional[dict] = None
    asset_count: int
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class MultimodalKBDetailResponse(MultimodalKBResponse):
    """知识库详情（含类型统计）."""
    type_stats: dict = Field(default_factory=dict)   # {image: 10, video: 3, ...}
    status_stats: dict = Field(default_factory=dict)  # {ready: 8, review_required: 2, ...}


class KBStatsResponse(BaseModel):
    """知识库统计."""
    total_assets: int = 0
    total_units: int = 0
    total_indexed: int = 0
    type_stats: dict = Field(default_factory=dict)
    status_stats: dict = Field(default_factory=dict)
