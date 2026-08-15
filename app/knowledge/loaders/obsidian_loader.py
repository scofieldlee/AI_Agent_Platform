"""
Obsidian vault loader: scans vault directory for Markdown files.

Supports:
- Recursive directory scan
- Frontmatter metadata extraction
- Wikilink [[]] reference tracking
- Change detection via content hash
"""

import os
import hashlib
import logging
from typing import List, Dict, Optional
from datetime import date, datetime
from pathlib import Path

import frontmatter

logger = logging.getLogger(__name__)


def _sanitize_metadata(obj):
    """Recursively convert date/datetime objects to ISO strings for JSON serialization."""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _sanitize_metadata(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_metadata(v) for v in obj]
    return obj


class ObsidianLoader:
    """Loads Markdown files from an Obsidian vault."""

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path)
        if not self.vault_path.exists():
            raise FileNotFoundError(f"Obsidian vault not found: {vault_path}")

    def scan(self, subdir: Optional[str] = None) -> List[Dict]:
        """Scan vault for Markdown files.

        Args:
            subdir: Optional subdirectory to scan (e.g., "2-领域/商品知识库")

        Returns:
            List of document dicts:
            [{path, title, content, metadata, content_hash, wikilinks}]
        """
        scan_path = self.vault_path / subdir if subdir else self.vault_path
        documents = []

        logger.info(f"Scanning Obsidian vault: {scan_path}")

        for md_file in scan_path.rglob("*.md"):
            # Skip .obsidian, .workbuddy, templates directories
            if any(part.startswith(".") for part in md_file.parts):
                continue
            if "7-模板" in str(md_file):
                continue

            try:
                doc = self._parse_file(md_file)
                if doc:
                    documents.append(doc)
            except Exception as e:
                logger.warning(f"Failed to parse {md_file}: {e}")

        logger.info(f"Scanned {len(documents)} Markdown files from vault")
        return documents

    def _parse_file(self, filepath: Path) -> Optional[Dict]:
        """Parse a single Markdown file with frontmatter."""
        content = filepath.read_text(encoding="utf-8")

        # Parse frontmatter
        post = frontmatter.loads(content)
        metadata = _sanitize_metadata(dict(post.metadata))
        body = post.content

        # Extract title from frontmatter or first heading
        # str() ensures title is always a string (frontmatter values may be int)
        title = str(metadata.get("商品名称") or metadata.get("title") or filepath.stem)

        # Calculate content hash for change detection
        content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()

        # Extract wikilinks [[...]]
        wikilinks = self._extract_wikilinks(body)

        # Determine document type from frontmatter
        doc_type = metadata.get("类型", "unknown")

        # Skip non-product documents for product knowledge base
        # (can be configured)

        return {
            "path": str(filepath),
            "relative_path": str(filepath.relative_to(self.vault_path)),
            "title": title,
            "content": body,
            "raw_content": content,
            "metadata": metadata,
            "content_hash": content_hash,
            "wikilinks": wikilinks,
            "doc_type": doc_type,
        }

    def _extract_wikilinks(self, content: str) -> List[str]:
        """Extract Obsidian wikilinks [[link]] from content."""
        import re
        pattern = r"\[\[([^\]]+)\]\]"
        matches = re.findall(pattern, content)
        # Handle aliases: [[link|alias]]
        links = [m.split("|")[0].strip() for m in matches]
        return list(set(links))

    def get_product_documents(self) -> List[Dict]:
        """Get product archive documents specifically."""
        return self.scan(subdir="2-领域/商品知识库/商品档案")

    def get_qa_documents(self) -> List[Dict]:
        """Get QA documents specifically from the 商品QA subdirectory."""
        return self.scan(subdir="2-领域/商品知识库/商品QA")

    def get_parameter_documents(self) -> List[Dict]:
        """Get product parameter documents from the 商品参数 subdirectory."""
        return self.scan(subdir="2-领域/商品知识库/商品参数")
