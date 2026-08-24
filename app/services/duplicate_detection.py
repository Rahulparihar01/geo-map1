import logging
from difflib import SequenceMatcher
from typing import List

from app.schemas.discovery import DiscoveryPlaceResult
from app.utils.geo import haversine_distance_meters

logger = logging.getLogger(__name__)

GEO_THRESHOLD_METERS = 50.0
NAME_SIMILARITY_THRESHOLD = 0.75


def deduplicate_places(
    places: List[DiscoveryPlaceResult],
) -> List[DiscoveryPlaceResult]:

    if not places:
        return []

    # --- Pass 1: Exact place_id dedup ---
    seen_ids: set = set()
    pass1: List[DiscoveryPlaceResult] = []
    for place in places:
        if place.place_id and place.place_id not in seen_ids:
            pass1.append(place)
            seen_ids.add(place.place_id)
        elif not place.place_id:
            pass1.append(place)

    # --- Pass 2: Fuzzy + geo dedup ---
    result: List[DiscoveryPlaceResult] = []
    merged_indices: set = set()
    duplicate_count = 0

    for i, candidate in enumerate(pass1):
        if i in merged_indices:
            continue

        best = candidate
        for j in range(i + 1, len(pass1)):
            if j in merged_indices:
                continue
            other = pass1[j]
            if _is_duplicate(best, other):
                best = _merge_places(best, other)
                merged_indices.add(j)
                duplicate_count += 1

        result.append(best)

    if duplicate_count > 0:
        logger.info(
            "Duplicate detection: merged %d duplicates from %d places",
            duplicate_count,
            len(places),
        )

    return result


def _is_duplicate(
    a: DiscoveryPlaceResult,
    b: DiscoveryPlaceResult,
) -> bool:
    # Both must have coordinates for geo check
    if a.latitude is None or b.latitude is None:
        return False
    if a.longitude is None or b.longitude is None:
        return False

    # Quick geo rejection — if far apart, not a duplicate
    dist = haversine_distance_meters(
        a.latitude, a.longitude,
        b.latitude, b.longitude,
    )
    if dist >= GEO_THRESHOLD_METERS:
        return False

    # Name similarity check
    name_a = (a.display_name or "").lower().strip()
    name_b = (b.display_name or "").lower().strip()
    if not name_a or not name_b:
        return False

    similarity = SequenceMatcher(None, name_a, name_b).ratio()
    return similarity >= NAME_SIMILARITY_THRESHOLD


def _merge_places(
    keep: DiscoveryPlaceResult,
    discard: DiscoveryPlaceResult,
) -> DiscoveryPlaceResult:
    if (discard.rating or 0) > (keep.rating or 0):
        keep, discard = discard, keep

    data = keep.model_dump()

    for field_name in data:
        if data[field_name] is None:
            data[field_name] = getattr(discard, field_name)

    if (keep.user_rating_count or 0) < (discard.user_rating_count or 0):
        data["user_rating_count"] = discard.user_rating_count
        data["rating"] = discard.rating

    return DiscoveryPlaceResult(**data)
