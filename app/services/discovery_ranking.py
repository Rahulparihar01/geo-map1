import json
import logging
import math
from typing import List, Optional

from app.schemas.discovery import DiscoveryPlaceResult
from app.utils.geo import haversine_distance_km

logger = logging.getLogger(__name__)

_AI_MAX_CANDIDATES = 10
_DETERMINISTIC_WEIGHT = 0.6
_AI_WEIGHT = 0.4


def _deterministic_score(
    place: DiscoveryPlaceResult,
    max_rating: float,
    max_reviews: int,
    max_distance: float,
) -> float:
    score = 0.0

    if place.rating is not None and max_rating > 0:
        score += (place.rating / max_rating) * 30.0

    reviews = place.user_rating_count or 0
    if max_reviews > 0 and reviews > 0:
        log_rev = math.log10(reviews + 1)
        log_max = math.log10(max_reviews + 1)
        score += (log_rev / log_max) * 20.0

    if place.latitude is not None and place.longitude is not None and max_distance > 0:
        dist = getattr(place, "_distance_km", None)
        if dist is None and max_distance > 0:
            dist = 0.0
        if dist is not None and max_distance > 0:
            proximity = max(0.0, 1.0 - (dist / max_distance))
            score += proximity * 30.0

    if place.open_now is True:
        score += 10.0

    if place.first_photo_name:
        score += 5.0

    if place.business_status and place.business_status != "OPERATIONAL":
        score *= 0.5

    return round(min(score, 100.0), 1)


def _compute_distances(
    places: List[DiscoveryPlaceResult],
    user_lat: float,
    user_lon: float,
) -> float:
    max_dist = 0.0
    for p in places:
        if p.latitude is not None and p.longitude is not None:
            d = haversine_distance_km(user_lat, user_lon, p.latitude, p.longitude)
            p._distance_km = d  # type: ignore[attr-defined]
            if d > max_dist:
                max_dist = d
        else:
            p._distance_km = None  # type: ignore[attr-defined]
    return max_dist


def _build_ai_prompt(
    places: List[DiscoveryPlaceResult],
    category: str,
    subcategories: Optional[List[str]],
) -> str:
    sub_desc = ", ".join(subcategories) if subcategories else "any"

    place_lines = []
    for i, p in enumerate(places, 1):
        parts = [f"{i}. {p.display_name or 'Unknown'}"]
        if p.primary_type:
            parts.append(f"(type: {p.primary_type})")
        if p.rating is not None:
            parts.append(f"rating: {p.rating}")
        if p.user_rating_count:
            parts.append(f"reviews: {p.user_rating_count}")
        dist = getattr(p, "_distance_km", None)
        if dist is not None:
            parts.append(f"distance: {dist:.1f}km")
        if p.price_level:
            parts.append(f"price: {p.price_level}")
        place_lines.append(" ".join(parts))

    return (
        f"You are a place discovery assistant. Score each place's relevance "
        f"from 0.0 to 1.0 for the user's request.\n\n"
        f"User request: category={category}, subcategories={sub_desc}\n\n"
        f"Places:\n" + "\n".join(place_lines) + "\n\n"
        f"Return a JSON array of objects with place_id and relevance_score (0.0-1.0).\n"
        f"Only return the JSON array, nothing else.\n"
        f'Example: [{{"place_id": "ChIJ...", "relevance_score": 0.92}}]'
    )


def _parse_ai_response(
    raw: str,
    places: List[DiscoveryPlaceResult],
) -> dict:
    try:
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        data = json.loads(raw)
        if not isinstance(data, list):
            return {}

        scores = {}
        for item in data:
            if isinstance(item, dict):
                pid = item.get("place_id")
                score = item.get("relevance_score")
                if pid and isinstance(score, (int, float)):
                    scores[pid] = max(0.0, min(1.0, float(score)))
        return scores
    except (json.JSONDecodeError, ValueError, TypeError):
        logger.warning("Failed to parse AI relevance response")
        return {}


async def rank_places_with_ai(
    places: List[DiscoveryPlaceResult],
    category: str,
    subcategories: Optional[List[str]],
    user_lat: float,
    user_lon: float,
    openai_client=None,
) -> List[DiscoveryPlaceResult]:
    if not places:
        return places

    max_distance = _compute_distances(places, user_lat, user_lon)

    max_rating = max((p.rating or 0.0) for p in places)
    max_reviews = max((p.user_rating_count or 0) for p in places)

    for p in places:
        p._det_score = _deterministic_score(  # type: ignore[attr-defined]
            p, max_rating, max_reviews, max_distance
        )

    ai_scores: dict = {}
    if openai_client is not None and len(places) > 1:
        candidates = sorted(places, key=lambda p: p._det_score, reverse=True)[:_AI_MAX_CANDIDATES]  # type: ignore[attr-defined]
        prompt = _build_ai_prompt(candidates, category, subcategories)

        try:
            raw_response = await openai_client.chat_completion(
                system_prompt="You are a JSON-only assistant. Return only valid JSON.",
                user_message=prompt,
                temperature=0.3,
                max_tokens=500,
            )
            ai_scores = _parse_ai_response(raw_response, candidates)
            logger.info(
                "AI re-ranking: scored %d/%d candidates for category=%s sub=%s",
                len(ai_scores),
                len(candidates),
                category,
                subcategories,
            )
        except Exception as exc:
            logger.warning("AI re-ranking failed, using deterministic only: %s", exc)

    for p in places:
        det = getattr(p, "_det_score", 50.0)  
        ai = ai_scores.get(p.place_id, 0.5) if ai_scores else 0.5

        if ai_scores:
            p._final_score = round(  
                (det * _DETERMINISTIC_WEIGHT) + (ai * 100.0 * _AI_WEIGHT), 1
            )
        else:
            p._final_score = round(det, 1)  

    places.sort(key=lambda p: getattr(p, "_final_score", 0), reverse=True)  

    for p in places:
        if hasattr(p, "_det_score"):
            del p._det_score
        if hasattr(p, "_final_score"):
            del p._final_score
        if hasattr(p, "_distance_km"):
            del p._distance_km

    return places
