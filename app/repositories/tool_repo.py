"""
Tool repository: data access for tools and execution logs.
"""

from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import and_, case, func, select
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


async def get_tool_stats(db: AsyncSession, since: datetime) -> Dict[str, dict]:
    """Aggregate execution stats per tool (24h window + lifetime).

    Returns:
        {tool_name: {
            total_24h, success_24h, error_24h, success_rate_24h,
            avg_duration_24h, last_executed_24h, total_all, success_all,
        }}
    """
    result = await db.execute(
        select(
            Tool.name.label("tool_name"),
            func.sum(case((ToolExecution.created_at >= since, 1), else_=0)).label("total_24h"),
            func.sum(case((and_(ToolExecution.created_at >= since, ToolExecution.status == "success"), 1), else_=0)).label("success_24h"),
            func.sum(case((and_(ToolExecution.created_at >= since, ToolExecution.status != "success"), 1), else_=0)).label("error_24h"),
            func.avg(case((ToolExecution.created_at >= since, ToolExecution.duration_ms), else_=None)).label("avg_duration_24h"),
            func.max(case((ToolExecution.created_at >= since, ToolExecution.created_at), else_=None)).label("last_executed_24h"),
            func.count(ToolExecution.id).label("total_all"),
            func.sum(case((ToolExecution.status == "success", 1), else_=0)).label("success_all"),
        )
        .join(Tool, ToolExecution.tool_id == Tool.id)
        .group_by(Tool.name)
    )

    stats: Dict[str, dict] = {}
    for row in result.all():
        total_24h = int(row.total_24h or 0)
        success_24h = int(row.success_24h or 0)
        error_24h = int(row.error_24h or 0)
        stats[row.tool_name] = {
            "total_24h": total_24h,
            "success_24h": success_24h,
            "error_24h": error_24h,
            "success_rate_24h": round(success_24h / total_24h * 100, 1) if total_24h else None,
            "avg_duration_24h": round(float(row.avg_duration_24h), 1) if row.avg_duration_24h is not None else None,
            "last_executed_24h": row.last_executed_24h.isoformat() if row.last_executed_24h else None,
            "total_all": int(row.total_all or 0),
            "success_all": int(row.success_all or 0),
        }
    return stats
