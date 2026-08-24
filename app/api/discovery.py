import logging
from fastapi import APIRouter, Depends, Query
from app.dependencies.auth import get_current_user
from app.dependencies.discovery import get_discovery_service
from app.exceptions.places import (
    GooglePlacesAPIError,
    GooglePlacesRateLimitError,
    GooglePlacesTimeoutError,
)
from app.models.user import User
from app.schemas.discovery import (
    AutocompleteResponse,
    AutocompletePrediction,
    DiscoveryCategory,
    NearbyDiscoveryRequest,
    NearbyDiscoveryResponse,
    TextSearchRequest,
    TextSearchResponse,
)
from app.services.discovery_service import DiscoveryService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/discovery", tags=["Discovery"])


@router.post("/search", response_model=TextSearchResponse)
async def text_search(
    payload: TextSearchRequest,
    current_user: User = Depends(get_current_user),
    service: DiscoveryService = Depends(get_discovery_service),
) -> TextSearchResponse:
    logger.info(
        "Text Search — user_id: %s, query: %r, max: %s",
        current_user.id,
        payload.text_query,
        payload.max_result_count,
    )

    places, from_cache, lat, lon = await service.text_search(
        request=payload,
        user_id=current_user.id,
    )

    return TextSearchResponse(
        success=True,
        search_mode="text",
        message="Text search completed successfully",
        data=places,
        total_results=len(places),
        cached=from_cache,
        query=payload.text_query,
        search_latitude=lat,
        search_longitude=lon,
    )


@router.post("/nearby", response_model=NearbyDiscoveryResponse)
async def nearby_search(
    payload: NearbyDiscoveryRequest,
    current_user: User = Depends(get_current_user),
    service: DiscoveryService = Depends(get_discovery_service),
) -> NearbyDiscoveryResponse:
    logger.info(
        "Nearby Discovery — user_id: %s, category: %s, subcategories: %s, radius: %sm, max: %s",
        current_user.id,
        payload.category.value,
        payload.subcategory_display,
        payload.radius,
        payload.max_result_count,
    )

    try:
        places, from_cache, lat, lon = await service.nearby_search(
            request=payload,
            user_id=current_user.id,
        )
    except (
        GooglePlacesAPIError,
        GooglePlacesRateLimitError,
        GooglePlacesTimeoutError,
    ) as exc:
        if payload.category != DiscoveryCategory.PARKING:
            raise
        logger.warning(
            "Parking nearby search failed — user_id: %s (%s)",
            current_user.id,
            type(exc).__name__,
        )
        raise type(exc)("Unable to find parking places. Please try again.") from exc

    return NearbyDiscoveryResponse(
        success=True,
        search_mode="nearby",
        message="Nearby search completed successfully",
        data=places,
        total_results=len(places),
        cached=from_cache,
        search_latitude=lat,
        search_longitude=lon,
    )


@router.get("/autocomplete", response_model=AutocompleteResponse)
async def autocomplete(
    input: str = Query(..., min_length=1, max_length=200),
    included_primary_types: str | None = Query(default=None),
    language_code: str = Query(default="en", max_length=10),
    use_user_location_bias: bool = Query(default=True),
    current_user: User = Depends(get_current_user),
    service: DiscoveryService = Depends(get_discovery_service),
) -> AutocompleteResponse:
    logger.info(
        "Autocomplete request — user_id: %s, input: %r",
        current_user.id,
        input,
    )

    predictions_raw, from_cache, bias_lat, bias_lon = await service.autocomplete(
        input_text=input,
        user_id=current_user.id,
        included_primary_types=[t.strip() for t in included_primary_types.split(",") if t.strip()] if included_primary_types else None,
        language_code=language_code,
        use_user_location_bias=use_user_location_bias,
    )

    predictions = [AutocompletePrediction(**p) for p in predictions_raw]

    return AutocompleteResponse(
        success=True,
        message="Autocomplete completed successfully",
        input=input,
        predictions=predictions,
        total_predictions=len(predictions),
        cached=from_cache,
        bias_latitude=bias_lat,
        bias_longitude=bias_lon,
    )
