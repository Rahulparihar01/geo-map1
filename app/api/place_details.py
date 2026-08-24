import logging

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.place_details import get_place_details_service
from app.models.user import User
from app.schemas.place_details import DetailSource, PlaceDetailsResponse
from app.services.place_details_service import PlaceDetailsService
from app.services.place_unlock_service import PlaceUnlockService
from app.repositories.visit_repository import VisitRepository
from app.utils.error_messages import PLACE_LOCKED

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/places", tags=["Place Details"])

_SOURCE_MESSAGES = {
    DetailSource.REDIS: "Place details retrieved successfully",
    DetailSource.DATABASE: "Place details retrieved successfully",
    DetailSource.GOOGLE: "Place details retrieved successfully",
}


@router.get("/{place_id}/details", response_model=PlaceDetailsResponse)
async def get_place_details(
    place_id: str = Path(..., min_length=1, max_length=255),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    service: PlaceDetailsService = Depends(get_place_details_service),) -> PlaceDetailsResponse:
    logger.info("Place Details request — user_id: %s, place_id: %s", current_user.id, place_id,)
    unlock_service = PlaceUnlockService(db, details_service=service)
    if not unlock_service.is_place_unlocked(current_user.id, place_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=PLACE_LOCKED,)

    detail, source = await service.get_place_details(place_id)
    
    # Enrich with is_visit
    visit_repo = VisitRepository(db)
    visited_ids = visit_repo.get_visited_place_ids(current_user.id, [place_id])
    detail.is_visit = place_id in visited_ids
    
    return PlaceDetailsResponse(
        success=True,
        source=source,
        message=_SOURCE_MESSAGES.get(source, "Place details retrieved"),
        data=detail,
        cached=(source == DetailSource.REDIS),
    )
