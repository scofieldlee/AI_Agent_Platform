"""
Tool schemas.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel


class ToolResponse(BaseModel):
    """Tool metadata for API responses."""
    name: str
    description: str
    tool_type: str
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None


class ToolExecuteRequest(BaseModel):
    """Execute a tool."""
    parameters: Dict[str, Any]


class ToolExecuteResponse(BaseModel):
    """Tool execution result."""
    tool: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    duration_ms: Optional[int] = None


class ToolExecutionLogResponse(BaseModel):
    """Tool execution log entry."""
    id: int
    tool_id: int
    agent_id: Optional[int] = None
    conversation_id: Optional[int] = None
    input_data: Optional[Dict] = None
    output_data: Optional[Dict] = None
    status: str
    error: Optional[str] = None
    duration_ms: Optional[int] = None
    trace_id: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ToolStatsResponse(BaseModel):
    """Tool with 24h execution statistics."""
    name: str
    description: str
    tool_type: str
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    total_24h: int = 0
    success_24h: int = 0
    error_24h: int = 0
    success_rate_24h: Optional[float] = None
    avg_duration_24h: Optional[float] = None
    last_executed_24h: Optional[str] = None
    total_all: int = 0
    success_all: int = 0
    requires_approval: bool = False


class ToolDetailResponse(ToolStatsResponse):
    """Tool detail for the management modal (stats + recent logs)."""
    recent_logs: List[ToolExecutionLogResponse] = []
