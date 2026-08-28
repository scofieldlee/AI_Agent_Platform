"""Adapters — 适配器工厂.

统一入口：根据类型获取适配器实例（默认单例缓存）。
"""

import logging
from typing import Optional

from app.core.config import settings
from app.multimodal.adapters.storage.base import StorageAdapter
from app.multimodal.adapters.storage.local_storage import LocalStorageAdapter
from app.multimodal.adapters.vision.base import VisionModelAdapter
from app.multimodal.adapters.vision.qwen_vl import QwenVisionAdapter
from app.multimodal.adapters.embedding.base import MultimodalEmbeddingAdapter

logger = logging.getLogger(__name__)
from app.multimodal.adapters.embedding.qwen_multimodal import QwenMultimodalEmbeddingAdapter
from app.multimodal.adapters.embedding.local_qwen_vl import LocalQwenVLEmbeddingAdapter

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
    """获取多模态 Embedding 适配器（按 MULTIMODAL_EMBEDDING_BACKEND 路由）.

    - dashscope（默认）: 通义 one-peace / text-embedding-v4 降级链（需按量 Key）
    - local: 本地 llama-server Qwen3-VL-Embedding-2B（2048 维，无 Key）
    """
    global _embedding
    if _embedding is None:
        if settings.multimodal_embedding_backend == "local":
            logger.info("Embedding backend: local llama-server (%s)",
                        settings.local_embedding_base_url)
            _embedding = LocalQwenVLEmbeddingAdapter()
        else:
            _embedding = QwenMultimodalEmbeddingAdapter()
    return _embedding
