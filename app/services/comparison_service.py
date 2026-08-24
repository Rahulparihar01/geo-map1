import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.integrations.openai_client import EmbeddingRateLimitError, OpenAIEmbeddingClient
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.saved_place_repository import SavedPlaceRepository
from app.repositories.visit_repository import VisitRepository
from app.repositories.location_repository import LocationRepository
from langfuse import observe, propagate_attributes
from app.schemas.comparison import (
    AttributeColumn,
    AttributeValue,
    CompareBasicResponse,
    CompareRecommendResponse,
    EnhancedComparisonResult,
    PhotoReference,
    PlaceUserContext,
    RecommendationResult,
    ReviewSummary,
    ScoreBreakdown,
)
from app.services.recommendation_engine import RecommendationEngine, price_sort_key
from app.utils.geo import haversine_distance_km
from app.utils.place_categories import CATEGORY_WEIGHTS, get_place_category

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.services.place_details_service import PlaceDetailsService


_ATTRIBUTE_DEFINITIONS: List[Tuple[str, str, str]] = [
    ("rating", "Rating", "numeric"),
    ("user_rating_count", "Reviews", "numeric"),
    ("price_level", "Price Level", "text"),
    ("business_status", "Status", "text"),
    ("open_now", "Open Now", "bool"),
    ("primary_type", "Type", "text"),
    ("wheelchair_accessible", "Wheelchair Accessible", "bool"),
    ("dine_in", "Dine-In", "bool"),
    ("takeout", "Takeout", "bool"),
    ("delivery", "Delivery", "bool"),
    ("outdoor_seating", "Outdoor Seating", "bool"),
    ("serves_breakfast", "Breakfast", "bool"),
    ("serves_lunch", "Lunch", "bool"),
    ("serves_dinner", "Dinner", "bool"),
    ("serves_beer", "Beer", "bool"),
    ("serves_wine", "Wine", "bool"),
    ("serves_cocktails", "Cocktails", "bool"),
    ("good_for_children", "Good for Children", "bool"),
    ("good_for_groups", "Good for Groups", "bool"),
    ("live_music", "Live Music", "bool"),
    ("reservable", "Reservations", "bool"),
    ("parking_free", "Free Parking", "bool"),
    ("parking_paid", "Paid Parking", "bool"),
    ("ev_charging", "EV Charging", "bool"),
    ("payment_credit_cards", "Cards Accepted", "bool"),
    ("distance_from_you_km", "Distance", "numeric"),
]

_PRICE_LABELS: Dict[str, str] = {
    "PRICE_LEVEL_FREE": "Free",
    "PRICE_LEVEL_INEXPENSIVE": "$",
    "PRICE_LEVEL_MODERATE": "$$",
    "PRICE_LEVEL_EXPENSIVE": "$$$",
    "PRICE_LEVEL_VERY_EXPENSIVE": "$$$$",
}


class ComparisonService:
    def __init__(
        self,
        db: Session,
        place_details_service: Optional["PlaceDetailsService"] = None,
        openai_client: Optional[OpenAIEmbeddingClient] = None,
    ) -> None:
        self.db = db
        self.knowledge_repo = KnowledgeRepository(db)
        self.saved_place_repo = SavedPlaceRepository(db)
        self.visit_repo = VisitRepository(db)
        self.location_repo = LocationRepository(db)
        self.recommendation_engine = RecommendationEngine()
        self.place_details_service = place_details_service
        self.openai_client = openai_client

    async def _ensure_place_details(self, place_ids: List[str]) -> None:
        if self.place_details_service is None:
            logger.debug(
                "Place details pre-fetch skipped — no PlaceDetailsService injected "
                "(falling back to DB-only lookup)"
            )
            return

        missing = [
            pid
            for pid in place_ids
            if self.knowledge_repo.get_place_detail(pid) is None
        ]
        if not missing:
            return

        logger.info(
            "Comparison pre-fetching place details from Google — missing=%d %s",
            len(missing),
            missing,
        )

        semaphore = asyncio.Semaphore(5)

        async def _fetch(pid: str) -> None:
            async with semaphore:
                try:
                    await self.place_details_service.get_place_details(pid)
                except Exception as exc:
                    logger.warning(
                        "Comparison pre-fetch failed for place_id=%s: %s",
                        pid,
                        exc,
                    )

        await asyncio.gather(*(_fetch(pid) for pid in missing))

    def _build_batch_user_contexts(
        self, user_id: int, place_ids: List[str]
    ) -> Dict[str, PlaceUserContext]:
        saved_by_place = {}
        try:
            saved_records = self.saved_place_repo.get_saved_by_place_ids(
                user_id, place_ids
            )
            for record in saved_records:
                saved_by_place[record.place_id] = record
        except Exception as exc:
            logger.debug("Batch load saved places failed: %s", exc)

        latest_visits = {}
        try:
            visit_records = self.visit_repo.get_latest_visits_by_place_ids(
                user_id, place_ids
            )
            for record in visit_records:
                latest_visits[record.place_id] = record
        except Exception as exc:
            logger.debug("Batch load visits failed: %s", exc)

        contexts = {}
        for pid in place_ids:
            ctx = PlaceUserContext()

            saved = saved_by_place.get(pid)
            if saved:
                ctx.is_saved = True
                ctx.saved_id = saved.id
                ctx.saved_at = saved.saved_at
                ctx.tags = saved.tags
                ctx.notes = saved.notes

            visit = latest_visits.get(pid)
            if visit:
                ctx.has_visited = True
                ctx.visited_at = visit.visited_at
                ctx.your_rating = visit.rating_given
                ctx.your_review = visit.review_text
                ctx.visit_mood = visit.mood
                ctx.visited_with = visit.with_whom

            contexts[pid] = ctx

        return contexts

    def _get_visited_place_ids(self, user_id: int, place_ids: List[str]) -> set:
        try:
            return self.visit_repo.get_visited_place_ids(user_id, place_ids)
        except Exception as exc:
            logger.debug("Batch load visited places failed: %s", exc)
            return set()

    def _get_user_gps(self, user_id: int) -> Tuple[Optional[float], Optional[float]]:
        try:
            loc = self.location_repo.get_current_location(user_id)
            if loc:
                return loc.latitude, loc.longitude
        except Exception as exc:
            logger.warning("Could not fetch user GPS for comparison: %s", exc)
        return None, None

    def _place_to_enhanced(
        self,
        place_id: str,
        batch_contexts: Dict[str, PlaceUserContext],
        user_lat: Optional[float] = None,
        user_lon: Optional[float] = None,
        visited_ids: Optional[set] = None,
    ) -> Optional[EnhancedComparisonResult]:
        place = self.knowledge_repo.get_place_detail(place_id)
        if not place:
            return None

        extended = place.extended_data or {}
        context = batch_contexts.get(place_id, PlaceUserContext())

        result = EnhancedComparisonResult(
            place_id=place.place_id,
            display_name=place.display_name,
            formatted_address=place.formatted_address,
            primary_type=place.primary_type,
            types=place.types,
            latitude=place.latitude,
            longitude=place.longitude,
            rating=place.rating,
            user_rating_count=place.user_rating_count,
            price_level=place.price_level,
            business_status=place.business_status,
            open_now=place.open_now,
            wheelchair_accessible=place.wheelchair_accessible_entrance,
            website_uri=place.website_uri,
            phone_number=place.international_phone_number
            or place.national_phone_number,
            google_maps_uri=place.google_maps_uri,
            editorial_summary=place.editorial_summary,
            dine_in=extended.get("dineIn"),
            takeout=extended.get("takeout"),
            delivery=extended.get("delivery"),
            curbside_pickup=extended.get("curbsidePickup"),
            serves_breakfast=extended.get("servesBreakfast"),
            serves_lunch=extended.get("servesLunch"),
            serves_dinner=extended.get("servesDinner"),
            serves_brunch=extended.get("servesBrunch"),
            serves_beer=extended.get("servesBeer"),
            serves_wine=extended.get("servesWine"),
            serves_cocktails=extended.get("servesCocktails"),
            serves_vegetarian_food=extended.get("servesVegetarianFood"),
            outdoor_seating=extended.get("outdoorSeating"),
            restroom=extended.get("restroom"),
            good_for_children=extended.get("goodForChildren"),
            good_for_groups=extended.get("goodForGroups"),
            live_music=extended.get("liveMusic"),
            reservable=extended.get("reservable"),
            allows_dogs=extended.get("allowsDogs"),
            parking_free=extended.get("parking_free"),
            parking_paid=extended.get("parking_paid"),
            parking_valet=extended.get("parking_valet"),
            ev_charging=extended.get("ev_charging"),
            payment_cash=extended.get("payment_cash"),
            payment_credit_cards=extended.get("payment_credit_cards"),
            payment_contactless=extended.get("payment_contactless"),
            payment_nfc=extended.get("payment_nfc"),
            wikipedia_extract=extended.get("wikipedia_extract"),
            neighborhood=extended.get("neighborhood") or extended.get("osm_suburb"),
            your_context=context,
            is_visit=place_id in (visited_ids or set()),
        )

        oh = place.opening_hours
        if oh:
            if isinstance(oh, dict):
                descs = oh.get("weekday_descriptions")
            else:
                descs = getattr(oh, "weekday_descriptions", None)
            if descs:
                result.opening_hours_summary = "; ".join(descs[:3])

        if place.photos and isinstance(place.photos, (list, tuple)):
            photos = []
            for photo in place.photos[:3]:
                if isinstance(photo, dict):
                    photos.append(
                        PhotoReference(
                            name=photo.get("name"),
                            width_px=photo.get("width_px", photo.get("widthPx")),
                            height_px=photo.get("height_px", photo.get("heightPx")),
                        )
                    )
            result.photo_references = photos or None

        if place.reviews and isinstance(place.reviews, (list, tuple)):
            reviews = []
            for review in place.reviews[:3]:
                if isinstance(review, dict):
                    text_obj = review.get("text", {})
                    text = (
                        text_obj.get("text") if isinstance(text_obj, dict) else text_obj
                    )
                    author = review.get("authorAttribution") or {}
                    author_name = (
                        author.get("displayName")
                        if isinstance(author, dict)
                        else review.get("author_name")
                    )
                    reviews.append(
                        ReviewSummary(
                            author_name=author_name or review.get("author_name"),
                            rating=review.get("rating"),
                            text=text,
                            relative_time=review.get("relativePublishTimeDescription")
                            or review.get("relative_publish_time_description"),
                        )
                    )
            result.top_reviews = reviews or None

        if (
            user_lat is not None
            and user_lon is not None
            and place.latitude is not None
            and place.longitude is not None
        ):
            result.distance_from_you_km = haversine_distance_km(
                user_lat, user_lon, place.latitude, place.longitude
            )

        return result

    async def _load_comparison_places(
        self,
        place_ids: List[str],
        user_id: int,
    ) -> Tuple[
        List[EnhancedComparisonResult],
        List[str],
        Optional[float],
        Optional[float],
    ]:
        user_lat, user_lon = self._get_user_gps(user_id)
        await self._ensure_place_details(place_ids)
        batch_contexts = self._build_batch_user_contexts(user_id, place_ids)
        visited_ids = self._get_visited_place_ids(user_id, place_ids)

        results: List[EnhancedComparisonResult] = []
        not_found: List[str] = []
        for place_id in place_ids:
            result = self._place_to_enhanced(
                place_id,
                batch_contexts,
                user_lat,
                user_lon,
                visited_ids,
            )
            if result:
                results.append(result)
            else:
                not_found.append(place_id)

        return results, not_found, user_lat, user_lon

    def _build_attribute_table(
        self, places: List[EnhancedComparisonResult]
    ) -> List[AttributeColumn]:
        columns: List[AttributeColumn] = []

        for key, label, _type in _ATTRIBUTE_DEFINITIONS:
            values: List[AttributeValue] = []
            for place in places:
                raw_value = getattr(place, key, None)
                display_label = None

                if key == "price_level" and raw_value:
                    display_label = _PRICE_LABELS.get(raw_value, raw_value)
                elif key == "distance_from_you_km" and raw_value is not None:
                    display_label = f"{raw_value} km"
                elif key == "business_status" and raw_value:
                    display_label = raw_value.replace("_", " ").title()
                elif key == "open_now":
                    display_label = (
                        "Yes" if raw_value else "No" if raw_value is False else None
                    )

                values.append(
                    AttributeValue(
                        place_id=place.place_id,
                        value=raw_value,
                        label=display_label,
                    )
                )

            if any(v.value is not None for v in values):
                columns.append(AttributeColumn(key=key, label=label, values=values))

        return columns

    def _compute_highlights(
        self, results: List[EnhancedComparisonResult]
    ) -> Dict[str, Any]:
        highlights: Dict[str, Any] = {}

        rated = [r for r in results if r.rating is not None]
        if rated:
            best_rated = max(rated, key=lambda r: (r.rating, r.user_rating_count or 0))
            highlights["highest_rated"] = {
                "place_id": best_rated.place_id,
                "name": best_rated.display_name,
                "rating": best_rated.rating,
                "review_count": best_rated.user_rating_count,
            }

        reviewed = [r for r in results if r.user_rating_count is not None]
        if reviewed:
            most = max(reviewed, key=lambda r: r.user_rating_count or 0)
            highlights["most_reviews"] = {
                "place_id": most.place_id,
                "name": most.display_name,
                "count": most.user_rating_count,
            }

        priced = [
            r
            for r in results
            if r.price_level is not None and r.rating is not None and r.rating >= 3.5
        ]
        if priced:
            cheapest = min(priced, key=lambda r: price_sort_key(r.price_level))
            highlights["best_value"] = {
                "place_id": cheapest.place_id,
                "name": cheapest.display_name,
                "price_level": _PRICE_LABELS.get(
                    cheapest.price_level, cheapest.price_level
                ),
                "rating": cheapest.rating,
            }

        amenity_fields = [
            "dine_in",
            "takeout",
            "delivery",
            "outdoor_seating",
            "serves_breakfast",
            "serves_lunch",
            "serves_dinner",
            "serves_beer",
            "serves_wine",
            "good_for_groups",
            "live_music",
            "reservable",
        ]
        amenity_counts = []
        for r in results:
            count = sum(
                1 for field in amenity_fields if getattr(r, field, None) is True
            )
            amenity_counts.append((r.place_id, r.display_name, count))

        if amenity_counts:
            most_amenities = max(amenity_counts, key=lambda x: x[2])
            if most_amenities[2] > 0:
                highlights["most_amenities"] = {
                    "place_id": most_amenities[0],
                    "name": most_amenities[1],
                    "count": most_amenities[2],
                }

        with_distance = [r for r in results if r.distance_from_you_km is not None]
        if with_distance:
            closest = min(with_distance, key=lambda r: r.distance_from_you_km or 999)
            highlights["closest_to_you"] = {
                "place_id": closest.place_id,
                "name": closest.display_name,
                "distance_km": closest.distance_from_you_km,
            }

        return highlights

    async def _get_summary(
        self,
        ranked: List[Tuple[EnhancedComparisonResult, float, ScoreBreakdown]],
    ) -> str:
        if self.openai_client is None:
            logger.warning("AI summary skipped — no OpenAI client, using fallback")
            return self._fallback_summary(ranked)

        try:
            place_lines = []
            for i, (place, score, breakdown) in enumerate(ranked[:5], 1):
                place_lines.append(
                    f"{i}. {place.display_name or 'Unknown'} "
                    f"(Score: {score}/100, Rating: {place.rating or 'N/A'}, "
                    f"Price: {place.price_level or 'N/A'}, "
                    f"Distance: {place.distance_from_you_km or 'N/A'} km)"
                )

            prompt = (
                "You are a travel recommendation assistant. "
                "Compare the following places and write 2-3 sentences explaining "
                "why each is ranked where it is. Be concise and helpful.\n\n"
                + "\n".join(place_lines)
                + "\n\nWrite a brief natural-language comparison summary."
            )

            summary = await self.openai_client.get_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=500,
            )
            return summary.strip()

        except EmbeddingRateLimitError:
            logger.warning("AI summary rate limited — using fallback template")
            return self._fallback_summary(ranked)
        except Exception as exc:
            logger.warning("AI summary failed: %s — using fallback template", exc)
            return self._fallback_summary(ranked)

    def _fallback_summary(
        self,
        ranked: List[Tuple[EnhancedComparisonResult, float, ScoreBreakdown]],
    ) -> str:
        if not ranked:
            return "No places to compare."

        top = ranked[0][0]
        top_score = ranked[0][1]
        parts = [
            f"{top.display_name or 'The top place'} is recommended with a score of {top_score}/100."
        ]

        if len(ranked) > 1:
            second = ranked[1][0]
            second_score = ranked[1][1]
            diff = round(top_score - second_score, 1)
            if diff > 10:
                parts.append(
                    f"It significantly outperforms {second.display_name or 'the next option'} "
                    f"by {diff} points."
                )
            else:
                parts.append(
                    f"{second.display_name or 'The second option'} is a close alternative "
                    f"with a score of {second_score}."
                )

        return " ".join(parts)

    async def compare_basic(
        self,
        place_ids: List[str],
        user_id: int,
    ) -> CompareBasicResponse:
        logger.info(
            "Comparison basic — user_id=%s places=%d ids=%s",
            user_id,
            len(place_ids),
            place_ids,
        )
        results, not_found, user_lat, user_lon = await self._load_comparison_places(
            place_ids,
            user_id,
        )

        if not results:
            not_found_msg = (
                "None of the requested places could be loaded — they may not "
                f"exist on Google Maps, or the upstream fetch failed. Not found: {', '.join(not_found) or 'n/a'}."
            )
            return CompareBasicResponse(
                success=False,
                message=not_found_msg,
                places=[],
                attribute_table=[],
                highlights=None,
                total_places=0,
                user_location_used=(user_lat is not None),
            )

        attribute_table = self._build_attribute_table(results)
        highlights = self._compute_highlights(results)
        suffix = (
            f" {len(not_found)} place(s) not found: {', '.join(not_found)}"
            if not_found
            else ""
        )
        msg = f"Compared {len(results)} place(s)." + suffix

        return CompareBasicResponse(
            success=True,
            message=msg,
            places=results,
            attribute_table=attribute_table,
            highlights=highlights,
            total_places=len(results),
            user_location_used=(user_lat is not None),
        )

    @observe(name="comparison-recommend")
    async def recommend(
        self,
        place_ids: List[str],
        user_id: int,
    ) -> CompareRecommendResponse:
        logger.info(
            "Comparison recommend — user_id=%s places=%d ids=%s",
            user_id,
            len(place_ids),
            place_ids,
        )
        results, not_found, _, _ = await self._load_comparison_places(
            place_ids,
            user_id,
        )

        if not results:
            not_found_msg = (
                "None of the requested places could be loaded — they may not "
                f"exist on Google Maps, or the upstream fetch failed. Not found: {', '.join(not_found) or 'n/a'}."
            )
            return CompareRecommendResponse(
                success=False,
                message=not_found_msg,
                recommendations=[],
                total_places_compared=0,
            )

        # Determine dominant category from the places being compared
        # and use category-specific scoring weights
        types_list = [p.primary_type for p in results if p.primary_type]
        if types_list:
            from collections import Counter
            most_common_type = Counter(types_list).most_common(1)[0][0]
            dominant_category = get_place_category(most_common_type) or "explore"
        else:
            dominant_category = "explore"

        category_weights = CATEGORY_WEIGHTS.get(dominant_category)
        scored = self.recommendation_engine.compute_scores(results, weights=category_weights)
        recommendations: List[RecommendationResult] = []
        for rank, (place, score, breakdown) in enumerate(scored, 1):
            strengths = self.recommendation_engine.extract_strengths(
                place, breakdown, results
            )

            photos = None
            if place.photo_references:
                photos = place.photo_references[:2]

            recommendations.append(
                RecommendationResult(
                    rank=rank,
                    place_id=place.place_id,
                    display_name=place.display_name,
                    primary_type=place.primary_type,
                    formatted_address=place.formatted_address,
                    latitude=place.latitude,
                    longitude=place.longitude,
                    rating=place.rating,
                    price_level=place.price_level,
                    photo_references=photos,
                    overall_score=score,
                    score_breakdown=breakdown,
                    strengths=strengths,
                    your_context=place.your_context,
                    is_visit=place.is_visit,
                )
            )

        with propagate_attributes(
            user_id=str(user_id),
            metadata={"feature": "comparison"},
        ):
            overall_summary = await self._get_summary(scored)
        suffix = (
            f" {len(not_found)} place(s) not found: {', '.join(not_found)}"
            if not_found
            else ""
        )
        msg = f"Compared and ranked {len(recommendations)} place(s)." + suffix
        return CompareRecommendResponse(
            success=True,
            message=msg,
            recommendations=recommendations,
            overall_ai_summary=overall_summary,
            total_places_compared=len(recommendations),
        )