import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List
from sqlalchemy.orm import Session
from app.exceptions.places import PlaceDetailNotFoundError
from app.integrations.openai_client import OpenAIEmbeddingClient
from app.integrations.pinecone_client import PineconeClient
from app.models.place_detail import PlaceDetail
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.place_details_repository import PlaceDetailsRepository
from app.schemas.knowledge import (
    KnowledgeChunk,
    KnowledgeSyncRequest,
    KnowledgeSyncResponse,
    SyncStatus,
)
from app.utils.place_field_mappings import SECTION_EXTRACTORS
from langfuse import observe, propagate_attributes

logger = logging.getLogger(__name__)
_MAX_CHUNK_CHARS = 3000
_NS_PREFIX = "place"


def build_place_document(place: PlaceDetail) -> Dict[str, str]:
    sections: Dict[str, str] = {}
    
    for section_name, extractor_fn in SECTION_EXTRACTORS.items():
        try:
            section_text = extractor_fn(place)
            if section_text and section_text.strip():
                sections[section_name] = section_text
        except Exception as exc:
            logger.warning(
                "Failed to extract section %s for place %s: %s",
                section_name,
                place.id,
                exc,
            )
    
    return sections


def _compute_source_version(sections: Dict[str, str]) -> str:
    full_text = "\n\n".join(f"[{k}]\n{v}" for k, v in sorted(sections.items()))
    return hashlib.sha256(full_text.encode("utf-8")).hexdigest()


def _truncate(text: str, max_chars: int = _MAX_CHUNK_CHARS) -> str:
    return text[:max_chars]

class KnowledgeService:
    def __init__(
        self,
        db: Session,
        openai_client: OpenAIEmbeddingClient,
        pinecone_client: PineconeClient,
    ) -> None:
        self.db = db
        self.openai_client = openai_client
        self.pinecone_client = pinecone_client
        self.repo = KnowledgeRepository(db)
        self.details_repo = PlaceDetailsRepository(db)

    @observe(name="knowledge-sync")
    async def sync_place_knowledge(
        self,
        place_id: str,
        request: KnowledgeSyncRequest,
    ) -> KnowledgeSyncResponse:
        logger.info(
            "Knowledge sync start — place_id: %s, force: %s",
            place_id,
            request.force_resync,
        )

        place = self.repo.get_place_detail(place_id)
        if place is None:
            raise PlaceDetailNotFoundError(place_id)

        sections = build_place_document(place)

        sections = {k: v for k, v in sections.items() if v.strip()}

        if not sections:
            logger.warning(
                "Knowledge sync: place_id %s has no content to embed", place_id)
            return KnowledgeSyncResponse(
                success=False,
                place_id=place_id,
                sync_status=SyncStatus.FAILED,
                message="Insufficient data to sync.",
                skipped=False,)

        source_version = _compute_source_version(sections)
        if not request.force_resync:
            existing = self.repo.get_sync_record(place_id)
            if (
                existing
                and existing.sync_status == SyncStatus.SYNCED
                and existing.source_version == source_version
            ):
                logger.info(
                    "Knowledge sync SKIPPED — place_id: %s (source_version unchanged)",
                    place_id,
                )
                return KnowledgeSyncResponse(
                    success=True,
                    place_id=place_id,
                    sync_status=SyncStatus.SYNCED,
                    message="Already synced.",
                    vector_count=existing.vector_count,
                    pinecone_namespace=existing.pinecone_namespace,
                    source_version=source_version,
                    skipped=True,
                    skip_reason="source_version unchanged",
                    synced_at=existing.synced_at,)

        section_names = list(sections.keys())
        chunk_texts = [_truncate(sections[name]) for name in section_names]

        logger.info(
            "Knowledge sync — embedding %d chunks for place_id: %s",
            len(chunk_texts),
            place_id,
        )
        try:
            with propagate_attributes(
                metadata={"place_id": place_id, "step": "embedding"},
            ):
                vectors_raw = await self.openai_client.embed_texts(chunk_texts)
        except Exception as exc:
            from app.integrations.openai_client import EmbeddingRateLimitError

            if isinstance(exc, EmbeddingRateLimitError):
                logger.warning(
                    "Knowledge sync rate limited for place_id %s — will retry later",
                    place_id,
                    extra={
                        "event": "knowledge_sync_rate_limited",
                        "place_id": place_id,
                        "chunks_count": len(chunk_texts),
                    },
                )
                self.repo.mark_failed(
                    place_id, "Rate limited - will retry"
                )
                self.db.commit()
                return KnowledgeSyncResponse(
                    success=False,
                    place_id=place_id,
                    sync_status=SyncStatus.FAILED,
                    message="Temporarily unavailable. Will retry automatically.",
                    skipped=False,
                )

            logger.error("Knowledge sync embed failed for place_id %s: %s", place_id, exc,)
            self.repo.mark_failed(place_id, str(exc))
            self.db.commit()
            raise

        # Only delete the old namespace AFTER new embeddings succeeded — a failed
        # refresh must not destroy the previously working knowledge.
        await self.pinecone_client.delete_place_namespace(place_id)

        namespace = f"{_NS_PREFIX}_{place_id}"
        pinecone_vectors: List[Dict[str, Any]] = []
        knowledge_chunks: List[KnowledgeChunk] = []

        for i, (section_name, text, embedding) in enumerate(
            zip(section_names, chunk_texts, vectors_raw)
        ):
            vector_id = f"{place_id}_section_{section_name}"
            metadata: Dict[str, Any] = {
                "place_id": place_id,
                "section": section_name,
                "text": text,  # stored for retrieval in Phase 4
                "display_name": place.display_name or "",
                "formatted_address": place.formatted_address or "",
            }
            pinecone_vectors.append(
                {
                    "id": vector_id,
                    "values": embedding,
                    "metadata": metadata,
                }
            )
            knowledge_chunks.append(
                KnowledgeChunk(
                    chunk_id=vector_id,
                    section=section_name,
                    text=text,
                    vector_dimension=len(embedding),
                )
            )

        logger.info(
            "Knowledge sync — upserting %d vectors to Pinecone namespace: %s",
            len(pinecone_vectors),
            namespace,
        )
        try:
            upserted_count = await self.pinecone_client.upsert_vectors(
                place_id=place_id,
                vectors=pinecone_vectors,
            )
        except Exception as exc:
            logger.error(
                "Knowledge sync Pinecone upsert failed for place_id %s: %s",
                place_id,
                exc,
            )
            self.repo.mark_failed(place_id, str(exc))
            self.db.commit()
            raise

        self.repo.upsert_sync_record(
            place_id=place_id,
            sync_status=SyncStatus.SYNCED,
            vector_count=upserted_count,
            pinecone_namespace=namespace,
            source_version=source_version,
            error_message=None,
        )

        self.details_repo.mark_knowledge_synced(place_id)

        self.db.commit()

        now = datetime.now(timezone.utc)
        logger.info(
            "Knowledge sync COMPLETE — place_id: %s, vectors: %d, namespace: %s",
            place_id,
            upserted_count,
            namespace,
        )

        return KnowledgeSyncResponse(
            success=True,
            place_id=place_id,
            sync_status=SyncStatus.SYNCED,
            message="Sync completed successfully.",
            vector_count=upserted_count,
            pinecone_namespace=namespace,
            source_version=source_version,
            chunks=knowledge_chunks,
            skipped=False,
            synced_at=now,
        )
