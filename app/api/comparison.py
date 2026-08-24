from typing import Union

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.rate_limiter import shared_limiter as limiter
from app.dependencies.auth import get_current_user
from app.dependencies.comparison import get_comparison_service
from app.models.user import User
from app.schemas.comparison import (
    CompareBasicResponse,
    ComparePlacesRequest,
    CompareRecommendResponse,
    ComparisonType,
)
from app.services.comparison_service import ComparisonService
from app.utils.error_messages import COMPARISON_FAILED

router = APIRouter(prefix="/compare", tags=["Comparison"])


@router.post("", response_model=Union[CompareBasicResponse, CompareRecommendResponse])
@limiter.limit("20/minute")
async def compare_places(
    request: Request,
    body: ComparePlacesRequest,
    current_user: User = Depends(get_current_user),
    service: ComparisonService = Depends(get_comparison_service),
) -> Union[CompareBasicResponse, CompareRecommendResponse]:
    if body.comparison_type is ComparisonType.RECOMMENDATION:
        result = await service.recommend(
            place_ids=body.place_ids,
            user_id=current_user.id,
        )
    else:
        result = await service.compare_basic(
            place_ids=body.place_ids,
            user_id=current_user.id,
        )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=COMPARISON_FAILED,
        )
    return result
