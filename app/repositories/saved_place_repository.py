import logging
from typing import List, Optional, Tuple

from sqlalchemy import and_
from sqlalchemy.orm import Session
from app.models.user_saved_place import UserSavedPlace

logger = logging.getLogger(__name__)


class SavedPlaceRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, saved_id: int, user_id: int) -> Optional[UserSavedPlace]:
        return (
            self.db.query(UserSavedPlace)
            .filter(
                and_(
                    UserSavedPlace.id == saved_id,
                    UserSavedPlace.user_id == user_id,
                )
            )
            .first()
        )

    def create(
        self,
        *,
        user_id: int,
        place_id: str,
        display_name: Optional[str] = None,
        formatted_address: Optional[str] = None,
        primary_type: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        rating: Optional[float] = None,
        saved_location_lat: Optional[float] = None,
        saved_location_lon: Optional[float] = None,
        notes: Optional[str] = None,
        tags: Optional[list] = None,
    ) -> UserSavedPlace:
        record = UserSavedPlace(
            user_id=user_id,
            place_id=place_id,
            display_name=display_name,
            formatted_address=formatted_address,
            primary_type=primary_type,
            latitude=latitude,
            longitude=longitude,
            rating=rating,
            saved_location_lat=saved_location_lat,
            saved_location_lon=saved_location_lon,
            notes=notes,
            tags=tags,
        )
        self.db.add(record)
        self.db.flush()
        logger.info("Saved place: user=%s place=%s", user_id, place_id)
        return record

    def delete(self, record: UserSavedPlace) -> None:
        self.db.delete(record)
        self.db.flush()
        logger.info(
            "Unsaved place: user=%s place=%s (saved_id=%s)",
            record.user_id,
            record.place_id,
            record.id,
        )

    def delete_by_id(self, saved_id: int, user_id: int) -> Optional[UserSavedPlace]:
        record = self.get_by_id(saved_id, user_id)
        if record:
            self.delete(record)
        return record

    def list_saved(
        self,
        user_id: int,
        *,
        tag: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[UserSavedPlace], int]:
        query = self.db.query(UserSavedPlace).filter(
            and_(
                UserSavedPlace.user_id == user_id,
                UserSavedPlace.is_archived == False,
            )
        )

        if tag:
            query = query.filter(UserSavedPlace.tags.any(tag))
        if search:
            query = query.filter(UserSavedPlace.display_name.ilike(f"%{search}%"))

        total = query.count()
        records = (
            query.order_by(UserSavedPlace.saved_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )
        return records, total

    def get_saved_by_place_ids(
        self, user_id: int, place_ids: List[str]
    ) -> List[UserSavedPlace]:
        if not place_ids:
            return []
        return (
            self.db.query(UserSavedPlace)
            .filter(
                and_(
                    UserSavedPlace.user_id == user_id,
                    UserSavedPlace.place_id.in_(place_ids),
                    UserSavedPlace.is_archived == False,
                )
            )
            .all()
        )

    def get_saved_nearby_by_place_location(
        self,
        user_id: int,
        lat: float,
        lon: float,
        radius_km: float = 2.0,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[UserSavedPlace], int]:
        return self._get_saved_nearby(
            user_id=user_id,
            lat=lat,
            lon=lon,
            radius_km=radius_km,
            latitude_column=UserSavedPlace.latitude,
            longitude_column=UserSavedPlace.longitude,
            limit=limit,
            offset=offset,
        )

    def get_saved_nearby_by_save_location(
        self,
        user_id: int,
        lat: float,
        lon: float,
        radius_km: float = 2.0,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[UserSavedPlace], int]:
        return self._get_saved_nearby(
            user_id=user_id,
            lat=lat,
            lon=lon,
            radius_km=radius_km,
            latitude_column=UserSavedPlace.saved_location_lat,
            longitude_column=UserSavedPlace.saved_location_lon,
            limit=limit,
            offset=offset,
        )

    def _get_saved_nearby(
        self,
        user_id: int,
        lat: float,
        lon: float,
        radius_km: float,
        latitude_column,
        longitude_column,
        limit: int,
        offset: int,
    ) -> Tuple[List[UserSavedPlace], int]:
        deg = radius_km / 111.0
        base_query = self.db.query(UserSavedPlace).filter(
            and_(
                UserSavedPlace.user_id == user_id,
                UserSavedPlace.is_archived == False,
                latitude_column.isnot(None),
                longitude_column.isnot(None),
                latitude_column >= lat - deg,
                latitude_column <= lat + deg,
                longitude_column >= lon - deg,
                longitude_column <= lon + deg,
            )
        )
        total = base_query.count()
        records = (
            base_query.order_by(UserSavedPlace.saved_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )
        return records, total
