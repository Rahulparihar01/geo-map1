from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database.base import Base


class AIChatMessage(Base):
    __tablename__ = "ai_chat_messages"

    id = Column(Integer, primary_key=True, index=True)

    session_id = Column(
        String(36),
        ForeignKey("ai_chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    token_count = Column(Integer, nullable=True)
    model_used = Column(String(100), nullable=True)
    session = relationship("AIChatSession", back_populates="messages")

    def __repr__(self) -> str:
        return f"<AIChatMessage(id={self.id}, session_id={self.session_id!r}, role='{self.role}')>"
