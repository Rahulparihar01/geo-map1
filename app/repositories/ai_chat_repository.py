import logging
from datetime import datetime
from typing import List, Optional
from sqlalchemy import and_, desc, func
from sqlalchemy.orm import Session
from app.models.ai_chat_message import AIChatMessage
from app.models.ai_chat_session import AIChatSession

logger = logging.getLogger(__name__)


class AIChatRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_session(self, *, user_id: int, title: str = "New Chat") -> AIChatSession:
        session = AIChatSession(user_id=user_id, title=title)
        self.db.add(session)
        self.db.flush()
        logger.info("Created AIChatSession id=%r for user_id=%s", session.id, user_id)
        return session

    def get_session(self, *, session_id: str, user_id: int) -> Optional[AIChatSession]:
        return (
            self.db.query(AIChatSession)
            .filter(
                and_(
                    AIChatSession.id == session_id,
                    AIChatSession.user_id == user_id,
                )
            )
            .first()
        )

    def count_user_sessions(self, *, user_id: int) -> int:
        return (
            self.db.query(func.count(AIChatSession.id))
            .filter(
                and_(
                    AIChatSession.user_id == user_id,
                    AIChatSession.is_archived.is_(False),
                )
            )
            .scalar()
            or 0
        )

    def update_session_timestamp_direct(self, *, session: AIChatSession, 
                                       timestamp: datetime) -> None:
        session.last_message_at = timestamp
        self.db.flush()
        logger.debug("Updated session %s timestamp to %s (direct, no query)", 
                     session.id, timestamp)

    def list_sessions(
        self, *, user_id: int, limit: int = 20, offset: int = 0
    ) -> tuple:
        query = self.db.query(AIChatSession).filter(
            and_(
                AIChatSession.user_id == user_id,
                AIChatSession.is_archived.is_(False),
            )
        )
        total = query.count()
        sessions = (
            query.order_by(desc(AIChatSession.last_message_at))
            .limit(limit)
            .offset(offset)
            .all()
        )
        return sessions, total

    def archive_session(self, *, session: AIChatSession) -> None:
        session.is_archived = True
        self.db.flush()

    def count_session_messages(self, *, session_id: str) -> int:
        return (
            self.db.query(func.count(AIChatMessage.id))
            .filter(AIChatMessage.session_id == session_id)
            .scalar()
            or 0
        )

    def add_message(
        self,
        *,
        session_id: str,
        role: str,
        content: str,
        token_count: Optional[int] = None,
        model_used: Optional[str] = None,
    ) -> AIChatMessage:
        msg = AIChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            token_count=token_count,
            model_used=model_used,
        )
        self.db.add(msg)
        self.db.flush()
        return msg

    def get_recent_messages(self, *, session_id: str, limit: int = 10) -> List[AIChatMessage]:
        return (
            self.db.query(AIChatMessage)
            .filter(AIChatMessage.session_id == session_id)
            .order_by(desc(AIChatMessage.created_at))
            .limit(limit)
            .all()
        )[::-1]

