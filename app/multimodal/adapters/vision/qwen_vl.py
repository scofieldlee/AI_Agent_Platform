"""通义千问 VL 视觉模型适配器 (DashScope qwen-vl-max).

依赖: DASHSCOPE_API_KEY（app/core/config.py settings.dashscope_api_key）。
未配置 Key 时 analyze 抛出明确异常，调用方（Processor）将任务标记为 failed。
"""

import base64
import json
import logging
import re
from typing import Optional

from app.core.config import settings
from app.multimodal.adapters.vision.base import VisionModelAdapter

logger = logging.getLogger(__name__)

# 图片分析 Prompt：要求按固定 JSON Schema 输出
IMAGE_ANALYSIS_PROMPT = """你是专业的商业视觉分析师。请分析这张图片，严格按以下 JSON 格式输出，不要输出任何其他内容：
{
  "description": "一句话整体描述",
  "detail": "详细描述（含视觉主体、背景、氛围）",
  "objects": ["识别出的物体列表"],
  "scene": ["场景标签，如 indoor/outdoor/desktop/nature"],
  "style": ["风格标签，如 minimal/premium/commercial/tech"],
  "composition": {"angle": "拍摄角度", "subject_position": "主体位置", "negative_space": "留白方向"},
  "lighting": {"type": "natural/studio/mixed", "description": "光线描述"},
  "color": ["主色调"],
  "tags": ["3-8 个核心标签，中文"],
  "ocr": ["图片中识别到的所有文字"],
  "usage": ["适用场景，如 amazon/advertisement/social_media/brand_page"]
}"""

# 视频帧分析 Prompt
FRAME_ANALYSIS_PROMPT = """你是专业的视频镜头分析师。请分析这个视频帧，严格按以下 JSON 格式输出，不要输出任何其他内容：
{
  "description": "镜头内容一句话描述",
  "camera": "景别（close_up/medium/wide）",
  "camera_movement": "推测的运镜（static/push_in/pull_out/pan/tilt/follow）",
  "subject": ["画面主体"],
  "action": "主体动作",
  "style": ["视觉风格标签"],
  "lighting": {"type": "natural/studio/mixed", "description": "光线描述"},
  "composition": {"type": "构图类型"},
  "tags": ["3-6 个核心标签，中文"]
}"""

OCR_PROMPT = """请识别图片中的所有文字，严格按以下 JSON 格式输出，不要输出任何其他内容：
{"texts": ["识别到的第一段文字", "识别到的第二段文字"]}"""

SCENE_PROMPT = """请简要描述图片，严格按以下 JSON 格式输出，不要输出任何其他内容：
{"description": "一句话描述", "scene": ["场景标签"], "objects": ["物体列表"]}"""


def _extract_json(text: str) -> dict:
    """从模型输出提取 JSON（三层防御：代码块 → 首尾大括号 → 失败抛异常）."""
    if not text:
        raise ValueError("Empty model output")
    # 1. ```json ... ``` 代码块
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    # 2. 首个 { 到末个 }
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start:end + 1])
    # 3. 直接解析
    return json.loads(text)


class QwenVisionAdapter(VisionModelAdapter):
    """通义千问 VL 适配器（DashScope MultiModalConversation API）."""

    def __init__(self, model: Optional[str] = None):
        self._model = model or settings.qwen_vl_model
        self._client = None

    @property
    def model_name(self) -> str:
        return self._model

    def _ensure_client(self):
        """懒加载 dashscope 并校验 API Key。"""
        if not settings.dashscope_api_key:
            raise RuntimeError(
                "DASHSCOPE_API_KEY 未配置：请在 .env 中设置后重启服务，"
                "并触发素材重新分析。")
        if self._client is None:
            import dashscope
            dashscope.api_key = settings.dashscope_api_key
            self._client = dashscope.MultiModalConversation
        return self._client

    @staticmethod
    def _image_content(image_path: str) -> dict:
        """读取本地图片 → base64 data URL 消息段."""
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        ext = image_path.rsplit(".", 1)[-1].lower()
        if ext in ("jpg", "jpeg"):
            ext = "jpeg"
        return {"image": f"data:image/{ext};base64,{b64}"}

    async def _call(self, image_path: str, prompt: str) -> str:
        """调用多模态对话，返回文本输出。"""
        client = self._ensure_client()
        messages = [{"role": "user", "content": [
            self._image_content(image_path),
            {"text": prompt},
        ]}]
        response = await client.acall(model=self._model, messages=messages)
        if response.status_code != 200:
            raise RuntimeError(f"DashScope API error {response.status_code}: {response.message}")
        # 输出格式: content = [[{"text": "..."}]]
        content = response.output.choices[0].message.content
        if isinstance(content, list):
            text = "".join(
                seg.get("text", "") for seg in content if isinstance(seg, dict))
        else:
            text = str(content)
        return text

    async def analyze_image(self, image_path: str, prompt: Optional[str] = None) -> dict:
        text = await self._call(image_path, prompt or IMAGE_ANALYSIS_PROMPT)
        try:
            result = _extract_json(text)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Image analysis JSON parse failed: {e}; raw={text[:200]}")
            # 降级：原文作为 description
            result = {"description": text.strip()[:500], "tags": [], "ocr": []}
        result.setdefault("tags", [])
        result.setdefault("objects", [])
        result.setdefault("scene", [])
        result.setdefault("style", [])
        result.setdefault("ocr", [])
        return result

    async def analyze_video_frame(self, frame_path: str, prompt: Optional[str] = None) -> dict:
        text = await self._call(frame_path, prompt or FRAME_ANALYSIS_PROMPT)
        try:
            result = _extract_json(text)
        except (json.JSONDecodeError, ValueError):
            result = {"description": text.strip()[:500], "tags": []}
        result.setdefault("tags", [])
        result.setdefault("subject", [])
        result.setdefault("style", [])
        return result

    async def ocr(self, image_path: str) -> list:
        text = await self._call(image_path, OCR_PROMPT)
        try:
            data = _extract_json(text)
            return data.get("texts", [])
        except (json.JSONDecodeError, ValueError):
            return []

    async def describe_scene(self, image_path: str) -> dict:
        text = await self._call(image_path, SCENE_PROMPT)
        try:
            return _extract_json(text)
        except (json.JSONDecodeError, ValueError):
            return {"description": text.strip()[:500], "scene": [], "objects": []}
