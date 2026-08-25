"""向量索引 Repository (mm_index_records + pgvector).

所有向量查询使用原生 SQL（CAST() 避免 SQLAlchemy 参数解析冲突，
与 app/knowledge/retrievers/vector_retriever.py 同模式）。
"""

import json
import logging
from typing import Optional, List

from sqlalchemy import text, delete as sa_delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.multimodal.models import IndexRecord
from app.multimodal.constants import EmbeddingType

logger = logging.getLogger(__name__)


async def create_index_record(db: AsyncSession, knowledge_base_id: int, asset_id: int,
                              knowledge_unit_id: Optional[int], embedding: List[float],
                              embedding_type: str, model_name: str,
                              metadata: Optional[dict] = None) -> IndexRecord:
    """写入向量索引记录。"""
    record = IndexRecord(
        knowledge_base_id=knowledge_base_id,
        asset_id=asset_id,
        knowledge_unit_id=knowledge_unit_id,
        embedding_type=embedding_type,
        model_name=model_name,
        embedding=embedding,
        meta=metadata or {})
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return record


async def delete_index_by_asset(db: AsyncSession, asset_id: int) -> int:
    """删除素材全部索引（重新索引前调用）。"""
    result = await db.execute(sa_delete(IndexRecord).where(
        IndexRecord.asset_id == asset_id))
    await db.flush()
    return result.rowcount or 0


async def delete_index_by_kb(db: AsyncSession, kb_id: int) -> int:
    result = await db.execute(sa_delete(IndexRecord).where(
        IndexRecord.knowledge_base_id == kb_id))
    await db.flush()
    return result.rowcount or 0


async def count_index_by_asset(db: AsyncSession, asset_id: int) -> int:
    return (await db.execute(
        select(func.count(IndexRecord.id)).where(IndexRecord.asset_id == asset_id)
    )).scalar() or 0


async def vector_search(db: AsyncSession, knowledge_base_id: int,
                        query_embedding: List[float],
                        asset_types: Optional[List[str]] = None,
                        top_k: int = 10,
                        min_score: float = 0.0) -> List[dict]:
    """余弦相似度向量检索，返回:
    [{record_id, asset_id, unit_id, embedding_type, score, metadata}]

    过滤条件：
    - 素材已就绪(ready)且未删除
    - asset_types 传入时按素材类型过滤（通过 JOIN mm_assets + JSONB metadata）
    """
    # 构造 SQL：JSONB metadata 中存 file_type，避免 JOIN 复杂化；
    # 但类型过滤最可靠的方式是 JOIN mm_assets
    sql = text("""
        SELECT r.id, r.asset_id, r.knowledge_unit_id, r.embedding_type,
               r.metadata AS meta,
               1 - (r.embedding <=> CAST(:query_vector AS vector)) AS score
        FROM mm_index_records r
        JOIN mm_assets a ON a.id = r.asset_id
        WHERE r.knowledge_base_id = :kb_id
          AND a.deleted_at IS NULL
          AND a.status = 'ready'
          AND (:asset_types IS NULL OR a.file_type = ANY(:asset_types))
        ORDER BY r.embedding <=> CAST(:query_vector AS vector)
        LIMIT :top_k
    """)

    types = asset_types if asset_types else None
    result = await db.execute(sql, {
        "query_vector": str(query_embedding),
        "kb_id": knowledge_base_id,
        "asset_types": types,
        "top_k": top_k,
    })
    rows = result.fetchall()

    items = []
    for row in rows:
        score = float(row.score) if row.score is not None else 0.0
        if score < min_score:
            continue
        meta = row.meta if isinstance(row.meta, dict) else {}
        items.append({
            "record_id": row.id,
            "asset_id": row.asset_id,
            "unit_id": row.knowledge_unit_id,
            "embedding_type": row.embedding_type,
            "score": round(score, 4),
            "metadata": meta,
        })
    return items


async def similar_assets_by_asset(db: AsyncSession, asset_id: int,
                                  top_k: int = 10) -> List[dict]:
    """以指定素材的向量为查询，找相似素材（以图搜图内部实现）。"""
    # 取该素材第一条索引向量作为查询
    sql = text("""
        SELECT r.id, r.asset_id, r.knowledge_unit_id,
               1 - (q.embedding <=> r.embedding) AS score
        FROM mm_index_records q
        JOIN mm_index_records r
          ON r.knowledge_base_id = q.knowledge_base_id
         AND r.id != q.id
        JOIN mm_assets a ON a.id = r.asset_id
        WHERE q.asset_id = :asset_id
          AND a.deleted_at IS NULL AND a.status = 'ready'
        ORDER BY q.embedding <=> r.embedding
        LIMIT :top_k
    """)
    result = await db.execute(sql, {"asset_id": asset_id, "top_k": top_k})
    return [{"record_id": r.id, "asset_id": r.asset_id, "unit_id": r.knowledge_unit_id,
             "score": round(float(r.score), 4)}
            for r in result.fetchall()]
