"""
Tool schemas.
"""

from typing import Optional, Dict, Any
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

    model_config = {"from_attributes": True}
