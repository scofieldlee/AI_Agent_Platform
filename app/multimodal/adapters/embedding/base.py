"""Multimodal embedding adapter — abstract base class.

为支持跨模态检索（文本↔图片），本模块统一使用同一多模态 Embedding 空间，
text / image / text+image 查询均由同一适配器生成向量。
"""

from abc import ABC, abstractmethod
from typing import List, Optional


class MultimodalEmbeddingAdapter(ABC):
    """多模态 Embedding 适配器接口."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """向量维度。"""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """模型名。"""

    @abstractmethod
    async def embed_text(self, text: str) -> List[float]:
        """文本 → 向量。"""

    @abstractmethod
    async def embed_image(self, image_path: str) -> List[float]:
        """本地图片 → 向量。"""

    @abstractmethod
    async def embed_text_image(self, text: str, image_path: str) -> List[float]:
        """文本 + 图片融合 → 向量（用于"参考这张图找类似素材"场景）。"""
