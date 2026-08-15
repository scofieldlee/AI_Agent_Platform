"""Health check endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.database.session import get_db
from app.database.redis_client import get_redis

router = APIRouter()


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """Check system health: API, Database, Redis."""
    status = {"api": "ok", "database": "ok", "redis": "ok"}

    # Check database
    try:
        result = await db.execute(text("SELECT 1"))
        result.fetchone()
    except Exception:
        status["database"] = "error"

    # Check Redis
    try:
        redis = get_redis()
        await redis  # get the client
        from app.database.redis_client import redis_client
        await redis_client.ping()
    except Exception:
        status["redis"] = "error"

    all_ok = all(v == "ok" for v in status.values())
    return {"status": "healthy" if all_ok else "degraded", "services": status}
