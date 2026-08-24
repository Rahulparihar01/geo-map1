import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session
from app.models.place_detail import PlaceDetail
from app.models.place_knowledge_sync import PlaceKnowledgeSync
from app.schemas.knowledge import SyncStatus

logger = logging.getLogger(__name__)


class KnowledgeRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_place_detail(self, place_id: str) -> Optional[PlaceDetail]:
        return (
            self.db.query(PlaceDetail).filter(PlaceDetail.place_id == place_id).first()
        )

    def get_denormalized_fields(
        self, place_id: str, *, include_rating: bool = False
    ) -> dict:
        fields = {
            "display_name": None,
            "formatted_address": None,
            "primary_type": None,
            "latitude": None,
            "longitude": None,
        }
        if include_rating:
            fields["rating"] = None

        place = self.get_place_detail(place_id)
        if place:
            fields["display_name"] = place.display_name
            fields["formatted_address"] = place.formatted_address
            fields["primary_type"] = place.primary_type
            fields["latitude"] = place.latitude
            fields["longitude"] = place.longitude
            if include_rating:
                fields["rating"] = place.rating
        return fields

    def get_sync_record(self, place_id: str) -> Optional[PlaceKnowledgeSync]:
        return (
            self.db.query(PlaceKnowledgeSync)
            .filter(PlaceKnowledgeSync.place_id == place_id)
            .first()
        )

    def upsert_sync_record(
        self,
        *,
        place_id: str,
        sync_status: str,
        vector_count: int,
        pinecone_namespace: str,
        source_version: str,
        error_message: Optional[str] = None,
    ) -> PlaceKnowledgeSync:
        existing = self.get_sync_record(place_id)
        now = datetime.now(timezone.utc)

        if existing:
            existing.sync_status = sync_status
            existing.vector_count = vector_count
            existing.pinecone_namespace = pinecone_namespace
            existing.source_version = source_version
            existing.error_message = error_message
            if sync_status == SyncStatus.SYNCED:
                existing.synced_at = now
            self.db.flush()
            logger.debug(
                "PlaceKnowledgeSync updated: place_id=%s status=%s vectors=%d",
                place_id,
                sync_status,
                vector_count,
            )
            return existing

        record = PlaceKnowledgeSync(
            place_id=place_id,
            sync_status=sync_status,
            vector_count=vector_count,
            pinecone_namespace=pinecone_namespace,
            source_version=source_version,
            error_message=error_message,
            synced_at=now if sync_status == SyncStatus.SYNCED else None,
        )
        self.db.add(record)
        self.db.flush()
        logger.debug(
            "PlaceKnowledgeSync inserted: place_id=%s status=%s vectors=%d",
            place_id,
            sync_status,
            vector_count,
        )
        return record

    def mark_failed(self, place_id: str, error_message: str) -> None:
        existing = self.get_sync_record(place_id)
        if existing:
            existing.sync_status = SyncStatus.FAILED
            existing.error_message = error_message
            self.db.flush()
        else:
            record = PlaceKnowledgeSync(
                place_id=place_id,
                sync_status=SyncStatus.FAILED,
                vector_count=0,
                error_message=error_message,
            )
            self.db.add(record)
            self.db.flush()
