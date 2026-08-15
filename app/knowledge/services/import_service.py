"""
Knowledge import service: import uploaded files (Excel/CSV) into a knowledge base.

Pipeline:
    1. Parse spreadsheet bytes into sheet/row records (excel_loader)
    2. Turn each data row into one retrieval chunk ("列名: 值" format)
    3. Generate embeddings via Model Center (batched)
    4. Upsert Document + Chunks in PostgreSQL (content_hash dedup)

Re-importing the same file updates the existing document instead of duplicating.
"""

import logging
from typing import Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class KnowledgeImportService:
    """Imports spreadsheet files into the RAG knowledge pipeline."""

    async def import_spreadsheet(
        self,
        knowledge_base_id: int,
        filename: str,
        content: bytes,
        saved_path: Optional[str] = None,
    ) -> Dict:
        """Import an Excel/CSV file into a knowledge base.

        Args:
            knowledge_base_id: Target knowledge base.
            filename: Original filename (used as document title & dedup key).
            content: Raw file bytes.
            saved_path: Local path where the original file was archived (optional).

        Returns:
            Stats dict: document_id, sheets, rows, chunks, skipped.
        """
        from pathlib import Path

        from app.database.session import async_session_factory
        from app.models.knowledge import KnowledgeBase, Document, Chunk
        from app.knowledge.loaders.excel_loader import parse_spreadsheet, row_to_chunk_text
        from sqlalchemy import select, func, delete

        parsed = parse_spreadsheet(filename, content)
        title = Path(filename).stem or filename
        source_path = f"excel://{filename}"

        # Build row-level chunks: one data row == one retrieval unit
        chunks_data: List[Dict] = []
        for sheet in parsed["sheets"]:
            for row_idx, row in enumerate(sheet["rows"], start=2):  # +1 header, 1-indexed
                text = row_to_chunk_text(sheet["headers"], row, sheet["name"])
                if len(text.strip()) < 4:
                    continue
                # Oversized rows are split with overlap to respect chunk_size
                segments = self._split_long_text(text)
                for seg_idx, seg in enumerate(segments):
                    chunks_data.append({
                        "content": seg,
                        "section": sheet["name"],
                        "chunk_index": len(chunks_data),
                        "token_count": max(1, len(seg) // 3),
                        "metadata": {
                            "title": title,
                            "section": sheet["name"],
                            "source_path": filename,
                            "row_number": row_idx,
                            "segment": seg_idx,
                            "imported": True,
                        },
                    })

        if not chunks_data:
            raise ValueError("文件解析成功但没有生成任何有效内容块，请检查表格内容")

        # Generate embeddings before opening the DB session (fail fast, no partial writes)
        chunk_texts = [c["content"] for c in chunks_data]
        embeddings = await self._generate_embeddings(chunk_texts)

        stats = {
            "knowledge_base_id": knowledge_base_id,
            "filename": filename,
            "sheets": [s["name"] for s in parsed["sheets"]],
            "rows": parsed["total_rows"],
            "chunks": len(chunks_data),
            "skipped": False,
        }

        async with async_session_factory() as session:
            kb = await session.get(KnowledgeBase, knowledge_base_id)
            if not kb:
                raise ValueError(f"Knowledge base {knowledge_base_id} not found")

            result = await session.execute(
                select(Document).where(
                    Document.knowledge_base_id == knowledge_base_id,
                    Document.source_path == source_path,
                )
            )
            existing_doc = result.scalars().first()

            # Skip unchanged file (same content hash)
            if existing_doc and existing_doc.content_hash == parsed["content_hash"]:
                stats.update({"skipped": True, "document_id": existing_doc.id})
                logger.info(f"Excel import skipped (unchanged): {filename}")
                return stats

            meta = {
                "imported": True,
                "sheets": [s["name"] for s in parsed["sheets"]],
                "row_count": parsed["total_rows"],
                "headers": {s["name"]: s["headers"] for s in parsed["sheets"]},
            }
            if saved_path:
                meta["saved_path"] = saved_path

            if existing_doc:
                existing_doc.title = title
                existing_doc.content_hash = parsed["content_hash"]
                existing_doc.meta = meta
                existing_doc.status = "ready"
                existing_doc.chunk_count = len(chunks_data)
                await session.execute(delete(Chunk).where(Chunk.document_id == existing_doc.id))
                doc_id = existing_doc.id
                stats["action"] = "updated"
            else:
                new_doc = Document(
                    knowledge_base_id=knowledge_base_id,
                    title=title,
                    source_path=source_path,
                    source_type="excel",
                    content_hash=parsed["content_hash"],
                    meta=meta,
                    status="ready",
                    chunk_count=len(chunks_data),
                )
                session.add(new_doc)
                await session.flush()
                doc_id = new_doc.id
                stats["action"] = "created"

            for chunk_data, embedding in zip(chunks_data, embeddings):
                session.add(Chunk(
                    document_id=doc_id,
                    chunk_index=chunk_data["chunk_index"],
                    content=chunk_data["content"],
                    section=chunk_data["section"],
                    token_count=chunk_data["token_count"],
                    meta=chunk_data["metadata"],
                    embedding=embedding,
                ))

            # Recompute KB counters from DB (keeps counts correct alongside Obsidian sync)
            doc_count = await session.execute(
                select(func.count(Document.id)).where(
                    Document.knowledge_base_id == knowledge_base_id,
                    Document.status == "ready",
                )
            )
            chunk_count = await session.execute(
                select(func.count(Chunk.id)).join(
                    Document, Chunk.document_id == Document.id
                ).where(Document.knowledge_base_id == knowledge_base_id)
            )
            kb.document_count = doc_count.scalar() or 0
            kb.chunk_count = chunk_count.scalar() or 0

            await session.commit()
            stats["document_id"] = doc_id
            logger.info(
                f"Excel imported: {filename} -> KB {kb.name} "
                f"(rows={stats['rows']} chunks={stats['chunks']})"
            )
            return stats

    @staticmethod
    def _split_long_text(text: str) -> List[str]:
        """Split an oversized row text into chunk_size segments with overlap."""
        size = settings.chunk_size or 500
        overlap = settings.chunk_overlap or 50
        if len(text) <= size:
            return [text]
        segments = []
        start = 0
        while start < len(text):
            segments.append(text[start:start + size])
            start += size - overlap
        return segments

    @staticmethod
    async def _generate_embeddings(texts: List[str]) -> List[List[float]]:
        """Generate embeddings in batches of 20 via Model Center."""
        from app.models_center.service import ModelService
        model_service = ModelService()

        batch_size = 20
        all_embeddings: List = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            try:
                embeddings = await model_service.embed(batch)
                all_embeddings.extend(embeddings)
            except Exception as e:
                logger.error(f"Embedding batch {i // batch_size} failed: {e}")
                all_embeddings.extend([None] * len(batch))
        return all_embeddings
