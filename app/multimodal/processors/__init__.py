"""异步处理器 — 每种素材类型一个 Processor."""

from app.multimodal.processors import (
    image_processor, video_processor, audio_processor, ppt_processor,
)

__all__ = ["image_processor", "video_processor", "audio_processor", "ppt_processor"]
