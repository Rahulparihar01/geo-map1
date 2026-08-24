from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func
from app.database.base import Base


class PlaceVisitLog(Base):
    __tablename__ = "place_visit_logs"

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

    rating_given = Column(
        Float,
        nullable=True,
        comment="User's personal rating 1-5 (supports decimal values)",
    )
    review_text = Column(Text, nullable=True, comment="User's personal notes/review")
    with_whom = Column(
        String(100),
        nullable=True,
        comment="Context: 'family', 'friends', 'solo', 'partner'",
    )
    mood = Column(
        String(50),
        nullable=True,
        comment="Feeling: 'romantic', 'fun', 'quiet', 'adventurous'",
    )

    visited_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<PlaceVisitLog(id={self.id}, user_id={self.user_id}, "
            f"place_id={self.place_id!r}, visited_at={self.visited_at})>"
        )
