import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Type, TypeVar

from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.place_detail import PlaceDetail
from app.schemas.place_details import (
    OpeningHours,
    PlaceDetailResult,
    PlacePhoto,
    PlaceReview,
)

logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=BaseModel)

_DETAIL_FIELDS = (
    "display_name",
    "formatted_address",
    "latitude",
    "longitude",
    "primary_type",
    "types",
    "international_phone_number",
    "national_phone_number",
    "website_uri",
    "google_maps_uri",
    "rating",
    "user_rating_count",
    "business_status",
    "open_now",
    "price_level",
    "wheelchair_accessible_entrance",
    "editorial_summary",
    "extended_data",
)


def _compute_content_hash(detail: PlaceDetailResult) -> str:
    parts = [
        str(detail.display_name or ""),
        str(detail.formatted_address or ""),
        str(detail.primary_type or ""),
        str(sorted(detail.types) if detail.types else []),
        str(detail.international_phone_number or ""),
        str(detail.national_phone_number or ""),
        str(detail.website_uri or ""),
        str(detail.google_maps_uri or ""),
        str(detail.rating or ""),
        str(detail.user_rating_count or ""),
        str(detail.business_status or ""),
        str(detail.open_now or ""),
        str(detail.price_level or ""),
        str(detail.wheelchair_accessible_entrance or ""),
        str(detail.editorial_summary or ""),
        str(detail.extended_data or ""),
        str(detail.opening_hours.model_dump() if detail.opening_hours else ""),
        str([r.model_dump() for r in detail.reviews] if detail.reviews else ""),
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _to_dict(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, list):
        return [_to_dict(item) for item in obj]
    if hasattr(obj, "model_dump"):  # Pydantic v2
        return obj.model_dump()
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    return obj


def _model_or_none(model: Type[ModelT], data: Optional[Dict]) -> Optional[ModelT]:
    if not data:
        return None
    try:
        return model(**data)
    except (ValueError, TypeError, KeyError):
        return None


def _model_list_or_none(
    model: Type[ModelT], data: Optional[List[Dict]]
) -> Optional[List[ModelT]]:
    if not data:
        return None
    try:
        return [model(**item) for item in data]
    except (ValueError, TypeError, KeyError):
        return None


class PlaceDetailsRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_place_id(self, place_id: str) -> Optional[PlaceDetail]:
        return (
            self.db.query(PlaceDetail).filter(PlaceDetail.place_id == place_id).first()
        )

    def mark_knowledge_synced(self, place_id: str) -> bool:
        updated = (
            self.db.query(PlaceDetail)
            .filter(PlaceDetail.place_id == place_id)
            .update({"knowledge_synced": True}, synchronize_session=False)
        )
        return updated > 0

    def to_result(self, record: PlaceDetail) -> PlaceDetailResult:
        values = {field: getattr(record, field) for field in _DETAIL_FIELDS}
        return PlaceDetailResult(
            place_id=record.place_id,
            **values,
            opening_hours=_model_or_none(OpeningHours, record.opening_hours),
            photos=_model_list_or_none(PlacePhoto, record.photos),
            reviews=_model_list_or_none(PlaceReview, record.reviews),
            last_fetched_at=record.last_fetched_at,
            knowledge_synced=record.knowledge_synced,
        )

    def _apply_detail_to_record(
        self,
        record: PlaceDetail,
        detail: PlaceDetailResult,
        content_changed: bool,
        now_utc: datetime,
    ) -> None:
        for field in _DETAIL_FIELDS:
            setattr(record, field, getattr(detail, field))
        record.opening_hours = _to_dict(detail.opening_hours)
        record.photos = _to_dict(detail.photos)
        record.reviews = _to_dict(detail.reviews)
        record.last_fetched_at = now_utc

        if content_changed:
            record.knowledge_synced = False

    def _compute_hash_for_record(self, record: PlaceDetail) -> str:
        return _compute_content_hash(self.to_result(record))

    def upsert(self, detail: PlaceDetailResult) -> PlaceDetail:
        existing = self.get_by_place_id(detail.place_id)

        now_utc = datetime.now(timezone.utc)

        if existing:
            new_content_hash = _compute_content_hash(detail)
            existing_content_hash = self._compute_hash_for_record(existing)
            content_changed = new_content_hash != existing_content_hash

            self._apply_detail_to_record(existing, detail, content_changed, now_utc)

            if content_changed:
                logger.debug(
                    "PlaceDetail content changed — knowledge_synced reset: place_id=%s",
                    detail.place_id,
                )
            else:
                logger.debug(
                    "PlaceDetail content unchanged — knowledge_synced preserved: place_id=%s",
                    detail.place_id,
                )

            self.db.flush()
            logger.debug("PlaceDetail updated: place_id=%s", detail.place_id)
            return existing

        record = PlaceDetail(
            place_id=detail.place_id,
            **{field: getattr(detail, field) for field in _DETAIL_FIELDS},
            opening_hours=_to_dict(detail.opening_hours),
            photos=_to_dict(detail.photos),
            reviews=_to_dict(detail.reviews),
            last_fetched_at=now_utc,
            knowledge_synced=False,
        )

        try:
            self.db.add(record)
            self.db.flush()
            logger.debug("PlaceDetail inserted: place_id=%s", detail.place_id)
            return record
        except Exception as e:

            if isinstance(e, IntegrityError) and "place_id" in str(e.orig).lower():
                logger.warning(
                    "Concurrent upsert detected for place_id=%s — another request "
                    "inserted first. Rolling back and updating the existing row.",
                    detail.place_id,
                )
                self.db.rollback()
                existing = self.get_by_place_id(detail.place_id)
                if not existing:
                    logger.error(
                        "Race condition recovery failed — place_id=%s not found after rollback",
                        detail.place_id,
                    )
                    raise

                new_content_hash = _compute_content_hash(detail)
                existing_content_hash = self._compute_hash_for_record(existing)
                content_changed = new_content_hash != existing_content_hash

                self._apply_detail_to_record(existing, detail, content_changed, now_utc)

                self.db.flush()
                logger.debug(
                    "PlaceDetail updated after race condition: place_id=%s",
                    detail.place_id,
                )
                return existing
            else:
                raise
