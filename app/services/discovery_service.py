import logging
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from app.core.config import settings
from app.exceptions.places import UserLocationNotFoundError
from app.integrations.google_autocomplete import GoogleAutocompleteClient
from app.integrations.google_places import GooglePlacesClient
from app.integrations.google_text_search import GoogleTextSearchClient
from app.models.user_location import UserLocation
from app.repositories.place_unlock_repository import PlaceUnlockRepository
from app.repositories.redis_repository import RedisRepository
from app.repositories.search_repository import SearchRepository
from app.repositories.visit_repository import VisitRepository
from app.schemas.discovery import (
    DiscoveryCategory,
    DiscoveryPlaceResult,
    NearbyDiscoveryRequest,
    TextSearchRequest,
)
from app.services.category_validator import (
    assign_categories,
    apply_fine_dining_filter,
    filter_places_by_category,
    filter_places_by_subcategory,
)
from app.services.discovery_ranking import rank_places_with_ai
from app.services.duplicate_detection import deduplicate_places
from app.utils.cache_keys import CacheKeyBuilder
from app.utils.place_categories import (
    CATEGORY_TO_GOOGLE_TYPES,
    PARKING_PLACE_TYPES,
    SUBCATEGORY_TO_GOOGLE_TYPES,
)

logger = logging.getLogger(__name__)


class DiscoveryService:
    def __init__(
        self,
        db: Session,
        redis_repo: RedisRepository,
        text_client: GoogleTextSearchClient,
        nearby_client: GooglePlacesClient,
        autocomplete_client: GoogleAutocompleteClient,
        openai_client=None,
    ) -> None:
        self.db = db
        self.redis_repo = redis_repo
        self.text_client = text_client
        self.nearby_client = nearby_client
        self.autocomplete_client = autocomplete_client
        self.openai_client = openai_client
        self.search_repo = SearchRepository(db)
        self.visit_repo = VisitRepository(db)
        self._search_cache_ttl = settings.REDIS_CACHE_TTL
        self._autocomplete_cache_ttl = settings.REDIS_AUTOCOMPLETE_CACHE_TTL

    def _get_user_location(self, user_id: int) -> Optional[UserLocation]:
        manual = (
            self.db.query(UserLocation)
            .filter(
                UserLocation.user_id == user_id,
                UserLocation.source == "manual",
                UserLocation.is_current.is_(True),
                UserLocation.is_active.is_(True),
            )
            .first()
        )
        if manual:
            logger.debug(
                "Using manual location for user_id=%s: lat=%s lon=%s",
                user_id,
                manual.latitude,
                manual.longitude,
            )
            return manual

        gps = (
            self.db.query(UserLocation)
            .filter(
                UserLocation.user_id == user_id,
                UserLocation.source == "gps",
                UserLocation.is_current.is_(True),
                UserLocation.is_active.is_(True),
            )
            .first()
        )
        if gps:
            logger.debug(
                "Using GPS location for user_id=%s: lat=%s lon=%s",
                user_id,
                gps.latitude,
                gps.longitude,
            )
        return gps

    async def _try_get_cache(self, key: str) -> Optional[List[DiscoveryPlaceResult]]:
        cached = await self.redis_repo.get(key)
        if cached is not None:
            try:
                return [DiscoveryPlaceResult(**item) for item in cached]
            except Exception as exc:
                logger.warning(
                    "Cache deserialisation failed for key %s — deleting stale entry: %s",
                    key,
                    exc,
                )
                await self.redis_repo.delete(key)
        return None

    async def _try_set_cache(
        self, key: str, places: List[DiscoveryPlaceResult], ttl: Optional[int] = None
    ) -> None:
        try:
            cache_ttl = ttl if ttl is not None else self._search_cache_ttl
            serialisable = [p.model_dump() for p in places]
            await self.redis_repo.set(key, serialisable, ttl=cache_ttl)
        except Exception as exc:
            logger.warning("Cache write failed for key %s: %s", key, exc)

    def _persist_audit(
        self,
        *,
        user_id: int,
        search_mode: str,
        resolved_mode: Optional[str],
        raw_query: Optional[str],
        latitude: Optional[float],
        longitude: Optional[float],
        radius: Optional[float],
        places: List[DiscoveryPlaceResult],
        from_cache: bool,
    ) -> None:
        try:
            from app.database.connection import SessionLocal

            audit_db = SessionLocal()
            try:
                audit_search_repo = SearchRepository(audit_db)
                query_row = audit_search_repo.create_search_query(
                    user_id=user_id,
                    search_mode=search_mode,
                    resolved_mode=resolved_mode,
                    raw_query=raw_query,
                    latitude=latitude,
                    longitude=longitude,
                    radius=radius,
                    result_count=len(places),
                    from_cache=from_cache,
                )
                audit_search_repo.create_search_results(
                    query_id=query_row.id,
                    user_id=user_id,
                    places=places,
                )
                audit_db.commit()
            except Exception:
                audit_db.rollback()
                raise
            finally:
                audit_db.close()
        except Exception as exc:
            logger.critical(
                "AUDIT PERSIST FAILED — search data lost (user=%s mode=%s query=%r): %s",
                user_id,
                search_mode,
                raw_query,
                exc,
                exc_info=True,
            )

    def _enrich_places_with_unlock_status(
        self, places: List[DiscoveryPlaceResult], user_id: int
    ) -> List[DiscoveryPlaceResult]:
        if not places:
            return places

        if not settings.PLACE_UNLOCK_ENABLED:
            for place in places:
                place.is_locked = False
            return places

        place_ids = [p.place_id for p in places if p.place_id]
        if not place_ids:
            return places

        unlock_repo = PlaceUnlockRepository(self.db)
        unlocked_ids = unlock_repo.get_active_unlock_place_ids(user_id, place_ids)

        for place in places:
            place.is_locked = place.place_id not in unlocked_ids if place.place_id else True

        return places

    def _enrich_places_with_visit_status(
        self, places: List[DiscoveryPlaceResult], user_id: int
    ) -> None:
        if not places:
            return
        place_ids = [p.place_id for p in places if p.place_id]
        if not place_ids:
            return
        visited_ids = self.visit_repo.get_visited_place_ids(user_id, place_ids)
        for place in places:
            if place.place_id:
                place.is_visit = place.place_id in visited_ids

    async def text_search(
        self,
        request: TextSearchRequest,
        user_id: int,
    ) -> Tuple[List[DiscoveryPlaceResult], bool, Optional[float], Optional[float]]:
        bias_lat: Optional[float] = None
        bias_lon: Optional[float] = None
        bias_radius: Optional[float] = None

        if request.location_bias:
            bias_lat = request.location_bias.latitude
            bias_lon = request.location_bias.longitude
            bias_radius = request.location_bias.radius
            logger.debug(
                "Text Search bias: explicit payload (%s, %s) r=%s",
                bias_lat,
                bias_lon,
                bias_radius,
            )
        elif request.use_user_location_as_bias:
            loc = self._get_user_location(user_id)
            if loc:
                bias_lat = loc.latitude
                bias_lon = loc.longitude
                bias_radius = 5000.0
                logger.debug(
                    "Text Search bias: user saved location (%s, %s)",
                    bias_lat,
                    bias_lon,
                )
            else:
                logger.info(
                    "Text Search for user %s: no saved location, Google uses IP bias",
                    user_id,
                )

        cache_key = CacheKeyBuilder.discovery_text_search(
            user_id=user_id,
            text_query=request.text_query,
            bias_lat=bias_lat,
            bias_lon=bias_lon,
        )

        cached_places = await self._try_get_cache(cache_key)
        if cached_places is not None:
            logger.info(
                "Text Search cache HIT — user=%s query=%r", user_id, request.text_query
            )
            places = cached_places
            self._enrich_places_with_unlock_status(places, user_id)
            self._enrich_places_with_visit_status(places, user_id)
            self._persist_audit(
                user_id=user_id,
                search_mode="text",
                resolved_mode="text",
                raw_query=request.text_query,
                latitude=bias_lat,
                longitude=bias_lon,
                radius=bias_radius,
                places=cached_places,
                from_cache=True,
            )
            return cached_places, True, bias_lat, bias_lon

        logger.info(
            "Text Search cache MISS — user=%s query=%r → calling Google",
            user_id,
            request.text_query,
        )
        places = await self.text_client.search_text(
            text_query=request.text_query,
            max_result_count=request.max_result_count,
            open_now=request.open_now,
            location_bias_lat=bias_lat,
            location_bias_lon=bias_lon,
            location_bias_radius=bias_radius,
        )

        places = deduplicate_places(places)
        self._enrich_places_with_unlock_status(places, user_id)
        self._enrich_places_with_visit_status(places, user_id)
        await self._try_set_cache(cache_key, places)

        self._persist_audit(
            user_id=user_id,
            search_mode="text",
            resolved_mode="text",
            raw_query=request.text_query,
            latitude=bias_lat,
            longitude=bias_lon,
            radius=bias_radius,
            places=places,
            from_cache=False,
        )

        return places, False, bias_lat, bias_lon

    def _build_nearby_type_filter(
        self,
        category: DiscoveryCategory,
        subcategories: Optional[List[str]],
    ) -> Tuple[Optional[List[str]], Optional[List[str]]]:
        if subcategories:
            merged_types: set = set()
            has_empty = False
            for sub in subcategories:
                sub_types = SUBCATEGORY_TO_GOOGLE_TYPES.get(sub)
                if sub_types is not None:
                    if sub_types:
                        merged_types.update(sub_types)
                    else:
                        has_empty = True

            if merged_types:
                return sorted(merged_types), None
            if has_empty:
                if category == DiscoveryCategory.EXPLORE:
                    return None, PARKING_PLACE_TYPES
                return None, None

        cat_types = CATEGORY_TO_GOOGLE_TYPES.get(category.value)

        if category == DiscoveryCategory.PARKING:
            return PARKING_PLACE_TYPES, None
        if category == DiscoveryCategory.EXPLORE:
            return None, PARKING_PLACE_TYPES
        return cat_types, None

    async def nearby_search(
        self,
        request: NearbyDiscoveryRequest,
        user_id: int,
    ) -> Tuple[List[DiscoveryPlaceResult], bool, float, float]:
        loc = self._get_user_location(user_id)
        if loc is None:
            logger.warning(
                "Nearby search blocked — user_id %s has no saved location", user_id
            )
            raise UserLocationNotFoundError()
        latitude = loc.latitude
        longitude = loc.longitude

        included_types, excluded_types = self._build_nearby_type_filter(
            request.category, request.subcategories,
        )

        cache_key = CacheKeyBuilder.discovery_nearby_search(
            user_id=user_id,
            latitude=latitude,
            longitude=longitude,
            radius=request.radius,
            included_types=(",".join(included_types) if included_types else None),
            excluded_types=(",".join(excluded_types) if excluded_types else None),
        )

        cached_places = await self._try_get_cache(cache_key)
        if cached_places is not None:
            logger.info(
                "Nearby Discovery cache HIT — user=%s lat=%s lon=%s category=%s sub=%s",
                user_id,
                latitude,
                longitude,
                request.category.value,
                request.subcategory_display,
            )
            places = deduplicate_places(cached_places)
            places = assign_categories(places, request.category)
            places = filter_places_by_category(places, request.category)
            places = filter_places_by_subcategory(places, request.subcategories, category=request.category)
            if request.has_fine_dining:
                places = apply_fine_dining_filter(places)
            self._enrich_places_with_unlock_status(places, user_id)
            self._enrich_places_with_visit_status(places, user_id)
            self._persist_audit(
                user_id=user_id,
                search_mode="nearby",
                resolved_mode="nearby",
                raw_query=None,
                latitude=latitude,
                longitude=longitude,
                radius=request.radius,
                places=places,
                from_cache=True,
            )
            return places, True, latitude, longitude

        logger.info(
            "Nearby Discovery cache MISS — user=%s category=%s sub=%s → Google (included: %s, excluded: %s)",
            user_id,
            request.category.value,
            request.subcategory_display,
            included_types if included_types else "none",
            excluded_types if excluded_types else "none",
        )

        places: List[DiscoveryPlaceResult] = await self.nearby_client.search_nearby(
            latitude=latitude,
            longitude=longitude,
            radius=request.radius,
            max_result_count=request.max_result_count,
            included_types=included_types,
            excluded_types=excluded_types,
        )

        places = deduplicate_places(places)
        places = assign_categories(places, request.category)
        places = filter_places_by_category(places, request.category)
        places = filter_places_by_subcategory(places, request.subcategories, category=request.category)
        if request.has_fine_dining:
            places = apply_fine_dining_filter(places)
        self._enrich_places_with_unlock_status(places, user_id)
        self._enrich_places_with_visit_status(places, user_id)

        places = await rank_places_with_ai(
            places=places,
            category=request.category.value,
            subcategories=request.subcategories,
            user_lat=latitude,
            user_lon=longitude,
            openai_client=self.openai_client,
        )

        await self._try_set_cache(cache_key, places)

        self._persist_audit(
            user_id=user_id,
            search_mode="nearby",
            resolved_mode="nearby",
            raw_query=None,
            latitude=latitude,
            longitude=longitude,
            radius=request.radius,
            places=places,
            from_cache=False,
        )

        return places, False, latitude, longitude

    async def autocomplete(
        self,
        input_text: str,
        user_id: int,
        included_primary_types: Optional[List[str]] = None,
        language_code: str = "en",
        use_user_location_bias: bool = True,
    ) -> Tuple[List[Dict[str, Any]], bool, Optional[float], Optional[float]]:
        bias_lat: Optional[float] = None
        bias_lon: Optional[float] = None
        bias_radius: Optional[float] = None

        if use_user_location_bias:
            loc = self._get_user_location(user_id)
            if loc:
                bias_lat = loc.latitude
                bias_lon = loc.longitude
                bias_radius = 5000.0
                logger.debug(
                    "Autocomplete bias: user saved location (%s, %s)",
                    bias_lat,
                    bias_lon,
                )
            else:
                logger.info(
                    "Autocomplete for user %s: no saved location, Google uses IP bias",
                    user_id,
                )

        cache_key = CacheKeyBuilder.discovery_autocomplete(
            user_id=user_id,
            input_text=input_text,
            bias_lat=bias_lat,
            bias_lon=bias_lon,
        )

        cached_predictions = await self.redis_repo.get(cache_key)
        if cached_predictions is not None:
            if isinstance(cached_predictions, list) and all(
                isinstance(p, dict) and "place_id" in p for p in cached_predictions
            ):
                logger.info(
                    "Autocomplete cache HIT — user=%s input=%r", user_id, input_text
                )
                return cached_predictions, True, bias_lat, bias_lon
            else:
                logger.warning(
                    "Autocomplete cache stale — invalid format for key %s, deleting",
                    cache_key,
                )
                await self.redis_repo.delete(cache_key)

        logger.info(
            "Autocomplete cache MISS — user=%s input=%r → calling Google",
            user_id,
            input_text,
        )
        predictions = await self.autocomplete_client.autocomplete(
            input_text=input_text,
            location_bias_lat=bias_lat,
            location_bias_lon=bias_lon,
            location_bias_radius=bias_radius,
            included_primary_types=included_primary_types,
            language_code=language_code,
        )

        try:
            await self.redis_repo.set(
                cache_key, predictions, ttl=self._autocomplete_cache_ttl
            )
        except Exception as exc:
            logger.warning(
                "Autocomplete cache write failed for key %s: %s", cache_key, exc
            )

        return predictions, False, bias_lat, bias_lon
