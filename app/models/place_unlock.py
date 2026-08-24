from sqlalchemy import Boolean, Column, DateTime, Float, Index, Integer, String
from sqlalchemy.sql import func

from app.database.base import Base


class PlaceUnlock(Base):

    __tablename__ = "place_unlocks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    place_id = Column(String(255), nullable=False, index=True)

    category = Column(
        String(50),
        nullable=False,
        comment="Place category: tourist_attraction, restaurant, shopping_mall",
    )
    tokens_spent = Column(
        Integer,
        nullable=False,
        comment="Number of tokens deducted for this unlock (always 10)",
    )

    questions_used = Column(
        Integer,
        default=0,
        nullable=False,
        comment="Number of Place Q&A questions asked about this place",
    )
    questions_limit = Column(
        Integer,
        default=15,
        nullable=False,
        comment="Maximum questions allowed before re-unlock required",
    )
    is_expired = Column(
        Boolean,
        default=False,
        nullable=False,
        comment="True when questions_used >= questions_limit",
    )

    display_name = Column(String(500), nullable=True)
    formatted_address = Column(String(1000), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    unlocked_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    expired_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the unlock expired (after 15 questions)",
    )

    __table_args__ = (
        Index(
            "ix_place_unlocks_user_place_active", "user_id", "place_id", "is_expired"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<PlaceUnlock(user_id={self.user_id}, place_id={self.place_id!r}, "
            f"questions={self.questions_used}/{self.questions_limit}, expired={self.is_expired})>"
        )
