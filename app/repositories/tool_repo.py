"""
Tool repository: data access for tools and execution logs.
"""

from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tool import Tool, ToolExecution


async def get_tool_by_name(db: AsyncSession, name: str) -> Optional[Tool]:
    """Find a tool by name."""
    result = await db.execute(select(Tool).where(Tool.name == name))
    return result.scalar_one_or_none()


async def list_execution_logs(db: AsyncSession, tool_id: int, limit: int = 20) -> List[ToolExecution]:
    """Get recent execution logs for a tool."""
    result = await db.execute(
        select(ToolExecution)
        .where(ToolExecution.tool_id == tool_id)
        .order_by(ToolExecution.id.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
