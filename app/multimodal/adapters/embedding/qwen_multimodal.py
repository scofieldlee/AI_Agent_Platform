"""通义多模态 Embedding 适配器 (DashScope multimodal-embedding-one-peace-v1, 1024 维).

依赖: DASHSCOPE_API_KEY。与 Vision 适配器共享同一个 Key。
"""

import logging
from typing import List

from app.core.config import settings
from app.multimodal.adapters.embedding.base import MultimodalEmbeddingAdapter

logger = logging.getLogger(__name__)


class QwenMultimodalEmbeddingAdapter(MultimodalEmbeddingAdapter):
    """通义多模态 Embedding：文本 / 图片 / 图文融合统一向量空间."""

    def __init__(self, model: str = None):
        self._model = model or settings.qwen_multimodal_embedding_model
        self._client = None

    @property
    def dimension(self) -> int:
        return settings.multimodal_embedding_dimension

    @property
    def model_name(self) -> str:
        return self._model

    def _ensure_client(self):
        if not settings.dashscope_api_key:
            raise RuntimeError(
                "DASHSCOPE_API_KEY 未配置：请在 .env 中设置后重启服务，"
                "并触发素材重新索引。")
        if self._client is None:
            import dashscope
            dashscope.api_key = settings.dashscope_api_key
            self._client = dashscope.MultiModalEmbedding
        return self._client

    async def _embed(self, contents: List[dict]) -> List[float]:
        """调用多模态 Embedding API."""
        client = self._ensure_client()
        response = await client.acall(model=self._model, input={"contents": contents})
        if response.status_code != 200:
            raise RuntimeError(
                f"DashScope embedding error {response.status_code}: {response.message}")
        embeddings = response.output.get("embeddings", [])
        if not embeddings:
            raise RuntimeError("DashScope embedding returned empty result")
        return embeddings[0].get("embedding", [])

    async def embed_text(self, text: str) -> List[float]:
        return await self._embed([{"text": text}])

    async def embed_image(self, image_path: str) -> List[float]:
        # dashscope SDK 支持本地文件路径（自动上传）
        return await self._embed([{"image": f"file://{image_path}"}])

    async def embed_text_image(self, text: str, image_path: str) -> List[float]:
        return await self._embed([{"image": f"file://{image_path}"}, {"text": text}])
