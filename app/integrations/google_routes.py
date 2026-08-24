import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.exceptions.places import (
    GooglePlacesAPIError,
    GooglePlacesRateLimitError,
    GooglePlacesTimeoutError,
)
from app.integrations.google_base import _trace_langfuse_span
from app.schemas.routes import (
    RouteMatrixElement,
    RouteResult,
    TravelMode,
    RoutingPreference,
)
from app.utils.formatting import format_distance, format_duration

logger = logging.getLogger(__name__)
COMPUTE_ROUTE_FIELD_MASK = ",".join(
    [
        "routes.distanceMeters",
        "routes.duration",
        "routes.staticDuration",
        "routes.polyline.encodedPolyline",
        "routes.legs.distanceMeters",
        "routes.legs.duration",
        "routes.legs.steps.distanceMeters",
        "routes.legs.steps.staticDuration",
        "routes.legs.steps.navigationInstruction",
        "routes.optimizedIntermediateWaypointIndex",
    ]
)

ROUTE_MATRIX_FIELD_MASK = ",".join(
    [
        "originIndex",
        "destinationIndex",
        "distanceMeters",
        "duration",
        "status",
        "condition",
    ]
)


class GoogleRoutesClient:
    def __init__(self, http_client: Optional[httpx.AsyncClient] = None) -> None:
        self.api_key = settings.GOOGLE_PLACES_API_KEY
        self.base_url = settings.GOOGLE_ROUTES_BASE_URL
        self._http_client = http_client
        self._timeout = httpx.Timeout(connect=5.0, read=20.0, write=5.0, pool=5.0)

    def _build_headers(self, field_mask: str) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": field_mask,
        }

    def _build_waypoint(
        self,
        latitude: float,
        longitude: float,
        place_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if place_id:
            return {"placeId": place_id}
        return {
            "location": {
                "latLng": {
                    "latitude": latitude,
                    "longitude": longitude,
                }
            }
        }

    async def _post(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        field_mask: str,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}:{endpoint}"
        headers = self._build_headers(field_mask)

        async def _do_request(client: httpx.AsyncClient) -> httpx.Response:
            return await client.post(url, json=payload, headers=headers)

        try:
            if self._http_client:
                response = await _do_request(self._http_client)
            else:
                logger.warning(
                    "GoogleRoutesClient: no shared client injected — "
                    "creating a per-call client (should only happen in tests)"
                )
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await _do_request(client)

        except httpx.TimeoutException as exc:
            _trace_langfuse_span(endpoint, success=False, error="timeout")
            logger.error("Routes API request timed out: %s", exc)
            raise GooglePlacesTimeoutError() from exc

        if response.status_code == 429:
            _trace_langfuse_span(endpoint, success=False, error="rate_limit")
            raise GooglePlacesRateLimitError()

        if response.status_code != 200:
            _trace_langfuse_span(endpoint, success=False, error=f"status_{response.status_code}")
            logger.error(
                "Routes API error %s: %s",
                response.status_code,
                response.text[:300],
            )
            raise GooglePlacesAPIError(
                "Unable to calculate the route. Please try again.",
                provider_status_code=response.status_code,
            )

        _trace_langfuse_span(endpoint, success=True)
        return response.json()

    async def compute_route(
        self,
        origin_lat: float,
        origin_lon: float,
        destination_lat: float,
        destination_lon: float,
        destination_place_id: Optional[str] = None,
        waypoints: Optional[List[Dict[str, Any]]] = None,
        optimize_waypoint_order: bool = False,
        departure_time: Optional[datetime] = None,
        travel_mode: TravelMode = TravelMode.DRIVE,
        routing_preference: RoutingPreference = RoutingPreference.TRAFFIC_AWARE,
        language_code: str = "en-US",
        avoid_tolls: bool = False,
        avoid_highways: bool = False,
        avoid_ferries: bool = False,
    ) -> RouteResult:
        effective_routing_preference = routing_preference
        if travel_mode in (TravelMode.WALK, TravelMode.TRANSIT):
            effective_routing_preference = RoutingPreference.TRAFFIC_UNAWARE

        payload: Dict[str, Any] = {
            "origin": self._build_waypoint(origin_lat, origin_lon),
            "destination": self._build_waypoint(
                destination_lat,
                destination_lon,
                place_id=destination_place_id,
            ),
            "travelMode": travel_mode.value,
            "routingPreference": effective_routing_preference.value,
            "computeAlternativeRoutes": False,  # keep costs down; enable later if needed
            "languageCode": language_code,
            "units": "METRIC",
            "routeModifiers": {
                "avoidTolls": avoid_tolls,
                "avoidHighways": avoid_highways,
                "avoidFerries": avoid_ferries,
            },
        }

        if waypoints:
            intermediates = []
            for wp in waypoints:
                waypoint_obj = self._build_waypoint(
                    wp.get("lat", 0.0),
                    wp.get("lon", 0.0),
                    place_id=wp.get("place_id"),
                )
                intermediates.append({"waypoint": waypoint_obj})

            payload["intermediates"] = intermediates
            payload["optimizeWaypointOrder"] = optimize_waypoint_order

        if departure_time:
            payload["departureTime"] = departure_time.isoformat()

        logger.info(
            "Routes API computeRoutes — mode: %s, origin: (%.4f, %.4f), "
            "destination: %s, waypoints: %d, departure_time: %s",
            travel_mode.value,
            origin_lat,
            origin_lon,
            destination_place_id or f"({destination_lat:.4f}, {destination_lon:.4f})",
            len(waypoints) if waypoints else 0,
            departure_time.isoformat() if departure_time else "now",
        )

        data = await self._post("computeRoutes", payload, COMPUTE_ROUTE_FIELD_MASK)
        return self._parse_route_response(data)

    async def compute_route_matrix(
        self,
        origin_lat: float,
        origin_lon: float,
        destinations: List[Dict[str, Any]],
        travel_mode: TravelMode = TravelMode.DRIVE,
        routing_preference: RoutingPreference = RoutingPreference.TRAFFIC_AWARE,
    ) -> List[RouteMatrixElement]:
        if not destinations:
            return []

        if travel_mode == TravelMode.WALK:
            routing_preference = RoutingPreference.TRAFFIC_UNAWARE

        origins = [
            {
                "waypoint": self._build_waypoint(origin_lat, origin_lon),
            }
        ]

        dest_waypoints = []
        for dest in destinations:
            waypoint = self._build_waypoint(
                dest["lat"],
                dest["lon"],
                place_id=dest.get("place_id"),
            )
            dest_waypoints.append({"waypoint": waypoint})

        payload: Dict[str, Any] = {
            "origins": origins,
            "destinations": dest_waypoints,
            "travelMode": travel_mode.value,
            "routingPreference": routing_preference.value,
        }

        logger.info(
            "Routes API computeRouteMatrix — mode: %s, origin: (%.4f, %.4f), "
            "destinations: %d",
            travel_mode.value,
            origin_lat,
            origin_lon,
            len(destinations),
        )

        data = await self._post("computeRouteMatrix", payload, ROUTE_MATRIX_FIELD_MASK)
        return self._parse_matrix_response(data)

    def _parse_route_response(self, data: Dict[str, Any]) -> RouteResult:
        routes = data.get("routes", [])
        if not routes:
            raise GooglePlacesAPIError(
                "Routes API returned no route for the given origin/destination. "
                "The destination may be unreachable by the selected travel mode."
            )

        route = routes[0]

        steps = []
        legs = route.get("legs", [])
        if legs:
            for step in legs[0].get("steps", []):
                nav = step.get("navigationInstruction", {})
                steps.append(
                    {
                        "distance_meters": step.get("distanceMeters", 0),
                        "duration_seconds": _duration_to_seconds(
                            step.get("staticDuration", "0s")
                        ),
                        "maneuver": nav.get("maneuver", ""),
                        "instruction": nav.get("instructions", ""),
                    }
                )

        distance_meters = route.get("distanceMeters", 0)
        duration_seconds = _duration_to_seconds(route.get("duration", "0s"))
        static_duration_seconds = _duration_to_seconds(
            route.get("staticDuration", "0s")
        )

        traffic_delay_seconds = max(0, duration_seconds - static_duration_seconds)

        distance_text = format_distance(distance_meters)
        duration_text = format_duration(duration_seconds)
        traffic_delay_text = (
            format_duration(traffic_delay_seconds) + " delay"
            if traffic_delay_seconds > 0
            else None
        )

        optimized_order = route.get("optimizedIntermediateWaypointIndex")

        return RouteResult(
            distance_meters=distance_meters,
            duration_seconds=duration_seconds,
            static_duration_seconds=static_duration_seconds,
            traffic_delay_seconds=traffic_delay_seconds,
            distance_text=distance_text,
            duration_text=duration_text,
            traffic_delay_text=traffic_delay_text,
            encoded_polyline=route.get("polyline", {}).get("encodedPolyline", ""),
            steps=steps,
            optimized_waypoint_order=optimized_order,
        )

    def _parse_matrix_response(self, data: Any) -> List[RouteMatrixElement]:

        if not isinstance(data, list):
            error_msg = (
                data.get("error", {}).get("message", str(data))
                if isinstance(data, dict)
                else str(data)
            )
            logger.error(
                "Route Matrix API returned unexpected response: %s", error_msg
            )
            raise GooglePlacesAPIError(
                "We couldn't calculate the routes. Please try again."
            )

        elements = []
        for item in data:
            condition = item.get("condition", "ROUTE_EXISTS")
            status_code = item.get("status", {}).get("code", 0)
            is_ok = condition == "ROUTE_EXISTS" and status_code == 0

            elements.append(
                RouteMatrixElement(
                    origin_index=item.get("originIndex", 0),
                    destination_index=item.get("destinationIndex", 0),
                    distance_meters=item.get("distanceMeters") if is_ok else None,
                    duration_seconds=(
                        _duration_to_seconds(item.get("duration", "0s"))
                        if is_ok
                        else None
                    ),
                    condition=condition,
                )
            )

        return sorted(elements, key=lambda e: e.destination_index)


def _duration_to_seconds(duration_str: str) -> int:

    if not duration_str:
        return 0
    try:
        return int(duration_str.rstrip("s"))
    except (ValueError, AttributeError):
        logger.warning("Failed to parse duration string: %r", duration_str)
        return 0



