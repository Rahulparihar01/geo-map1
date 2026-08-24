import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.place_unlock import PlaceUnlock

logger = logging.getLogger(__name__)


class PlaceUnlockRepository:
    def __init__(self, db: Session):
        self.db = db

    def _build_active_unlock_query(self, user_id: int, place_id: str):
        return self.db.query(PlaceUnlock).filter(
            PlaceUnlock.user_id == user_id,
            PlaceUnlock.place_id == place_id,
            PlaceUnlock.is_expired == False,
        )

    def get_active_unlock(self, user_id: int, place_id: str) -> Optional[PlaceUnlock]:
        return self._build_active_unlock_query(user_id, place_id).first()

    def get_active_unlock_for_update(
        self, user_id: int, place_id: str
    ) -> Optional[PlaceUnlock]:
        return self._build_active_unlock_query(user_id, place_id).with_for_update().first()

    def is_unlocked(self, user_id: int, place_id: str) -> bool:
        return self.get_active_unlock(user_id, place_id) is not None

    def get_active_unlock_place_ids(self, user_id: int, place_ids: List[str]) -> set:
        if not place_ids:
            return set()
        rows = (
            self.db.query(PlaceUnlock.place_id)
            .filter(
                PlaceUnlock.user_id == user_id,
                PlaceUnlock.place_id.in_(place_ids),
                PlaceUnlock.is_expired == False,
            )
            .all()
        )
        return {row[0] for row in rows}

    def create_unlock(
        self,
        user_id: int,
        place_id: str,
        category: str,
        tokens_spent: int,
        questions_limit: int = 15,
        display_name: Optional[str] = None,
        formatted_address: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> PlaceUnlock:
        unlock = PlaceUnlock(
            user_id=user_id,
            place_id=place_id,
            category=category,
            tokens_spent=tokens_spent,
            questions_used=0,
            questions_limit=questions_limit,
            is_expired=False,
            display_name=display_name,
            formatted_address=formatted_address,
            latitude=latitude,
            longitude=longitude,
        )
        self.db.add(unlock)
        self.db.flush()
        logger.info(
            "Created unlock record: user_id=%s place_id=%s tokens=%s limit=%s",
            user_id,
            place_id,
            tokens_spent,
            questions_limit,
        )
        return unlock

    def increment_question_usage(self, unlock: PlaceUnlock) -> PlaceUnlock:
        if unlock.is_expired:
            return unlock

        unlock.questions_used += 1

        if unlock.questions_used >= unlock.questions_limit:
            unlock.is_expired = True
            unlock.expired_at = datetime.now(timezone.utc)
            logger.info(
                "Unlock expired: user_id=%s place_id=%s (reached %s/%s questions)",
                unlock.user_id,
                unlock.place_id,
                unlock.questions_used,
                unlock.questions_limit,
            )

        self.db.flush()
        return unlock

    def get_user_unlocks(
        self,
        user_id: int,
        limit: int = 20,
        offset: int = 0,
        include_expired: bool = False,
    ) -> Tuple[List[PlaceUnlock], int]:
        query = self.db.query(PlaceUnlock).filter(PlaceUnlock.user_id == user_id)

        if not include_expired:
            query = query.filter(PlaceUnlock.is_expired == False)
        query = query.order_by(desc(PlaceUnlock.unlocked_at))
        total = query.count()
        unlocks = query.limit(limit).offset(offset).all()
        return unlocks, total
