from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field


class LogVisitRequest(BaseModel):

    rating_given: Optional[float] = Field(
        None,
        ge=1,
        le=5,
    )
    review_text: Optional[str] = Field(None, max_length=2000)


class UpdateVisitRequest(BaseModel):
    rating_given: Optional[float] = Field(
        None,
        ge=1,
        le=5,
    )
    review_text: Optional[str] = Field(None, max_length=2000)


class UpdatedVisitData(BaseModel):
    id: int
    place_id: str
    display_name: Optional[str] = None
    formatted_address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    rating_given: Optional[float] = None
    review_text: Optional[str] = None
    visited_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class VisitLogResponse(BaseModel):

    id: int
    place_id: str
    display_name: Optional[str] = None
    formatted_address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    rating_given: Optional[float] = None
    review_text: Optional[str] = None
    with_whom: Optional[str] = None
    mood: Optional[str] = None
    visited_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ListVisitsResponse(BaseModel):

    success: bool = True
    message: str = "Visits retrieved successfully"
    data: List[VisitLogResponse]
    total_count: int
    page: int
    page_size: int
    has_next: bool
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class VisitStatsResponse(BaseModel):

    success: bool = True
    total_visits: int
    unique_places: int
    by_category: dict = Field(default_factory=dict)
    by_month: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LogVisitActionResponse(BaseModel):

    success: bool = True
    message: str
    place_id: str
    visit_id: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DeleteVisitResponse(BaseModel):

    success: bool = True
    message: str
    visit_id: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class UpdateVisitResponse(BaseModel):

    success: bool = True
    message: str
    visit_id: int
    data: UpdatedVisitData
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
