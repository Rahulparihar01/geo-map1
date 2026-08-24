import asyncio
import concurrent.futures
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status
from pinecone import Pinecone, ServerlessSpec

from app.core.config import settings

logger = logging.getLogger(__name__)
_EMBEDDING_DIM = 1536
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="pinecone")


class PineconeError(HTTPException):
    def __init__(self, detail: str = "Pinecone operation failed"):
        super().__init__(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail,
        )


def shutdown_executor() -> None:
    logger.info("Shutting down Pinecone thread pool executor...")
    _executor.shutdown(wait=False)
    logger.info("Pinecone thread pool executor shut down.")


class PineconeClient:
    def __init__(self) -> None:
        self._pc: Optional[Pinecone] = None
        self._index = None
        self._index_name = settings.PINECONE_INDEX_NAME

    async def initialise(self) -> None:
        logger.info("Initialising Pinecone client — index: %s", self._index_name)
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(_executor, self._sync_initialise)
            logger.info("Pinecone client ready — index: %s", self._index_name)
        except (ValueError, TypeError, RuntimeError) as exc:
            logger.error("Pinecone initialisation failed: %s", exc)
            raise PineconeError(detail="Search service is temporarily unavailable. Please try again.")

    def _sync_initialise(self) -> None:
        self._pc = Pinecone(api_key=settings.PINECONE_API_KEY)
        existing_names = [idx.name for idx in self._pc.list_indexes()]

        if self._index_name not in existing_names:
            logger.info(
                "Pinecone index '%s' not found — creating serverless index",
                self._index_name,
            )
            self._pc.create_index(
                name=self._index_name,
                dimension=_EMBEDDING_DIM,
                metric="cosine",
                spec=ServerlessSpec(
                    cloud="aws",
                    region=settings.PINECONE_ENVIRONMENT or "us-east-1",
                ),
            )
            logger.info("Pinecone index '%s' created successfully", self._index_name)

        self._index = self._pc.Index(self._index_name)

    async def _get_index(self):
        if self._index is not None:
            return self._index

        logger.warning(
            "PineconeClient._get_index called before initialise() — "
            "performing async fallback init. "
            "Ensure initialise() is called in the FastAPI lifespan."
        )
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(_executor, self._sync_initialise)
        return self._index

    def _make_namespace(self, place_id: str) -> str:
        return f"place_{place_id}"

    def _sync_get_index(self):
        if self._index is not None:
            return self._index

        self._sync_initialise()
        return self._index

    def _sync_upsert(
        self,
        vectors: List[Dict[str, Any]],
        namespace: str,
    ) -> int:
        idx = self._sync_get_index()
        response = idx.upsert(vectors=vectors, namespace=namespace)
        return response.upserted_count

    def _sync_query(
        self,
        vector: List[float],
        namespace: str,
        top_k: int,
        filter_dict: Optional[Dict[str, Any]],
        include_metadata: bool,
    ) -> List[Dict[str, Any]]:
        idx = self._sync_get_index()
        kwargs: Dict[str, Any] = {
            "vector": vector,
            "top_k": top_k,
            "namespace": namespace,
            "include_metadata": include_metadata,
        }
        if filter_dict:
            kwargs["filter"] = filter_dict

        response = idx.query(**kwargs)
        return [
            {
                "id": match.id,
                "score": match.score,
                "metadata": match.metadata or {},
            }
            for match in response.matches
        ]

    def _sync_delete_namespace(self, namespace: str) -> None:
        idx = self._sync_get_index()
        idx.delete(delete_all=True, namespace=namespace)

    async def upsert_vectors(
        self,
        place_id: str,
        vectors: List[Dict[str, Any]],
    ) -> int:
        namespace = self._make_namespace(place_id)
        logger.info(
            "Pinecone upsert — place_id: %s, namespace: %s, vectors: %d",
            place_id,
            namespace,
            len(vectors),
        )
        try:
            loop = asyncio.get_running_loop()
            count = await loop.run_in_executor(
                _executor,
                lambda: self._sync_upsert(vectors, namespace),
            )
            logger.info(
                "Pinecone upsert complete — place_id: %s, upserted: %d",
                place_id,
                count,
            )
            return count
        except PineconeError:
            raise
        except (ValueError, TypeError, RuntimeError) as exc:
            logger.error("Pinecone upsert failed for place_id %s: %s", place_id, exc)
            raise PineconeError(detail="Search service is temporarily unavailable. Please try again.")

    async def query_vectors(
        self,
        place_id: str,
        query_vector: List[float],
        top_k: int = 5,
        filter_dict: Optional[Dict[str, Any]] = None,
        include_metadata: bool = True,
    ) -> List[Dict[str, Any]]:
        namespace = self._make_namespace(place_id)
        logger.info(
            "Pinecone query — place_id: %s, namespace: %s, top_k: %d",
            place_id,
            namespace,
            top_k,
        )
        try:
            loop = asyncio.get_running_loop()
            matches = await loop.run_in_executor(
                _executor,
                lambda: self._sync_query(
                    query_vector, namespace, top_k, filter_dict, include_metadata
                ),
            )
            logger.info(
                "Pinecone query returned %d matches for place_id: %s",
                len(matches),
                place_id,
            )
            return matches
        except PineconeError:
            raise
        except (
            ValueError,
            TypeError,
            RuntimeError,
            concurrent.futures.TimeoutError,
        ) as exc:
            logger.error("Pinecone query failed for place_id %s: %s", place_id, exc)
            raise PineconeError(detail="Search service is temporarily unavailable. Please try again.")

    async def delete_place_namespace(self, place_id: str) -> None:
        namespace = self._make_namespace(place_id)
        logger.info(
            "Pinecone delete namespace — place_id: %s, namespace: %s",
            place_id,
            namespace,
        )
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                _executor,
                lambda: self._sync_delete_namespace(namespace),
            )
        except (
            ValueError,
            TypeError,
            RuntimeError,
            OSError,
            concurrent.futures.TimeoutError,
        ) as exc:
            logger.warning(
                "Pinecone namespace delete failed for place_id %s: %s",
                place_id,
                exc,
            )

