import logging
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings
from app.exceptions.places import (
    GooglePlacesAPIError,
    GooglePlacesRateLimitError,
    GooglePlacesTimeoutError,
)
from app.integrations.google_base import _trace_langfuse_span

logger = logging.getLogger(__name__)


class GoogleGeocodingClient:
    """Client for the Google Geocoding API (reverse geocoding)."""

    def __init__(self, http_client: Optional[httpx.AsyncClient] = None) -> None:
        self.api_key = settings.GOOGLE_PLACES_API_KEY
        self.base_url = settings.GOOGLE_GEOCODING_BASE_URL
        self._http_client = http_client
        self._timeout = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)

    async def reverse_geocode(
        self,
        latitude: float,
        longitude: float,
        language_code: str = "en",
    ) -> Dict[str, Any]:
        """
        Call the Google Geocoding API to reverse-geocode coordinates.

        Returns the raw JSON response from the provider.
        Raises GooglePlacesAPIError, GooglePlacesRateLimitError, or
        GooglePlacesTimeoutError on failure.
        """
        url = f"{self.base_url}/json"
        params = {
            "latlng": f"{latitude},{longitude}",
            "key": self.api_key,
            "language": language_code,
        }

        logger.info(
            "Google Geocoding reverse geocode — lat: %.6f, lon: %.6f, lang: %s",
            latitude,
            longitude,
            language_code,
        )

        async def _do_request(client: httpx.AsyncClient) -> httpx.Response:
            return await client.get(url, params=params)

        try:
            if self._http_client is not None:
                response = await _do_request(self._http_client)
            else:
                logger.warning(
                    "GoogleGeocodingClient: No shared HTTP client — "
                    "creating per-request client (should only happen in tests)."
                )
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await _do_request(client)

        except httpx.TimeoutException:
            _trace_langfuse_span("reverse-geocode", success=False, error="timeout")
            logger.error("Google Geocoding API request timed out")
            raise GooglePlacesTimeoutError()

        except Exception as exc:
            _trace_langfuse_span(
                "reverse-geocode", success=False, error=str(exc)[:200]
            )
            logger.error("Google Geocoding API unexpected error: %s", exc)
            raise GooglePlacesAPIError(
                "Something went wrong while resolving the address. Please try again."
            )

        data = await self._check_response(response)
        _trace_langfuse_span("reverse-geocode", success=True)
        return data

    async def _check_response(self, response: httpx.Response) -> Dict[str, Any]:
        """Validate the HTTP response and return parsed JSON."""
        if response.status_code == 429:
            logger.warning("Google Geocoding API rate limit hit")
            raise GooglePlacesRateLimitError()

        if response.status_code == 403:
            logger.error(
                "Google Geocoding API forbidden — check API key and billing: %s",
                response.text[:500],
            )
            raise GooglePlacesAPIError(
                "We couldn't complete your request. Please try again."
            )

        if response.status_code != 200:
            error_body = response.text[:1000] if response.text else "No response body"
            logger.error(
                "Google Geocoding API error — status %s: %s",
                response.status_code,
                error_body,
            )
            raise GooglePlacesAPIError(
                "The address service is temporarily unavailable. Please try again later.",
                provider_status_code=response.status_code,
            )

        try:
            data = response.json()
        except Exception as exc:
            logger.error("Failed to parse Google Geocoding response: %s", exc)
            raise GooglePlacesAPIError(
                "We received an invalid response from the address service. Please try again."
            )

        # Check the API-level status field
        status = data.get("status", "")
        if status == "OK":
            return data
        if status == "ZERO_RESULTS":
            # Return the data as-is; the caller decides how to handle no results
            return data
        if status == "OVER_QUERY_LIMIT":
            logger.warning("Google Geocoding API quota exceeded")
            raise GooglePlacesRateLimitError()

        logger.error("Google Geocoding API returned status: %s", status)
        raise GooglePlacesAPIError(
            "Unable to resolve coordinates to an address. Please try again.",
            provider_status_code=None,
        )
