from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.database.base import Base


class PlaceAnswerLog(Base):
    __tablename__ = "place_answer_logs"

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(
        Integer,
        ForeignKey("place_questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    session_id = Column(
        String(36),
        ForeignKey("place_qa_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    user_id = Column(Integer, nullable=False, index=True)
    place_id = Column(String(255), nullable=False, index=True)
    answer_text = Column(Text, nullable=False)
    confidence_score = Column(Float, nullable=True)
    answer_source = Column(String(20), nullable=False, default="rag")
    grounding_chunks = Column(JSONB, nullable=True)
    context_tokens = Column(Integer, nullable=True)
    model_used = Column(String(100), nullable=True)
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
