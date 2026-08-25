"""Multimodal repositories — data access layer (module-level async functions, flush 不 commit)."""

from app.multimodal.repositories import (
    knowledge_base_repo, asset_repo, knowledge_unit_repo,
    processing_repo, index_repo,
)

__all__ = ["knowledge_base_repo", "asset_repo", "knowledge_unit_repo",
           "processing_repo", "index_repo"]
