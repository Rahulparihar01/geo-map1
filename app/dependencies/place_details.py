from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.dependencies import get_redis_repo
from app.core.service_registry import ServiceRegistry
from app.repositories.redis_repository import RedisRepository
from app.services.place_details_service import PlaceDetailsService


def get_place_details_service(
    request: Request,
    db: Session = Depends(get_db),
    redis_repo: RedisRepository = Depends(get_redis_repo),
) -> PlaceDetailsService:
    registry = ServiceRegistry(request.app.state)
    return registry.get_place_details_service(db, redis_repo)
