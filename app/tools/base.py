"""
Base classes for the Tool system.

BaseTool: abstract tool that every concrete tool implements.
ToolResult: standardized execution result.

Design principles (from project spec):
- Every tool MUST have input_schema (JSON Schema) for parameter validation.
- Every tool MUST have a description (used by LLM for tool selection).
- Tools do NOT directly access DB or third-party APIs; they go through
  Service + Tool encapsulation.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Standardized result from tool execution."""

    success: bool
    data: Any = None
    error: Optional[str] = None
    duration_ms: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


class BaseTool(ABC):
    """Abstract base class for all tools.

    Subclasses must implement:
    - name: unique tool identifier (snake_case)
    - description: human-readable description (used by LLM for tool selection)
    - input_schema: JSON Schema for input parameters
    - execute(): async method that performs the tool's action

    Usage:
        class MyTool(BaseTool):
            name = "my_tool"
            description = "Does something useful"
            input_schema = {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"}
                },
                "required": ["query"],
            }

            async def execute(self, **kwargs) -> ToolResult:
                ...
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool identifier (snake_case)."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description. Used by LLM for tool selection."""

    @property
    @abstractmethod
    def input_schema(self) -> Dict[str, Any]:
        """JSON Schema for input parameters."""

    @property
    def tool_type(self) -> str:
        """Tool type: internal, business, api, database, mcp."""
        return "internal"

    @property
    def output_schema(self) -> Optional[Dict[str, Any]]:
        """Optional JSON Schema for output."""
        return None

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with validated parameters.

        Returns ToolResult with data or error.
        """

    def to_dict(self) -> Dict[str, Any]:
        """Serialize tool metadata for API responses."""
        return {
            "name": self.name,
            "description": self.description,
            "tool_type": self.tool_type,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
        }
