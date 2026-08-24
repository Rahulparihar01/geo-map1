import logging
from typing import Any, Dict, List, Optional

from app.exceptions.places import (
    GooglePlacesAPIError,
    GooglePlacesRateLimitError,
    GooglePlacesTimeoutError,
)
from app.integrations.google_geocoding import GoogleGeocodingClient

logger = logging.getLogger(__name__)

# Address component types we care about, in priority order
_COMPONENT_TYPES_NEIGHBORHOOD = {"neighborhood", "sublocality", "sublocality_level_1"}
_COMPONENT_TYPES_CITY = {"locality"}
_COMPONENT_TYPES_DISTRICT = {
    "administrative_area_level_2",
    "administrative_area_level_3",
}
_COMPONENT_TYPES_STATE = {"administrative_area_level_1"}


class GeocodingService:
    def __init__(self, geocoding_client: GoogleGeocodingClient) -> None:
        self._client = geocoding_client

    async def reverse_geocode(
        self,
        latitude: float,
        longitude: float,
        language_code: str = "en",
    ) -> Dict[str, Any]:
        try:
            data = await self._client.reverse_geocode(
                latitude=latitude,
                longitude=longitude,
                language_code=language_code,
            )
        except (GooglePlacesAPIError, GooglePlacesTimeoutError, GooglePlacesRateLimitError):
            raise
        except Exception as exc:
            logger.error("Unexpected error during reverse geocode: %s", exc)
            raise GooglePlacesAPIError(
                "Unable to resolve coordinates to an address. Please try again."
            )

        address = self._build_medium_address(data)

        if not address:
            logger.warning(
                "No address components found for lat=%.6f, lon=%.6f",
                latitude,
                longitude,
            )
            raise GooglePlacesAPIError(
                "Unable to resolve coordinates to an address. Please try again."
            )

        return {
            "latitude": latitude,
            "longitude": longitude,
            "address": address,
        }

    # ------------------------------------------------------------------
    # Address building logic
    # ------------------------------------------------------------------

    def _build_medium_address(self, data: Dict[str, Any]) -> Optional[str]:
        results = data.get("results", [])
        if not results:
            return None

        first_result = results[0]
        components: List[Dict[str, Any]] = first_result.get("address_components", [])

        type_map = self._build_type_map(components)
        neighbourhood = self._pick_first(type_map, _COMPONENT_TYPES_NEIGHBORHOOD)
        city = self._pick_first(type_map, _COMPONENT_TYPES_CITY)
        state = self._pick_first(type_map, _COMPONENT_TYPES_STATE)
        district = self._pick_first(type_map, _COMPONENT_TYPES_DISTRICT)

        # Strategy 1: neighbourhood + city + state
        if neighbourhood and city and state:
            return self._deduplicate_and_join([neighbourhood, city, state])

        # Strategy 2: city + state
        if city and state:
            return self._deduplicate_and_join([city, state])

        # Strategy 3: district + state
        if district and state:
            return self._deduplicate_and_join([district, state])

        # Strategy 4: any available combination with state
        if state:
            parts = [p for p in [neighbourhood, city, district] if p]
            if parts:
                return self._deduplicate_and_join([parts[0], state])

        # Strategy 5: just city if available
        if city:
            return city

        return None

    @staticmethod
    def _build_type_map(
        components: List[Dict[str, Any]],
    ) -> Dict[str, List[str]]:
        type_map: Dict[str, List[str]] = {}
        for comp in components:
            short_name = comp.get("short_name", "")
            long_name = comp.get("long_name", "")
            display = long_name or short_name
            if not display:
                continue
            for comp_type in comp.get("types", []):
                type_map.setdefault(comp_type, []).append(display)
        return type_map

    @staticmethod
    def _pick_first(
        type_map: Dict[str, List[str]], type_set: set
    ) -> Optional[str]:
        for comp_type in type_set:
            values = type_map.get(comp_type, [])
            if values:
                return values[0]
        return None

    @staticmethod
    def _deduplicate_and_join(parts: List[str]) -> str:
        seen: set = set()
        unique: List[str] = []
        for part in parts:
            normalized = part.strip().lower()
            if normalized not in seen:
                seen.add(normalized)
                unique.append(part.strip())
        return ", ".join(unique)
