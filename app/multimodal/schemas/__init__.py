"""Multimodal Knowledge Base — Pydantic schemas."""

from app.multimodal.schemas.knowledge_base import (
    MultimodalKBCreate, MultimodalKBUpdate, MultimodalKBResponse,
    MultimodalKBDetailResponse, KBStatsResponse,
)
from app.multimodal.schemas.asset import (
    AssetResponse, AssetDetailResponse, AssetUpdate, AssetUserMetadataUpdate,
    TagAddRequest, AssetListParams, AssetListResponse,
    UploadResponse, UploadResultItem, RelationCreate, ApproveRequest,
)
from app.multimodal.schemas.knowledge_unit import (
    KnowledgeUnitResponse, UnitListResponse,
    VideoShotResponse, AudioSegmentResponse, PptSlideResponse,
)
from app.multimodal.schemas.processing import (
    ProcessingTaskResponse, ProcessingTaskListResponse,
    TaskTriggerResponse, BatchAnalyzeRequest,
)
from app.multimodal.schemas.search import SearchRequest, SearchResponse, SearchResultItem

__all__ = [
    "MultimodalKBCreate", "MultimodalKBUpdate", "MultimodalKBResponse",
    "MultimodalKBDetailResponse", "KBStatsResponse",
    "AssetResponse", "AssetDetailResponse", "AssetUpdate", "AssetUserMetadataUpdate",
    "TagAddRequest", "AssetListParams", "AssetListResponse",
    "UploadResponse", "UploadResultItem", "RelationCreate", "ApproveRequest",
    "KnowledgeUnitResponse", "UnitListResponse",
    "VideoShotResponse", "AudioSegmentResponse", "PptSlideResponse",
    "ProcessingTaskResponse", "ProcessingTaskListResponse",
    "TaskTriggerResponse", "BatchAnalyzeRequest",
    "SearchRequest", "SearchResponse", "SearchResultItem",
]
