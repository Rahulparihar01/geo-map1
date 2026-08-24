from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.database.base import Base


class PlaceCategoryPrice(Base):

    __tablename__ = "place_category_prices"

    id = Column(Integer, primary_key=True, index=True)

    category = Column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="Category key: tourist_attraction, restaurant, shopping_mall",
    )
    category_label = Column(
        String(100),
        nullable=False,
        comment="Human-readable label: 'Tourist Places & Attractions'",
    )
    description = Column(
        Text, nullable=True, comment="Description of what's included in this category"
    )

    token_cost = Column(
        Integer,
        nullable=False,
        comment="Number of tokens required to unlock places in this category (currently 10 for all)",
    )
    questions_limit = Column(
        Integer,
        default=15,
        nullable=False,
        comment="Number of questions allowed per unlock before re-unlock required",
    )

    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
        comment="Whether this category pricing is currently active",
    )

    created_at = Column(
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
            f"<PlaceCategoryPrice(category={self.category!r}, "
            f"cost={self.token_cost}, limit={self.questions_limit}, active={self.is_active})>"
        )
