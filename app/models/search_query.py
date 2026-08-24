from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.sql import func
from app.database.base import Base


class SearchQuery(Base):

    __tablename__ = "search_queries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    search_mode = Column(String(10), nullable=False)
    resolved_mode = Column(String(10), nullable=True)
    raw_query = Column(Text, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    radius = Column(Float, nullable=True)
    result_count = Column(Integer, nullable=True, default=0)
    from_cache = Column(Boolean, nullable=False, default=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )

    __table_args__ = (Index("ix_search_queries_user_created", "user_id", "created_at"),)
