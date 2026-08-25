"""图片处理器 — 图片素材的 AI 分析流程（Phase 2）.

图片的上传即时缩略图在 asset_service 完成；
本处理器负责 AI 分析编排（调 analysis_service）。
"""

import logging
from typing import Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.multimodal.services import analysis_service

logger = logging.getLogger(__name__)


async def process(db: AsyncSession, asset_id: int) -> Dict[str, Any]:
    """图片素材处理入口（Worker 调用）。"""
    return await analysis_service.analyze_image_asset(db, asset_id)
