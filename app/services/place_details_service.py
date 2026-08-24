import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from redis.exceptions import RedisError
from sqlalchemy.orm import Session
from app.integrations.google_place_details import GooglePlaceDetailsClient
from app.repositories.place_details_repository import PlaceDetailsRepository
from app.repositories.redis_repository import RedisRepository
from app.services.knowledge_service import KnowledgeService
from app.schemas.place_details import (
    DetailSource,
    PlaceDetailResult,
)
from app.core.config import settings
from app.schemas.knowledge import KnowledgeSyncRequest
from app.database.connection import SessionLocal
from app.utils.cache_keys import CacheKeyBuilder

logger = logging.getLogger(__name__)

_LOCK_KEY_PREFIX = "place_details_lock"
_LOCK_TTL_SECONDS = 30


class PlaceDetailsService:
    def __init__(
        self,
        db: Session,
        redis_repo: RedisRepository,
        google_client: GooglePlaceDetailsClient,
        knowledge_service=None,
    ) -> None:
        self.db = db
        self.redis_repo = redis_repo
        self.google_client = google_client
        self.repo = PlaceDetailsRepository(db)
        self._details_ttl = settings.REDIS_DETAILS_CACHE_TTL
        self.knowledge_service = knowledge_service
        self._stale_after_days: int = getattr(settings, "DETAILS_STALE_AFTER_DAYS", 7)

    def _is_stale(self, fetched_at: Optional[datetime]) -> bool:
        if fetched_at is None:
            return False

        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)

        stale_threshold = datetime.now(timezone.utc) - timedelta(
            days=self._stale_after_days
        )
        return fetched_at < stale_threshold

    async def _try_get_from_cache(self, place_id: str) -> Optional[PlaceDetailResult]:
        key = CacheKeyBuilder.place_details(place_id)
        raw = await self.redis_repo.get(key)
        if raw is None:
            return None
        try:
            result = PlaceDetailResult(**raw)
            logger.info("Place Details cache HIT — place_id: %s", place_id)
            return result
        except Exception as exc:
            logger.warning(
                "Place Details cache deserialisation error for %s: %s",
                place_id,
                exc,
            )
            return None

    async def _write_to_cache(self, detail: PlaceDetailResult) -> None:
        key = CacheKeyBuilder.place_details(detail.place_id)
        try:
            await self.redis_repo.set(
                key, detail.model_dump(mode="json"), ttl=self._details_ttl
            )
        except Exception as exc:
            logger.warning(
                "Place Details cache write failed for %s: %s",
                detail.place_id,
                exc,
            )

    async def _acquire_lock(self, place_id: str) -> bool:
        if self.redis_repo.client is None:

            logger.debug(
                "Lock acquire skipped for %s — Redis unavailable, returning False",
                place_id,
            )
            return False
        try:
            key = f"{_LOCK_KEY_PREFIX}:{place_id}"
            acquired = await self.redis_repo.client.set(
                key, "1", nx=True, ex=_LOCK_TTL_SECONDS
            )
            return bool(acquired)
        except (RedisError, ConnectionError, OSError) as exc:
            logger.warning(
                "Lock acquire failed for %s: %s — returning False, will retry cache",
                place_id,
                exc,
            )
            return False

    async def _release_lock(self, place_id: str) -> None:
        if self.redis_repo.client is None:
            return
        try:
            key = f"{_LOCK_KEY_PREFIX}:{place_id}"
            await self.redis_repo.client.delete(key)
        except Exception as exc:
            logger.warning("Lock release failed for %s: %s", place_id, exc)

    _bg_sync_semaphore = asyncio.Semaphore(5)

    async def _trigger_background_knowledge_sync(self, place_id: str) -> None:

        if self.knowledge_service is None:
            logger.debug(
                "Knowledge sync skipped (no KnowledgeService injected) — "
                "place_id: %s",
                place_id,
            )
            return

        if self._bg_sync_semaphore.locked():
            logger.warning(
                "Background knowledge sync throttled — too many concurrent "
                "syncs (place_id: %s). Skipping.",
                place_id,
            )
            return

        async def _sync_task():
            async with self.__class__._bg_sync_semaphore:
                try:

                    task_db = SessionLocal()
                    try:
                        logger.info(
                            "Background knowledge sync started — place_id: %s",
                            place_id,
                        )
                        task_knowledge_service = KnowledgeService(
                            db=task_db,
                            openai_client=self.knowledge_service.openai_client,
                            pinecone_client=self.knowledge_service.pinecone_client,
                        )
                        result = await task_knowledge_service.sync_place_knowledge(
                            place_id=place_id,
                            request=KnowledgeSyncRequest(force_resync=False),
                        )
                        if result.skipped:
                            logger.info(
                                "Background knowledge sync skipped "
                                "(already up-to-date) — place_id: %s",
                                place_id,
                            )
                        else:
                            logger.info(
                                "Background knowledge sync completed — "
                                "place_id: %s, vectors: %d",
                                place_id,
                                result.vector_count or 0,
                            )
                    finally:
                        task_db.close()
                except Exception as exc:
                    logger.warning(
                        "Background knowledge sync failed for place_id %s: %s",
                        place_id,
                        exc,
                    )

        asyncio.create_task(_sync_task())
        logger.debug("Background knowledge sync task created — place_id: %s", place_id)

    async def _fetch_from_google_with_lock(
        self, place_id: str
    ) -> Tuple[PlaceDetailResult, str]:
        acquired = await self._acquire_lock(place_id)

        if not acquired:
            await asyncio.sleep(0.5)
            cached = await self._try_get_from_cache(place_id)
            if cached is not None:
                logger.info(
                    "Place Details — cache populated by concurrent request: place_id=%s",
                    place_id,
                )
                return cached, DetailSource.REDIS

            db_record = self.repo.get_by_place_id(place_id)
            if db_record is not None and not self._is_stale(db_record.last_fetched_at):
                result = self.repo.to_result(db_record)
                logger.info(
                    "Place Details — using DB fallback (lock contention): place_id=%s",
                    place_id,
                )
                return result, DetailSource.DATABASE

            logger.warning(
                "Place Details — lock unavailable and no fallback, fetching from Google: place_id=%s",
                place_id,
            )

        try:
            cached = await self._try_get_from_cache(place_id)
            if cached is not None:
                return cached, DetailSource.REDIS

            detail = await self.google_client.get_place_details(place_id)
            detail.last_fetched_at = datetime.now(timezone.utc)
            self.repo.upsert(detail)
            self.db.commit()
            logger.info("Place Details saved to DB — place_id: %s", place_id)

            await self._write_to_cache(detail)
            await self._trigger_background_knowledge_sync(place_id)
            return detail, DetailSource.GOOGLE
        finally:
            if acquired:
                await self._release_lock(place_id)

    async def get_place_details(self, place_id: str) -> Tuple[PlaceDetailResult, str]:
        cached = await self._try_get_from_cache(place_id)
        if cached is not None:
            return cached, DetailSource.REDIS

        logger.info("Place Details cache MISS — place_id: %s", place_id)

        db_record = self.repo.get_by_place_id(place_id)
        if db_record is not None:
            last_fetched = db_record.last_fetched_at
            stale_threshold = datetime.now(timezone.utc) - timedelta(days=self._stale_after_days)
            if self._is_stale(db_record.last_fetched_at):
                logger.info(
                    "Place Details DB record stale (last_fetched=%s, "
                    "threshold=%s) — refreshing from Google: place_id=%s",
                    last_fetched,
                    stale_threshold,
                    place_id,
                )
            else:
                logger.info(
                    "Place Details DB HIT — place_id: %s (last_fetched: %s)",
                    place_id,
                    db_record.last_fetched_at,
                )
                result = self.repo.to_result(db_record)
                await self._write_to_cache(result)
                return result, DetailSource.DATABASE

        logger.info("Place Details DB MISS — place_id: %s → calling Google", place_id)
        return await self._fetch_from_google_with_lock(place_id)
