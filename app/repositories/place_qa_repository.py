import logging
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import and_, desc, func
from sqlalchemy.orm import Session
from app.models.place_answer_log import PlaceAnswerLog
from app.models.place_question import PlaceQuestion
from app.models.place_qa_session import PlaceQASession
from app.models.place_qa_message import PlaceQAMessage

logger = logging.getLogger(__name__)


class PlaceQARepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_session(
        self,
        *,
        user_id: int,
        place_id: Optional[str] = None,
        title: str = "New Q&A",
    ) -> PlaceQASession:
        session = PlaceQASession(
            user_id=user_id,
            place_id=place_id,
            title=title,
        )
        self.db.add(session)
        self.db.flush()
        logger.info(
            "Created Place Q&A session id=%r for user_id=%s, place_id=%s",
            session.id,
            user_id,
            place_id,
        )
        return session

    def get_session(self, session_id: str, user_id: int) -> Optional[PlaceQASession]:
        return (
            self.db.query(PlaceQASession)
            .filter(
                and_(
                    PlaceQASession.id == session_id,
                    PlaceQASession.user_id == user_id,
                    PlaceQASession.is_deleted.is_(False),
                )
            )
            .first()
        )

    def get_session_with_messages(
        self, session_id: str, user_id: int, limit: int = 50, offset: int = 0
    ) -> Optional[PlaceQASession]:
        session = self.get_session(session_id, user_id)
        if not session:
            return None

        messages = (
            self.db.query(PlaceQAMessage)
            .filter(PlaceQAMessage.session_id == session_id)
            .order_by(PlaceQAMessage.created_at.asc())
            .limit(limit)
            .offset(offset)
            .all()
        )

        session.messages = messages
        return session

    def list_sessions(
        self,
        user_id: int,
        place_id: Optional[str] = None,
        search: Optional[str] = None,
        sort_by: str = "last_message",
        limit: int = 10,
        offset: int = 0,
    ) -> Tuple[List[PlaceQASession], int]:
        query = self.db.query(PlaceQASession).filter(
            and_(
                PlaceQASession.user_id == user_id,
                PlaceQASession.is_deleted.is_(False),
            )
        )

        if place_id:
            query = query.filter(PlaceQASession.place_id == place_id)

        if search:
            query = query.filter(PlaceQASession.title.ilike(f"%{search}%"))

        total = query.count()

        if sort_by == "created_at":
            query = query.order_by(desc(PlaceQASession.created_at))
        elif sort_by == "title":
            query = query.order_by(PlaceQASession.title.asc())
        else:
            query = query.order_by(
                desc(PlaceQASession.last_message_at),
                desc(PlaceQASession.created_at),
            )

        sessions = query.limit(limit).offset(offset).all()
        return sessions, total

    def update_session_timestamp(self, session: PlaceQASession) -> None:
        last_msg = (
            self.db.query(func.max(PlaceQAMessage.created_at))
            .filter(PlaceQAMessage.session_id == session.id)
            .scalar()
        )
        session.last_message_at = last_msg
        self.db.flush()

    def bulk_delete_sessions(self, session_ids: List[str], user_id: int) -> List[str]:
        sessions = (
            self.db.query(PlaceQASession)
            .filter(
                and_(
                    PlaceQASession.id.in_(session_ids),
                    PlaceQASession.user_id == user_id,
                    PlaceQASession.is_deleted.is_(False),
                )
            )
            .all()
        )

        deleted_ids: List[str] = []
        for session in sessions:
            session.is_deleted = True
            deleted_ids.append(session.id)

        self.db.flush()
        logger.info("Bulk deleted %d sessions for user %s", len(deleted_ids), user_id)
        return deleted_ids

    def create_message(
        self,
        *,
        session_id: str,
        role: str,
        content: str,
        token_count: Optional[int] = None,
        metadata_json: Optional[Dict[str, Any]] = None,
    ) -> PlaceQAMessage:
        message = PlaceQAMessage(
            session_id=session_id,
            role=role,
            content=content,
            token_count=token_count,
            metadata_json=metadata_json,
        )
        self.db.add(message)
        self.db.flush()
        logger.debug(
            "Created Place Q&A message id=%s in session_id=%r, role=%s",
            message.id,
            session_id,
            role,
        )
        return message

    def get_recent_messages(
        self,
        session_id: str,
        limit: int = 10,
    ) -> List[PlaceQAMessage]:
        return (
            self.db.query(PlaceQAMessage)
            .filter(PlaceQAMessage.session_id == session_id)
            .order_by(desc(PlaceQAMessage.created_at))
            .limit(limit)
            .all()
        )[::-1]

    def count_session_messages(
        self,
        session_id: str,
    ) -> int:
        return (
            self.db.query(func.count(PlaceQAMessage.id))
            .filter(PlaceQAMessage.session_id == session_id)
            .scalar()
        ) or 0

    def get_last_message_preview(self, session_id: str) -> Optional[str]:
        last_msg = (
            self.db.query(PlaceQAMessage.content)
            .filter(PlaceQAMessage.session_id == session_id)
            .order_by(desc(PlaceQAMessage.created_at))
            .first()
        )
        return last_msg[0] if last_msg else None

    def count_user_sessions(self, user_id: int) -> int:
        return (
            self.db.query(func.count(PlaceQASession.id))
            .filter(
                and_(
                    PlaceQASession.user_id == user_id,
                    PlaceQASession.is_deleted.is_(False),
                )
            )
            .scalar()
        ) or 0

    def create_question(
        self,
        *,
        user_id: int,
        place_id: str,
        question_text: str,
        knowledge_available: bool,
        pinecone_matches: int,
        session_id: Optional[str] = None,
    ) -> PlaceQuestion:
        record = PlaceQuestion(
            user_id=user_id,
            place_id=place_id,
            question_text=question_text,
            knowledge_available=knowledge_available,
            pinecone_matches=pinecone_matches,
            session_id=session_id,
        )
        self.db.add(record)
        self.db.flush()
        logger.debug(
            "PlaceQuestion flushed: id=%s user=%s place=%s knowledge=%s session=%r",
            record.id,
            user_id,
            place_id,
            knowledge_available,
            session_id,
        )
        return record

    def create_answer_log(
        self,
        *,
        question_id: int,
        user_id: int,
        place_id: str,
        answer_text: str,
        confidence_score: Optional[float],
        answer_source: str,
        grounding_chunks: Optional[List[Dict[str, Any]]],
        context_tokens: Optional[int],
        model_used: str,
        latency_ms: Optional[int],
        session_id: Optional[str] = None,
    ) -> PlaceAnswerLog:
        record = PlaceAnswerLog(
            question_id=question_id,
            user_id=user_id,
            place_id=place_id,
            answer_text=answer_text,
            confidence_score=confidence_score,
            answer_source=answer_source,
            grounding_chunks=grounding_chunks,
            context_tokens=context_tokens,
            model_used=model_used,
            latency_ms=latency_ms,
            session_id=session_id,
        )
        self.db.add(record)
        self.db.flush()
        logger.debug(
            "PlaceAnswerLog flushed: question_id=%s source=%s confidence=%s session=%r",
            question_id,
            answer_source,
            confidence_score,
            session_id,
        )
        return record

