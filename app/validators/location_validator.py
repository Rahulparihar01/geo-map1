from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.models.user_location import UserLocation
from app.exceptions.custom_exceptions import InvalidCoordinatesError
from app.utils.geo import haversine_distance_meters
from app.utils.error_messages import VALIDATION_INVALID_COORDINATES

DUPLICATE_DISTANCE = 10.0
MANUAL_LOCATION_PER_HOUR = 20


def validate_coordinates(latitude: float, longitude: float) -> None:
    if not (-90.0 <= latitude <= 90.0):
        raise InvalidCoordinatesError(VALIDATION_INVALID_COORDINATES)
    if not (-180.0 <= longitude <= 180.0):
        raise InvalidCoordinatesError(VALIDATION_INVALID_COORDINATES)


def validate_accuracy(accuracy: float | None) -> None:
    if accuracy is not None and accuracy < 0:
        raise InvalidCoordinatesError(VALIDATION_INVALID_COORDINATES)


def is_duplicate_location(
    new_lat: float,
    new_lon: float,
    existing_lat: float,
    existing_lon: float,
    threshold_meters: float = DUPLICATE_DISTANCE,
) -> bool:
    distance = haversine_distance_meters(
        new_lat, new_lon, existing_lat, existing_lon
    )
    return distance < threshold_meters


def validate_manual_location_rate_limit(
    db: Session, user_id: int, max_per_hour: int = MANUAL_LOCATION_PER_HOUR
):
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    
    count = (
        db.query(UserLocation)
        .filter(
            UserLocation.user_id == user_id,
            UserLocation.source == "manual",
            UserLocation.created_at >= one_hour_ago,
        )
        .count()
    )
    
    return count < max_per_hour
