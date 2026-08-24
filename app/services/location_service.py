import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.exceptions.custom_exceptions import LocationNotFoundError, NotFoundError
from app.models.user_location import UserLocation
from app.repositories.location_repository import LocationRepository
from app.schemas.location import GPSUpdateRequest, ManualLocationRequest
from app.validators.location_validator import (
    is_duplicate_location,
    validate_accuracy,
    validate_coordinates,
    validate_manual_location_rate_limit,
)
from app.utils.error_messages import LOCATION_MANUAL_RATE_LIMIT

logger = logging.getLogger(__name__)

LOCATION_HISTORY_RETENTION_DAYS = 90


class LocationService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = LocationRepository(db)

    def _do_location_write(
        self, user_id: int, latitude: float, longitude: float, source: str, **kwargs
    ) -> tuple[UserLocation, bool]:
        existing = self.repo.get_current_location(user_id)

        if existing and is_duplicate_location(
            latitude,
            longitude,
            existing.latitude,
            existing.longitude,
        ):
            return existing, False

        self.repo.deactivate_current_location(user_id)

        new_location = self.repo.create_location(
            user_id=user_id,
            latitude=latitude,
            longitude=longitude,
            source=source,
            is_current=True,
            is_active=True,
            **kwargs,
        )

        self.repo.create_history_entry(
            user_id=user_id,
            location_id=new_location.id,
            latitude=latitude,
            longitude=longitude,
            source=source,
        )

        self.db.commit()
        self.db.refresh(new_location)
        return new_location, True

    def _do_gps_write(
        self, user_id: int, payload: GPSUpdateRequest
    ) -> tuple[UserLocation, bool]:
        return self._do_location_write(
            user_id=user_id,
            latitude=payload.latitude,
            longitude=payload.longitude,
            source="gps",
            accuracy=payload.accuracy,
            client_timestamp=payload.client_timestamp,
            metadata_notes=payload.metadata_notes,
        )

    def process_gps_update(
        self, user_id: int, payload: GPSUpdateRequest
    ) -> tuple[UserLocation, bool]:
        validate_coordinates(payload.latitude, payload.longitude)
        validate_accuracy(payload.accuracy)

        try:
            self._cleanup_old_history(user_id)  # Clean old entries
            return self._do_gps_write(user_id, payload)
        except IntegrityError as e:
            constraint_name = "uix_user_locations_single_current"
            if constraint_name in str(e.orig):
                logger.warning(
                    "GPS update IntegrityError for user_id=%s — concurrent write "
                    "detected on %s constraint, retrying once.",
                    user_id,
                    constraint_name,
                )
                self.db.rollback()

                existing = self.repo.get_current_location(user_id)
                if existing:
                    logger.info(
                        "GPS update race resolved — using concurrent write's location "
                        "for user_id=%s: location_id=%s",
                        user_id,
                        existing.id,
                    )
                    return existing, True

                logger.info(
                    "GPS update race retry — no current location found after rollback "
                    "for user_id=%s, retrying write",
                    user_id,
                )
                return self._do_gps_write(user_id, payload)
            else:
                logger.error(
                    "GPS update IntegrityError for user_id=%s — NOT a race condition: %s",
                    user_id,
                    str(e),
                )
                raise

    def process_manual_location(
        self, user_id: int, payload: ManualLocationRequest
    ) -> tuple[UserLocation, bool]:
        validate_coordinates(payload.latitude, payload.longitude)

        if not validate_manual_location_rate_limit(self.db, user_id):
            raise ValueError(LOCATION_MANUAL_RATE_LIMIT)

        try:
            self._cleanup_old_history(user_id)
            return self._do_location_write(
                user_id=user_id,
                latitude=payload.latitude,
                longitude=payload.longitude,
                source="manual",
                address=payload.address,
                client_timestamp=datetime.now(timezone.utc),
                metadata_notes=payload.metadata_notes,
            )
        except IntegrityError as e:
            constraint_name = "uix_user_locations_single_current"
            if constraint_name in str(e.orig):
                logger.warning(
                    "Manual location IntegrityError for user_id=%s — race detected",
                    user_id,
                )
                self.db.rollback()

                existing = self.repo.get_current_location(user_id)
                if existing:
                    logger.info(
                        "Manual location race resolved for user_id=%s: location_id=%s",
                        user_id,
                        existing.id,
                    )
                    return existing, True

                logger.info(
                    "Manual location race retry for user_id=%s",
                    user_id,
                )
                return self._do_location_write(
                    user_id=user_id,
                    latitude=payload.latitude,
                    longitude=payload.longitude,
                    source="manual",
                    address=payload.address,
                    client_timestamp=datetime.now(timezone.utc),
                    metadata_notes=payload.metadata_notes,
                )
            else:
                logger.error(
                    "Manual location IntegrityError for user_id=%s — NOT a race condition: %s",
                    user_id,
                    str(e),
                )
                raise

    def get_current_location(self, user_id: int) -> UserLocation:
        location = self.repo.get_current_location(user_id)
        if not location:
            raise LocationNotFoundError()
        return location

    def get_latest_location(self, user_id: int) -> UserLocation:
        location = self.repo.get_latest_location(user_id)
        if not location:
            raise LocationNotFoundError()
        return location

    def get_location_history(self, user_id: int, page: int, page_size: int, source: str | None = None):
        if source and source not in ["gps", "manual"]:
            raise ValueError("Invalid location source. Use 'gps' or 'manual'.")
        return self.repo.get_history(user_id, page, page_size, source=source)

    def _cleanup_old_history(self, user_id: int) -> None:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=LOCATION_HISTORY_RETENTION_DAYS)
        deleted_count = (
            self.db.query(UserLocation)
            .filter(
                UserLocation.user_id == user_id,
                UserLocation.created_at < cutoff_date,
                UserLocation.is_active.is_(False),  # Only delete inactive entries
            )
            .delete(synchronize_session="evaluate")
        )
        if deleted_count > 0:
            logger.info(
                "Cleaned up %d old location entries for user_id=%s (older than %d days)",
                deleted_count,
                user_id,
                LOCATION_HISTORY_RETENTION_DAYS,
            )

    def delete_location(self, user_id: int, history_id: int | None = None) -> str:
        if history_id is None:
            if not self.repo.soft_delete_current(user_id):
                raise LocationNotFoundError()
            self.db.commit()
            return "Location cleared successfully"

        entry = self.repo.get_history_by_id(user_id, history_id)
        if not entry:
            raise NotFoundError(
                detail="Location entry not found."
            )
        self.repo.delete_history_entry(entry)
        self.db.commit()
        return "Location entry deleted successfully"
