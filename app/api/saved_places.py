import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from sqlalchemy.orm import Session
from app.core.rate_limiter import shared_limiter as limiter
from app.database.connection import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.saved_places import (
    ListSavedPlacesResponse,
    SavePlaceActionResponse,
    SavePlaceRequest,
)
from app.services.saved_place_service import SavedPlaceService
from app.utils.error_messages import SAVED_PLACE_NOT_FOUND

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Places — Saved Places"])


def get_service(db: Session = Depends(get_db)) -> SavedPlaceService:
    return SavedPlaceService(db)

@router.post("/places/{place_id}/save", response_model=SavePlaceActionResponse)
@limiter.limit("30/minute")
async def save_place(
    request: Request,
    payload: SavePlaceRequest,
    place_id: str = Path(..., min_length=1, max_length=255),
    current_user: User = Depends(get_current_user),
    service: SavedPlaceService = Depends(get_service),) -> SavePlaceActionResponse:
    message, saved_id = await service.save_place(
        user_id=current_user.id,
        place_id=place_id,
        notes=payload.notes,
        tags=payload.tags,)
    return SavePlaceActionResponse(
        message=message,
        place_id=place_id,
        saved=True,
        saved_id=saved_id,)


@router.delete("/places/saved/{saved_id}", response_model=SavePlaceActionResponse, status_code=status.HTTP_200_OK,)
@limiter.limit("30/minute")
async def unsave_place(
    request: Request,
    saved_id: int = Path(..., ge=1),
    current_user: User = Depends(get_current_user),
    service: SavedPlaceService = Depends(get_service),) -> SavePlaceActionResponse:
    deleted = await service.unsave_place(saved_id=saved_id, user_id=current_user.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=SAVED_PLACE_NOT_FOUND,)
    return SavePlaceActionResponse(
        message="Place removed from saved.",
        place_id="",
        saved=False,
        saved_id=saved_id,)


@router.get("/places/saved", response_model=ListSavedPlacesResponse)
@limiter.limit("30/minute")
async def list_saved_places(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    search: Optional[str] = Query(None, description="Search by name"),
    current_user: User = Depends(get_current_user),
    service: SavedPlaceService = Depends(get_service),) -> ListSavedPlacesResponse:
    items, total, has_next = await service.list_saved(
        user_id=current_user.id,
        page=page,
        page_size=page_size,
        tag=tag,
        search=search,
    )
    return ListSavedPlacesResponse(
        data=items,
        total_count=total,
        page=page,
        page_size=page_size,
        has_next=has_next,
    )


@router.get("/places/saved/nearby", response_model=ListSavedPlacesResponse)
@limiter.limit("30/minute")
async def get_saved_nearby(
    request: Request,
    lat: Optional[float] = Query(None, ge=-90, le=90),
    lon: Optional[float] = Query(None, ge=-180, le=180),
    radius_km: float = Query(2.0, ge=0.1, le=50),
    filter_by: str = Query(
        "place",
        description="'place' = filter by place's location, 'saved' = filter by where you saved it",),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=50, description="Items per page (max 50)"),
    current_user: User = Depends(get_current_user),
    service: SavedPlaceService = Depends(get_service),) -> ListSavedPlacesResponse:
    items, total, has_next = await service.get_saved_nearby(
        user_id=current_user.id,
        lat=lat,
        lon=lon,
        radius_km=radius_km,
        filter_by=filter_by,
        page=page,
        page_size=page_size,)
    return ListSavedPlacesResponse(
        data=items,
        total_count=total,
        page=page,
        page_size=page_size,
        has_next=has_next,
    )
