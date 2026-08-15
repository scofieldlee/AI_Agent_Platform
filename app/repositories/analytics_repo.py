"""
Analytics repository: data access for traces and spans.
"""

from typing import List, Optional, Dict, Any
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import AgentTrace, AgentSpan


async def list_traces(
    db: AsyncSession,
    limit: int = 20,
    offset: int = 0,
    status: Optional[str] = None,
    agent_id: Optional[int] = None,
) -> List[AgentTrace]:
    """List recent agent execution traces with optional filters."""
    query = select(AgentTrace).order_by(desc(AgentTrace.id))
    if status:
        query = query.where(AgentTrace.status == status)
    if agent_id:
        query = query.where(AgentTrace.agent_id == agent_id)
    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_trace(db: AsyncSession, trace_id: str) -> Optional[AgentTrace]:
    """Get a trace by trace_id."""
    result = await db.execute(
        select(AgentTrace).where(AgentTrace.trace_id == trace_id)
    )
    return result.scalar_one_or_none()


async def get_spans(db: AsyncSession, trace_id: str) -> List[AgentSpan]:
    """Get all spans for a trace ordered by ID."""
    result = await db.execute(
        select(AgentSpan)
        .where(AgentSpan.trace_id == trace_id)
        .order_by(AgentSpan.id)
    )
    return list(result.scalars().all())


async def get_stats(db: AsyncSession, agent_id: Optional[int] = None) -> Dict[str, Any]:
    """Compute aggregate analytics stats.

    Returns dict with: total_traces, success_count, failed_count,
    human_transfer_count, success_rate, avg_duration_ms, avg_confidence,
    intent_distribution.
    """
    # Total count
    total_result = await db.execute(select(func.count(AgentTrace.id)))
    total_traces = total_result.scalar() or 0

    # Get recent traces for computation (MVP approach)
    result = await db.execute(
        select(AgentTrace).order_by(desc(AgentTrace.id)).limit(500)
    )
    traces = list(result.scalars().all())

    success_count = sum(1 for t in traces if t.status == "success")
    failed_count = sum(1 for t in traces if t.status == "failed")
    human_count = sum(1 for t in traces if t.status == "human_transfer")

    durations = [t.duration_ms for t in traces if t.duration_ms is not None]
    confidences = [t.confidence for t in traces if t.confidence is not None]

    intent_dist: Dict[str, int] = {}
    for t in traces:
        if t.intent:
            intent_dist[t.intent] = intent_dist.get(t.intent, 0) + 1

    return {
        "total_traces": total_traces,
        "success_count": success_count,
        "failed_count": failed_count,
        "human_transfer_count": human_count,
        "success_rate": round(success_count / total_traces * 100, 1) if total_traces > 0 else 0,
        "avg_duration_ms": round(sum(durations) / len(durations)) if durations else None,
        "avg_confidence": round(sum(confidences) / len(confidences), 3) if confidences else None,
        "intent_distribution": intent_dist,
    }
