import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.place_details import get_place_details_service
from app.models.user import User
from app.schemas.place_unlock import (
    PlaceUnlockResponse,
    UnlockedPlaceItem,
    UnlockedPlacesListResponse,
)
from app.services.place_unlock_service import PlaceUnlockService
from app.services.place_details_service import PlaceDetailsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/places", tags=["Place Unlock"])


def get_unlock_service(
    db: Session = Depends(get_db),
    details_service: PlaceDetailsService = Depends(get_place_details_service),
) -> PlaceUnlockService:
    return PlaceUnlockService(db, details_service=details_service)


@router.post("/{place_id}/unlock", response_model=PlaceUnlockResponse)
async def unlock_place(
    place_id: str,
    current_user: User = Depends(get_current_user),
    service: PlaceUnlockService = Depends(get_unlock_service),
):
    logger.info("Unlock request — user_id: %s, place_id: %s", current_user.id, place_id)
    unlock = await service.unlock_place(user_id=current_user.id, place_id=place_id,)
    return PlaceUnlockResponse(
        success=True,
        message="Place unlocked successfully",
        place_id=place_id,
        tokens_spent=unlock["tokens_spent"],
        remaining_credits=unlock["remaining_credits"],
        category=unlock["category"],
        questions_limit=unlock["questions_limit"],
        questions_used=unlock["questions_used"],
        questions_remaining=unlock["questions_remaining"],
        is_unlocked=True,
    )

@router.get("/unlocked", response_model=UnlockedPlacesListResponse)
async def list_unlocked_places(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    include_expired: bool = Query(False),
    current_user: User = Depends(get_current_user),
    service: PlaceUnlockService = Depends(get_unlock_service),
):
    logger.info("List unlocked places — user_id: %s, page: %s, page_size: %s", current_user.id, page, page_size,)
    unlocks, total = service.get_user_unlocked_places(
        user_id=current_user.id,
        page=page,
        page_size=page_size,
        include_expired=include_expired,
    )

    items = [UnlockedPlaceItem(**unlock) for unlock in unlocks]
    has_next = (page * page_size) < total

    return UnlockedPlacesListResponse(
        data=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=has_next,
    )
