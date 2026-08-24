import asyncio
import logging
from typing import Optional
import redis.asyncio as aioredis
from redis.exceptions import RedisError
from app.core.config import settings

logger = logging.getLogger(__name__)
_redis_client: Optional[aioredis.Redis] = None
_redis_lock = asyncio.Lock()


def get_redis_client() -> Optional[aioredis.Redis]:
    return _redis_client


async def initialise_redis() -> None:
    global _redis_client

    async with _redis_lock:
        if _redis_client is not None:
            logger.info("Redis already initialized")
            return

        try:
            client = aioredis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD or None,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30,
            )
            await client.ping()
            _redis_client = client
            logger.info(
                "Redis connection established at %s:%s",
                settings.REDIS_HOST,
                settings.REDIS_PORT,
            )
        except RedisError as exc:
            logger.warning(
                "Redis unavailable at startup (%s:%s) — running without cache. "
                "All search and detail requests will hit Google directly. "
                "Error: %s",
                settings.REDIS_HOST,
                settings.REDIS_PORT,
                exc,
            )
            _redis_client = None


async def close_redis() -> None:
    global _redis_client

    async with _redis_lock:
        if _redis_client:
            await _redis_client.aclose()
            _redis_client = None
            logger.info("Redis connection closed.")
