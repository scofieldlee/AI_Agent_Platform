"""
Redis client for caching, sessions, and queues.
"""

import redis.asyncio as redis
from app.core.config import settings

# Async Redis client
redis_client = redis.from_url(
    settings.redis_url,
    decode_responses=True,
    encoding="utf-8",
)


async def get_redis() -> redis.Redis:
    """FastAPI dependency: returns the Redis client."""
    return redis_client


async def close_redis():
    """Close Redis connection on shutdown."""
    await redis_client.close()
