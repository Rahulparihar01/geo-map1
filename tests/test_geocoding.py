"""
Tests for the reverse geocoding feature.

Covers:
- Schema validation (latitude, longitude bounds)
- GeocodingService address building logic (various component combinations)
- GoogleGeocodingClient response handling
- Edge cases: no results, duplicates, missing components
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.schemas.location import ReverseGeocodeRequest, ReverseGeocodeResponse
from app.services.geocoding_service import GeocodingService
from app.integrations.google_geocoding import GoogleGeocodingClient
from app.exceptions.places import (
    GooglePlacesAPIError,
    GooglePlacesRateLimitError,
    GooglePlacesTimeoutError,
)


# ─── Schema Tests ──────────────────────────────────────────────────────────


class TestReverseGeocodeRequest:
    def test_valid_coordinates(self):
        req = ReverseGeocodeRequest(latitude=22.0797, longitude=82.1391)
        assert req.latitude == 22.0797
        assert req.longitude == 82.1391
        assert req.language_code == "en"

    def test_valid_coordinates_negative(self):
        req = ReverseGeocodeRequest(latitude=-33.8688, longitude=151.2093)
        assert req.latitude == -33.8688
        assert req.longitude == 151.2093

    def test_custom_language(self):
        req = ReverseGeocodeRequest(latitude=28.6139, longitude=77.209, language_code="hi")
        assert req.language_code == "hi"

    def test_invalid_latitude_too_high(self):
        with pytest.raises(Exception):
            ReverseGeocodeRequest(latitude=91.0, longitude=0.0)

    def test_invalid_latitude_too_low(self):
        with pytest.raises(Exception):
            ReverseGeocodeRequest(latitude=-91.0, longitude=0.0)

    def test_invalid_longitude_too_high(self):
        with pytest.raises(Exception):
            ReverseGeocodeRequest(latitude=0.0, longitude=181.0)

    def test_invalid_longitude_too_low(self):
        with pytest.raises(Exception):
            ReverseGeocodeRequest(latitude=0.0, longitude=-181.0)

    def test_boundary_values(self):
        req = ReverseGeocodeRequest(latitude=90.0, longitude=180.0)
        assert req.latitude == 90.0
        assert req.longitude == 180.0

        req2 = ReverseGeocodeRequest(latitude=-90.0, longitude=-180.0)
        assert req2.latitude == -90.0
        assert req2.longitude == -180.0


class TestReverseGeocodeResponse:
    def test_response_model(self):
        resp = ReverseGeocodeResponse(
            latitude=22.0797, longitude=82.1391, address="Mangla Chowk, Bilaspur, Chhattisgarh"
        )
        assert resp.latitude == 22.0797
        assert resp.longitude == 82.1391
        assert resp.address == "Mangla Chowk, Bilaspur, Chhattisgarh"


# ─── Helper to build mock geocoding responses ──────────────────────────────


def _build_geocoding_response(components: list[dict]) -> dict:
    """Build a mock Google Geocoding API response."""
    return {
        "status": "OK",
        "results": [
            {
                "address_components": components,
                "formatted_address": "Mock Address",
            }
        ],
    }


def _make_component(short_name: str, long_name: str, types: list[str]) -> dict:
    return {
        "long_name": long_name,
        "short_name": short_name,
        "types": types,
    }


# ─── GeocodingService Address Building Tests ───────────────────────────────

class TestGeocodingServiceAddressBuilding:

    def _get_service(self) -> GeocodingService:
        mock_client = MagicMock(spec=GoogleGeocodingClient)
        return GeocodingService(mock_client)

    def test_full_address_neighbourhood_city_state(self):
        """Primary: neighbourhood + city + state."""
        service = self._get_service()
        data = _build_geocoding_response([
            _make_component("Mangla Chowk", "Mangla Chowk", ["neighborhood"]),
            _make_component("Bilaspur", "Bilaspur", ["locality"]),
            _make_component("Chhattisgarh", "Chhattisgarh", ["administrative_area_level_1"]),
        ])
        address = service._build_medium_address(data)
        assert address == "Mangla Chowk, Bilaspur, Chhattisgarh"

    def test_fallback_sublocality(self):
        """Fallback: sublocality when neighbourhood is missing."""
        service = self._get_service()
        data = _build_geocoding_response([
            _make_component("Zone 1", "Zone 1", ["sublocality", "sublocality_level_1"]),
            _make_component("Raipur", "Raipur", ["locality"]),
            _make_component("Chhattisgarh", "Chhattisgarh", ["administrative_area_level_1"]),
        ])
        address = service._build_medium_address(data)
        assert address == "Zone 1, Raipur, Chhattisgarh"

    def test_fallback_city_state(self):
        """Fallback: city + state when neighbourhood is missing."""
        service = self._get_service()
        data = _build_geocoding_response([
            _make_component("Mumbai", "Mumbai", ["locality"]),
            _make_component("Maharashtra", "Maharashtra", ["administrative_area_level_1"]),
        ])
        address = service._build_medium_address(data)
        assert address == "Mumbai, Maharashtra"

    def test_fallback_district_state(self):
        """Fallback: district + state when no neighbourhood or city."""
        service = self._get_service()
        data = _build_geocoding_response([
            _make_component("Bilaspur", "Bilaspur", ["administrative_area_level_2"]),
            _make_component("Chhattisgarh", "Chhattisgarh", ["administrative_area_level_1"]),
        ])
        address = service._build_medium_address(data)
        assert address == "Bilaspur, Chhattisgarh"

    def test_fallback_state_only_with_other(self):
        """Fallback: state + available component when no city."""
        service = self._get_service()
        data = _build_geocoding_response([
            _make_component("Some Area", "Some Area", ["neighborhood"]),
            _make_component("Karnataka", "Karnataka", ["administrative_area_level_1"]),
        ])
        address = service._build_medium_address(data)
        assert address == "Some Area, Karnataka"

    def test_fallback_city_only(self):
        """Fallback: just city when no state."""
        service = self._get_service()
        data = _build_geocoding_response([
            _make_component("Delhi", "Delhi", ["locality"]),
        ])
        address = service._build_medium_address(data)
        assert address == "Delhi"

    def test_duplicate_components_removed(self):
        """Duplicate components (case-insensitive) should be deduplicated."""
        service = self._get_service()
        data = _build_geocoding_response([
            _make_component("Bilaspur", "Bilaspur", ["locality"]),
            _make_component("Bilaspur", "Bilaspur", ["administrative_area_level_2"]),
            _make_component("Chhattisgarh", "Chhattisgarh", ["administrative_area_level_1"]),
        ])
        address = service._build_medium_address(data)
        # Should not have "Bilaspur, Bilaspur"
        assert address == "Bilaspur, Chhattisgarh"

    def test_duplicate_case_insensitive(self):
        """Duplicates should be case-insensitive."""
        service = self._get_service()
        data = _build_geocoding_response([
            _make_component("bilaspur", "BILASPUR", ["locality"]),
            _make_component("Bilaspur", "Bilaspur", ["administrative_area_level_2"]),
            _make_component("Chhattisgarh", "Chhattisgarh", ["administrative_area_level_1"]),
        ])
        address = service._build_medium_address(data)
        assert address == "BILASPUR, Chhattisgarh"

    def test_no_results_returns_none(self):
        """No results at all → None."""
        service = self._get_service()
        data = {"status": "ZERO_RESULTS", "results": []}
        address = service._build_medium_address(data)
        assert address is None

    def test_empty_components_returns_none(self):
        """Results exist but no address components → None."""
        service = self._get_service()
        data = _build_geocoding_response([])
        address = service._build_medium_address(data)
        assert address is None

    def test_only_neighbourhood_returns_none(self):
        """Only neighbourhood without city/state → None (can't form meaningful address)."""
        service = self._get_service()
        data = _build_geocoding_response([
            _make_component("Some Place", "Some Place", ["neighborhood"]),
        ])
        address = service._build_medium_address(data)
        assert address is None


# ─── GeocodingService Async Tests ──────────────────────────────────────────


class TestGeocodingServiceAsync:
    @pytest.mark.asyncio
    async def test_success_calls_client(self):
        """Service calls the client and returns formatted result."""
        mock_client = AsyncMock(spec=GoogleGeocodingClient)
        mock_client.reverse_geocode.return_value = {
            "status": "OK",
            "results": [{
                "address_components": [
                    _make_component("MG Road", "MG Road", ["neighborhood"]),
                    _make_component("Bangalore", "Bangalore", ["locality"]),
                    _make_component("Karnataka", "Karnataka", ["administrative_area_level_1"]),
                ],
            }],
        }
        service = GeocodingService(mock_client)
        result = await service.reverse_geocode(latitude=12.9716, longitude=77.5946)
        assert result["latitude"] == 12.9716
        assert result["longitude"] == 77.5946
        assert result["address"] == "MG Road, Bangalore, Karnataka"
        mock_client.reverse_geocode.assert_called_once_with(
            latitude=12.9716, longitude=77.5946, language_code="en"
        )

    @pytest.mark.asyncio
    async def test_no_address_raises_error(self):
        """Service raises GooglePlacesAPIError when no address can be built."""
        mock_client = AsyncMock(spec=GoogleGeocodingClient)
        mock_client.reverse_geocode.return_value = {
            "status": "ZERO_RESULTS",
            "results": [],
        }
        service = GeocodingService(mock_client)
        with pytest.raises(GooglePlacesAPIError):
            await service.reverse_geocode(latitude=0.0, longitude=0.0)

    @pytest.mark.asyncio
    async def test_client_timeout_propagates(self):
        """Timeout from client propagates through the service."""
        mock_client = AsyncMock(spec=GoogleGeocodingClient)
        mock_client.reverse_geocode.side_effect = GooglePlacesTimeoutError()
        service = GeocodingService(mock_client)
        with pytest.raises(GooglePlacesTimeoutError):
            await service.reverse_geocode(latitude=22.0797, longitude=82.1391)

    @pytest.mark.asyncio
    async def test_client_rate_limit_propagates(self):
        """Rate limit from client propagates through the service."""
        mock_client = AsyncMock(spec=GoogleGeocodingClient)
        mock_client.reverse_geocode.side_effect = GooglePlacesRateLimitError()
        service = GeocodingService(mock_client)
        with pytest.raises(GooglePlacesRateLimitError):
            await service.reverse_geocode(latitude=22.0797, longitude=82.1391)

    @pytest.mark.asyncio
    async def test_client_api_error_propagates(self):
        """API error from client propagates through the service."""
        mock_client = AsyncMock(spec=GoogleGeocodingClient)
        mock_client.reverse_geocode.side_effect = GooglePlacesAPIError("Some error")
        service = GeocodingService(mock_client)
        with pytest.raises(GooglePlacesAPIError):
            await service.reverse_geocode(latitude=22.0797, longitude=82.1391)

    @pytest.mark.asyncio
    async def test_unexpected_exception_wrapped(self):
        """Unexpected exceptions are wrapped in GooglePlacesAPIError."""
        mock_client = AsyncMock(spec=GoogleGeocodingClient)
        mock_client.reverse_geocode.side_effect = RuntimeError("something broke")
        service = GeocodingService(mock_client)
        with pytest.raises(GooglePlacesAPIError):
            await service.reverse_geocode(latitude=22.0797, longitude=82.1391)


# ─── GoogleGeocodingClient Tests ───────────────────────────────────────────


class TestGoogleGeocodingClient:
    @pytest.mark.asyncio
    async def test_successful_reverse_geocode(self):
        """Client returns parsed JSON on 200 OK with status=OK."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "OK",
            "results": [{
                "address_components": [
                    _make_component("MG Road", "MG Road", ["neighborhood"]),
                    _make_component("Bangalore", "Bangalore", ["locality"]),
                    _make_component("Karnataka", "Karnataka", ["administrative_area_level_1"]),
                ],
            }],
        }
        mock_response.text = ""

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)

        with patch("app.integrations.google_geocoding.settings") as mock_settings:
            mock_settings.GOOGLE_PLACES_API_KEY = "test-key"
            mock_settings.GOOGLE_GEOCODING_BASE_URL = "https://maps.googleapis.com/maps/api/geocode"
            client = GoogleGeocodingClient(http_client=mock_http)
            result = await client.reverse_geocode(12.9716, 77.5946)

        assert result["status"] == "OK"
        assert len(result["results"]) == 1

    @pytest.mark.asyncio
    async def test_rate_limit_raises(self):
        """429 status raises GooglePlacesRateLimitError."""
        mock_response = AsyncMock()
        mock_response.status_code = 429
        mock_response.text = ""

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)

        with patch("app.integrations.google_geocoding.settings") as mock_settings:
            mock_settings.GOOGLE_PLACES_API_KEY = "test-key"
            mock_settings.GOOGLE_GEOCODING_BASE_URL = "https://maps.googleapis.com/maps/api/geocode"
            client = GoogleGeocodingClient(http_client=mock_http)
            with pytest.raises(GooglePlacesRateLimitError):
                await client.reverse_geocode(12.9716, 77.5946)

    @pytest.mark.asyncio
    async def test_forbidden_raises(self):
        """403 status raises GooglePlacesAPIError."""
        mock_response = AsyncMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)

        with patch("app.integrations.google_geocoding.settings") as mock_settings:
            mock_settings.GOOGLE_PLACES_API_KEY = "test-key"
            mock_settings.GOOGLE_GEOCODING_BASE_URL = "https://maps.googleapis.com/maps/api/geocode"
            client = GoogleGeocodingClient(http_client=mock_http)
            with pytest.raises(GooglePlacesAPIError):
                await client.reverse_geocode(12.9716, 77.5946)

    @pytest.mark.asyncio
    async def test_server_error_raises(self):
        """500 status raises GooglePlacesAPIError."""
        mock_response = AsyncMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)

        with patch("app.integrations.google_geocoding.settings") as mock_settings:
            mock_settings.GOOGLE_PLACES_API_KEY = "test-key"
            mock_settings.GOOGLE_GEOCODING_BASE_URL = "https://maps.googleapis.com/maps/api/geocode"
            client = GoogleGeocodingClient(http_client=mock_http)
            with pytest.raises(GooglePlacesAPIError):
                await client.reverse_geocode(12.9716, 77.5946)

    @pytest.mark.asyncio
    async def test_timeout_raises(self):
        """httpx.TimeoutException raises GooglePlacesTimeoutError."""
        import httpx

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

        with patch("app.integrations.google_geocoding.settings") as mock_settings:
            mock_settings.GOOGLE_PLACES_API_KEY = "test-key"
            mock_settings.GOOGLE_GEOCODING_BASE_URL = "https://maps.googleapis.com/maps/api/geocode"
            client = GoogleGeocodingClient(http_client=mock_http)
            with pytest.raises(GooglePlacesTimeoutError):
                await client.reverse_geocode(12.9716, 77.5946)

    @pytest.mark.asyncio
    async def test_zero_results_returns_data(self):
        """ZERO_RESULTS status returns the data (caller decides what to do)."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "ZERO_RESULTS",
            "results": [],
        }
        mock_response.text = ""

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)

        with patch("app.integrations.google_geocoding.settings") as mock_settings:
            mock_settings.GOOGLE_PLACES_API_KEY = "test-key"
            mock_settings.GOOGLE_GEOCODING_BASE_URL = "https://maps.googleapis.com/maps/api/geocode"
            client = GoogleGeocodingClient(http_client=mock_http)
            result = await client.reverse_geocode(0.0, 0.0)
        assert result["status"] == "ZERO_RESULTS"
        assert result["results"] == []

    @pytest.mark.asyncio
    async def test_over_query_limit_raises(self):
        """OVER_QUERY_LIMIT raises GooglePlacesRateLimitError."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "OVER_QUERY_LIMIT"}
        mock_response.text = ""

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)

        with patch("app.integrations.google_geocoding.settings") as mock_settings:
            mock_settings.GOOGLE_PLACES_API_KEY = "test-key"
            mock_settings.GOOGLE_GEOCODING_BASE_URL = "https://maps.googleapis.com/maps/api/geocode"
            client = GoogleGeocodingClient(http_client=mock_http)
            with pytest.raises(GooglePlacesRateLimitError):
                await client.reverse_geocode(12.9716, 77.5946)
