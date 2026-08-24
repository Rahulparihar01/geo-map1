import json
import logging
from typing import Any, Optional

from redis.asyncio import Redis
from redis.exceptions import RedisError
from app.core.config import settings

logger = logging.getLogger(__name__)


class RedisRepository:

    def __init__(self, client: Optional[Redis]):
        self.client = client
        self.ttl = settings.REDIS_CACHE_TTL

    async def get(self, key: str) -> Optional[Any]:
        if self.client is None:
            return None
        try:
            raw = await self.client.get(key)
            if raw is None:
                logger.debug("Cache MISS: %s", key)
                return None
            logger.debug("Cache HIT: %s", key)
            return json.loads(raw)
        except (RedisError, json.JSONDecodeError) as exc:
            logger.error("Redis GET error for key '%s': %s", key, exc)
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        if self.client is None:
            return False
        try:
            expiry = ttl or self.ttl
            await self.client.setex(key, expiry, json.dumps(value))
            logger.debug("Cache SET: %s (TTL: %ss)", key, expiry)
            return True
        except (RedisError, TypeError, ValueError) as exc:
            logger.error("Redis SET error for key '%s': %s", key, exc)
            return False

    async def delete(self, key: str) -> bool:
        if self.client is None:
            return False
        try:
            result = await self.client.delete(key)
            return result > 0
        except RedisError as exc:
            logger.error("Redis DELETE error for key '%s': %s", key, exc)
            return False

    async def exists(self, key: str) -> bool:
        if self.client is None:
            return False
        try:
            return bool(await self.client.exists(key))
        except RedisError as exc:
            logger.error("Redis EXISTS error for key '%s': %s", key, exc)
            return False
