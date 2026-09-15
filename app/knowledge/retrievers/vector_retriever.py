"""
Vector retriever: RAG knowledge retrieval.

Flow: Query -> [Query Translation] -> Embedding -> Vector Search (pgvector)
      -> Merge (bilingual queries, max score) -> Context.

Cross-language note: the embedding model (bge-small-zh) is Chinese-centric.
An English query barely matches Chinese content (cosine ~0.66 vs ~0.84 for
the Chinese equivalent). To handle foreign-language queries, non-Chinese
queries are translated via the chat model and BOTH queries are searched;
results are merged by chunk id keeping the max score.

MVP: Uses pgvector for similarity search.
Future: Add BM25 for hybrid search + reranker model.
"""

import asyncio
import logging
import re
from typing import Dict, Any, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _has_chinese(text: str) -> bool:
    return bool(_CJK_RE.search(text or ""))


async def _translate_to_chinese(query: str) -> Optional[str]:
    """Translate a non-Chinese query into Chinese via the chat model.

    Returns None on failure/timeout (caller degrades to original query).
    """
    try:
        from app.models_center.service import ModelService

        async def _do():
            service = ModelService()
            result = await service.chat(
                system_prompt=(
                    "你是检索查询翻译器。把用户问题准确翻译成中文，"
                    "只输出翻译结果本身，不要解释、不要加引号。"
                ),
                user_prompt=query,
                temperature=0.0,
                max_tokens=200,
            )
            return (result.get("content") or "").strip()

        translated = await asyncio.wait_for(
            _do(), timeout=settings.knowledge_translation_timeout
        )
        if translated and _has_chinese(translated):
            return translated
        return None
    except Exception as e:
        logger.warning(f"Query translation failed (degrade to original): {e}")
        return None


async def _search_chunks(
    query_vector: List[float],
    top_k: int,
    knowledge_base_id: Optional[int] = None,
) -> List[Any]:
    """Cosine similarity search in pgvector. Returns raw rows."""
    from app.database.session import async_session_factory
    from sqlalchemy import text

    kb_filter = ""
    params: Dict[str, Any] = {
        "query_vector": str(query_vector),
        "top_k": top_k,
    }
    if knowledge_base_id:
        kb_filter = "JOIN documents d ON d.id = c.document_id AND d.knowledge_base_id = :kb_id"
        params["kb_id"] = knowledge_base_id

    sql = text(f"""
        SELECT c.id, c.content, c.section, c.metadata as meta,
               1 - (c.embedding <=> CAST(:query_vector AS vector)) as score
        FROM chunks c
        {kb_filter}
        WHERE c.embedding IS NOT NULL
        ORDER BY c.embedding <=> CAST(:query_vector AS vector)
        LIMIT :top_k
    """)

    async with async_session_factory() as session:
        results = await session.execute(sql, params)
        return results.fetchall()


async def retrieve_knowledge(
    query: str,
    top_k: int = None,
    knowledge_base_id: int = None,
) -> Dict[str, Any]:
    """Retrieve relevant knowledge for a user query.

    Args:
        query: User's question (any language; non-Chinese queries are
            auto-translated and searched bilingually).
        top_k: Number of chunks to retrieve.
        knowledge_base_id: Filter by knowledge base (optional).

    Returns:
        Dict with:
        - context: Assembled context string for LLM
        - sources: List of source chunks [{title, section, content, score}]
        - translated_query: Chinese translation used (None if not applied)
    """
    if top_k is None:
        top_k = settings.rerank_top_k

    logger.info(f"Retrieving knowledge | query={query[:50]}... top_k={top_k}")

    try:
        from app.models_center.service import ModelService

        model_service = ModelService()

        # 0. Query translation for cross-language retrieval
        translated_query = None
        if settings.knowledge_query_translation and not _has_chinese(query):
            translated_query = await _translate_to_chinese(query)
            if translated_query:
                logger.info(f"Query translated: {query[:40]} -> {translated_query[:40]}")

        # 1. Embed original (+ translated) queries
        queries = [query]
        if translated_query and translated_query != query:
            queries.append(translated_query)

        embeddings = await model_service.embed(queries)

        # 2. Vector search per query, merge by chunk id keeping max score
        merged: Dict[int, Any] = {}
        for vec in embeddings:
            rows = await _search_chunks(vec, settings.vector_search_top_k, knowledge_base_id)
            for row in rows:
                if row.id not in merged or float(row.score) > float(merged[row.id].score):
                    merged[row.id] = row

        rows = sorted(merged.values(), key=lambda r: float(r.score), reverse=True)[:top_k]

        # 3. Assemble context
        sources = []
        context_parts = []

        for row in rows:
            score = float(row.score) if row.score else 0.0
            meta = row.meta if row.meta else {}
            title = meta.get("title", "Unknown") if isinstance(meta, dict) else "Unknown"
            section = row.section or "General"

            sources.append({
                "title": title,
                "section": section,
                "content": row.content[:200] + "..." if len(row.content) > 200 else row.content,
                "score": round(score, 4),
            })

            context_parts.append(f"[{title} - {section}]\n{row.content}")

        context = "\n\n---\n\n".join(context_parts) if context_parts else ""

        # 4. Check confidence
        avg_score = sum(s["score"] for s in sources) / len(sources) if sources else 0.0
        if avg_score < settings.knowledge_confidence_threshold:
            logger.warning(
                f"Low knowledge confidence: {avg_score:.3f} < {settings.knowledge_confidence_threshold}"
            )

        logger.info(f"Knowledge retrieved: {len(sources)} sources, avg_score={avg_score:.3f}")

        return {
            "context": context,
            "sources": sources,
            "avg_score": avg_score,
            "translated_query": translated_query,
        }

    except Exception as e:
        logger.error(f"Knowledge retrieval failed: {e}", exc_info=True)
        return {
            "context": "",
            "sources": [],
            "avg_score": 0.0,
            "translated_query": None,
        }
