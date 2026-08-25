"""Adapters — 适配器工厂.

统一入口：根据类型获取适配器实例（默认单例缓存）。
"""

from typing import Optional

from app.core.config import settings
from app.multimodal.adapters.storage.base import StorageAdapter
from app.multimodal.adapters.storage.local_storage import LocalStorageAdapter
from app.multimodal.adapters.vision.base import VisionModelAdapter
from app.multimodal.adapters.vision.qwen_vl import QwenVisionAdapter
from app.multimodal.adapters.embedding.base import MultimodalEmbeddingAdapter
from app.multimodal.adapters.embedding.qwen_multimodal import QwenMultimodalEmbeddingAdapter

# ---- 单例缓存 ----
_storage: Optional[StorageAdapter] = None
_vision: Optional[VisionModelAdapter] = None
_embedding: Optional[MultimodalEmbeddingAdapter] = None


def get_storage() -> StorageAdapter:
    """获取存储适配器（V1.0 本地文件系统）。"""
    global _storage
    if _storage is None:
        _storage = LocalStorageAdapter(settings.multimodal_storage_path)
    return _storage


def get_vision_adapter() -> VisionModelAdapter:
    """获取视觉模型适配器（通义千问 VL）。"""
    global _vision
    if _vision is None:
        _vision = QwenVisionAdapter()
    return _vision


def get_embedding_adapter() -> MultimodalEmbeddingAdapter:
    """获取多模态 Embedding 适配器（通义多模态）。"""
    global _embedding
    if _embedding is None:
        _embedding = QwenMultimodalEmbeddingAdapter()
    return _embedding
