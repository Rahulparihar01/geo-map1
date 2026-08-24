from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator

from app.utils.session_id import validate_uuid4


class AnswerSource(str, Enum):
    RAG = "rag"
    STRUCTURED_ONLY = "structured_only"
    FALLBACK = "fallback"


class GroundingFragment(BaseModel):

    section: str
    text: str
    similarity_score: float
    source_type: str


class PlaceQuestionRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=3,
        max_length=1000,
    )
    session_id: Optional[str] = Field(
        default=None,
    )
    @field_validator("session_id", mode="before")
    @classmethod
    def validate_session_id(cls, v):
        return validate_uuid4(v)


class TechnicalMetadata(BaseModel):

    answer_source: str
    confidence_score: Optional[float] = None
    knowledge_synced: bool
    pinecone_matches: int
    model_used: str
    context_tokens: Optional[int] = None
    grounding_fragments: Optional[List[GroundingFragment]] = None


class PlaceQuestionResponse(BaseModel):
    success: bool = True
    session_id: str
    answer: str

    title: Optional[str] = None
    is_new_session: bool = False
    fallback: bool = False
    fallback_reason: Optional[str] = None
    
    credits_deducted: int = 0
    remaining_credits: int = 0

    metadata: Optional[TechnicalMetadata] = None

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PlaceQAMessageSchema(BaseModel):
    id: int
    role: str = Field(...)
    content: str
    created_at: datetime
    token_count: Optional[int] = None

    class Config:
        from_attributes = True


class PlaceInfo(BaseModel):
    place_id: str
    name: Optional[str] = None
    address: Optional[str] = None


class PlaceQASessionListItem(BaseModel):
    session_id: str
    place: Optional[PlaceInfo] = None
    title: str
    last_message: Optional[str] = None
    message_count: int = 0
    last_message_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class PlaceQASessionDetail(BaseModel):
    session_id: str
    place: Optional[PlaceInfo] = None
    title: str
    message_count: int
    created_at: datetime
    updated_at: datetime
    last_message_at: Optional[datetime] = None
    messages: List[PlaceQAMessageSchema] = Field(default_factory=list)

    class Config:
        from_attributes = True


class ListPlaceQASessionsResponse(BaseModel):
    success: bool = True
    message: str = "Sessions retrieved successfully"
    sessions: List[PlaceQASessionListItem]
    total_count: int
    page: int
    page_size: int
    has_next: bool
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GetPlaceQASessionResponse(BaseModel):
    success: bool = True
    session: PlaceQASessionDetail
    total_messages: int
    page: int
    page_size: int
    has_next: bool


class DeletePlaceQASessionResponse(BaseModel):

    success: bool = True
    message: str = "Session deleted successfully"
    deleted_session_ids: List[str]


class DeletePlaceQASessionsRequest(BaseModel):

    session_ids: List[str] = Field(
        ..., min_length=1
    )

