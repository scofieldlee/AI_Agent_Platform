"""
Markdown chunk splitter: splits documents into semantically meaningful chunks.

Strategy (per requirement docs):
1. Split by Markdown headers (## sections)
2. If a section is too long, recursively split by paragraphs
3. Add overlap between chunks for context continuity
4. Preserve section metadata (title, heading path)

Chunk size guidelines:
- Chinese: 300-800 characters
- English: 500-1000 tokens
"""

import re
import logging
from typing import List, Dict, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class MarkdownSplitter:
    """Splits Markdown documents into chunks for RAG indexing."""

    def __init__(
        self,
        chunk_size: int = None,
        chunk_overlap: int = None,
    ):
        self.chunk_size = chunk_size or settings.chunk_size
        self.chunk_overlap = chunk_overlap or settings.chunk_overlap

    def split(self, content: str, metadata: Dict = None) -> List[Dict]:
        """Split Markdown content into chunks.

        Args:
            content: Markdown text (without frontmatter).
            metadata: Document metadata (title, product_name, etc.).

        Returns:
            List of chunk dicts:
            [{content, section, chunk_index, metadata, token_count}]
        """
        if metadata is None:
            metadata = {}

        # Step 1: Split by headers
        sections = self._split_by_headers(content)

        # Step 2: Split long sections into smaller chunks
        chunks = []
        chunk_index = 0

        for section in sections:
            section_title = section["title"]
            section_content = section["content"]

            if len(section_content) <= self.chunk_size:
                # Section is small enough, keep as one chunk
                if section_content.strip():
                    chunks.append(self._make_chunk(
                        content=section_content,
                        section=section_title,
                        chunk_index=chunk_index,
                        metadata=metadata,
                    ))
                    chunk_index += 1
            else:
                # Split long section recursively
                sub_chunks = self._split_recursive(
                    section_content,
                    section_title,
                    chunk_index,
                    metadata,
                )
                chunks.extend(sub_chunks)
                chunk_index += len(sub_chunks)

        logger.info(f"Split document into {len(chunks)} chunks")
        return chunks

    def _split_by_headers(self, content: str) -> List[Dict]:
        """Split content by Markdown headers (#, ##, ###)."""
        sections = []
        current_title = "General"
        current_content = []

        for line in content.split("\n"):
            # Match headers: # Title, ## Title, ### Title
            header_match = re.match(r"^(#{1,3})\s+(.+)$", line)
            if header_match:
                # Save previous section
                if current_content:
                    sections.append({
                        "title": current_title,
                        "content": "\n".join(current_content).strip(),
                    })

                current_title = header_match.group(2).strip()
                current_content = []
            else:
                current_content.append(line)

        # Save last section
        if current_content:
            sections.append({
                "title": current_title,
                "content": "\n".join(current_content).strip(),
            })

        # Filter empty sections
        sections = [s for s in sections if s["content"]]

        return sections

    def _split_recursive(
        self,
        content: str,
        section: str,
        start_index: int,
        metadata: Dict,
    ) -> List[Dict]:
        """Recursively split long content by paragraphs."""
        chunks = []
        chunk_index = start_index

        # Split by double newline (paragraphs)
        paragraphs = content.split("\n\n")

        current_chunk = ""
        for para in paragraphs:
            if len(current_chunk) + len(para) <= self.chunk_size:
                current_chunk += para + "\n\n"
            else:
                # Save current chunk
                if current_chunk.strip():
                    chunks.append(self._make_chunk(
                        content=current_chunk.strip(),
                        section=section,
                        chunk_index=chunk_index,
                        metadata=metadata,
                    ))
                    chunk_index += 1

                # Start new chunk with overlap
                if self.chunk_overlap > 0:
                    overlap_text = current_chunk[-self.chunk_overlap:] if current_chunk else ""
                    current_chunk = overlap_text + para + "\n\n"
                else:
                    current_chunk = para + "\n\n"

        # Save remaining content
        if current_chunk.strip():
            chunks.append(self._make_chunk(
                content=current_chunk.strip(),
                section=section,
                chunk_index=chunk_index,
                metadata=metadata,
            ))
            chunk_index += 1

        return chunks

    def _make_chunk(
        self,
        content: str,
        section: str,
        chunk_index: int,
        metadata: Dict,
    ) -> Dict:
        """Create a chunk dict with metadata."""
        # Estimate token count (rough: 1 token ≈ 2 Chinese chars or 4 English chars)
        token_count = len(content) // 3

        # Merge document metadata with chunk-specific info
        chunk_metadata = {
            **metadata,
            "section": section,
            "chunk_index": chunk_index,
        }

        return {
            "content": content,
            "section": section,
            "chunk_index": chunk_index,
            "metadata": chunk_metadata,
            "token_count": token_count,
        }
