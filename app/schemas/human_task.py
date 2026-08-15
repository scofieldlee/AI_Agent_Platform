"""
Human task schemas.
"""

from typing import Optional
from pydantic import BaseModel


class AssignRequest(BaseModel):
    """Assign a task to a user."""
    assigned_to: int


class ResolveRequest(BaseModel):
    """Resolve a human task."""
    resolution_note: str
    resolution_type: str = "resolved"
    assigned_to: Optional[int] = None
