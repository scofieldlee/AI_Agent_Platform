"""
Analytics schemas.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel


class SpanItem(BaseModel):
    """A single span within a trace."""
    id: int
    span_id: str
    node_name: str
    node_type: str
    status: str
    duration_ms: Optional[int] = None
    input_data: Optional[dict] = None
    output_data: Optional[dict] = None
    token_usage: Optional[dict] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TraceListItem(BaseModel):
    """Trace list item."""
    id: int
    trace_id: str
    agent_id: Optional[int] = None
    conversation_id: Optional[int] = None
    status: str
    intent: Optional[str] = None
    confidence: Optional[float] = None
    duration_ms: Optional[int] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TraceDetail(BaseModel):
    """Detailed trace with spans."""
    trace_id: str
    agent_id: Optional[int] = None
    conversation_id: Optional[int] = None
    status: str
    intent: Optional[str] = None
    confidence: Optional[float] = None
    duration_ms: Optional[int] = None
    total_tokens: Optional[int] = None
    total_cost: Optional[float] = None
    input_data: Optional[dict] = None
    output_data: Optional[dict] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    spans: List[SpanItem] = []

    model_config = {"from_attributes": True}


class StatsResponse(BaseModel):
    """Analytics statistics."""
    total_traces: int
    success_count: int
    failed_count: int
    human_transfer_count: int
    success_rate: float
    avg_duration_ms: Optional[float] = None
    avg_confidence: Optional[float] = None
    intent_distribution: dict
