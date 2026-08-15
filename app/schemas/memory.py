"""
Memory schemas.
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel


class MemoryCreate(BaseModel):
    """Create a new memory."""
    content: str
    memory_type: str = "fact"
    importance: float = 0.5
    user_id: Optional[int] = None
    agent_id: Optional[int] = None


class MemoryUpdate(BaseModel):
    """Update an existing memory."""
    importance: Optional[float] = None
    status: Optional[str] = None


class MemoryResponse(BaseModel):
    """Memory item for API responses."""
    id: int
    user_id: Optional[int] = None
    agent_id: Optional[int] = None
    memory_type: str
    content: str
    importance: float
    status: str
    access_count: int
    last_accessed_at: Optional[str] = None
    meta: Optional[dict] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class MemoryListResponse(BaseModel):
    """Paginated memory list."""
    items: List[MemoryResponse]
    total: int
    page: int
    size: int
