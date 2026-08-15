"""
ToolRegistry: tool registration and discovery.

Singleton that holds all registered tools.
Agents use the registry to discover and call tools.

Usage:
    registry = ToolRegistry()
    registry.register(MyTool())
    tool = registry.get("my_tool")
    tools = registry.list_tools()
"""

import logging
from typing import Dict, List, Optional

from app.tools.base import BaseTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry for all available tools.

    Singleton pattern ensures one global registry.
    """

    _instance: Optional["ToolRegistry"] = None

    def __new__(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools: Dict[str, BaseTool] = {}
            cls._instance._initialized = False
        return cls._instance

    def register(self, tool: BaseTool) -> None:
        """Register a tool.

        Args:
            tool: BaseTool instance to register.
        """
        if tool.name in self._tools:
            logger.warning(f"Tool '{tool.name}' already registered, overwriting.")
        self._tools[tool.name] = tool
        logger.info(f"Tool registered: {tool.name} ({tool.tool_type})")

    def get(self, tool_name: str) -> Optional[BaseTool]:
        """Get a tool by name."""
        return self._tools.get(tool_name)

    def list_tools(self) -> List[BaseTool]:
        """List all registered tools."""
        return list(self._tools.values())

    def list_metadata(self) -> List[Dict]:
        """List all tools as metadata dicts (for API responses)."""
        return [t.to_dict() for t in self._tools.values()]

    def has(self, tool_name: str) -> bool:
        """Check if a tool is registered."""
        return tool_name in self._tools

    def count(self) -> int:
        """Number of registered tools."""
        return len(self._tools)

    def clear(self) -> None:
        """Clear all registered tools (mainly for testing)."""
        self._tools.clear()


def get_registry() -> ToolRegistry:
    """Get the global ToolRegistry instance."""
    return ToolRegistry()
