"""VideoGenerationTool: generate videos from text prompts (+ optional first frame).

Bridges Agent workflows with the Model Center's video generation capability
(Token Plan HappyHorse models, billed against the plan quota).

The upstream API is asynchronous (submit → poll → video URL valid 24h), so
the tool downloads the generated MP4 and persists it to multimodal storage,
returning a stable API URL that remains valid.
"""

import logging
import uuid
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings
from app.multimodal.adapters import get_storage
from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class VideoGenerationTool(BaseTool):
    """Generate videos from text descriptions using a Plan-included AI model.

    Two modes:
    - Text-to-video (T2V): prompt only → happyhorse-1.1-t2v.
    - Image-to-video (I2V): prompt + first_frame_image (base64 data URL or
      public URL) → happyhorse-1.1-i2v; the image drives the first frame
      while the prompt steers motion/content.
    """

    @property
    def name(self) -> str:
        return "video_generation"

    @property
    def description(self) -> str:
        return (
            "AI 视频生成工具。根据用户文字描述生成短视频（支持 3-15 秒、"
            "480P/720P/1080P、16:9 等比例），适用于产品宣传视频、场景演示、"
            "创意短片等。可提供一张首帧参考图（知识库素材图或用户上传图片）"
            "进行图生视频（I2V）创作，使视频画面与参考图主体保持一致；"
            "未提供首帧则按文字描述纯文生视频（T2V）。生成结果会保存到本地"
            "并通过 URL 返回，可在回答中直接展示给用户。"
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
                    "description": (
                        "视频内容描述/提示词，包含主体、动作、场景、镜头运动等，"
                        "例如 'F11PRO 无人机在夕阳下的草原上空平稳飞行，镜头环绕跟拍'"
                    ),
                },
                "resolution": {
                    "type": "string",
                    "description": "视频分辨率：480P、720P（默认）、1080P",
                    "default": "720P",
                },
                "ratio": {
                    "type": "string",
                    "description": "视频宽高比（仅文生视频生效），如 16:9（默认）、9:16、1:1",
                    "default": "16:9",
                },
                "duration": {
                    "type": "integer",
                    "description": "视频时长（秒），3-15 之间，默认 5",
                    "default": 5,
                },
                "first_frame_image": {
                    "type": "string",
                    "description": (
                        "首帧参考图（base64 data URL 或公网 URL，最多 1 张）。"
                        "提供后走图生视频（I2V）：视频第一帧与该图一致，"
                        "提示词控制后续运动与内容；未提供则纯文生视频（T2V）。"
                    ),
                    "default": "",
                },
                "model": {
                    "type": "string",
                    "description": (
                        "视频生成模型名。默认自动选择：有首帧图用 "
                        "happyhorse-1.1-i2v，无首帧图用 happyhorse-1.1-t2v"
                    ),
                    "default": "",
                },
            },
            "required": ["prompt"],
        }

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "videos": {
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
                "duration": {"type": "integer"},
            },
        }

    async def execute(
        self,
        prompt: str,
        resolution: str = "720P",
        ratio: str = "16:9",
        duration: int = 5,
        first_frame_image: Optional[str] = None,
        model: Optional[str] = None,
        agent_id: Any = None,
        conversation_id: Any = None,
        trace_id: Any = None,
        **kwargs,
    ) -> ToolResult:
        """Generate a video and persist it to multimodal storage.

        Note: this call is long-running — the upstream async task typically
        takes 1-5 minutes, and the tool blocks until it completes (or the
        configured max wait is exceeded).
        """
        try:
            from app.models_center.service import ModelService

            first_frame = first_frame_image if first_frame_image else None

            service = ModelService()
            result = await service.generate_video(
                prompt=prompt,
                model=model or None,
                resolution=resolution,
                ratio=ratio,
                duration=duration,
                first_frame_image=first_frame,
            )

            videos = result.get("videos", [])
            if not videos:
                return ToolResult(success=False, error="模型未返回任何视频")

            storage = get_storage()
            folder = f"generated/{agent_id or 'anonymous'}/{conversation_id or 'default'}"

            saved_videos = []
            download_timeout = settings.qwen_video_download_timeout_seconds
            async with httpx.AsyncClient(timeout=download_timeout) as client:
                for idx, vid in enumerate(videos):
                    url = vid.get("url")
                    if not url:
                        continue
                    try:
                        r = await client.get(url)
                        r.raise_for_status()
                        video_bytes = r.content
                    except Exception as e:
                        logger.warning(
                            f"Failed to download generated video from {url[:100]}: {e}"
                        )
                        continue

                    filename = f"{uuid.uuid4().hex}_{idx}.mp4"
                    path = f"{folder}/{filename}"
                    await storage.upload(video_bytes, path)
                    local_abs_path = storage.abs_path(path)
                    public_url = f"/api/v1/multimodal/files/{path}"

                    saved_videos.append({
                        "url": public_url,
                        "local_path": local_abs_path,
                        "source": url,
                    })

            if not saved_videos:
                return ToolResult(
                    success=False,
                    error="视频生成成功但下载/保存失败，请稍后重试",
                )

            logger.info(
                f"VideoGenerationTool saved {len(saved_videos)} video(s) "
                f"for prompt: {prompt[:60]}"
            )

            return ToolResult(
                success=True,
                data={
                    "videos": saved_videos,
                    "prompt": prompt,
                    "model": result.get("model", "unknown"),
                    "resolution": result.get("resolution", resolution),
                    "duration": result.get("duration", duration),
                    "first_frame_used": result.get("first_frame_used", False),
                    "task_id": result.get("task_id"),
                },
            )

        except Exception as e:
            logger.error(f"VideoGenerationTool failed: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))
