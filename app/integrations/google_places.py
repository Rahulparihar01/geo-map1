import logging
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.integrations.google_base import GoogleAPIClientBase, parse_google_place
from app.schemas.discovery import DiscoveryPlaceResult

logger = logging.getLogger(__name__)

_FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.rating",
        "places.userRatingCount",
        "places.primaryType",
        "places.types",
        "places.googleMapsUri",
        "places.businessStatus",
        "places.priceLevel",
        "places.currentOpeningHours.openNow",
        "places.photos",
    ]
)


def _sanitize_place_types(types: Optional[List[str]], field_name: str) -> List[str]:
    if not types:
        return []

    if isinstance(types, str):
        types = types.split(",")

    sanitized = [
        place_type.strip()
        for place_type in types
        if isinstance(place_type, str)
        and place_type.strip()
        and place_type.strip().lower() != "string"
    ]
    if len(sanitized) != len(types):
        logger.warning(
            "Ignoring placeholder or invalid %s value before Google request: %s",
            field_name,
            types,
        )
    return sanitized


class GooglePlacesClient(GoogleAPIClientBase):

    def _get_url(self) -> str:
        return f"{settings.GOOGLE_PLACES_BASE_URL}/places:searchNearby"

    def _get_field_mask(self) -> str:
        return _FIELD_MASK

    def _build_payload(
        self,
        latitude: float,
        longitude: float,
        radius: float,
        max_result_count: int,
        included_types: Optional[List[str]] = None,
        excluded_types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        payload = {
            "maxResultCount": max_result_count,
            "locationRestriction": {
                "circle": {
                    "center": {
                        "latitude": latitude,
                        "longitude": longitude,
                    },
                    "radius": radius,
                }
            },
            "languageCode": "en",
        }

        included_types = _sanitize_place_types(included_types, "includedTypes")
        if included_types:
            payload["includedTypes"] = included_types
            logger.debug("Added includedTypes to payload: %s", included_types)

        # Google rejects requests that put a type in both includedTypes and
        # excludedTypes, so only one of the two is ever set per request.
        excluded_types = _sanitize_place_types(excluded_types, "excludedTypes")
        if excluded_types:
            payload["excludedTypes"] = excluded_types
            logger.debug("Added excludedTypes to payload: %s", excluded_types)

        return payload

    async def search_nearby(
        self,
        latitude: float,
        longitude: float,
        radius: float,
        max_result_count: int,
        included_types: Optional[List[str]] = None,
        excluded_types: Optional[List[str]] = None,
    ) -> List[DiscoveryPlaceResult]:
        payload = self._build_payload(
            latitude,
            longitude,
            radius,
            max_result_count,
            included_types,
            excluded_types,
        )

        logger.info(
            "Google Places API call — lat: %s, lon: %s, radius: %sm, max: %s, included: %s, excluded: %s",
            latitude,
            longitude,
            radius,
            max_result_count,
            included_types if included_types else "all",
            excluded_types if excluded_types else "none",
        )

        data = await self._execute_request(payload, context="Nearby Search")
        places_raw = data.get("places", [])
        logger.info("Google Places API returned %d results", len(places_raw))
        return [parse_google_place(p) for p in places_raw]
