"""本地多模态 Embedding 适配器（llama.cpp llama-server + Qwen3-VL-Embedding-2B）.

部署参考: docs/多模态向量检索说明.md

- 服务: llama-server (launchd 常驻), OpenAI 兼容 POST /v1/embeddings
- 端点: http://127.0.0.1:8088 (仅本机监听)
- 向量: 2048 维, 文本 / 图像 / 图文混合统一向量空间
- 图像输入: 必须用 image_data 格式(base64) 并带 prompt_string 占位符 [img-<id>]
- 图文融合: 多元素 input 每元素独立输出向量, 融合向量取二者平均后归一化
  (模型为统一嵌入空间, 相关图文对余弦 ~0.9, 平均是合理的联合表示)
"""

import base64
import json
import logging
import math
from pathlib import Path
from typing import List

import httpx

from app.core.config import settings
from app.multimodal.adapters.embedding.base import MultimodalEmbeddingAdapter

logger = logging.getLogger(__name__)

IMAGE_PROMPT_TEMPLATE = "Image: [img-{id}]."


class LocalQwenVLEmbeddingAdapter(MultimodalEmbeddingAdapter):
    """Qwen3-VL-Embedding-2B 本地适配器（无 Key、无网络依赖、2048 维）."""

    def __init__(self):
        self._base_url = settings.local_embedding_base_url.rstrip("/")
        self._model = settings.local_embedding_model
        self._timeout = settings.local_embedding_timeout_seconds

    @property
    def dimension(self) -> int:
        return settings.multimodal_embedding_dimension

    @property
    def model_name(self) -> str:
        return self._model

    # ---------- 底层调用 ----------

    async def _embed(self, input_items: List[dict]) -> List[List[float]]:
        """调用 llama-server /v1/embeddings, 返回与 input 等长的向量列表."""
        url = f"{self._base_url}/v1/embeddings"
        payload = {"model": self._model, "input": input_items}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
            except httpx.ConnectError as e:
                raise RuntimeError(
                    f"本地 Embedding 服务不可达（{self._base_url}）: {e}. "
                    "请确认 llama-server 已启动: "
                    "launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/"
                    "com.local.llama-qwen3-vl-embed.plist")
            except httpx.HTTPStatusError as e:
                raise RuntimeError(
                    f"本地 Embedding 服务返回 {e.response.status_code}: "
                    f"{e.response.text[:200]}")
        data = resp.json().get("data", [])
        if not data:
            raise RuntimeError("本地 Embedding 服务返回空结果")
        # 按 index 排序, 保证与 input 顺序一致
        data.sort(key=lambda x: x.get("index", 0))
        vectors = [item.get("embedding", []) for item in data]
        for v in vectors:
            if len(v) != self.dimension:
                raise RuntimeError(
                    f"Embedding 维度不匹配: {len(v)} != {self.dimension}"
                    "（请检查 MULTIMODAL_EMBEDDING_DIMENSION 与模型配置）")
        return vectors

    @staticmethod
    def _image_to_data_url_b64(image_path: str) -> str:
        """本地图片 → base64（llama-server image_data.data 要求裸 base64）."""
        path = Path(image_path)
        if not path.exists():
            raise RuntimeError(f"图片文件不存在: {image_path}")
        return base64.b64encode(path.read_bytes()).decode()

    @staticmethod
    def _normalize(vec: List[float]) -> List[float]:
        """L2 归一化（平均融合后恢复单位长度，保证余弦计算语义一致）."""
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    # ---------- 公共接口 ----------

    async def embed_text(self, text: str) -> List[float]:
        vectors = await self._embed([{"type": "text", "prompt_string": text[:2000]}])
        return vectors[0]

    async def embed_image(self, image_path: str) -> List[float]:
        img_b64 = self._image_to_data_url_b64(image_path)
        vectors = await self._embed([{
            "type": "image_data",
            "image_data": {"id": 1, "data": img_b64},
            "prompt_string": IMAGE_PROMPT_TEMPLATE.format(id=1),
        }])
        return vectors[0]

    async def embed_text_image(self, text: str, image_path: str) -> List[float]:
        """图文融合向量：image 与 text 独立编码后取平均并归一化."""
        img_b64 = self._image_to_data_url_b64(image_path)
        vectors = await self._embed([
            {
                "type": "image_data",
                "image_data": {"id": 1, "data": img_b64},
                "prompt_string": IMAGE_PROMPT_TEMPLATE.format(id=1),
            },
            {"type": "text", "prompt_string": (text or "")[:2000]},
        ])
        fused = [(a + b) / 2.0 for a, b in zip(vectors[0], vectors[1])]
        return self._normalize(fused)
