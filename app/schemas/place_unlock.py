from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field


class PlaceUnlockResponse(BaseModel):

    success: bool = True
    message: str = "Place unlocked successfully"
    place_id: str
    tokens_spent: int
    remaining_credits: int
    category: str
    questions_limit: int = Field(default=15)
    questions_used: int = Field(default=0)
    questions_remaining: int = Field(default=15)
    is_unlocked: bool = Field(default=True)


class UnlockedPlaceItem(BaseModel):

    place_id: str
    display_name: Optional[str] = None
    formatted_address: Optional[str] = None
    category: str
    tokens_spent: int
    unlocked_at: datetime
    questions_used: int = Field()
    questions_limit: int = Field()
    is_expired: bool = Field()
    expired_at: Optional[datetime] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class UnlockedPlacesListResponse(BaseModel):

    success: bool = True
    message: str = "Unlocked places retrieved successfully"
    data: List[UnlockedPlaceItem]
    total: int
    page: int
    page_size: int
    has_next: bool
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
