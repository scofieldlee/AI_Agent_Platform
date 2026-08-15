"""
Knowledge base schemas.
"""

from typing import Optional
from pydantic import BaseModel, Field


class KnowledgeBaseCreate(BaseModel):
    """Create a new knowledge base."""
    name: str
    code: str
    description: Optional[str] = None
    kb_type: str = "product"
    source_type: str = "obsidian"
    source_path: Optional[str] = None
    config: dict = Field(default_factory=dict)


class KnowledgeBaseResponse(BaseModel):
    """Knowledge base list item."""
    id: int
    name: str
    code: str
    description: Optional[str] = None
    kb_type: str
    source_type: str
    source_path: Optional[str] = None
    document_count: int
    chunk_count: int
    is_active: bool

    model_config = {"from_attributes": True}


class DocumentResponse(BaseModel):
    """Document in a knowledge base."""
    id: int
    title: str
    source_path: Optional[str] = None
    status: str
    chunk_count: int
    meta: dict

    model_config = {"from_attributes": True}
