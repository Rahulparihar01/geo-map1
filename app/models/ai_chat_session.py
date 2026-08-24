import uuid
import sqlalchemy as sa
from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database.base import Base


class AIChatSession(Base):
    __tablename__ = "ai_chat_sessions"
    id = Column(
        String(36),
        primary_key=True,
        index=True,
        default=lambda: str(uuid.uuid4()),
    )

    user_id = Column(Integer, nullable=False, index=True)
    title = Column(String(255), nullable=False, default="New Chat")
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
    is_archived = Column(
        Boolean, nullable=False, default=False, server_default=sa.text("false")
    )
    messages = relationship(
        "AIChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="AIChatMessage.created_at",
    )

    def __repr__(self) -> str:
        return f"<AIChatSession(id={self.id!r}, user_id={self.user_id}, title='{self.title}')>"
