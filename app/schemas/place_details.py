from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class OpeningHoursPeriod(BaseModel):

    open_day: Optional[int] = None
    open_hour: Optional[int] = None
    open_minute: Optional[int] = None
    close_day: Optional[int] = None
    close_hour: Optional[int] = None
    close_minute: Optional[int] = None


class OpeningHours(BaseModel):

    open_now: Optional[bool] = None
    weekday_descriptions: Optional[List[str]] = None
    periods: Optional[List[OpeningHoursPeriod]] = None


class PlacePhoto(BaseModel):

    name: Optional[str] = None  # resource name: "places/{id}/photos/{ref}"
    width_px: Optional[int] = None
    height_px: Optional[int] = None


class PlaceReview(BaseModel):

    author_name: Optional[str] = None
    rating: Optional[float] = None
    text: Optional[str] = None
    publish_time: Optional[str] = None
    relative_publish_time_description: Optional[str] = None


class PlaceDetailResult(BaseModel):
    place_id: str
    display_name: Optional[str] = None
    formatted_address: Optional[str] = None

    latitude: Optional[float] = None
    longitude: Optional[float] = None

    primary_type: Optional[str] = None
    types: Optional[List[str]] = None

    international_phone_number: Optional[str] = None
    national_phone_number: Optional[str] = None
    website_uri: Optional[str] = None
    google_maps_uri: Optional[str] = None

    rating: Optional[float] = None
    user_rating_count: Optional[int] = None

    business_status: Optional[str] = None
    opening_hours: Optional[OpeningHours] = None
    open_now: Optional[bool] = None

    photos: Optional[List[PlacePhoto]] = None
    reviews: Optional[List[PlaceReview]] = None

    price_level: Optional[str] = None
    wheelchair_accessible_entrance: Optional[bool] = None

    editorial_summary: Optional[str] = None

    extended_data: Optional[Dict[str, Any]] = None

    last_fetched_at: Optional[datetime] = None
    knowledge_synced: Optional[bool] = None

    is_visit: bool = False

    model_config = {"from_attributes": True}


class PlaceDetailsResponse(BaseModel):

    success: bool
    source: str
    message: str
    data: PlaceDetailResult
    cached: bool
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DetailSource(str, Enum):
    GOOGLE = "google_places"
    REDIS = "redis_cache"
    DATABASE = "database"
