import uuid
from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database.base import Base


class PlaceQASession(Base):
    __tablename__ = "place_qa_sessions"

    id = Column(
        String(36),
        primary_key=True,
        index=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id = Column(Integer, nullable=False, index=True)
    place_id = Column(String(255), nullable=True, index=True)
    title = Column(String(255), nullable=False, default="New Q&A")
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    last_message_at = Column(DateTime(timezone=True), nullable=True, index=True)
    is_deleted = Column(Boolean, nullable=False, default=False)
    messages = relationship(
        "PlaceQAMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="PlaceQAMessage.created_at",
    )

    def __repr__(self) -> str:
        return (
            f"<PlaceQASession(id={self.id!r}, user_id={self.user_id!r}, "
            f"place_id={self.place_id!r}, title={self.title!r})>"
        )
