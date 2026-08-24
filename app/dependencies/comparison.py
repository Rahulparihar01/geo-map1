from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.dependencies.place_details import get_place_details_service
from app.services.comparison_service import ComparisonService
from app.services.place_details_service import PlaceDetailsService


def get_comparison_service(
    request: Request,
    db: Session = Depends(get_db),
    place_details_service: PlaceDetailsService = Depends(get_place_details_service),
) -> ComparisonService:
    openai_client = getattr(request.app.state, "openai_client", None)
    return ComparisonService(
        db=db,
        place_details_service=place_details_service,
        openai_client=openai_client,
    )
