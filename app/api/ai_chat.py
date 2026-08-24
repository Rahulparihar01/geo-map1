import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.rate_limiter import shared_limiter as limiter
from app.database.connection import get_db
from app.dependencies.auth import get_current_user
from app.exceptions.custom_exceptions import BadRequestError, NotFoundError
from app.integrations.openai_client import OpenAIEmbeddingClient
from app.models.user import User
from app.repositories.ai_chat_repository import AIChatRepository
from app.schemas.ai_chat import (
    AIChatResponse,
    AIChatSessionDeleteResponse,
    AIChatSessionListResponse,
    AIChatSessionListItem,
    AIChatStartRequest,
)
from app.services.ai_chat_service import AIChatService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["Travel Agent"])


@router.get("/sessions", response_model=AIChatSessionListResponse)
@limiter.limit("30/minute")
async def list_chat_sessions(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = AIChatRepository(db)
    sessions, total = repo.list_sessions(
        user_id=current_user.id,
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    items = [
        AIChatSessionListItem(
            session_id=s.id,
            title=s.title,
            message_count=repo.count_session_messages(session_id=s.id),
            last_message_at=s.last_message_at,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in sessions
    ]
    return AIChatSessionListResponse(
        sessions=items,
        total_count=total,
        page=page,
        page_size=page_size,
        has_next=(page * page_size) < total,
    )


@router.delete("/sessions/{session_id}", response_model=AIChatSessionDeleteResponse)
@limiter.limit("30/minute")
async def delete_chat_session(
    request: Request,
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = AIChatRepository(db)
    session = repo.get_session(session_id=session_id, user_id=current_user.id)
    if session is None:
        raise NotFoundError("Chat session not found")
    repo.archive_session(session=session)
    db.commit()
    logger.info(
        "Chat session deleted — user_id=%s session_id=%s",
        current_user.id,
        session_id,
    )
    return AIChatSessionDeleteResponse(session_id=session_id)


@router.post("/message", response_model=AIChatResponse)
@limiter.limit("30/minute")
async def chat_message(
    request: Request,
    payload: AIChatStartRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session_id: Optional[str] = payload.session_id
    session_id_header = request.headers.get("X-Chat-Session-Id")
    if session_id_header:
        header_sid = session_id_header.strip() or None
        if header_sid and session_id is not None and header_sid != session_id:
            logger.warning(
                "X-Chat-Session-Id header (%s) overrides body session_id (%s) "
                "for user_id=%s",
                header_sid,
                session_id,
                current_user.id,
            )
        session_id = header_sid

    if session_id is not None:
        session_id = session_id.strip()
        if session_id == "":
            session_id = None

    if session_id is not None:
        try:
            uuid.UUID(session_id)
        except (ValueError, AttributeError):
            raise BadRequestError("Invalid chat session")

    openai_client: OpenAIEmbeddingClient = getattr(request.app.state, "openai_client")
    service = AIChatService(db=db, openai_client=openai_client)

    try:
        return await service.chat(
            current_user.id,
            session_id,
            payload.query,
        )
    except Exception:
        logger.exception(
            "/chat/message failed (user_id=%s session_id=%s)",
            current_user.id,
            session_id,
        )
        raise
