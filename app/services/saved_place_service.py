import logging
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.repositories.location_repository import LocationRepository
from app.repositories.saved_place_repository import SavedPlaceRepository
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.visit_repository import VisitRepository
from app.schemas.saved_places import SavedPlaceResponse
from app.services.place_unlock_service import PlaceUnlockService

logger = logging.getLogger(__name__)


class SavedPlaceService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = SavedPlaceRepository(db)
        self.location_repo = LocationRepository(db)
        self.knowledge_repo = KnowledgeRepository(db)
        self.unlock_service = PlaceUnlockService(db)
        self.visit_repo = VisitRepository(db)

    def _build_responses(
        self, records: List, user_id: int
    ) -> List[SavedPlaceResponse]:
        place_ids = [record.place_id for record in records]
        unlocked_place_ids = self.unlock_service.get_unlocked_place_ids(
            user_id=user_id,
            place_ids=place_ids,
        )
        visited_place_ids = self.visit_repo.get_visited_place_ids(user_id, place_ids)
        return [
            SavedPlaceResponse.model_validate(record).model_copy(
                update={
                    "is_unlocked": record.place_id in unlocked_place_ids,
                    "is_visit": record.place_id in visited_place_ids,
                }
            )
            for record in records
        ]

    def _get_user_location(
        self, user_id: int
    ) -> Tuple[Optional[float], Optional[float]]:
        try:
            loc = self.location_repo.get_current_location(user_id)
            if loc:
                return loc.latitude, loc.longitude
        except Exception as exc:
            logger.debug("Could not fetch user location for save context: %s", exc)
        return None, None

    async def save_place(
        self,
        user_id: int,
        place_id: str,
        notes: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Tuple[str, int]:
        place_fields = self.knowledge_repo.get_denormalized_fields(
            place_id, include_rating=True
        )

        saved_lat, saved_lon = self._get_user_location(user_id)

        record = self.repo.create(
            user_id=user_id,
            place_id=place_id,
            notes=notes,
            tags=tags,
            saved_location_lat=saved_lat,
            saved_location_lon=saved_lon,
            **place_fields,
        )
        self.db.commit()
        logger.info(
            "Place saved: user=%s place=%s saved_id=%s location=(%s, %s)",
            user_id,
            place_id,
            record.id,
            saved_lat,
            saved_lon,
        )
        return "Place saved successfully!", record.id

    async def unsave_place(self, saved_id: int, user_id: int) -> bool:
        record = self.repo.delete_by_id(saved_id, user_id)
        if record:
            self.db.commit()
            logger.info(
                "Place unsaved: user=%s saved_id=%s place=%s",
                user_id,
                saved_id,
                record.place_id,
            )
            return True
        logger.warning("Unsave failed: saved_id=%s not found for user=%s", saved_id, user_id)
        return False

    async def list_saved(
        self,
        user_id: int,
        page: int = 1,
        page_size: int = 20,
        tag: Optional[str] = None,
        search: Optional[str] = None,
    ) -> Tuple[List[SavedPlaceResponse], int, bool]:
        offset = (page - 1) * page_size
        records, total = self.repo.list_saved(
            user_id=user_id,
            tag=tag,
            search=search,
            limit=page_size,
            offset=offset,
        )
        has_next = (offset + page_size) < total

        items = self._build_responses(records, user_id)
        return items, total, has_next

    async def get_saved_nearby(
        self,
        user_id: int,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        radius_km: float = 2.0,
        filter_by: str = "place",
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[SavedPlaceResponse], int, bool]:
        if lat is None or lon is None:
            loc = self.location_repo.get_current_location(user_id)
            if loc:
                lat, lon = loc.latitude, loc.longitude
                logger.info(
                    "Nearby saved places: using user's GPS location (%s, %s)",
                    lat,
                    lon,
                )
            else:
                logger.warning(
                    "Nearby saved places: no location provided and no user GPS found"
                )
                return [], 0, False

        offset = (page - 1) * page_size
        if filter_by == "saved":
            records, total = self.repo.get_saved_nearby_by_save_location(
                user_id, lat, lon, radius_km, limit=page_size, offset=offset
            )
        else:
            records, total = self.repo.get_saved_nearby_by_place_location(
                user_id, lat, lon, radius_km, limit=page_size, offset=offset
            )

        has_next = (offset + page_size) < total
        items = self._build_responses(records, user_id)
        return items, total, has_next
