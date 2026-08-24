import logging
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.repositories.visit_repository import VisitRepository
from app.repositories.knowledge_repository import KnowledgeRepository
from app.schemas.visits import VisitLogResponse, UpdatedVisitData

logger = logging.getLogger(__name__)


class VisitService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = VisitRepository(db)
        self.knowledge_repo = KnowledgeRepository(db)

    async def log_visit(
        self,
        user_id: int,
        place_id: str,
        rating_given: Optional[float] = None,
        review_text: Optional[str] = None,
    ) -> VisitLogResponse:
        place_fields = self.knowledge_repo.get_denormalized_fields(place_id)
        record = self.repo.create(
            user_id=user_id,
            place_id=place_id,
            rating_given=rating_given,
            review_text=review_text,
            **place_fields,
        )
        self.db.commit()
        logger.info(
            "Visit logged — user_id=%s place_id=%s visit_id=%s rating=%s",
            user_id,
            place_id,
            record.id,
            rating_given,
        )
        return VisitLogResponse.model_validate(record)

    async def list_visits(
        self,
        user_id: int,
        page: int = 1,
        page_size: int = 20,
        place_id: Optional[str] = None,
    ) -> Tuple[List[VisitLogResponse], int, bool]:
        offset = (page - 1) * page_size
        records, total = self.repo.list_visits(
            user_id=user_id,
            place_id=place_id,
            limit=page_size,
            offset=offset,
        )
        has_next = (offset + page_size) < total
        items = [VisitLogResponse.model_validate(r) for r in records]
        return items, total, has_next

    async def delete_visit(self, visit_id: int, user_id: int) -> bool:
        record = self.repo.get_by_id(visit_id, user_id)
        if not record:
            logger.warning(
                "Visit delete failed — visit_id=%s not found for user_id=%s",
                visit_id,
                user_id,
            )
            return False
        self.repo.delete(record)
        self.db.commit()
        logger.info("Visit deleted — visit_id=%s user_id=%s", visit_id, user_id)
        return True

    async def update_visit(
        self,
        user_id: int,
        visit_id: int,
        rating_given: Optional[float] = None,
        review_text: Optional[str] = None,
    ) -> Optional[UpdatedVisitData]:
        updates = {}
        if rating_given is not None:
            updates["rating_given"] = rating_given
        if review_text is not None:
            updates["review_text"] = review_text

        record = self.repo.update_visit(visit_id, user_id, updates)
        if not record:
            logger.warning(
                "Visit update failed — visit_id=%s not found for user_id=%s",
                visit_id,
                user_id,
            )
            return None

        self.db.commit()
        logger.info(
            "Visit updated — user_id=%s visit_id=%s fields=%s",
            user_id,
            visit_id,
            list(updates.keys()),
        )
        return UpdatedVisitData.model_validate(record)

    async def get_stats(self, user_id: int) -> Dict:
        return self.repo.get_stats(user_id)
