from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.sql import func
from app.database.base import Base


class SearchResult(Base):

    __tablename__ = "search_results"

    id = Column(Integer, primary_key=True, index=True)
    query_id = Column(
        Integer,
        ForeignKey("search_queries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(Integer, nullable=False, index=True)

    place_id = Column(String(255), nullable=False, index=True)
    display_name = Column(String(500), nullable=True)
    formatted_address = Column(Text, nullable=True)
    primary_type = Column(String(100), nullable=True)

    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    rating = Column(Float, nullable=True)
    user_rating_count = Column(Integer, nullable=True)
    business_status = Column(String(50), nullable=True)

    rank_position = Column(Integer, nullable=False, default=0)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
