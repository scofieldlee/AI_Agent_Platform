"""Model token usage statistics endpoints.

Aggregates model_usage_logs by model / agent / time. All groupings use
Beijing time (Asia/Shanghai) per platform convention.
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_permission, get_current_user
from app.database.session import get_db
from app.models.user import User

router = APIRouter(dependencies=[Depends(require_permission("usage:view"))])

# tz-conversion helper: timestamptz -> Beijing local timestamp
_TZ = "Asia/Shanghai"


def _parse_range(
    start: Optional[datetime], end: Optional[datetime]
) -> tuple[datetime, datetime]:
    """Default window: last 30 days (now -> now-30d)."""
    now = datetime.now().astimezone()
    e = end or now
    s = start or (e - timedelta(days=30))
    return s, e


@router.get("/summary")
async def usage_summary(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Headline cards: totals over the window."""
    s, e = _parse_range(start, end)
    row = (await db.execute(text("""
        SELECT COALESCE(SUM(total_tokens), 0)      AS total_tokens,
               COALESCE(SUM(prompt_tokens), 0)     AS prompt_tokens,
               COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
               COALESCE(SUM(cost), 0)              AS total_cost,
               COUNT(*)                            AS calls,
               COALESCE(AVG(duration_ms), 0)       AS avg_duration_ms,
               COALESCE(SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END), 0) AS error_calls
        FROM model_usage_logs
        WHERE created_at >= :s AND created_at < :e
    """), {"s": s, "e": e})).mappings().first()

    data = dict(row)
    calls = data["calls"] or 0
    data["error_rate"] = round(data["error_calls"] / calls, 4) if calls else 0.0
    data["start"] = s.isoformat()
    data["end"] = e.isoformat()
    return data


@router.get("/timeline")
async def usage_timeline(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    granularity: str = Query("day", pattern="^(hour|day|month)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Time series of token usage grouped by hour/day/month (Beijing time)."""
    s, e = _parse_range(start, end)
    bucket = {"hour": "hour", "day": "day", "month": "month"}[granularity]
    rows = (await db.execute(text(f"""
        SELECT date_trunc('{bucket}', created_at AT TIME ZONE '{_TZ}') AS bucket,
               COALESCE(SUM(total_tokens), 0)      AS total_tokens,
               COALESCE(SUM(prompt_tokens), 0)     AS prompt_tokens,
               COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
               COALESCE(SUM(cost), 0)              AS cost,
               COUNT(*)                            AS calls
        FROM model_usage_logs
        WHERE created_at >= :s AND created_at < :e
        GROUP BY 1
        ORDER BY 1
    """), {"s": s, "e": e})).mappings().all()

    return [
        {
            "bucket": r["bucket"].isoformat(),
            "total_tokens": r["total_tokens"],
            "prompt_tokens": r["prompt_tokens"],
            "completion_tokens": r["completion_tokens"],
            "cost": round(float(r["cost"]), 4),
            "calls": r["calls"],
        }
        for r in rows
    ]


@router.get("/by-model")
async def usage_by_model(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aggregated usage per model (provider/model name joined for display)."""
    s, e = _parse_range(start, end)
    rows = (await db.execute(text("""
        SELECT u.model_config_id,
               u.model_id,
               u.model_type,
               COALESCE(p.name, 'default')           AS provider_name,
               COALESCE(mc.name, u.model_id)         AS model_name,
               COALESCE(SUM(u.total_tokens), 0)      AS total_tokens,
               COALESCE(SUM(u.prompt_tokens), 0)     AS prompt_tokens,
               COALESCE(SUM(u.completion_tokens), 0) AS completion_tokens,
               COALESCE(SUM(u.cost), 0)              AS cost,
               COUNT(*)                              AS calls,
               COALESCE(SUM(CASE WHEN u.status = 'error' THEN 1 ELSE 0 END), 0) AS error_calls
        FROM model_usage_logs u
        LEFT JOIN model_configs mc ON mc.id = u.model_config_id
        LEFT JOIN model_providers p ON p.id = mc.provider_id
        WHERE u.created_at >= :s AND u.created_at < :e
        GROUP BY u.model_config_id, u.model_id, u.model_type, p.name, mc.name
        ORDER BY total_tokens DESC
    """), {"s": s, "e": e})).mappings().all()

    return [dict(r) for r in rows]


@router.get("/by-agent")
async def usage_by_agent(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aggregated usage per agent; calls without agent_id roll into 系统内部调用."""
    s, e = _parse_range(start, end)
    rows = (await db.execute(text(f"""
        SELECT u.agent_id,
               COALESCE(a.name, '系统内部调用')       AS agent_name,
               COALESCE(SUM(u.total_tokens), 0)      AS total_tokens,
               COALESCE(SUM(u.prompt_tokens), 0)     AS prompt_tokens,
               COALESCE(SUM(u.completion_tokens), 0) AS completion_tokens,
               COALESCE(SUM(u.cost), 0)              AS cost,
               COUNT(*)                              AS calls
        FROM model_usage_logs u
        LEFT JOIN agents a ON a.id = u.agent_id
        WHERE u.created_at >= :s AND u.created_at < :e
        GROUP BY u.agent_id, a.name
        ORDER BY total_tokens DESC
    """), {"s": s, "e": e})).mappings().all()

    return [dict(r) for r in rows]
