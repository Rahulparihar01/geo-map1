import logging
from typing import List, Optional

from sqlalchemy import insert as sql_insert
from sqlalchemy.orm import Session
from app.models.search_query import SearchQuery
from app.models.search_result import SearchResult
from app.schemas.discovery import DiscoveryPlaceResult

logger = logging.getLogger(__name__)


class SearchRepository:

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_search_query(
        self,
        *,
        user_id: int,
        search_mode: str,
        resolved_mode: Optional[str],
        raw_query: Optional[str],
        latitude: Optional[float],
        longitude: Optional[float],
        radius: Optional[float],
        result_count: int,
        from_cache: bool,
    ) -> SearchQuery:
        record = SearchQuery(
            user_id=user_id,
            search_mode=search_mode,
            resolved_mode=resolved_mode,
            raw_query=raw_query,
            latitude=latitude,
            longitude=longitude,
            radius=radius,
            result_count=result_count,
            from_cache=from_cache,
        )
        self.db.add(record)
        self.db.flush()
        logger.debug(
            "SearchQuery flushed: id=%s user=%s mode=%s query=%r results=%s cache=%s",
            record.id,
            user_id,
            search_mode,
            raw_query,
            result_count,
            from_cache,
        )
        return record

    def create_search_results(
        self,
        *,
        query_id: int,
        user_id: int,
        places: List[DiscoveryPlaceResult],
    ) -> List[SearchResult]:
        mappings = []
        for position, place in enumerate(places):
            mappings.append(
                {
                    "query_id": query_id,
                    "user_id": user_id,
                    "place_id": place.place_id or "",
                    "display_name": place.display_name,
                    "formatted_address": place.formatted_address,
                    "primary_type": place.primary_type,
                    "latitude": place.latitude,
                    "longitude": place.longitude,
                    "rating": place.rating,
                    "user_rating_count": place.user_rating_count,
                    "business_status": place.business_status,
                    "rank_position": position,
                }
            )

        if mappings:
            self.db.execute(sql_insert(SearchResult), mappings)
            self.db.flush()
            return [SearchResult(**m) for m in mappings]
        return []
