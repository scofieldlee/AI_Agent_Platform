"""
Monitoring API endpoints.
Provides real-time system health, resource usage, and runtime metrics.
All endpoints require 'system:config' permission.
"""

import logging
from fastapi import APIRouter, Depends

from app.auth.dependencies import require_permission
from app.monitoring.collector import collector

logger = logging.getLogger(__name__)

router = APIRouter(
    dependencies=[Depends(require_permission("system:config"))],
)


@router.get("/overview")
async def monitoring_overview():
    """Combined overview of all metrics in a single call."""
    return await collector.collect_overview()


@router.get("/health")
async def monitoring_health():
    """Service health checks (FastAPI, PostgreSQL, Redis, Embedding)."""
    return await collector.collect_service_health()


@router.get("/system")
async def monitoring_system():
    """System resources (CPU, memory, disk, process)."""
    return collector.collect_system_resources()


@router.get("/database")
async def monitoring_database():
    """Database connection pool, table sizes, active connections."""
    return await collector.collect_database_stats()


@router.get("/redis")
async def monitoring_redis():
    """Redis server info (memory, keys, hit rate, ops/sec)."""
    return await collector.collect_redis_stats()


@router.get("/llm")
async def monitoring_llm():
    """LLM call statistics (calls, tokens, cost, latency, model breakdown)."""
    return await collector.collect_llm_stats()


@router.get("/agents")
async def monitoring_agents():
    """Agent runtime statistics (traces, spans, conversations, human tasks)."""
    return await collector.collect_agent_stats()
