from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field


class SavePlaceRequest(BaseModel):

    notes: Optional[str] = Field(None, max_length=500)
    tags: Optional[List[str]] = Field(None)


class SavedPlaceResponse(BaseModel):

    id: int
    place_id: str
    display_name: Optional[str] = None
    formatted_address: Optional[str] = None
    primary_type: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    rating: Optional[float] = None
    saved_location_lat: Optional[float] = Field(None)
    saved_location_lon: Optional[float] = Field(None)
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    saved_at: datetime
    updated_at: Optional[datetime] = None
    is_unlocked: bool = False
    is_visit: bool = False

    model_config = {"from_attributes": True}


class ListSavedPlacesResponse(BaseModel):
    success: bool = True
    message: str = "Saved places retrieved successfully"
    data: List[SavedPlaceResponse]
    total_count: int
    page: int
    page_size: int
    has_next: bool
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SavePlaceActionResponse(BaseModel):

    success: bool = True
    message: str
    place_id: str
    saved: bool
    saved_id: Optional[int] = Field(None)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
