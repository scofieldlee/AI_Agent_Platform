"""
Vector retriever: RAG knowledge retrieval.

Flow: Query -> Embedding -> Vector Search (pgvector) -> Rerank -> Context.

MVP: Uses pgvector for similarity search.
Future: Add BM25 for hybrid search + reranker model.
"""

import logging
from typing import Dict, Any, List

from app.core.config import settings

logger = logging.getLogger(__name__)


async def retrieve_knowledge(
    query: str,
    top_k: int = None,
    knowledge_base_id: int = None,
) -> Dict[str, Any]:
    """Retrieve relevant knowledge for a user query.

    Args:
        query: User's question.
        top_k: Number of chunks to retrieve.
        knowledge_base_id: Filter by knowledge base (optional).

    Returns:
        Dict with:
        - context: Assembled context string for LLM
        - sources: List of source chunks [{title, section, content, score}]
    """
    if top_k is None:
        top_k = settings.rerank_top_k

    logger.info(f"Retrieving knowledge | query={query[:50]}... top_k={top_k}")

    try:
        # 1. Embed the query
        from app.models_center.service import ModelService
        model_service = ModelService()
        query_embedding = await model_service.embed([query])
        query_vector = query_embedding[0]

        # 2. Vector search in pgvector
        from app.database.session import async_session_factory
        from sqlalchemy import select, text
        from app.models.knowledge import Chunk

        async with async_session_factory() as session:
            # Cosine similarity search
            # Use CAST() instead of :: to avoid SQLAlchemy parameter parsing conflict
            sql = text("""
                SELECT id, content, section, metadata as meta,
                       1 - (embedding <=> CAST(:query_vector AS vector)) as score
                FROM chunks
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> CAST(:query_vector AS vector)
                LIMIT :top_k
            """)

            results = await session.execute(
                sql,
                {"query_vector": str(query_vector), "top_k": settings.vector_search_top_k}
            )
            rows = results.fetchall()

        # 3. Assemble context
        sources = []
        context_parts = []

        for row in rows[:top_k]:
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
        }

    except Exception as e:
        logger.error(f"Knowledge retrieval failed: {e}", exc_info=True)
        return {
            "context": "",
            "sources": [],
            "avg_score": 0.0,
        }
