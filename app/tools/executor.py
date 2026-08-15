"""
ToolExecutor: validates parameters and executes tools.

Flow:
  1. Look up tool by name in ToolRegistry
  2. Validate input parameters against tool's JSON Schema
  3. Execute the tool
  4. Record execution to tool_executions table (for analytics)

Design rules from project spec:
- Tools MUST have schema validation before execution.
- Tool executions are logged for debugging and analytics.
"""

import logging
import time
from typing import Dict, Any, Optional

from app.tools.base import BaseTool, ToolResult
from app.tools.registry import get_registry

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Executes tools with parameter validation and logging.

    Usage:
        executor = ToolExecutor()
        result = await executor.execute(
            tool_name="product_query",
            parameters={"query": "Q150", "max_results": 5},
            agent_id=2,
        )
    """

    def __init__(self):
        self.registry = get_registry()

    async def execute(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        agent_id: Optional[int] = None,
        conversation_id: Optional[int] = None,
        trace_id: Optional[str] = None,
    ) -> ToolResult:
        """Execute a tool by name with validated parameters.

        Args:
            tool_name: Name of the registered tool.
            parameters: Input parameters for the tool.
            agent_id: Agent requesting execution (for logging).
            conversation_id: Conversation context (for logging).
            trace_id: Trace ID for analytics correlation.

        Returns:
            ToolResult with success/data/error.
        """
        # 1. Look up tool
        tool = self.registry.get(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                error=f"Tool '{tool_name}' not found in registry.",
            )

        # 2. Validate parameters (basic JSON Schema check)
        validation_error = self._validate_parameters(tool, parameters)
        if validation_error:
            return ToolResult(
                success=False,
                error=f"Parameter validation failed: {validation_error}",
            )

        # 3. Execute
        start_time = time.time()
        status = "success"
        error_msg = None
        result_data = None

        try:
            result = await tool.execute(**parameters)
            result_data = result.data
            if not result.success:
                status = "error"
                error_msg = result.error
            logger.info(
                f"Tool executed: {tool_name} | status={status} "
                f"duration={result.duration_ms or 'N/A'}ms"
            )
        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name} error={e}", exc_info=True)
            status = "error"
            error_msg = str(e)
            result = ToolResult(success=False, error=str(e))

        duration_ms = int((time.time() - start_time) * 1000)

        # 4. Record to database (async, non-blocking)
        try:
            await self._record_execution(
                tool_name=tool_name,
                agent_id=agent_id,
                conversation_id=conversation_id,
                input_data=parameters,
                output_data=result_data,
                status=status,
                error=error_msg,
                duration_ms=duration_ms,
                trace_id=trace_id,
            )
        except Exception as e:
            logger.warning(f"Failed to record tool execution: {e}")

        result.duration_ms = duration_ms
        return result

    def _validate_parameters(
        self, tool: BaseTool, parameters: Dict[str, Any]
    ) -> Optional[str]:
        """Basic parameter validation against JSON Schema.

        Checks required fields and basic types.
        Does not do full JSON Schema validation (keep it simple for MVP).
        """
        schema = tool.input_schema
        if not schema:
            return None

        # Check required fields
        required = schema.get("required", [])
        for field_name in required:
            if field_name not in parameters:
                return f"Missing required field: '{field_name}'"

        # Check types (basic)
        properties = schema.get("properties", {})
        for field_name, field_schema in properties.items():
            if field_name not in parameters:
                continue

            value = parameters[field_name]
            expected_type = field_schema.get("type")
            type_map = {
                "string": str,
                "integer": int,
                "number": (int, float),
                "boolean": bool,
                "array": list,
                "object": dict,
            }
            expected_python = type_map.get(expected_type)
            if expected_python and value is not None:
                # bool is subclass of int, so check bool before int
                if expected_type == "integer" and isinstance(value, bool):
                    return f"Field '{field_name}' must be integer, got boolean"
                if not isinstance(value, expected_python):
                    return (
                        f"Field '{field_name}' must be {expected_type}, "
                        f"got {type(value).__name__}"
                    )

        return None

    async def _record_execution(
        self,
        tool_name: str,
        agent_id: Optional[int],
        conversation_id: Optional[int],
        input_data: Dict,
        output_data: Any,
        status: str,
        error: Optional[str],
        duration_ms: int,
        trace_id: Optional[str],
    ):
        """Record tool execution to the database."""
        from app.database.session import async_session_factory
        from app.models.tool import Tool, ToolExecution
        from sqlalchemy import select

        async with async_session_factory() as db:
            # Find tool by name
            result = await db.execute(
                select(Tool).where(Tool.name == tool_name)
            )
            tool_row = result.scalar_one_or_none()

            if not tool_row:
                logger.debug(f"Tool '{tool_name}' not in DB, skipping execution record.")
                return

            log = ToolExecution(
                tool_id=tool_row.id,
                agent_id=agent_id,
                conversation_id=conversation_id,
                input_data=input_data,
                output_data=output_data if isinstance(output_data, dict) else {"result": output_data},
                status=status,
                error=error,
                duration_ms=duration_ms,
                trace_id=trace_id,
            )
            db.add(log)
            await db.commit()
