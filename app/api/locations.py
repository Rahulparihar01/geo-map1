import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.dependencies.auth import get_current_user
from app.exceptions.places import (
    GooglePlacesAPIError,
    GooglePlacesRateLimitError,
    GooglePlacesTimeoutError,
)
from app.integrations.google_geocoding import GoogleGeocodingClient
from app.integrations.google_text_search import GoogleTextSearchClient
from app.models.user import User
from app.schemas.location import (
    APIResponse,
    GPSUpdateRequest,
    LocationSearchResponse,
    LocationSearchResult,
    LocationHistoryItem,
    ManualLocationRequest,
    PaginatedHistoryResponse,
    ReverseGeocodeRequest,
    ReverseGeocodeResponse,
    UnifiedLocationResponse,
)
from app.services.geocoding_service import GeocodingService
from app.services.location_service import LocationService
from app.utils.error_messages import (
    LOCATION_GEOCODING_FAILED,
    LOCATION_HISTORY_ERROR,
    LOCATION_MANUAL_RATE_LIMIT,
    LOCATION_SEARCH_FAILED,
    LOCATION_SEARCH_INVALID_QUERY,
    LOCATION_UPDATE_FAILED,
)
from app.core.rate_limiter import shared_limiter as limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/locations", tags=["Locations"])

def _service(db: Session = Depends(get_db)) -> LocationService:
    return LocationService(db)

@router.get("/me", response_model=APIResponse)
async def get_my_location(
    current_user: User = Depends(get_current_user),
    service: LocationService = Depends(_service),
):
    location = service.get_current_location(current_user.id)
    return APIResponse(
        success=True,
        message="Current location retrieved",
        data=UnifiedLocationResponse(
            latitude=location.latitude,
            longitude=location.longitude,
            accuracy=location.accuracy,
            location_type=location.source,
            address=location.address,
            updated_at=location.updated_at or location.created_at,
        ),
    )


@router.post("/gps", response_model=APIResponse)
@limiter.limit("60/minute")
async def gps_update(
    request: Request,
    payload: GPSUpdateRequest,
    current_user: User = Depends(get_current_user),
    service: LocationService = Depends(_service),
):
    location, is_new = service.process_gps_update(current_user.id, payload)

    message = ("GPS location updated successfully"
        if is_new
        else "Location unchanged — duplicate update acknowledged")
    return APIResponse(
        success=True,
        message=message,
        data=UnifiedLocationResponse(
            latitude=location.latitude,
            longitude=location.longitude,
            accuracy=location.accuracy,
            location_type=location.source,
            address=location.address,
            updated_at=location.updated_at or location.created_at,
        ),
    )

@router.get("/search", response_model=LocationSearchResponse)
@limiter.limit("30/minute")
async def search_locations(
    request: Request,
    q: str = Query(..., min_length=2, max_length=100, description="Location to search for"),
    current_user: User = Depends(get_current_user),
):
    query = q.strip()
    if len(query) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=LOCATION_SEARCH_INVALID_QUERY,
        )

    http_client = getattr(request.app.state, "http_text_search", None)
    client = GoogleTextSearchClient(http_client=http_client)

    try:
        places = await client.search_text(
            text_query=query,
            max_result_count=8,
        )
    except (
        GooglePlacesAPIError,
        GooglePlacesRateLimitError,
        GooglePlacesTimeoutError,
    ):
        logger.exception(
            "Location search failed — user_id: %s, query: %r",
            current_user.id,
            query,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=LOCATION_SEARCH_FAILED,
        )

    results = [
        LocationSearchResult(
            name=place.display_name,
            address=place.formatted_address,
            latitude=place.latitude,
            longitude=place.longitude,
        )
        for place in places
        if place.display_name
        and place.latitude is not None
        and place.longitude is not None
    ]

    return LocationSearchResponse(results=results)

@router.post("/manual", response_model=APIResponse)
@limiter.limit("60/minute")
async def set_manual_location(
    request: Request,
    payload: ManualLocationRequest,
    current_user: User = Depends(get_current_user),
    service: LocationService = Depends(_service),
):
    try:
        location, is_new = service.process_manual_location(current_user.id, payload)

        message = ("Manual location set successfully"
            if is_new
            else "Location unchanged — duplicate update acknowledged")
        return APIResponse(
            success=True,
            message=message,
            data=UnifiedLocationResponse(
                latitude=location.latitude,
                longitude=location.longitude,
                accuracy=location.accuracy,
                location_type=location.source,
                address=location.address,
                updated_at=location.updated_at or location.created_at,
            ),
        )
    except ValueError as e:
        if "Too many manual location updates" in str(e):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=LOCATION_MANUAL_RATE_LIMIT,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=LOCATION_UPDATE_FAILED,
        )



@router.post("/reverse-geocode", response_model=APIResponse, summary="Reverse geocode")
@limiter.limit("30/minute")
async def reverse_geocode(
    request: Request,
    payload: ReverseGeocodeRequest,
    current_user: User = Depends(get_current_user),
):
    http_client = getattr(request.app.state, "http_geocoding", None)
    client = GoogleGeocodingClient(http_client=http_client)
    service = GeocodingService(client)

    try:
        result = await service.reverse_geocode(
            latitude=payload.latitude,
            longitude=payload.longitude,
            language_code=payload.language_code,
        )
    except (
        GooglePlacesAPIError,
        GooglePlacesRateLimitError,
        GooglePlacesTimeoutError,
    ):
        logger.exception(
            "Reverse geocode failed — user_id: %s, lat: %.6f, lon: %.6f",
            current_user.id,
            payload.latitude,
            payload.longitude,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=LOCATION_GEOCODING_FAILED,
        )

    return APIResponse(
        success=True,
        message="Address resolved successfully",
        data=ReverseGeocodeResponse(
            latitude=result["latitude"],
            longitude=result["longitude"],
            address=result["address"],
        ),
    )

@router.get("/history", response_model=APIResponse)
async def get_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    source: str | None = Query(default=None, description="Filter by source: 'gps' or 'manual'"),
    current_user: User = Depends(get_current_user),
    service: LocationService = Depends(_service),
):
    try:
        items, total = service.get_location_history(current_user.id, page, page_size, source=source)
    except ValueError as e:
        logger.error(
            "Location history error for user=%s: %s",
            current_user.id,
            e,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=LOCATION_HISTORY_ERROR,
        )
    
    history_items = [
        LocationHistoryItem(
            id=item.id,
            latitude=item.latitude,
            longitude=item.longitude,
            accuracy=item.accuracy,
            location_type=item.source,
            created_at=item.created_at,
        )
        for item in items
    ]

    return APIResponse(
        success=True,
        message="Location history retrieved",
        data=PaginatedHistoryResponse(
            items=history_items,
            total=total,
            page=page,
            page_size=page_size,
            has_next=(page * page_size) < total,
        ),
    )


@router.get("/latest", response_model=APIResponse)
async def get_latest(
    current_user: User = Depends(get_current_user),
    service: LocationService = Depends(_service),
):
    location = service.get_latest_location(current_user.id)
    return APIResponse(
        success=True,
        message="Latest location retrieved",
        data=UnifiedLocationResponse(
            latitude=location.latitude,
            longitude=location.longitude,
            accuracy=location.accuracy,
            location_type=location.source,
            address=location.address,
            updated_at=location.updated_at or location.created_at,
        ),
    )

@router.delete("/delete", response_model=APIResponse)
async def delete_location(
    history_id: int | None = Query(default=None, ge=1),
    current_user: User = Depends(get_current_user),
    service: LocationService = Depends(_service),
):
    message = service.delete_location(current_user.id, history_id)
    return APIResponse(success=True, message=message)


