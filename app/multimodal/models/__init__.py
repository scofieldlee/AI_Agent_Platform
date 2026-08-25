"""Multimodal Knowledge Base — SQLAlchemy models.

全部 13 张 mm_ 前缀表。注册入口：
- app/database/session.py init_db()
- alembic/env.py
"""

from app.multimodal.models.knowledge_base import MultimodalKnowledgeBase
from app.multimodal.models.asset import MultimodalAsset
from app.multimodal.models.asset_metadata import AssetMetadata
from app.multimodal.models.asset_tag import AssetTag, AssetTagRelation
from app.multimodal.models.asset_relation import AssetRelation
from app.multimodal.models.asset_version import AssetVersion
from app.multimodal.models.knowledge_unit import KnowledgeUnit
from app.multimodal.models.video_shot import VideoShot
from app.multimodal.models.audio_segment import AudioSegment
from app.multimodal.models.ppt_slide import PptSlide
from app.multimodal.models.processing_task import ProcessingTask
from app.multimodal.models.index_record import IndexRecord

__all__ = [
    "MultimodalKnowledgeBase",
    "MultimodalAsset",
    "AssetMetadata",
    "AssetTag",
    "AssetTagRelation",
    "AssetRelation",
    "AssetVersion",
    "KnowledgeUnit",
    "VideoShot",
    "AudioSegment",
    "PptSlide",
    "ProcessingTask",
    "IndexRecord",
]
