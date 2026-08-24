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
        "places.businessStatus",
        "places.googleMapsUri",
        "places.currentOpeningHours.openNow",
        "places.priceLevel",
        "places.photos",
    ]
)


class GoogleTextSearchClient(GoogleAPIClientBase):

    def _get_url(self) -> str:
        return f"{settings.GOOGLE_PLACES_BASE_URL}/places:searchText"

    def _get_field_mask(self) -> str:
        return _FIELD_MASK

    def _build_payload(
        self,
        text_query: str,
        max_result_count: int,
        open_now: Optional[bool],
        location_bias_lat: Optional[float],
        location_bias_lon: Optional[float],
        location_bias_radius: Optional[float],
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "textQuery": text_query,
            "maxResultCount": max_result_count,
        }
        if open_now is not None:
            payload["openNow"] = open_now
        if location_bias_lat is not None and location_bias_lon is not None:
            radius = location_bias_radius or 5000.0
            payload["locationBias"] = {
                "circle": {
                    "center": {
                        "latitude": location_bias_lat,
                        "longitude": location_bias_lon,
                    },
                    "radius": radius,
                }
            }
        return payload

    async def search_text(
        self,
        text_query: str,
        max_result_count: int = 20,
        open_now: Optional[bool] = None,
        location_bias_lat: Optional[float] = None,
        location_bias_lon: Optional[float] = None,
        location_bias_radius: Optional[float] = None,
    ) -> List[DiscoveryPlaceResult]:
        payload = self._build_payload(
            text_query=text_query,
            max_result_count=max_result_count,
            open_now=open_now,
            location_bias_lat=location_bias_lat,
            location_bias_lon=location_bias_lon,
            location_bias_radius=location_bias_radius,
        )

        logger.info(
            "Google Text Search — query: %r, max: %s, bias: (%s, %s) r=%s",
            text_query,
            max_result_count,
            location_bias_lat,
            location_bias_lon,
            location_bias_radius,
        )

        data = await self._execute_request(payload, context="Text Search")
        places_raw = data.get("places", [])
        logger.info(
            "Google Text Search returned %d results for query %r",
            len(places_raw),
            text_query,
        )
        return [parse_google_place(p) for p in places_raw]
