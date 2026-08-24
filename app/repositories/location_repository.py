import logging
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.location_history import LocationHistory
from app.models.user_location import UserLocation

logger = logging.getLogger(__name__)


class LocationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_current_location(self, user_id: int) -> UserLocation | None:
        if user_id <= 0:
            raise ValueError(f"Invalid user_id: {user_id}")
        return (
            self.db.query(UserLocation)
            .filter(
                UserLocation.user_id == user_id,
                UserLocation.is_current.is_(True),
                UserLocation.is_active.is_(True),
            )
            .first()
        )

    def get_latest_location(self, user_id: int) -> UserLocation | None:
        if user_id <= 0:
            raise ValueError(f"Invalid user_id: {user_id}")
        return (
            self.db.query(UserLocation)
            .filter(UserLocation.user_id == user_id)
            .order_by(UserLocation.created_at.desc())
            .first()
        )

    def get_history(
        self, user_id: int, page: int = 1, page_size: int = 20, source: str | None = None
    ) -> tuple[list[LocationHistory], int]:
        if user_id <= 0:
            raise ValueError(f"Invalid user_id: {user_id}")
        count_col = func.count(LocationHistory.id).over().label("total_count")
        query = (
            self.db.query(LocationHistory, count_col)
            .filter(LocationHistory.user_id == user_id)
        )
        
        if source:
            query = query.filter(LocationHistory.source == source)
        
        rows = (
            query
            .order_by(LocationHistory.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        if not rows:
            return [], 0
        items = [row[0] for row in rows]
        total = rows[0][1]
        return items, total

    def deactivate_current_location(self, user_id: int) -> None:
        if user_id <= 0:
            raise ValueError(f"Invalid user_id: {user_id}")
        self.db.query(UserLocation).filter(
            UserLocation.user_id == user_id,
            UserLocation.is_current.is_(True),
        ).update({"is_current": False}, synchronize_session="evaluate")
        logger.debug("Deactivated current location for user_id=%s", user_id)

    def create_location(self, user_id: int, **kwargs) -> UserLocation:
        if user_id <= 0:
            raise ValueError(f"Invalid user_id: {user_id}")
        location = UserLocation(user_id=user_id, **kwargs)
        self.db.add(location)
        self.db.flush()
        logger.debug(
            "Location record created — user_id=%s source=%s lat=%s lon=%s",
            user_id,
            kwargs.get("source", "unknown"),
            kwargs.get("latitude"),
            kwargs.get("longitude"),
        )
        return location

    def create_history_entry(
        self, user_id: int, location_id: int, **kwargs
    ) -> LocationHistory:
        entry = LocationHistory(
            user_id=user_id,
            location_id=location_id,
            **kwargs,
        )
        self.db.add(entry)
        logger.debug(
            "Location history entry staged — user_id=%s location_id=%s source=%s",
            user_id,
            location_id,
            kwargs.get("source", "unknown"),
        )
        return entry

    def soft_delete_current(self, user_id: int) -> bool:
        if user_id <= 0:
            raise ValueError(f"Invalid user_id: {user_id}")
        updated = (
            self.db.query(UserLocation)
            .filter(
                UserLocation.user_id == user_id,
                UserLocation.is_current.is_(True),
                UserLocation.is_active.is_(True),
            )
            .update(
                {"is_current": False, "is_active": False},
                synchronize_session="evaluate",
            )
        )
        if updated:
            logger.info("Soft-deleted current location for user_id=%s", user_id)
        return updated > 0

    def get_history_by_id(
        self, user_id: int, history_id: int
    ) -> LocationHistory | None:
        if user_id <= 0:
            raise ValueError(f"Invalid user_id: {user_id}")
        if history_id <= 0:
            raise ValueError(f"Invalid history_id: {history_id}")
        return (
            self.db.query(LocationHistory)
            .filter(
                LocationHistory.id == history_id,
                LocationHistory.user_id == user_id,
            )
            .first()
        )

    def delete_history_entry(self, entry: LocationHistory) -> None:
        self.db.delete(entry)
        self.db.flush()
        logger.debug(
            "Location history entry deleted — id=%s user_id=%s",
            entry.id,
            entry.user_id,
        )
