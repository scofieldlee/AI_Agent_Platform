"""
Knowledge base schemas.
"""

from typing import List, Optional
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


class ChunkResponse(BaseModel):
    """A chunk within a document (embedding vector omitted to keep payload light)."""
    id: int
    chunk_index: int
    content: str
    section: Optional[str] = None
    token_count: Optional[int] = None
    meta: dict = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class DocumentDetailResponse(BaseModel):
    """Document detail including its chunks."""
    id: int
    title: str
    source_path: Optional[str] = None
    source_type: str
    status: str
    chunk_count: int
    meta: dict = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    chunks: List[ChunkResponse] = Field(default_factory=list)


class DocumentUpdate(BaseModel):
    """Editable fields of a document."""
    title: Optional[str] = None
    meta: Optional[dict] = None


class ChunkUpdate(BaseModel):
    """Editable fields of a chunk."""
    content: Optional[str] = None
    section: Optional[str] = None


class DocumentContentUpdate(BaseModel):
    """Update the full markdown content of a document.

    The document will be re-chunked and re-embedded automatically.
    """
    content: str = Field(..., min_length=1, description="完整 Markdown 正文（不含 frontmatter）")
    title: Optional[str] = Field(None, description="可选：同时更新文档标题")
    meta: Optional[dict] = Field(None, description="可选：同时更新 frontmatter 元数据")


class ExcelImportResponse(BaseModel):
    """Result of importing an Excel/CSV file into a knowledge base."""
    status: str = "completed"
    knowledge_base_id: int
    document_id: int
    filename: str
    action: str = "created"  # created / updated / skipped
    sheets: list = Field(default_factory=list)
    rows: int = 0
    chunks: int = 0
