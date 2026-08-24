import logging
from typing import TYPE_CHECKING, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.exceptions.custom_exceptions import BadRequestError, NotFoundError, InsufficientCreditsError
from app.repositories.place_details_repository import PlaceDetailsRepository
from app.repositories.place_unlock_repository import PlaceUnlockRepository
from app.services.credit_service import CreditService
from app.utils.place_categories import get_place_category
from app.utils.error_messages import (
    PLACE_ALREADY_UNLOCKED,
    PLACE_NOT_FOUND,
    PLACE_CATEGORY_NOT_SUPPORTED,
    PLACE_LOCKED,
    PLACE_QUESTION_LIMIT_REACHED,
    FEATURE_DISABLED,
)

if TYPE_CHECKING:
    from app.services.place_details_service import PlaceDetailsService

logger = logging.getLogger(__name__)


UNLOCK_TOKEN_COST = 10
QUESTIONS_PER_UNLOCK = 15


class PlaceUnlockService:
    def __init__(self, db: Session, details_service: Optional["PlaceDetailsService"] = None):
        self.db = db
        self.repo = PlaceUnlockRepository(db)
        self.details_repo = PlaceDetailsRepository(db)
        self.details_service = details_service

    def is_unlock_enabled(self) -> bool:
        return settings.PLACE_UNLOCK_ENABLED

    def is_place_unlocked(self, user_id: int, place_id: str) -> bool:
        if not self.is_unlock_enabled():
            return True
        
        return self.repo.is_unlocked(user_id, place_id)

    def get_unlocked_place_ids(self, user_id: int, place_ids: List[str]) -> set:
        if not self.is_unlock_enabled():
            return set(place_ids)
        return self.repo.get_active_unlock_place_ids(user_id, place_ids)

    async def _resolve_place_details(self, place_id: str) -> Optional[dict]:
        place = self.details_repo.get_by_place_id(place_id)
        if place is not None:
            return {
                "primary_type": place.primary_type,
                "types": place.types,
                "display_name": place.display_name,
                "formatted_address": place.formatted_address,
                "latitude": place.latitude,
                "longitude": place.longitude,
            }

        if self.details_service is None:
            logger.error(
                "Cannot fetch place details for %s — details_service not provided",
                place_id,
            )
            return None

        try:
            detail, _source = await self.details_service.get_place_details(place_id)
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(
                "Failed to fetch place details during unlock for %s: %s",
                place_id,
                exc,
            )
            return None

        if detail is None:
            return None

        return {
            "primary_type": detail.primary_type,
            "types": detail.types,
            "display_name": detail.display_name,
            "formatted_address": detail.formatted_address,
            "latitude": detail.latitude,
            "longitude": detail.longitude,
        }

    async def unlock_place(
        self,
        user_id: int,
        place_id: str,
    ) -> dict:
        if not self.is_unlock_enabled():
            raise BadRequestError(FEATURE_DISABLED)

        if self.repo.is_unlocked(user_id, place_id):
            raise BadRequestError(PLACE_ALREADY_UNLOCKED)

        place_details = await self._resolve_place_details(place_id)
        if not place_details:
            logger.error("Place details not found for place_id: %s", place_id)
            raise BadRequestError(PLACE_NOT_FOUND)

        primary_type = place_details.get("primary_type")
        types = place_details.get("types") or []
        category_source = primary_type or (types[0] if types else None)
        if not category_source:
            logger.warning(
                "No primary type or types for place_id: %s — cannot assign category",
                place_id,
            )
            raise BadRequestError(PLACE_CATEGORY_NOT_SUPPORTED)

        category = get_place_category(category_source) or "other"

        token_cost = UNLOCK_TOKEN_COST

        try:
            remaining_credits = await CreditService.deduct(self.db, user_id, token_cost)
        except (InsufficientCreditsError, NotFoundError):
            raise

        try:
            display_name = place_details.get("display_name")
            formatted_address = place_details.get("formatted_address")
            latitude = place_details.get("latitude")
            longitude = place_details.get("longitude")

            unlock = self.repo.create_unlock(
                user_id=user_id,
                place_id=place_id,
                category=category,
                tokens_spent=token_cost,
                questions_limit=QUESTIONS_PER_UNLOCK,
                display_name=display_name,
                formatted_address=formatted_address,
                latitude=latitude,
                longitude=longitude,
            )
            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            if "place_unlocks" in str(e) or "uq_user_place_active" in str(e):
                logger.warning("Duplicate unlock attempt for user_id=%s place_id=%s", user_id, place_id)
                raise BadRequestError(PLACE_ALREADY_UNLOCKED)
            raise

        logger.info(
            "Place unlocked: user_id=%s place_id=%s tokens=%s limit=%s",
            user_id,
            place_id,
            token_cost,
            QUESTIONS_PER_UNLOCK,
        )

        return {
            "tokens_spent": token_cost,
            "remaining_credits": remaining_credits,
            "category": category,
            "questions_limit": QUESTIONS_PER_UNLOCK,
            "questions_used": unlock.questions_used,
            "questions_remaining": QUESTIONS_PER_UNLOCK - unlock.questions_used,
        }

    def get_question_usage_info(self, user_id: int, place_id: str) -> dict:
        if not self.is_unlock_enabled():
            return {
                "questions_used": 0,
                "questions_remaining": 999,
                "is_expired": False,
            }

        unlock = self.repo.get_active_unlock(user_id, place_id)
        if unlock is None:
            return {
                "questions_used": 0,
                "questions_remaining": 0,
                "is_expired": False,
            }

        return {
            "questions_used": unlock.questions_used,
            "questions_remaining": max(0, unlock.questions_limit - unlock.questions_used),
            "is_expired": unlock.is_expired,
        }

    async def record_question_usage(self, user_id: int, place_id: str) -> dict:
        if not self.is_unlock_enabled():
            return {
                "questions_used": 1,
                "questions_remaining": 999,
                "is_expired": False,
            }

        unlock = self.repo.get_active_unlock_for_update(user_id, place_id)

        if unlock is None:
            raise BadRequestError(PLACE_LOCKED)

        if unlock.is_expired or unlock.questions_used >= unlock.questions_limit:
            raise BadRequestError(PLACE_QUESTION_LIMIT_REACHED)

        assert unlock.questions_used < unlock.questions_limit, \
            f"Question limit already reached for place {place_id}"

        unlock = self.repo.increment_question_usage(unlock)

        return {
            "questions_used": unlock.questions_used,
            "questions_remaining": max(0, unlock.questions_limit - unlock.questions_used),
            "is_expired": unlock.is_expired,
        }

    def get_user_unlocked_places(
        self,
        user_id: int,
        page: int = 1,
        page_size: int = 20,
        include_expired: bool = False,
    ) -> Tuple[List[dict], int]:
        offset = (page - 1) * page_size
        unlocks, total = self.repo.get_user_unlocks(
            user_id, page_size, offset, include_expired
        )

        results = [
            {
                "place_id": u.place_id,
                "display_name": u.display_name,
                "formatted_address": u.formatted_address,
                "category": u.category,
                "tokens_spent": u.tokens_spent,
                "unlocked_at": u.unlocked_at,
                "questions_used": u.questions_used,
                "questions_limit": u.questions_limit,
                "is_expired": u.is_expired,
                "expired_at": u.expired_at,
                "latitude": u.latitude,
                "longitude": u.longitude,
            }
            for u in unlocks
        ]

        return results, total
