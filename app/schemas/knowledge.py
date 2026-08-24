from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class SyncStatus(str, Enum):
    PENDING = "pending"
    SYNCED = "synced"
    FAILED = "failed"


class KnowledgeChunk(BaseModel):
    chunk_id: str
    section: str
    text: str
    vector_dimension: int


class KnowledgeSyncRequest(BaseModel):
    force_resync: bool = Field(
        default=False,
    )


class KnowledgeSyncResponse(BaseModel):
    success: bool
    place_id: str
    sync_status: str
    message: str

    vector_count: Optional[int] = None
    pinecone_namespace: Optional[str] = None
    source_version: Optional[str] = None
    chunks: Optional[List[KnowledgeChunk]] = None

    skipped: bool = False
    skip_reason: Optional[str] = None

    synced_at: Optional[datetime] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
