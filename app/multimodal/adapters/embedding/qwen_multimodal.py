"""通义多模态 Embedding 适配器 (DashScope multimodal-embedding-one-peace-v1, 1024 维).

依赖: DASHSCOPE_API_KEY。与 Vision 适配器共享同一个 Key。

降级策略（自动）:
- 首选 multimodal-embedding-one-peace-v1（图文统一向量空间，跨模态检索效果最佳）。
- 该模型不可用（如免费额度耗尽 403 Throttling.AllocationQuota）时自动降级:
  * 文本 → text-embedding-v4（1024 维，与 pgvector Vector(1024) 列一致）
  * 图片 → qwen-vl-max 生成中文描述 → 描述文本走 text-embedding-v4
    （跨模态检索仍可用：文本查询与"图片描述向量"同空间，精度略低于原生多模态）
- 降级状态在单例适配器生命周期内保持（sticky），model_name 反映实际使用的模型，
  会被写入 mm_index_records.model_name 便于审计与重建索引。
- 恢复 one-peace 额度后重启服务并触发重建索引（reindex）即可切回原生多模态。
"""

import asyncio
import logging
from typing import List

from app.core.config import settings
from app.multimodal.adapters.embedding.base import MultimodalEmbeddingAdapter

logger = logging.getLogger(__name__)

# 图片降级描述 Prompt：生成适合检索的密集描述
CAPTION_PROMPT = (
    "请用一段简洁的中文详细描述这张图片，包含主体、场景、动作、风格和主要颜色，"
    "直接输出描述文字本身，不要任何前缀、引号或标点以外的格式。"
)


class QwenMultimodalEmbeddingAdapter(MultimodalEmbeddingAdapter):
    """通义多模态 Embedding：文本 / 图片 / 图文融合统一向量空间（含自动降级）."""

    def __init__(self, model: str = None):
        self._model = model or settings.qwen_multimodal_embedding_model
        self._fallback_model = settings.qwen_text_embedding_model
        self._mm_client = None
        self._text_client = None
        self._fallback_mode = False   # one-peace 不可用后置 True（sticky）

    @property
    def dimension(self) -> int:
        return settings.multimodal_embedding_dimension

    @property
    def model_name(self) -> str:
        """实际生效的模型（写入 mm_index_records 供审计）."""
        return self._fallback_model if self._fallback_mode else self._model

    def _ensure_clients(self):
        if not settings.dashscope_api_key:
            raise RuntimeError(
                "DASHSCOPE_API_KEY 未配置：请在 .env 中设置后重启服务，"
                "并触发素材重新索引。")
        import dashscope
        dashscope.api_key = settings.dashscope_api_key
        if self._mm_client is None:
            self._mm_client = dashscope.MultiModalEmbedding
        if self._text_client is None:
            self._text_client = dashscope.TextEmbedding
        return self._mm_client, self._text_client

    # ---------- 原生多模态（one-peace） ----------

    async def _embed_one_peace(self, contents: List[dict]) -> List[float]:
        mm_client, _ = self._ensure_clients()
        # dashscope SDK 仅提供同步 call（无 acall），用线程池避免阻塞事件循环
        response = await asyncio.to_thread(
            mm_client.call, model=self._model, input={"contents": contents})
        if response.status_code != 200:
            raise RuntimeError(
                f"DashScope embedding error {response.status_code}: {response.message}")
        embeddings = response.output.get("embeddings", [])
        if not embeddings:
            raise RuntimeError("DashScope embedding returned empty result")
        return embeddings[0].get("embedding", [])

    # ---------- 降级路径（text-embedding-v4 + VL 描述） ----------

    async def _embed_text_fallback(self, text: str) -> List[float]:
        _, text_client = self._ensure_clients()
        # dashscope SDK 仅提供同步 call，用线程池包装
        response = await asyncio.to_thread(
            text_client.call, model=self._fallback_model, input=[text[:2000]])
        if response.status_code != 200:
            raise RuntimeError(
                f"DashScope text-embedding error {response.status_code}: "
                f"{response.message}")
        embeddings = response.output.get("embeddings", [])
        if not embeddings:
            raise RuntimeError("DashScope text-embedding returned empty result")
        vec = embeddings[0].get("embedding", [])
        if len(vec) != settings.multimodal_embedding_dimension:
            raise RuntimeError(
                f"Embedding 维度不匹配: {len(vec)} != "
                f"{settings.multimodal_embedding_dimension}（请检查模型配置）")
        return vec

    async def _caption_image(self, image_path: str) -> str:
        """降级：用 qwen-vl 生成图片中文描述（懒导入避免循环依赖）."""
        from app.multimodal.adapters.vision.qwen_vl import QwenVisionAdapter
        vision = QwenVisionAdapter()
        text = await vision._call(image_path, CAPTION_PROMPT)
        return text.strip()

    def _engage_fallback(self, error: RuntimeError):
        logger.warning(
            "多模态 Embedding(%s) 不可用，自动降级: 文本→%s，图片→VL描述→文本向量。"
            "原因: %s", self._model, self._fallback_model, error)
        self._fallback_mode = True

    # ---------- 公共接口 ----------

    async def embed_text(self, text: str) -> List[float]:
        if not self._fallback_mode:
            try:
                return await self._embed_one_peace([{"text": text}])
            except RuntimeError as e:
                self._engage_fallback(e)
        return await self._embed_text_fallback(text)

    async def embed_image(self, image_path: str) -> List[float]:
        if not self._fallback_mode:
            try:
                # dashscope SDK 支持本地文件路径（自动上传）
                return await self._embed_one_peace([{"image": f"file://{image_path}"}])
            except RuntimeError as e:
                self._engage_fallback(e)
        caption = await self._caption_image(image_path)
        if not caption:
            caption = "empty image"
        return await self._embed_text_fallback(caption)

    async def embed_text_image(self, text: str, image_path: str) -> List[float]:
        if not self._fallback_mode:
            try:
                return await self._embed_one_peace(
                    [{"image": f"file://{image_path}"}, {"text": text}])
            except RuntimeError as e:
                self._engage_fallback(e)
        caption = await self._caption_image(image_path)
        combined = f"{text}\n{caption.strip()}" if text else caption.strip()
        return await self._embed_text_fallback(combined or "empty query")
