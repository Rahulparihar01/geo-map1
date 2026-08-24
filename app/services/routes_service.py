import logging
from typing import List, Tuple
from sqlalchemy.orm import Session
from app.core.config import settings
from app.exceptions.places import (
    GooglePlacesAPIError,
    UserLocationNotFoundError,
)
from app.integrations.google_routes import GoogleRoutesClient
from app.repositories.location_repository import LocationRepository
from app.repositories.redis_repository import RedisRepository
from app.schemas.routes import (
    ComputeRouteMatrixRequest,
    ComputeRouteRequest,
    RouteMatrixElement,
    RouteMatrixItem,
    RouteMatrixResponse,
    RouteResponse,
    RouteResult,
    TravelMode,
    RoutingPreference,
)
from app.utils.formatting import format_distance, format_duration
from app.utils.cache_keys import CacheKeyBuilder

logger = logging.getLogger(__name__)


class RoutesService:
    def __init__(
        self,
        db: Session,
        redis_repo: RedisRepository,
        routes_client: GoogleRoutesClient,
    ) -> None:
        self._db = db
        self._redis = redis_repo
        self._client = routes_client
        self._location_repo = LocationRepository(db)

    async def compute_route(
        self,
        request: ComputeRouteRequest,
        user_id: int,
    ) -> Tuple[RouteResponse, float, float]:

        location = self._location_repo.get_current_location(user_id)
        if not location:
            raise UserLocationNotFoundError()

        origin_lat, origin_lon = location.latitude, location.longitude

        if not request.place_id and not request.has_valid_destination():
            raise GooglePlacesAPIError(
                "A destination is required."
            )

        cache_key = CacheKeyBuilder.routes_direction(
            user_id=user_id,
            origin_lat=location.latitude,
            origin_lon=location.longitude,
            destination_lat=request.destination_latitude or 0,
            destination_lon=request.destination_longitude or 0,
            travel_mode=request.travel_mode.value,
        )
        cached_data = await self._redis.get(cache_key)
        if cached_data:
            try:
                result = RouteResult.model_validate(cached_data)
                logger.info("Route cache HIT — key: %s", cache_key)
                return (
                    RouteResponse(
                        success=True,
                        message="Route retrieved successfully",
                        cached=True,
                        travel_mode=request.travel_mode.value,
                        data=result,
                    ),
                    origin_lat,
                    origin_lon,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to deserialise cached route — treating as miss: %s", exc
                )

        logger.info("Route cache MISS — calling Routes API for user_id: %s", user_id)
        result = await self._client.compute_route(
            origin_lat=origin_lat,
            origin_lon=origin_lon,
            destination_lat=request.destination_latitude or 0.0,
            destination_lon=request.destination_longitude or 0.0,
            destination_place_id=request.place_id,
            waypoints=request.waypoints if request.waypoints else None,
            optimize_waypoint_order=request.optimize_waypoint_order,
            departure_time=request.departure_time,
            travel_mode=request.travel_mode,
            routing_preference=(
                RoutingPreference.TRAFFIC_AWARE
                if request.travel_mode == TravelMode.DRIVE
                else RoutingPreference.TRAFFIC_UNAWARE
            ),
            language_code=request.language_code,
            avoid_tolls=request.avoid_tolls,
            avoid_highways=request.avoid_highways,
            avoid_ferries=request.avoid_ferries,
        )

        await self._redis.set(
            cache_key,
            result.model_dump(mode="json"),
            ttl=settings.REDIS_ROUTES_CACHE_TTL,
        )

        return (
            RouteResponse(
                success=True,
                message="Route computed successfully",
                cached=False,
                travel_mode=request.travel_mode.value,
                data=result,
            ),
            origin_lat,
            origin_lon,
        )

    async def compute_route_matrix(
        self,
        request: ComputeRouteMatrixRequest,
        user_id: int,
    ) -> RouteMatrixResponse:

        location = self._location_repo.get_current_location(user_id)
        if not location:
            raise UserLocationNotFoundError(
                "No current location saved. POST /api/locations/gps first."
            )

        origin_lat, origin_lon = location.latitude, location.longitude

        dest_string = "|".join(
            [f"{d.get('lat', 0)},{d.get('lon', 0)}" for d in request.destinations]
        )
        cache_key = CacheKeyBuilder.routes_matrix(
            user_id=user_id,
            origin_lat=location.latitude,
            origin_lon=location.longitude,
            destinations=dest_string,
            travel_mode=request.travel_mode.value,
        )
        cached_data = await self._redis.get(cache_key)
        if cached_data:
            try:
                items = [RouteMatrixItem.model_validate(item) for item in cached_data]
                logger.info("Route matrix cache HIT — key: %s", cache_key)
                return RouteMatrixResponse(
                    success=True,
                    message="Route matrix retrieved successfully",
                    cached=True,
                    travel_mode=request.travel_mode.value,
                    origin_latitude=origin_lat,
                    origin_longitude=origin_lon,
                    data=items,
                    total_destinations=len(items),
                )
            except Exception as exc:
                logger.warning(
                    "Failed to deserialise cached matrix — treating as miss: %s", exc
                )

        logger.info(
            "Route matrix cache MISS — calling Routes API for user_id: %s, "
            "destinations: %d",
            user_id,
            len(request.destinations),
        )
        elements: List[RouteMatrixElement] = await self._client.compute_route_matrix(
            origin_lat=origin_lat,
            origin_lon=origin_lon,
            destinations=request.destinations,
            travel_mode=request.travel_mode,
        )

        items: List[RouteMatrixItem] = []
        for element in elements:
            idx = element.destination_index
            dest = request.destinations[idx] if idx < len(request.destinations) else {}

            items.append(
                RouteMatrixItem(
                    destination_index=idx,
                    place_id=dest.get("place_id"),
                    distance_meters=element.distance_meters,
                    duration_seconds=element.duration_seconds,
                    distance_text=format_distance(element.distance_meters),
                    duration_text=format_duration(element.duration_seconds),
                    reachable=element.condition == "ROUTE_EXISTS",
                )
            )

        await self._redis.set(
            cache_key,
            [item.model_dump(mode="json") for item in items],
            ttl=settings.REDIS_ROUTE_MATRIX_CACHE_TTL,
        )

        return RouteMatrixResponse(
            success=True,
            message="Route matrix computed successfully",
            cached=False,
            travel_mode=request.travel_mode.value,
            origin_latitude=origin_lat,
            origin_longitude=origin_lon,
            data=items,
            total_destinations=len(items),
        )
