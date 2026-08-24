from datetime import datetime, timezone
from typing import Any, List, Optional
from pydantic import BaseModel, Field, field_validator


class GPSUpdateRequest(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    accuracy: Optional[float] = Field(None, ge=0)
    client_timestamp: Optional[datetime] = Field(None)
    metadata_notes: Optional[str] = Field(None, max_length=500)

    @field_validator("accuracy")
    @classmethod
    def round_accuracy(cls, value):
        if value is not None:
            return round(value, 2)
        return value


class ManualLocationRequest(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    address: Optional[str] = Field(None, max_length=500)
    metadata_notes: Optional[str] = Field(None, max_length=500)


class UnifiedLocationResponse(BaseModel):
    latitude: float
    longitude: float
    accuracy: Optional[float] = None
    location_type: str
    address: Optional[str] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class LocationHistoryItem(BaseModel):
    id: int
    latitude: float
    longitude: float
    accuracy: Optional[float] = None
    location_type: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PaginatedHistoryResponse(BaseModel):
    items: List[LocationHistoryItem]
    total: int
    page: int
    page_size: int
    has_next: bool


class LocationSearchResult(BaseModel):
    name: str
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class LocationSearchResponse(BaseModel):
    results: List[LocationSearchResult] = []


class ReverseGeocodeRequest(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    language_code: str = Field(
        default="en",
        max_length=5,
        description="Language code for the address (e.g., 'en', 'hi', 'mr').",
    )


class ReverseGeocodeResponse(BaseModel):
    latitude: float
    longitude: float
    address: str


class APIResponse(BaseModel):

    success: bool
    message: str
    data: Optional[Any] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
