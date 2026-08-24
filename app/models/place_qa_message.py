from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database.base import Base


class PlaceQAMessage(Base):
    __tablename__ = "place_qa_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        String(36),
        ForeignKey("place_qa_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    token_count = Column(Integer, nullable=True)
    metadata_json = Column(JSONB, nullable=True)
    session = relationship("PlaceQASession", back_populates="messages")

    def __repr__(self) -> str:
        return (
            f"<PlaceQAMessage(id={self.id}, session_id={self.session_id!r}, "
            f"role={self.role!r})>"
        )
