"""Multimodal Knowledge Base schemas — 多模态检索."""

from typing import Optional, List, Dict
from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """多模态检索请求（文本 / 图片 / 文本+图片）."""
    knowledge_base_id: int
    query: Optional[str] = None                                    # 文本查询
    asset_types: List[str] = Field(default_factory=list)           # 素材类型过滤
    tags: List[str] = Field(default_factory=list)                  # 标签过滤
    top_k: int = Field(10, ge=1, le=100)
    min_score: float = Field(0.0, ge=0.0, le=1.0)                  # 相似度阈值


class SearchResultItem(BaseModel):
    """单条检索结果."""
    asset_id: int
    asset_code: Optional[str] = None
    asset_name: Optional[str] = None
    asset_type: Optional[str] = None
    unit_id: Optional[int] = None
    unit_type: Optional[str] = None
    unit_index: Optional[int] = None
    score: float
    description: Optional[str] = None
    content: Optional[str] = None
    metadata: Optional[dict] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    thumbnail_url: Optional[str] = None
    preview_url: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    """检索响应."""
    query: Optional[str] = None
    query_type: str = "text"     # text / image / text+image
    total: int
    results: List[SearchResultItem] = Field(default_factory=list)
