from fastapi import Depends, Request
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.dependencies import get_redis_repo
from app.core.service_registry import ServiceRegistry
from app.repositories.redis_repository import RedisRepository
from app.services.routes_service import RoutesService


def get_routes_service(
    request: Request,
    db: Session = Depends(get_db),
    redis_repo: RedisRepository = Depends(get_redis_repo),
) -> RoutesService:
    registry = ServiceRegistry(request.app.state)
    return registry.get_routes_service(db, redis_repo)
