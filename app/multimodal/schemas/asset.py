"""Multimodal Knowledge Base schemas — 素材."""

from typing import Optional, List, Dict
from datetime import datetime
from pydantic import BaseModel, Field

from app.multimodal.constants import FileType


class AssetResponse(BaseModel):
    """素材列表项."""
    id: int
    knowledge_base_id: int
    asset_code: str
    name: str
    original_filename: Optional[str] = None
    file_type: str
    mime_type: Optional[str] = None
    file_size: int = 0
    storage_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    preview_path: Optional[str] = None
    status: str
    version: int = 1
    attributes: Optional[dict] = None
    tags: List[Dict] = Field(default_factory=list)  # [{id, name, source}]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AssetDetailResponse(AssetResponse):
    """素材详情（含 metadata / units / relations 概要）."""
    metadata: Dict[str, dict] = Field(default_factory=dict)       # {system: {...}, ai: {...}, user: {...}}
    units_count: int = 0
    units: List[Dict] = Field(default_factory=list)               # 知识单元概要
    relations: List[Dict] = Field(default_factory=list)           # 关联素材
    processing_summary: Dict[str, int] = Field(default_factory=dict)  # {success: 3, failed: 1}
    ai_tags: List[str] = Field(default_factory=list)


class AssetUpdate(BaseModel):
    """编辑素材（名称 + 用户 metadata + 分类）."""
    name: Optional[str] = None
    attributes: Optional[dict] = None


class AssetUserMetadataUpdate(BaseModel):
    """更新用户 metadata（category/tags/usage/copyright/remark）."""
    metadata: dict


class TagAddRequest(BaseModel):
    """添加标签."""
    tags: List[str] = Field(..., min_length=1)
    source: str = Field("user", pattern="^(ai|user)$")


class AssetListParams(BaseModel):
    """素材列表查询参数."""
    knowledge_base_id: int
    file_type: Optional[str] = None
    status: Optional[str] = None
    tag: Optional[str] = None
    keyword: Optional[str] = None       # 名称/编码模糊搜索
    include_deleted: bool = False       # 回收站查询
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


class AssetListResponse(BaseModel):
    """素材列表分页响应."""
    total: int
    page: int
    page_size: int
    items: List[AssetResponse] = Field(default_factory=list)


class UploadResultItem(BaseModel):
    """批量上传单项结果."""
    success: bool
    asset_id: Optional[int] = None
    asset_code: Optional[str] = None
    filename: str
    file_type: Optional[str] = None
    error: Optional[str] = None


class UploadResponse(BaseModel):
    """上传响应."""
    total: int
    success_count: int
    failed_count: int
    items: List[UploadResultItem] = Field(default_factory=list)


class RelationCreate(BaseModel):
    """建立素材关联."""
    target_asset_id: int
    relation_type: str = Field("related")
    metadata: dict = Field(default_factory=dict)


class ApproveRequest(BaseModel):
    """审核通过（可附最终确认的 metadata 修正）."""
    user_metadata: Optional[dict] = None
