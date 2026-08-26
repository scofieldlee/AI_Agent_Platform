"""ImageGenerationTool: generate images from text prompts.

Bridges Agent workflows with the Model Center's image generation capability.
Generated images are persisted to the multimodal storage so they remain
accessible via the standard file serving endpoint.
"""

import asyncio
import base64
import logging
import uuid
from typing import Any, Dict

import httpx

from app.core.config import settings
from app.multimodal.adapters import get_storage
from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class ImageGenerationTool(BaseTool):
    """Generate images from text descriptions using an AI image model.

    Routes to DashScope Tongyi Wanxiang (wan2.7-image / wan2.7-image-pro)
    via the Model Center. Generated images are downloaded and stored in the
    multimodal storage area, returning API URLs that remain valid.
    """

    @property
    def name(self) -> str:
        return "image_generation"

    @property
    def description(self) -> str:
        return (
            "AI 图片生成工具。根据用户文字描述生成图片，适用于产品宣传图、"
            "场景图、创意图、概念图等。生成结果会保存到本地并通过 URL 返回，"
            "可在回答中直接展示给用户。"
        )

    @property
    def tool_type(self) -> str:
        return "creative"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "图片描述/提示词，越详细效果越好，例如 '一个小孩子在草地上玩 F11MINI 无人机，阳光明媚，产品特写'",
                },
                "size": {
                    "type": "string",
                    "description": "图片尺寸，例如 1024x1024（默认）、1024x768、768x1024",
                    "default": "1024x1024",
                },
                "n": {
                    "type": "integer",
                    "description": "生成图片数量，默认 1",
                    "default": 1,
                },
                "reference_images": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "参考图列表（最多 3 张，base64 或 data URL）。"
                        "提供后模型将基于参考图进行图生图（I2I）创作，"
                        "例如：知识库检索到的产品素材图、用户上传的图片。"
                        "未提供则执行纯文生图（T2I）。"
                    ),
                    "default": [],
                },
            },
            "required": ["prompt"],
        }

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "images": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "local_path": {"type": "string"},
                        },
                    },
                },
                "prompt": {"type": "string"},
                "model": {"type": "string"},
            },
        }

    async def execute(
        self,
        prompt: str,
        size: str = "1024x1024",
        n: int = 1,
        reference_images: list = None,
        agent_id: Any = None,
        conversation_id: Any = None,
        trace_id: Any = None,
        **kwargs,
    ) -> ToolResult:
        """Generate images and persist them to multimodal storage.

        Args:
            prompt: Text description of the desired image.
            size: Output size, e.g. "1024x1024".
            n: Number of images to generate.
            reference_images: Optional list of up to 3 reference images
                (base64 or data URLs). When provided, the model performs
                image-to-image creation grounded on these references
                (knowledge-base assets / user uploads); otherwise it falls
                back to pure text-to-image generation.
        """
        try:
            from app.models_center.service import ModelService

            references = [r for r in (reference_images or []) if r][:3]

            service = ModelService()
            result = await service.generate_image(
                prompt=prompt,
                size=size,
                n=n,
                reference_images=references,
            )

            images = result.get("images", [])
            if not images:
                return ToolResult(success=False, error="模型未返回任何图片")

            storage = get_storage()
            folder = f"generated/{agent_id or 'anonymous'}/{conversation_id or 'default'}"

            saved_images = []
            async with httpx.AsyncClient(timeout=120) as client:
                for idx, img in enumerate(images):
                    image_bytes = None
                    source = None

                    b64 = img.get("b64_json")
                    url = img.get("url")

                    if b64:
                        image_bytes = base64.b64decode(b64)
                        source = "b64"
                    elif url:
                        try:
                            r = await client.get(url)
                            r.raise_for_status()
                            image_bytes = r.content
                            source = url
                        except Exception as e:
                            logger.warning(
                                f"Failed to download generated image from {url}: {e}"
                            )
                            continue

                    if not image_bytes:
                        continue

                    filename = f"{uuid.uuid4().hex}_{idx}.png"
                    path = f"{folder}/{filename}"
                    await storage.upload(image_bytes, path)
                    local_abs_path = storage.abs_path(path)
                    public_url = f"/api/v1/multimodal/files/{path}"

                    saved_images.append({
                        "url": public_url,
                        "local_path": local_abs_path,
                        "source": source,
                    })

            if not saved_images:
                return ToolResult(
                    success=False,
                    error="图片生成成功但下载/保存失败，请稍后重试",
                )

            logger.info(
                f"ImageGenerationTool saved {len(saved_images)} image(s) "
                f"for prompt: {prompt[:60]}"
            )

            return ToolResult(
                success=True,
                data={
                    "images": saved_images,
                    "prompt": prompt,
                    "model": result.get("model", "unknown"),
                    "references_used": len(references),
                },
            )

        except Exception as e:
            logger.error(f"ImageGenerationTool failed: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))
