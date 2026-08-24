from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Text,
)
from sqlalchemy.sql import func

from app.database.base import Base


class PlaceKnowledgeSync(Base):
    __tablename__ = "place_knowledge_sync"

    id = Column(Integer, primary_key=True, index=True)
    place_id = Column(String(255), nullable=False, unique=True, index=True)
    sync_status = Column(String(10), nullable=False, default="pending", index=True)
    vector_count = Column(Integer, nullable=True, default=0)
    pinecone_namespace = Column(String(300), nullable=True)
    source_version = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    synced_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
    )
