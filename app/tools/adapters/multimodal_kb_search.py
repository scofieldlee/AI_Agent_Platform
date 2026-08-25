"""
MultimodalKBSearchTool: search the multimodal knowledge base.

Tool Center adapter that bridges Agent workflows with the multimodal
knowledge base module (app.multimodal). Supports text-query retrieval
across indexed assets (documents / images / audio / video / PPT).

If knowledge_base_id is not provided, the first active KB is used.
"""

import logging
from typing import Dict, Any, List

from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class MultimodalKBSearchTool(BaseTool):
    """Search the multimodal knowledge base by text and/or image.

    Executes a vector search over multimodal knowledge units
    (asset descriptions, slide content, audio transcripts, etc.)
    and returns the most relevant assets with their descriptions.

    Supported query modes:
    - query only: text vector search
    - image_base64 only: image-to-image search (以图搜图)
    - query + image_base64: fused text+image retrieval (图文融合检索)

    Parameters:
    - query: Search keyword or question
    - image_base64: Optional base64-encoded query image
    - knowledge_base_id: Optional KB id (defaults to first active KB)
    - max_results: Maximum number of assets (default 5)
    """

    @property
    def name(self) -> str:
        return "multimodal_kb_search"

    @property
    def description(self) -> str:
        return (
            "多模态知识库检索工具。支持三种检索方式："
            "1) 文本检索：根据关键词在多模态知识库中向量检索；"
            "2) 以图搜图：传入 base64 图片，检索视觉上最相似的素材；"
            "3) 图文融合：同时传入文字和图片，融合检索最相关素材。"
            "返回最相关的素材（文档/图片/音频/视频/PPT）及其描述内容。"
            "适用场景：查找产品资料、图片素材、视频介绍，或根据用户"
            "上传的图片在素材库中寻找相似内容。"
        )

    @property
    def tool_type(self) -> str:
        return "knowledge"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词或问题，如 '产品参数'、'宣传图'",
                },
                "image_base64": {
                    "type": "string",
                    "description": "查询图片的 base64 编码（可不含 data: 前缀）。"
                    "提供后启用以图搜图/图文融合检索",
                },
                "image_ext": {
                    "type": "string",
                    "description": "查询图片扩展名，默认 jpg",
                },
                "knowledge_base_id": {
                    "type": "integer",
                    "description": "多模态知识库 ID，不填则使用默认（第一个活跃知识库）",
                },
                "max_results": {
                    "type": "integer",
                    "description": "最大返回结果数，默认 5",
                },
            },
            "required": [],
        }

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "assets": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "asset_id": {"type": "integer"},
                            "asset_name": {"type": "string"},
                            "asset_type": {"type": "string"},
                            "description": {"type": "string"},
                            "content": {"type": "string"},
                            "tags": {"type": "array", "items": {"type": "string"}},
                            "score": {"type": "number"},
                        },
                    },
                },
                "total": {"type": "integer"},
                "knowledge_base_id": {"type": "integer"},
            },
        }

    async def execute(self, query: str = None, image_base64: str = None,
                      image_ext: str = "jpg", knowledge_base_id: int = None,
                      max_results: int = 5, **kwargs) -> ToolResult:
        """Search the multimodal knowledge base.

        Args:
            query: Search keyword or question (optional if image given).
            image_base64: Optional base64-encoded query image; enables
                image-to-image or fused text+image retrieval.
            image_ext: Query image file extension (default 'jpg').
            knowledge_base_id: Optional KB id; defaults to first active KB.
            max_results: Maximum assets to return.
        """
        import base64 as b64_mod

        try:
            from app.database.session import async_session_factory
            from app.multimodal.repositories import knowledge_base_repo
            from app.multimodal.services import search_service

            if not query and not image_base64:
                return ToolResult(
                    success=False,
                    error="必须提供 query（文本检索）或 image_base64（以图搜图）",
                )

            # Decode query image (strip data URI prefix if present)
            query_image_data = None
            if image_base64:
                raw = image_base64
                if raw.startswith("data:"):
                    raw = raw.split(",", 1)[1]
                try:
                    query_image_data = b64_mod.b64decode(raw)
                except Exception as e:
                    return ToolResult(
                        success=False,
                        error=f"image_base64 解码失败: {e}",
                    )

            async with async_session_factory() as db:
                # 1. Resolve target KB
                kb_id = knowledge_base_id
                if not kb_id:
                    kbs = await knowledge_base_repo.list_kbs(db)
                    active = [k for k in kbs if k.is_active and k.status == "active"]
                    if not active:
                        return ToolResult(
                            success=True,
                            data={
                                "assets": [],
                                "total": 0,
                                "message": "多模态知识库为空或无活跃知识库",
                            },
                        )
                    kb_id = active[0].id

                # 2. Vector search (text / image / fused)
                result = await search_service.search(
                    db,
                    knowledge_base_id=kb_id,
                    query=query,
                    query_image_data=query_image_data,
                    query_image_ext=image_ext or "jpg",
                    top_k=max_results,
                )

            if "error" in result:
                return ToolResult(success=False, error=result["error"])

            # 3. Build structured results
            assets: List[Dict[str, Any]] = []
            for item in result.get("results", []):
                assets.append({
                    "asset_id": item.get("asset_id"),
                    "asset_name": item.get("asset_name"),
                    "asset_type": item.get("asset_type"),
                    "description": (item.get("description") or "")[:300] or None,
                    "content": item.get("content"),
                    "tags": item.get("tags", []),
                    "score": round(float(item.get("score", 0.0)), 4),
                })

            total = len(assets)
            logger.info(
                f"MultimodalKBSearch executed | query={str(query)[:50]} | "
                f"mode={result.get('query_type')} | kb={kb_id} | results={total}"
            )

            return ToolResult(
                success=True,
                data={
                    "query": query,
                    "query_type": result.get("query_type", "text"),
                    "knowledge_base_id": kb_id,
                    "assets": assets,
                    "total": total,
                },
            )

        except Exception as e:
            logger.error(f"MultimodalKBSearch failed: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))
