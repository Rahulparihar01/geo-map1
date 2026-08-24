from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.sql import func
from app.database.base import Base


class PlaceQuestion(Base):
    __tablename__ = "place_questions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    place_id = Column(String(255), nullable=False, index=True)
    question_text = Column(Text, nullable=False)

    session_id = Column(
        String(36),
        ForeignKey("place_qa_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    knowledge_available = Column(Boolean, nullable=False, default=False)
    pinecone_matches = Column(Integer, nullable=True, default=0)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
        nullable=False,
    )
