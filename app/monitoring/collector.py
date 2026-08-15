"""
Metrics collector for system monitoring.
Gathers real-time data from: OS (psutil), PostgreSQL, Redis, LLM logs, Agent traces.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

import psutil
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database.session import engine, async_session_factory
from app.database.redis_client import redis_client

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collects platform-wide runtime metrics for monitoring."""

    # ── Service Health ──────────────────────────────────────────

    async def check_postgres(self) -> Dict[str, Any]:
        """Check PostgreSQL connectivity and basic stats."""
        try:
            start = time.monotonic()
            async with async_session_factory() as db:
                await db.execute(text("SELECT 1"))
            latency_ms = round((time.monotonic() - start) * 1000, 2)
            return {"status": "healthy", "latency_ms": latency_ms, "error": None}
        except Exception as e:
            return {"status": "unhealthy", "latency_ms": None, "error": str(e)}

    async def check_redis(self) -> Dict[str, Any]:
        """Check Redis connectivity."""
        try:
            start = time.monotonic()
            await redis_client.ping()
            latency_ms = round((time.monotonic() - start) * 1000, 2)
            return {"status": "healthy", "latency_ms": latency_ms, "error": None}
        except Exception as e:
            return {"status": "unhealthy", "latency_ms": None, "error": str(e)}

    async def check_embedding_service(self) -> Dict[str, Any]:
        """Check embedding microservice health."""
        import httpx
        try:
            start = time.monotonic()
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get("http://localhost:8001/health")
            latency_ms = round((time.monotonic() - start) * 1000, 2)
            if resp.status_code == 200:
                return {"status": "healthy", "latency_ms": latency_ms, "error": None}
            return {"status": "unhealthy", "latency_ms": latency_ms,
                    "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"status": "unhealthy", "latency_ms": None, "error": str(e)}

    async def check_fastapi(self) -> Dict[str, Any]:
        """FastAPI is always healthy if this endpoint responds."""
        return {"status": "healthy", "latency_ms": 0, "error": None}

    async def collect_service_health(self) -> Dict[str, Dict[str, Any]]:
        """Run all service health checks concurrently."""
        results = await asyncio.gather(
            self.check_fastapi(),
            self.check_postgres(),
            self.check_redis(),
            self.check_embedding_service(),
            return_exceptions=True,
        )
        services = ["fastapi", "postgresql", "redis", "embedding"]
        health = {}
        for name, result in zip(services, results):
            if isinstance(result, Exception):
                health[name] = {"status": "unhealthy", "latency_ms": None,
                                "error": str(result)}
            else:
                health[name] = result
        # Overall status
        all_healthy = all(h["status"] == "healthy" for h in health.values())
        health["overall"] = "healthy" if all_healthy else "degraded"
        return health

    # ── System Resources ────────────────────────────────────────

    def collect_system_resources(self) -> Dict[str, Any]:
        """Collect CPU, memory, and disk metrics via psutil."""
        cpu_percent = psutil.cpu_percent(interval=0.5)
        cpu_count = psutil.cpu_count(logical=True)
        cpu_count_physical = psutil.cpu_count(logical=False)

        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        disk = psutil.disk_usage("/")

        # Load average (Unix only)
        try:
            load_avg = psutil.getloadavg()
        except Exception:
            load_avg = [None, None, None]

        # Process info for the current Python process
        proc = psutil.Process()
        proc_mem = proc.memory_info()
        proc_cpu = proc.cpu_percent(interval=0.1)

        # Uptime
        boot_time = psutil.boot_time()
        uptime_seconds = time.time() - boot_time

        return {
            "cpu": {
                "percent": cpu_percent,
                "logical_cores": cpu_count,
                "physical_cores": cpu_count_physical,
                "load_avg_1m": load_avg[0],
                "load_avg_5m": load_avg[1],
                "load_avg_15m": load_avg[2],
            },
            "memory": {
                "total_mb": round(mem.total / (1024 * 1024), 2),
                "available_mb": round(mem.available / (1024 * 1024), 2),
                "used_mb": round(mem.used / (1024 * 1024), 2),
                "percent": mem.percent,
            },
            "swap": {
                "total_mb": round(swap.total / (1024 * 1024), 2),
                "used_mb": round(swap.used / (1024 * 1024), 2),
                "percent": swap.percent,
            },
            "disk": {
                "total_gb": round(disk.total / (1024 ** 3), 2),
                "used_gb": round(disk.used / (1024 ** 3), 2),
                "free_gb": round(disk.free / (1024 ** 3), 2),
                "percent": disk.percent,
            },
            "process": {
                "pid": proc.pid,
                "rss_mb": round(proc_mem.rss / (1024 * 1024), 2),
                "vms_mb": round(proc_mem.vms / (1024 * 1024), 2),
                "cpu_percent": proc_cpu,
                "threads": proc.num_threads(),
                "create_time": datetime.fromtimestamp(
                    proc.create_time(), tz=timezone.utc
                ).isoformat(),
            },
            "uptime_seconds": round(uptime_seconds, 0),
        }

    # ── Database Stats ──────────────────────────────────────────

    async def collect_database_stats(self) -> Dict[str, Any]:
        """Collect PostgreSQL connection pool and table stats."""
        # Connection pool stats from SQLAlchemy engine
        pool = engine.pool
        pool_stats = {
            "pool_size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "checked_out_count": pool.checkedout(),
        }

        async with async_session_factory() as db:
            # Table sizes and row counts
            table_query = text("""
                SELECT
                    schemaname || '.' || relname AS table_name,
                    pg_size_pretty(pg_total_relation_size(relid)) AS size_pretty,
                    pg_total_relation_size(relid) AS size_bytes,
                    n_live_tup AS row_count
                FROM pg_stat_user_tables
                ORDER BY pg_total_relation_size(relid) DESC
                LIMIT 20
            """)
            result = await db.execute(table_query)
            tables = []
            for row in result.mappings():
                tables.append({
                    "table": row["table_name"],
                    "size": row["size_pretty"],
                    "size_bytes": row["size_bytes"],
                    "rows": row["row_count"],
                })

            # Active connections
            conn_query = text("""
                SELECT count(*) AS total,
                       count(*) FILTER (WHERE state = 'active') AS active,
                       count(*) FILTER (WHERE state = 'idle') AS idle
                FROM pg_stat_activity
                WHERE datname = current_database()
            """)
            result = await db.execute(conn_query)
            conn_row = result.mappings().first()
            connections = {
                "total": conn_row["total"] if conn_row else 0,
                "active": conn_row["active"] if conn_row else 0,
                "idle": conn_row["idle"] if conn_row else 0,
            }

            # Database size
            db_size_query = text("SELECT pg_size_pretty(pg_database_size(current_database()))")
            result = await db.execute(db_size_query)
            db_size = result.scalar()

        return {
            "pool": pool_stats,
            "connections": connections,
            "database_size": db_size,
            "tables": tables,
        }

    # ── Redis Stats ─────────────────────────────────────────────

    async def collect_redis_stats(self) -> Dict[str, Any]:
        """Collect Redis server info."""
        try:
            info = await redis_client.info()
            db_size = await redis_client.dbsize()

            # Count keys by prefix pattern
            key_samples = []
            async for key in redis_client.scan_iter(count=100):
                key_samples.append(key)
                if len(key_samples) >= 20:
                    break

            return {
                "status": "healthy",
                "version": info.get("redis_version", "unknown"),
                "mode": info.get("redis_mode", "unknown"),
                "connected_clients": info.get("connected_clients", 0),
                "used_memory_mb": round(
                    info.get("used_memory", 0) / (1024 * 1024), 2
                ),
                "used_memory_peak_mb": round(
                    info.get("used_memory_peak", 0) / (1024 * 1024), 2
                ),
                "total_keys": db_size,
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "hit_rate": round(
                    info.get("keyspace_hits", 0) /
                    max(info.get("keyspace_hits", 0) + info.get("keyspace_misses", 0), 1) * 100,
                    2,
                ),
                "ops_per_sec": info.get("instantaneous_ops_per_sec", 0),
                "uptime_days": info.get("uptime_in_days", 0),
                "sample_keys": key_samples[:20],
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    # ── LLM Stats ───────────────────────────────────────────────

    async def collect_llm_stats(self) -> Dict[str, Any]:
        """Collect LLM call statistics from model_usage_logs."""
        async with async_session_factory() as db:
            # Overall stats
            overall_query = text("""
                SELECT
                    count(*) AS total_calls,
                    count(*) FILTER (WHERE status = 'success') AS success_count,
                    count(*) FILTER (WHERE status = 'error') AS error_count,
                    COALESCE(sum(prompt_tokens), 0) AS total_prompt_tokens,
                    COALESCE(sum(completion_tokens), 0) AS total_completion_tokens,
                    COALESCE(sum(total_tokens), 0) AS total_tokens,
                    COALESCE(sum(cost), 0) AS total_cost,
                    COALESCE(round(avg(duration_ms)), 0) AS avg_latency_ms,
                    COALESCE(max(duration_ms), 0) AS max_latency_ms
                FROM model_usage_logs
            """)
            result = await db.execute(overall_query)
            row = result.one()

            # Calls by model
            model_query = text("""
                SELECT model_id,
                       count(*) AS calls,
                       COALESCE(sum(total_tokens), 0) AS tokens,
                       COALESCE(sum(cost), 0) AS cost,
                       COALESCE(round(avg(duration_ms)), 0) AS avg_ms
                FROM model_usage_logs
                GROUP BY model_id
                ORDER BY calls DESC
            """)
            result = await db.execute(model_query)
            by_model = [
                {
                    "model": r.model_id,
                    "calls": r.calls,
                    "tokens": r.tokens,
                    "cost": round(r.cost, 4),
                    "avg_latency_ms": r.avg_ms,
                }
                for r in result
            ]

            # Recent 24h trend (calls per hour)
            trend_query = text("""
                SELECT date_trunc('hour', created_at) AS hour,
                       count(*) AS calls,
                       COALESCE(sum(total_tokens), 0) AS tokens
                FROM model_usage_logs
                WHERE created_at > now() - interval '24 hours'
                GROUP BY hour
                ORDER BY hour ASC
            """)
            result = await db.execute(trend_query)
            trend = [
                {
                    "hour": r.hour.isoformat() if r.hour else None,
                    "calls": r.calls,
                    "tokens": r.tokens,
                }
                for r in result
            ]

        total = row.total_calls or 0
        error_count = row.error_count or 0
        return {
            "total_calls": total,
            "success_count": row.success_count or 0,
            "error_count": error_count,
            "error_rate": round(error_count / total * 100, 2) if total > 0 else 0,
            "total_prompt_tokens": row.total_prompt_tokens or 0,
            "total_completion_tokens": row.total_completion_tokens or 0,
            "total_tokens": row.total_tokens or 0,
            "total_cost": round(row.total_cost or 0, 4),
            "avg_latency_ms": row.avg_latency_ms or 0,
            "max_latency_ms": row.max_latency_ms or 0,
            "by_model": by_model,
            "trend_24h": trend,
        }

    # ── Agent Runtime Stats ────────────────────────────────────

    async def collect_agent_stats(self) -> Dict[str, Any]:
        """Collect Agent runtime statistics from traces and spans."""
        async with async_session_factory() as db:
            # Overall trace stats
            trace_query = text("""
                SELECT
                    count(*) AS total_traces,
                    count(*) FILTER (WHERE status = 'success') AS success_count,
                    count(*) FILTER (WHERE status = 'failed') AS failed_count,
                    count(*) FILTER (WHERE status = 'human_transfer') AS transfer_count,
                    COALESCE(round(avg(duration_ms)), 0) AS avg_duration_ms,
                    COALESCE(max(duration_ms), 0) AS max_duration_ms
                FROM agent_traces
            """)
            result = await db.execute(trace_query)
            row = result.one()

            # Intent distribution
            intent_query = text("""
                SELECT intent, count(*) AS count
                FROM agent_traces
                WHERE intent IS NOT NULL
                GROUP BY intent
                ORDER BY count DESC
            """)
            result = await db.execute(intent_query)
            intent_dist = [
                {"intent": r.intent, "count": r.count}
                for r in result
            ]

            # Span node performance
            span_query = text("""
                SELECT node_name,
                       count(*) AS count,
                       COALESCE(round(avg(duration_ms)), 0) AS avg_ms,
                       COALESCE(max(duration_ms), 0) AS max_ms,
                       count(*) FILTER (WHERE status = 'success') AS success_count,
                       count(*) FILTER (WHERE status != 'success') AS error_count
                FROM agent_spans
                GROUP BY node_name
                ORDER BY avg_ms DESC
            """)
            result = await db.execute(span_query)
            node_perf = [
                {
                    "node": r.node_name,
                    "count": r.count,
                    "avg_ms": r.avg_ms,
                    "max_ms": r.max_ms,
                    "success_count": r.success_count,
                    "error_count": r.error_count,
                }
                for r in result
            ]

            # Recent 24h trace trend
            trend_query = text("""
                SELECT date_trunc('hour', started_at) AS hour,
                       count(*) AS traces,
                       count(*) FILTER (WHERE status = 'success') AS success
                FROM agent_traces
                WHERE started_at > now() - interval '24 hours'
                GROUP BY hour
                ORDER BY hour ASC
            """)
            result = await db.execute(trend_query)
            trace_trend = [
                {
                    "hour": r.hour.isoformat() if r.hour else None,
                    "traces": r.traces,
                    "success": r.success,
                }
                for r in result
            ]

            # Conversation stats
            conv_query = text("""
                SELECT count(*) AS total,
                       count(*) FILTER (WHERE status = 'active') AS active
                FROM conversations
            """)
            result = await db.execute(conv_query)
            conv_row = result.one()

            # Human task stats
            task_query = text("""
                SELECT count(*) AS total,
                       count(*) FILTER (WHERE status = 'pending') AS pending,
                       count(*) FILTER (WHERE status = 'assigned') AS assigned,
                       count(*) FILTER (WHERE status = 'resolved') AS resolved
                FROM human_tasks
            """)
            result = await db.execute(task_query)
            task_row = result.one()

        total = row.total_traces or 0
        success = row.success_count or 0
        return {
            "traces": {
                "total": total,
                "success": success,
                "failed": row.failed_count or 0,
                "human_transfer": row.transfer_count or 0,
                "success_rate": round(success / total * 100, 2) if total > 0 else 0,
                "avg_duration_ms": row.avg_duration_ms or 0,
                "max_duration_ms": row.max_duration_ms or 0,
            },
            "intent_distribution": intent_dist,
            "node_performance": node_perf,
            "trace_trend_24h": trace_trend,
            "conversations": {
                "total": conv_row.total or 0,
                "active": conv_row.active or 0,
            },
            "human_tasks": {
                "total": task_row.total or 0,
                "pending": task_row.pending or 0,
                "assigned": task_row.assigned or 0,
                "resolved": task_row.resolved or 0,
            },
        }

    # ── Overview (combined) ─────────────────────────────────────

    async def collect_overview(self) -> Dict[str, Any]:
        """Collect a combined overview of all metrics in one call."""
        import httpx

        # Run independent collectors concurrently
        health, sys_res, db_stats, redis_stats, llm_stats, agent_stats = (
            await asyncio.gather(
                self.collect_service_health(),
                asyncio.to_thread(self.collect_system_resources),
                self.collect_database_stats(),
                self.collect_redis_stats(),
                self.collect_llm_stats(),
                self.collect_agent_stats(),
                return_exceptions=True,
            )
        )

        # Handle exceptions gracefully
        def safe(v, default):
            return v if not isinstance(v, Exception) else default

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "services": safe(health, {"error": str(health)}),
            "system": safe(sys_res, {"error": str(sys_res)}),
            "database": safe(db_stats, {"error": str(db_stats)}),
            "redis": safe(redis_stats, {"error": str(redis_stats)}),
            "llm": safe(llm_stats, {"error": str(llm_stats)}),
            "agents": safe(agent_stats, {"error": str(agent_stats)}),
        }


# Singleton
collector = MetricsCollector()
