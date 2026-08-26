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
                    "description": "多模态知识库 ID，不填则搜索全部活跃知识库并合并结果",
                },
                "asset_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "素材类型过滤，如 ['image'] 只检索图片素材；不填则不过滤",
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
                            "thumbnail_url": {"type": "string"},
                        },
                    },
                },
                "total": {"type": "integer"},
                "knowledge_base_id": {"type": "integer"},
            },
        }

    async def execute(self, query: str = None, image_base64: str = None,
                      image_ext: str = "jpg", knowledge_base_id: int = None,
                      asset_types: List[str] = None, max_results: int = 5,
                      **kwargs) -> ToolResult:
        """Search the multimodal knowledge base.

        Args:
            query: Search keyword or question (optional if image given).
            image_base64: Optional base64-encoded query image; enables
                image-to-image or fused text+image retrieval.
            image_ext: Query image file extension (default 'jpg').
            knowledge_base_id: Optional KB id; defaults to ALL active KBs.
            asset_types: Optional list of asset types to filter, e.g.
                ["image"] to only retrieve image assets (used by the
                image generation flow to find reference assets).
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
                # 1. Resolve target KB(s)
                #    - knowledge_base_id given  → search that KB only
                #    - otherwise                → search ALL active KBs and merge
                #      (previous behaviour of picking only the first active KB
                #       silently missed assets living in other KBs)
                kb_ids = [knowledge_base_id] if knowledge_base_id else []
                if not kb_ids:
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
                    kb_ids = [k.id for k in active]

                # 2. Vector search (text / image / fused) across KBs
                merged: List[Dict[str, Any]] = []
                seen_assets = set()
                query_type = "text"
                first_error = None
                for kid in kb_ids:
                    result = await search_service.search(
                        db,
                        knowledge_base_id=kid,
                        query=query,
                        query_image_data=query_image_data,
                        query_image_ext=image_ext or "jpg",
                        asset_types=asset_types,
                        top_k=max_results,
                    )
                    if "error" in result:
                        first_error = first_error or result["error"]
                        continue
                    query_type = result.get("query_type", query_type)
                    for item in result.get("results", []):
                        aid = item.get("asset_id")
                        if aid in seen_assets:
                            continue
                        seen_assets.add(aid)
                        item["_kb_id"] = kid
                        merged.append(item)

            if not kb_ids or (first_error and not merged):
                return ToolResult(success=False, error=first_error or "检索失败")

            # Sort merged hits by score desc, keep top_k
            merged.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)
            result = {"results": merged[:max_results], "query_type": query_type}

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
                    # Thumbnail URL so the LLM can display image assets inline
                    "thumbnail_url": item.get("thumbnail_url"),
                    "knowledge_base_id": item.get("_kb_id"),
                })

            total = len(assets)
            logger.info(
                f"MultimodalKBSearch executed | query={str(query)[:50]} | "
                f"mode={result.get('query_type')} | kbs={kb_ids} | results={total}"
            )

            return ToolResult(
                success=True,
                data={
                    "query": query,
                    "query_type": result.get("query_type", "text"),
                    "knowledge_base_ids": kb_ids,
                    "assets": assets,
                    "total": total,
                },
            )

        except Exception as e:
            logger.error(f"MultimodalKBSearch failed: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))
