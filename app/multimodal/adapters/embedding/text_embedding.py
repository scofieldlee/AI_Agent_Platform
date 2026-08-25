"""文本 Embedding 适配器 — 复用现有 :8001 Embedding 微服务 (bge-small-zh-v1.5, 512 维).

仅用于纯文本单元的降级索引（如 DashScope 不可用时的音频转写检索）。
注意：bge 向量与通义多模态向量不在同一空间，**不可混用**，
mm_index_records 中统一使用 QwenMultimodalEmbeddingAdapter，
本适配器仅作为 text 维度备选方案保留。
"""

import logging
from typing import List

import httpx

from app.core.config import settings
from app.multimodal.adapters.embedding.base import MultimodalEmbeddingAdapter

logger = logging.getLogger(__name__)

EMBEDDING_SERVICE_URL = "http://localhost:8001/embed"


class TextEmbeddingAdapter(MultimodalEmbeddingAdapter):
    """复用本地 Embedding 微服务的文本适配器（512 维，仅文本）。"""

    def __init__(self, service_url: str = EMBEDDING_SERVICE_URL):
        self._service_url = service_url

    @property
    def dimension(self) -> int:
        return settings.embedding_dimension  # 512

    @property
    def model_name(self) -> str:
        return settings.embedding_model

    async def embed_text(self, text: str) -> List[float]:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(self._service_url, json={"texts": [text]})
            resp.raise_for_status()
            data = resp.json()
            embeddings = data.get("embeddings") or data.get("data")
            if not embeddings:
                raise RuntimeError("Embedding service returned empty result")
            return embeddings[0]

    async def embed_image(self, image_path: str) -> List[float]:
        raise NotImplementedError("TextEmbeddingAdapter 不支持图片 Embedding")

    async def embed_text_image(self, text: str, image_path: str) -> List[float]:
        raise NotImplementedError("TextEmbeddingAdapter 不支持图文融合 Embedding")
