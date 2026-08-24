import re
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


def _reject_float_int(value, field_name: str):
    if isinstance(value, float):
        raise ValueError(
            f"{field_name} must be a whole number (integer). "
            f"Decimal values are not supported."
        )
    return value


class DiscoveryCategory(str, Enum):
    EXPLORE = "explore"
    TOURIST = "tourist"
    RESTAURANT = "restaurant"
    SHOPPING = "shopping"
    PARKING = "parking"


class LocationBias(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    radius: float = Field(default=5000.0, ge=1.0, le=50000.0)
    
    @field_validator("latitude", "longitude", mode="after")
    @classmethod
    def validate_not_pole(cls, v, info):
        if abs(v) == 90.0 or abs(v) == 180.0:
            field_name = info.field_name
            raise ValueError(
                f"{field_name} cannot be at extreme poles (±90 for latitude, ±180 for longitude). "
                f"Please provide a valid location within normal range."
            )
        return v


class TextSearchRequest(BaseModel):
    text_query: str = Field(..., min_length=1, max_length=500)
    max_result_count: int = Field(default=20, ge=1, le=20)
    open_now: Optional[bool] = None
    location_bias: Optional[LocationBias] = None
    use_user_location_as_bias: bool = True

    @field_validator("max_result_count", mode="before")
    @classmethod
    def reject_float_max_result_count(cls, v):
        return _reject_float_int(v, "max_result_count")

    @field_validator("text_query")
    @classmethod
    def sanitize_text_query(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("text_query must not be empty")

        v = v.replace("\x00", "")

        dangerous_patterns = ["--", "/*", "*/", ";--", "';", '";']
        for pattern in dangerous_patterns:
            v = v.replace(pattern, " ")

        v = re.sub(r"\s+", " ", v)

        return v.strip()


class NearbyDiscoveryRequest(BaseModel):
    category: DiscoveryCategory = DiscoveryCategory.EXPLORE
    subcategories: Optional[List[str]] = Field(default=None)
    radius: float = Field(default=500.0, ge=100.0, le=50000.0)
    max_result_count: int = Field(default=20, ge=1, le=20)

    @field_validator("max_result_count", mode="before")
    @classmethod
    def reject_float_max_result_count(cls, v):
        return _reject_float_int(v, "max_result_count")

    @field_validator("subcategories")
    @classmethod
    def validate_subcategories(cls, v: Optional[List[str]], info) -> Optional[List[str]]:
        if not v:
            return None
        from app.utils.place_categories import SUBCATEGORIES
        category = info.data.get("category")
        if category is None:
            return v
        valid = SUBCATEGORIES.get(category.value, [])
        cleaned = []
        for item in v:
            item = item.strip().lower()
            if not item:
                continue
            if item not in valid:
                raise ValueError(
                    f"Subcategory '{item}' is not valid for category '{category.value}'. "
                    f"Valid options: {', '.join(valid)}"
                )
            cleaned.append(item)
        return cleaned or None

    @property
    def has_fine_dining(self) -> bool:
        return self.subcategories is not None and "fine_dining" in self.subcategories

    @property
    def subcategory_display(self) -> str:
        if not self.subcategories:
            return "none"
        return ",".join(self.subcategories)


class DiscoveryPlaceResult(BaseModel):
    place_id: Optional[str] = None
    display_name: Optional[str] = None
    formatted_address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    rating: Optional[float] = None
    user_rating_count: Optional[int] = None
    primary_type: Optional[str] = None
    types: Optional[List[str]] = None
    business_status: Optional[str] = None
    google_maps_uri: Optional[str] = None
    open_now: Optional[bool] = None
    price_level: Optional[str] = None
    first_photo_name: Optional[str] = None
    is_locked: bool = True
    is_visit: bool = False
    assigned_category: Optional[str] = None
    assigned_subcategory: Optional[str] = None
    is_duplicate: bool = False


class AutocompletePrediction(BaseModel):
    place_id: str
    main_text: str
    secondary_text: str
    full_text: str
    types: List[str]


class AutocompleteResponse(BaseModel):

    success: bool
    message: str
    input: str
    predictions: List[AutocompletePrediction]
    total_predictions: int
    cached: bool
    bias_latitude: Optional[float] = None
    bias_longitude: Optional[float] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TextSearchResponse(BaseModel):

    success: bool
    search_mode: str
    message: str
    data: List[DiscoveryPlaceResult]
    total_results: int
    cached: bool
    query: Optional[str] = None
    search_latitude: Optional[float] = None
    search_longitude: Optional[float] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class NearbyDiscoveryResponse(BaseModel):

    success: bool
    search_mode: str
    message: str
    data: List[DiscoveryPlaceResult]
    total_results: int
    cached: bool
    search_latitude: float
    search_longitude: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))