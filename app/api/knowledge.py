import logging
from fastapi import APIRouter, Depends, Path, Request
from app.core.rate_limiter import shared_limiter as limiter
from app.dependencies.auth import get_current_user
from app.dependencies.knowledge import get_knowledge_service
from app.models.user import User
from app.schemas.knowledge import KnowledgeSyncRequest, KnowledgeSyncResponse
from app.services.knowledge_service import KnowledgeService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/places", tags=["Knowledge Sync"], include_in_schema=False)


@router.post("/{place_id}/knowledge-sync", response_model=KnowledgeSyncResponse, include_in_schema=False)
@limiter.limit("5/minute")
async def sync_place_knowledge(
    request: Request,
    place_id: str = Path(..., min_length=1, max_length=255),
    payload: KnowledgeSyncRequest = KnowledgeSyncRequest(),
    current_user: User = Depends(get_current_user),
    service: KnowledgeService = Depends(get_knowledge_service),
) -> KnowledgeSyncResponse:
    logger.info(
        "Knowledge sync request — user_id: %s, place_id: %s, force: %s",
        current_user.id,
        place_id,
        payload.force_resync,
    )

    return await service.sync_place_knowledge(
        place_id=place_id,
        request=payload,
    )
