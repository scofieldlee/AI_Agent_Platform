"""
Knowledge sync service: orchestrates the full RAG indexing pipeline.

Flow: Obsidian Vault -> Loader -> Splitter -> Embedding -> PostgreSQL + pgvector.

Usage:
    service = KnowledgeSyncService()
    await service.sync_knowledge_base(kb_id=1)
"""

import logging
from typing import Optional, List, Dict
from datetime import datetime

from app.core.config import settings

logger = logging.getLogger(__name__)

# Candidate subdirectories per KB type — first existing one wins.
# Supports both the original Obsidian vault layout and simple English layouts
# (e.g. <source_path>/product, <source_path>/QA). Falls back to scanning the
# whole source path when none of the candidates exist.
_SCAN_DIR_CANDIDATES = {
    "product": ("2-领域/商品知识库/商品档案", "product", "products"),
    "qa": ("2-领域/商品知识库/商品QA", "QA", "qa"),
    "parameter": ("2-领域/商品知识库/商品参数", "parameter", "parameters"),
}


def _resolve_scan_subdir(vault_path, kb_type: str) -> Optional[str]:
    """Return the subdirectory to scan for this KB type, or None for root."""
    from pathlib import Path

    root = Path(vault_path)
    for candidate in _SCAN_DIR_CANDIDATES.get(kb_type, ()):
        if (root / candidate).is_dir():
            return candidate
    return None


class KnowledgeSyncService:
    """Syncs knowledge from source (Obsidian) to vector database.

    Pipeline:
    1. Load Markdown files from Obsidian vault
    2. Parse frontmatter and extract metadata
    3. Split into chunks (Markdown Header Splitter + Recursive)
    4. Generate embeddings for each chunk
    5. Store in PostgreSQL (documents + chunks) with pgvector embeddings
    """

    async def sync_knowledge_base(
        self,
        knowledge_base_id: int,
        force: bool = False,
    ) -> Dict:
        """Sync a knowledge base from its source.

        Args:
            knowledge_base_id: Knowledge base ID to sync.
            force: If True, re-index all documents even if unchanged.

        Returns:
            Dict with sync statistics.
        """
        from app.database.session import async_session_factory
        from app.models.knowledge import KnowledgeBase, Document, Chunk
        from sqlalchemy import select

        stats = {
            "documents_scanned": 0,
            "documents_created": 0,
            "documents_updated": 0,
            "documents_unchanged": 0,
            "chunks_created": 0,
            "errors": [],
        }

        async with async_session_factory() as session:
            # Get knowledge base
            kb = await session.get(KnowledgeBase, knowledge_base_id)
            if not kb:
                raise ValueError(f"Knowledge base {knowledge_base_id} not found")

            if not kb.source_path:
                raise ValueError(f"Knowledge base {kb.name} has no source path")

            logger.info(f"Syncing knowledge base: {kb.name} from {kb.source_path}")

            # Step 1: Load documents from source
            from app.knowledge.loaders.obsidian_loader import ObsidianLoader
            loader = ObsidianLoader(kb.source_path)

            # Determine subdirectory based on KB type (flexible layout)
            subdir = _resolve_scan_subdir(loader.vault_path, kb.kb_type)
            documents = loader.scan(subdir=subdir)
            if subdir:
                logger.info(f"KB type '{kb.kb_type}' resolves to subdirectory: {subdir}")
            else:
                logger.info(f"KB type '{kb.kb_type}' scans the whole source path")

            stats["documents_scanned"] = len(documents)
            logger.info(f"Loaded {len(documents)} documents from source")

            # Step 2: Process each document
            for doc_data in documents:
                try:
                    # Check if document already exists
                    result = await session.execute(
                        select(Document).where(
                            Document.knowledge_base_id == knowledge_base_id,
                            Document.source_path == doc_data["path"],
                        )
                    )
                    existing_doc = result.scalars().first()

                    # Check if content has changed
                    if existing_doc and not force:
                        if existing_doc.content_hash == doc_data["content_hash"]:
                            stats["documents_unchanged"] += 1
                            continue

                    # Step 3: Split into chunks
                    from app.knowledge.splitters.markdown_splitter import MarkdownSplitter
                    splitter = MarkdownSplitter()
                    chunks_data = splitter.split(
                        content=doc_data["content"],
                        metadata={
                            **doc_data["metadata"],
                            "title": doc_data["title"],
                            "source_path": doc_data["relative_path"],
                        },
                    )

                    # Step 4: Generate embeddings for all chunks
                    chunk_texts = [c["content"] for c in chunks_data]
                    embeddings = await self._generate_embeddings(chunk_texts)

                    # Step 5: Store document and chunks
                    if existing_doc:
                        # Update existing document
                        existing_doc.title = doc_data["title"]
                        existing_doc.content_hash = doc_data["content_hash"]
                        existing_doc.meta = doc_data["metadata"]
                        existing_doc.status = "ready"
                        existing_doc.chunk_count = len(chunks_data)

                        # Delete old chunks
                        chunk_result = await session.execute(
                            select(Chunk).where(Chunk.document_id == existing_doc.id)
                        )
                        old_chunks = chunk_result.scalars().all()
                        for old_chunk in old_chunks:
                            await session.delete(old_chunk)

                        doc_id = existing_doc.id
                        stats["documents_updated"] += 1
                    else:
                        # Create new document
                        new_doc = Document(
                            knowledge_base_id=knowledge_base_id,
                            title=doc_data["title"],
                            source_path=doc_data["path"],
                            source_type="markdown",
                            content_hash=doc_data["content_hash"],
                            meta=doc_data["metadata"],
                            status="ready",
                            chunk_count=len(chunks_data),
                        )
                        session.add(new_doc)
                        await session.flush()
                        doc_id = new_doc.id
                        stats["documents_created"] += 1

                    # Create chunks with embeddings
                    for i, (chunk_data, embedding) in enumerate(zip(chunks_data, embeddings)):
                        chunk = Chunk(
                            document_id=doc_id,
                            chunk_index=chunk_data["chunk_index"],
                            content=chunk_data["content"],
                            section=chunk_data["section"],
                            token_count=chunk_data["token_count"],
                            meta=chunk_data["metadata"],
                            embedding=embedding,
                        )
                        session.add(chunk)
                        stats["chunks_created"] += 1

                    # Commit after each document
                    await session.commit()
                    logger.info(f"Indexed: {doc_data['title']} ({len(chunks_data)} chunks)")

                except Exception as e:
                    logger.error(f"Failed to index {doc_data.get('path', 'unknown')}: {e}", exc_info=True)
                    stats["errors"].append({
                        "document": doc_data.get("path", "unknown"),
                        "error": str(e),
                    })
                    await session.rollback()

            # Update knowledge base stats
            kb.document_count = stats["documents_created"] + stats["documents_updated"] + stats["documents_unchanged"]
            kb.chunk_count = stats["chunks_created"]
            await session.commit()

        logger.info(
            f"Sync complete | scanned={stats['documents_scanned']} "
            f"created={stats['documents_created']} updated={stats['documents_updated']} "
            f"unchanged={stats['documents_unchanged']} chunks={stats['chunks_created']} "
            f"errors={len(stats['errors'])}"
        )

        return stats

    async def _generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts.

        Uses Model Center to call the configured embedding model.
        Handles batching for large lists.
        """
        if not texts:
            return []

        from app.models_center.service import ModelService
        model_service = ModelService()

        # Process in batches of 20 (API limit safety)
        batch_size = 20
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            try:
                embeddings = await model_service.embed(batch)
                all_embeddings.extend(embeddings)
            except Exception as e:
                logger.error(f"Embedding batch {i//batch_size} failed: {e}")
                # Fill with None for failed batch
                all_embeddings.extend([None] * len(batch))

        return all_embeddings
