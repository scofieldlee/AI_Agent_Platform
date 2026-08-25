"""多模态检索服务 — 文本→图片 / 图片→图片 / 文本+图片 融合检索."""

import logging
import uuid
from typing import Optional, List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.multimodal.adapters import get_embedding_adapter
from app.multimodal.repositories import index_repo, asset_repo, knowledge_unit_repo
from app.multimodal.services import storage_service

logger = logging.getLogger(__name__)


async def _assemble_results(db: AsyncSession, hits: List[dict],
                            top_k: int) -> List[Dict[str, Any]]:
    """把向量检索命中组装为完整结果（素材信息 + 单元信息 + 标签）。"""
    results = []
    seen_assets = set()
    for hit in hits:
        if len(results) >= top_k:
            break
        asset = await asset_repo.get_asset(db, hit["asset_id"])
        if not asset:
            continue
        # 同素材去重（保留最高分单元）
        if asset.id in seen_assets:
            continue
        seen_assets.add(asset.id)

        unit = await knowledge_unit_repo.get_unit(db, hit["unit_id"]) if hit["unit_id"] else None
        tags = await asset_repo.get_asset_tags(db, asset.id)

        item = {
            "asset_id": asset.id,
            "asset_code": asset.asset_code,
            "asset_name": asset.name,
            "asset_type": asset.file_type,
            "unit_id": unit.id if unit else None,
            "unit_type": unit.unit_type if unit else None,
            "unit_index": unit.unit_index if unit else None,
            "score": hit["score"],
            "description": (unit.description if unit and unit.description
                            else (asset.attributes or {}).get("description")),
            "content": (unit.content[:300] if unit and unit.content else None),
            "metadata": (unit.meta if unit else None) or {},
            "start_time": unit.start_time if unit else None,
            "end_time": unit.end_time if unit else None,
            "thumbnail_url": storage_service.file_url(
                unit.thumbnail_path if unit and unit.thumbnail_path
                else asset.thumbnail_path),
            "preview_url": storage_service.file_url(asset.preview_path),
            "tags": [t["name"] for t in tags],
        }
        results.append(item)
    return results


async def search(db: AsyncSession, knowledge_base_id: int,
                 query: Optional[str] = None,
                 query_image_data: Optional[bytes] = None,
                 query_image_ext: str = "jpg",
                 asset_types: Optional[List[str]] = None,
                 top_k: int = 10,
                 min_score: float = 0.0) -> Dict[str, Any]:
    """统一检索入口。

    - 仅 query: 文本检索
    - 仅 query_image_data: 以图搜图
    - 两者都有: 图文融合检索
    """
    if not query and not query_image_data:
        return {"error": "必须提供文本查询或查询图片"}

    embedding_adapter = get_embedding_adapter()

    # 1. 生成查询向量
    if query and query_image_data:
        # 查询图片落临时文件（DashScope 本地文件上传）
        import tempfile, os
        tmp = tempfile.NamedTemporaryFile(suffix=f".{query_image_ext}", delete=False)
        try:
            tmp.write(query_image_data)
            tmp.close()
            query_embedding = await embedding_adapter.embed_text_image(query, tmp.name)
        finally:
            os.unlink(tmp.name)
        query_type = "text+image"
    elif query_image_data:
        import tempfile, os
        tmp = tempfile.NamedTemporaryFile(suffix=f".{query_image_ext}", delete=False)
        try:
            tmp.write(query_image_data)
            tmp.close()
            query_embedding = await embedding_adapter.embed_image(tmp.name)
        finally:
            os.unlink(tmp.name)
        query_type = "image"
    else:
        query_embedding = await embedding_adapter.embed_text(query)
        query_type = "text"

    # 2. 向量检索
    hits = await index_repo.vector_search(
        db, knowledge_base_id=knowledge_base_id, query_embedding=query_embedding,
        asset_types=asset_types, top_k=top_k * 2,  # 取2倍用于同素材去重后仍有足量
        min_score=min_score)

    # 3. 组装结果
    results = await _assemble_results(db, hits, top_k)
    return {
        "query": query,
        "query_type": query_type,
        "total": len(results),
        "results": results,
    }


async def search_by_asset(db: AsyncSession, asset_id: int,
                          top_k: int = 10) -> Dict[str, Any]:
    """以图搜图（基于已有素材）。"""
    hits = await index_repo.similar_assets_by_asset(db, asset_id, top_k=top_k)
    results = await _assemble_results(db, hits, top_k)
    return {"query_type": "asset", "total": len(results), "results": results}
