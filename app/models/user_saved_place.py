from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.database.base import Base


class UserSavedPlace(Base):
    __tablename__ = "user_saved_places"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    place_id = Column(String(255), nullable=False, index=True)

    display_name = Column(String(500), nullable=True)
    formatted_address = Column(Text, nullable=True)
    primary_type = Column(String(100), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    rating = Column(Float, nullable=True)
    saved_location_lat = Column(Float, nullable=True)
    saved_location_lon = Column(Float, nullable=True)
    notes = Column(Text, nullable=True, comment="User's personal note about this place")
    tags = Column(
        JSONB,
        nullable=True,
        comment='e.g. ["want_to_visit", "favorite", "recommended"]',
    )
    is_archived = Column(Boolean, default=False, nullable=False)

    saved_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )

    __table_args__ = (Index("ix_user_saved_places_user_place", "user_id", "place_id"),)

    def __repr__(self) -> str:
        return (
            f"<UserSavedPlace(id={self.id}, user_id={self.user_id}, "
            f"place_id={self.place_id!r}, saved_at={self.saved_at})>"
        )
