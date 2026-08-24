import logging
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.exceptions.places import (
    GooglePlacesAPIError,
    GooglePlacesRateLimitError,
    GooglePlacesTimeoutError,
)
from app.schemas.discovery import DiscoveryPlaceResult

logger = logging.getLogger(__name__)


def parse_google_place(raw: Dict[str, Any]) -> DiscoveryPlaceResult:
    location = raw.get("location", {})
    display_name_obj = raw.get("displayName", {})
    opening_hours = raw.get("currentOpeningHours", {})

    photos_raw: List[Dict[str, Any]] = raw.get("photos", [])
    first_photo_name = None
    if photos_raw and isinstance(photos_raw, list) and len(photos_raw) > 0:
        first_photo = photos_raw[0]
        if isinstance(first_photo, dict):
            first_photo_name = first_photo.get("name")

    return DiscoveryPlaceResult(
        place_id=raw.get("id"),
        display_name=(
            display_name_obj.get("text")
            if isinstance(display_name_obj, dict)
            else display_name_obj
        ),
        formatted_address=raw.get("formattedAddress"),
        latitude=location.get("latitude"),
        longitude=location.get("longitude"),
        rating=raw.get("rating"),
        user_rating_count=raw.get("userRatingCount"),
        primary_type=raw.get("primaryType"),
        types=raw.get("types"),
        business_status=raw.get("businessStatus"),
        google_maps_uri=raw.get("googleMapsUri"),
        open_now=opening_hours.get("openNow") if opening_hours else None,
        price_level=raw.get("priceLevel"),
        first_photo_name=first_photo_name,
    )


def _trace_langfuse_span(context: str, success: bool, error: str = None) -> None:
    try:
        from langfuse import get_client
        output = {"success": success}
        if error:
            output["error"] = error
        get_client().span(
            name=f"google-{context}" if context else "google-api",
            input={"provider": "google", "endpoint": context},
            output=output,
            level="ERROR" if error else "DEFAULT",
        )
    except Exception:
        pass


class GoogleAPIClientBase:
    def __init__(self, http_client: Optional[httpx.AsyncClient] = None) -> None:
        self.api_key = settings.GOOGLE_PLACES_API_KEY
        self._http_client = http_client
        self._timeout = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)

    def _get_url(self) -> str:
        raise NotImplementedError("Subclass must implement _get_url()")

    def _get_field_mask(self) -> str:
        raise NotImplementedError("Subclass must implement _get_field_mask()")

    def _build_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": self._get_field_mask(),
        }

    async def _do_request(self, payload: Dict, headers: Dict) -> httpx.Response:
        url = self._get_url()
        if self._http_client is not None:
            return await self._http_client.post(url, json=payload, headers=headers)

        logger.warning(
            "%s: No shared HTTP client - creating per-request client. "
            "This should only happen in tests.",
            self.__class__.__name__,
        )
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await client.post(url, json=payload, headers=headers)

    async def _check_response(self, response: httpx.Response, context: str = "") -> Dict[str, Any]:
        if response.status_code == 429:
            logger.warning("Google API rate limit hit %s", context)
            raise GooglePlacesRateLimitError()

        if response.status_code == 403:
            logger.error(
                "Google API forbidden %s — check API key and billing: %s",
                context,
                response.text[:500],
            )
            raise GooglePlacesAPIError(
                "We couldn't complete your request. Please try again."
            )

        if response.status_code != 200:
            error_body = response.text[:1000] if response.text else "No response body"
            logger.error(
                "Google API error %s status %s: %s",
                context,
                response.status_code,
                error_body,
            )

            raise GooglePlacesAPIError(
                "The search service is temporarily unavailable. Please try again later.",
                provider_status_code=response.status_code,
            )

        try:
            return response.json()
        except Exception as exc:
            logger.error("Failed to parse Google API response %s: %s", context, exc)
            raise GooglePlacesAPIError(
                "We received an invalid response from the search service. Please try again."
            )

    async def _execute_request(
        self,
        payload: Dict,
        context: str = "",
    ) -> Dict[str, Any]:
        headers = self._build_headers()

        try:
            response = await self._do_request(payload, headers)
            result = await self._check_response(response, context)
            _trace_langfuse_span(context, success=True)
            return result
        except httpx.TimeoutException:
            _trace_langfuse_span(context, success=False, error="timeout")
            logger.error("Google API request timeout %s", context)
            raise GooglePlacesTimeoutError()
        except (
            GooglePlacesAPIError,
            GooglePlacesRateLimitError,
            GooglePlacesTimeoutError,
        ):
            _trace_langfuse_span(context, success=False, error="api_error")
            raise
        except Exception as exc:
            _trace_langfuse_span(context, success=False, error=str(exc)[:200])
            logger.error("Unexpected error calling Google API %s: %s", context, exc)
            raise GooglePlacesAPIError(
                "Something went wrong while searching. Please try again."
            )
