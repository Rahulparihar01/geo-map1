from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator

from app.utils.session_id import validate_uuid4


class AIChatResponse(BaseModel):
    success: bool = True
    session_id: str
    answer: str
    is_new_session: bool = False
    title: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error_type: Optional[str] = None  
    credits_remaining: Optional[int] = None  


class AIChatStartRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    session_id: Optional[str] = Field(default=None)

    @field_validator("session_id", mode="before")
    @classmethod
    def validate_session_id(cls, v):
        return validate_uuid4(v)


class AIChatSessionListItem(BaseModel):
    session_id: str
    title: str
    message_count: int = 0
    last_message_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AIChatSessionListResponse(BaseModel):
    success: bool = True
    sessions: List[AIChatSessionListItem]
    total_count: int
    page: int
    page_size: int
    has_next: bool
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AIChatSessionDeleteResponse(BaseModel):
    success: bool = True
    message: str = "Chat session deleted successfully"
    session_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
