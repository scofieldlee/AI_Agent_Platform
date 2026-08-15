"""Tools API endpoints: list and execute tools."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.tools.registry import get_registry
from app.tools.executor import ToolExecutor
from app.auth.dependencies import require_permission
from app.schemas.tool import ToolResponse, ToolExecuteRequest, ToolExecuteResponse, ToolExecutionLogResponse
from app.repositories.tool_repo import get_tool_by_name, list_execution_logs

router = APIRouter(dependencies=[Depends(require_permission("tool:view"))])


@router.get("", response_model=List[ToolResponse])
async def list_tools_endpoint():
    """List all registered tools (from in-memory registry)."""
    registry = get_registry()
    return [ToolResponse(**t.to_dict()) for t in registry.list_tools()]


@router.get("/{tool_name}", response_model=ToolResponse)
async def get_tool_endpoint(tool_name: str):
    """Get details of a specific tool."""
    registry = get_registry()
    tool = registry.get(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
    return ToolResponse(**tool.to_dict())


@router.post("/{tool_name}/execute", response_model=ToolExecuteResponse)
async def execute_tool_endpoint(
    tool_name: str,
    request: ToolExecuteRequest,
    agent_id: Optional[int] = None,
    conversation_id: Optional[int] = None,
):
    """Execute a tool directly (for testing/debugging)."""
    registry = get_registry()
    if not registry.has(tool_name):
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

    executor = ToolExecutor()
    result = await executor.execute(
        tool_name=tool_name,
        parameters=request.parameters,
        agent_id=agent_id,
        conversation_id=conversation_id,
    )

    return ToolExecuteResponse(
        tool=tool_name,
        success=result.success,
        data=result.data,
        error=result.error,
        duration_ms=result.duration_ms,
    )


@router.get("/{tool_name}/logs", response_model=List[ToolExecutionLogResponse])
async def get_tool_logs_endpoint(
    tool_name: str,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """Get recent execution logs for a tool."""
    tool_row = await get_tool_by_name(db, tool_name)
    if not tool_row:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not in database")

    return await list_execution_logs(db, tool_row.id, limit=limit)
