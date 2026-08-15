"""Analytics endpoints: trace/span inspection and stats."""

from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.auth.dependencies import require_permission
from app.schemas.analytics import TraceListItem, SpanItem, TraceDetail, StatsResponse
from app.repositories.analytics_repo import list_traces, get_trace, get_spans, get_stats

router = APIRouter(dependencies=[Depends(require_permission("analytics:view"))])


@router.get("/traces", response_model=List[TraceListItem])
async def list_traces_endpoint(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None, description="Filter by status"),
    agent_id: Optional[int] = Query(None, description="Filter by agent"),
    db: AsyncSession = Depends(get_db),
):
    """List recent agent execution traces."""
    return await list_traces(db, limit=limit, offset=offset, status=status, agent_id=agent_id)


@router.get("/traces/{trace_id}", response_model=TraceDetail)
async def get_trace_detail_endpoint(trace_id: str, db: AsyncSession = Depends(get_db)):
    """Get a trace with all its spans."""
    trace = await get_trace(db, trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")

    spans = await get_spans(db, trace_id)

    return TraceDetail(
        trace_id=trace.trace_id,
        agent_id=trace.agent_id,
        conversation_id=trace.conversation_id,
        status=trace.status,
        intent=trace.intent,
        confidence=trace.confidence,
        duration_ms=trace.duration_ms,
        total_tokens=trace.total_tokens,
        total_cost=trace.total_cost,
        input_data=trace.input_data,
        output_data=trace.output_data,
        started_at=trace.started_at,
        completed_at=trace.completed_at,
        spans=[SpanItem.model_validate(s) for s in spans],
    )


@router.get("/stats", response_model=StatsResponse)
async def get_stats_endpoint(
    agent_id: Optional[int] = Query(None, description="Filter by agent"),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate analytics stats."""
    stats = await get_stats(db, agent_id=agent_id)
    return StatsResponse(**stats)


@router.get("/traces/{trace_id}/spans", response_model=List[SpanItem])
async def get_trace_spans_endpoint(trace_id: str, db: AsyncSession = Depends(get_db)):
    """Get all spans for a trace."""
    return await get_spans(db, trace_id)
