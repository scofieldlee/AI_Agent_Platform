"""Vision model adapter — abstract base class.

视觉理解统一入口：图片分析 / 视频帧分析 / OCR / 场景描述。
业务层通过 AnalysisService 调用，不直接依赖具体厂商 SDK。
"""

from abc import ABC, abstractmethod
from typing import Optional


class VisionModelAdapter(ABC):
    """视觉模型适配器接口."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """当前使用的模型名。"""

    @abstractmethod
    async def analyze_image(self, image_path: str, prompt: Optional[str] = None) -> dict:
        """图片 AI 分析，返回结构化结果:
        {description, tags, scene, style, objects, composition, lighting, ocr, usage}
        """

    @abstractmethod
    async def analyze_video_frame(self, frame_path: str, prompt: Optional[str] = None) -> dict:
        """视频关键帧分析，返回:
        {description, camera, camera_movement, subject, action, style, lighting, composition, tags}
        """

    @abstractmethod
    async def ocr(self, image_path: str) -> list:
        """OCR 文字识别，返回 [{text, position}]。"""

    @abstractmethod
    async def describe_scene(self, image_path: str) -> dict:
        """场景描述（轻量），返回 {description, scene, objects}。"""
