import logging

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.integrations.openai_client import OpenAIEmbeddingClient
from app.integrations.pinecone_client import PineconeClient
from app.services.place_qa_service import PlaceQAService

logger = logging.getLogger(__name__)

_UNAVAILABLE_DETAIL = "This feature is temporarily unavailable. Please try again later."


def get_place_qa_service(
    request: Request,
    db: Session = Depends(get_db),
) -> PlaceQAService:
    pinecone_client: PineconeClient = getattr(
        request.app.state, "pinecone_client", None
    )
    if pinecone_client is None:
        logger.warning("Pinecone client not initialized — Q&A service unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_UNAVAILABLE_DETAIL,
        )

    openai_client: OpenAIEmbeddingClient = getattr(
        request.app.state, "openai_client", None
    )
    if openai_client is None:
        logger.warning("OpenAI client not initialized — Q&A service unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_UNAVAILABLE_DETAIL,
        )

    return PlaceQAService(
        db=db,
        openai_client=openai_client,
        pinecone_client=pinecone_client,
    )
