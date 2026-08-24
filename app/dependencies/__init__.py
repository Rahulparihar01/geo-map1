from app.core.redis import get_redis_client
from app.repositories.redis_repository import RedisRepository


def get_redis_repo() -> RedisRepository:
    return RedisRepository(get_redis_client())
