import logging

from fastapi import APIRouter, Depends, Path, Query, Request

from app.core.rate_limiter import shared_limiter as limiter
from app.dependencies.auth import get_current_user
from app.dependencies.place_qa import get_place_qa_service
from app.exceptions.custom_exceptions import NotFoundError
from app.models.user import User
from app.schemas.place_qa import (
    DeletePlaceQASessionResponse,
    DeletePlaceQASessionsRequest,
    GetPlaceQASessionResponse,
    ListPlaceQASessionsResponse,
    PlaceQAMessageSchema,
    PlaceQASessionDetail,
    PlaceQuestionRequest,
    PlaceQuestionResponse,
)
from app.services.place_qa_service import PlaceQAService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/places", tags=["Place Q&A"])


@router.post("/{place_id}/question", response_model=PlaceQuestionResponse)
@limiter.limit("20/minute")
async def ask_place_question(
    request: Request,
    place_id: str = Path(..., min_length=1, max_length=255),
    payload: PlaceQuestionRequest = ...,
    current_user: User = Depends(get_current_user),
    service: PlaceQAService = Depends(get_place_qa_service),
):
    logger.info(
        "Ask question — user: %s, place: %s, session: %s",
        current_user.id,
        place_id,
        payload.session_id,
    )
    return await service.answer_question(
        place_id=place_id,
        request=payload,
        user_id=current_user.id,
    )


@router.get("/qa/sessions", response_model=ListPlaceQASessionsResponse)
@limiter.limit("30/minute")
async def list_place_qa_sessions(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=50, description="Items per page (max 50)"),
    place_id: str = Query(None, description="Filter by place ID"),
    search: str = Query(None, description="Search in session titles"),
    sort: str = Query(
        "last_message", description="Sort: last_message | created_at | title"
    ),
    current_user: User = Depends(get_current_user),
    service: PlaceQAService = Depends(get_place_qa_service),
) -> ListPlaceQASessionsResponse:
    logger.info(
        "List sessions — user: %s, filters: place=%s, search=%s",
        current_user.id,
        place_id,
        search,
    )

    session_items, total_count, has_next = await service.list_sessions(
        user_id=current_user.id,
        page=page,
        page_size=page_size,
        place_id=place_id,
        search=search,
        sort_by=sort,
    )

    return ListPlaceQASessionsResponse(
        success=True,
        sessions=session_items,
        total_count=total_count,
        page=page,
        page_size=page_size,
        has_next=has_next,
    )


@router.get("/qa/sessions/{session_id}", response_model=GetPlaceQASessionResponse)
@limiter.limit("30/minute")
async def get_place_qa_session(
    request: Request,
    session_id: str = Path(..., min_length=36, max_length=36),
    page: int = Query(1, ge=1, description="Message page"),
    page_size: int = Query(10, ge=1, le=50, description="Messages per page"),
    current_user: User = Depends(get_current_user),
    service: PlaceQAService = Depends(get_place_qa_service),) -> GetPlaceQASessionResponse:
    logger.info("Get session — session: %s, user: %s", session_id, current_user.id)
    session, total_messages, has_next = await service.get_session_detail(
        session_id=session_id,
        user_id=current_user.id,
        page=page,
        page_size=page_size,)

    if not session:
        raise NotFoundError(f"Session {session_id} not found")

    place_info = None
    if session.place_id:
        place_info = service.get_place_info(session.place_id)

    messages = [
        PlaceQAMessageSchema(
            id=msg.id,
            role=msg.role,
            content=msg.content,
            created_at=msg.created_at,
            token_count=msg.token_count,
        )
        for msg in session.messages
    ]

    detail = PlaceQASessionDetail(
        session_id=session.id,
        place=place_info,
        title=session.title,
        message_count=total_messages,
        created_at=session.created_at,
        updated_at=session.updated_at,
        last_message_at=session.last_message_at,
        messages=messages,
    )

    return GetPlaceQASessionResponse(
        success=True,
        session=detail,
        total_messages=total_messages,
        page=page,
        page_size=page_size,
        has_next=has_next,
    )

@router.delete("/qa/sessions", response_model=DeletePlaceQASessionResponse)
@limiter.limit("20/minute")
async def delete_place_qa_sessions(
    request: Request,
    payload: DeletePlaceQASessionsRequest,
    current_user: User = Depends(get_current_user),
    service: PlaceQAService = Depends(get_place_qa_service),) -> DeletePlaceQASessionResponse:
    logger.info("Bulk delete — sessions: %s, user: %s", payload.session_ids, current_user.id)
    deleted_ids = await service.bulk_delete_sessions(
        session_ids=payload.session_ids,
        user_id=current_user.id,)

    return DeletePlaceQASessionResponse(
        success=True,
        message=f"Successfully deleted {len(deleted_ids)} session(s)",
        deleted_session_ids=deleted_ids,
    )


