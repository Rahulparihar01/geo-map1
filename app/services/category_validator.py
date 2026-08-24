import logging
from typing import List, Optional

from app.schemas.discovery import DiscoveryCategory, DiscoveryPlaceResult
from app.utils.place_categories import (
    get_place_category,
    get_place_subcategory,
)

logger = logging.getLogger(__name__)

_CATEGORY_TARGET_MAP = {
    DiscoveryCategory.TOURIST: "tourist_attraction",
    DiscoveryCategory.RESTAURANT: "restaurant",
    DiscoveryCategory.SHOPPING: "shopping_mall",
    DiscoveryCategory.PARKING: "parking",
}


def assign_categories(
    places: List[DiscoveryPlaceResult],
    requested_category: DiscoveryCategory,
) -> List[DiscoveryPlaceResult]:
    cat_val = requested_category.value
    for place in places:
        place.assigned_category = get_place_category(place.primary_type)
        place.assigned_subcategory = get_place_subcategory(place.primary_type, category=cat_val)
    return places


def filter_places_by_category(
    places: List[DiscoveryPlaceResult],
    requested_category: DiscoveryCategory,
) -> List[DiscoveryPlaceResult]:
    if requested_category == DiscoveryCategory.EXPLORE:
        return places

    target = _CATEGORY_TARGET_MAP.get(requested_category)
    if not target:
        return places

    filtered: List[DiscoveryPlaceResult] = []
    removed_count = 0

    for place in places:
        assigned = get_place_category(place.primary_type)
        if assigned == target:
            filtered.append(place)
        else:
            removed_count += 1
            logger.debug(
                "Category filter removed: %s (type=%s, assigned=%s, expected=%s)",
                place.display_name,
                place.primary_type,
                assigned,
                target,
            )

    if removed_count > 0:
        logger.info(
            "Category filter: removed %d/%d places for category=%s",
            removed_count,
            len(places),
            requested_category.value,
        )

    return filtered


def filter_places_by_subcategory(
    places: List[DiscoveryPlaceResult],
    requested_subcategories: Optional[List[str]],
    category: Optional[DiscoveryCategory] = None,
) -> List[DiscoveryPlaceResult]:
    if not requested_subcategories:
        return places

    cat_val = category.value if category else None
    sub_set = set(requested_subcategories)
    filtered: List[DiscoveryPlaceResult] = []
    removed_count = 0

    for place in places:
        assigned = get_place_subcategory(place.primary_type, category=cat_val)
        if assigned in sub_set:
            place.assigned_subcategory = assigned
            filtered.append(place)
            continue

        types_match = None
        if place.types:
            for t in place.types:
                sub = get_place_subcategory(t, category=cat_val)
                if sub in sub_set:
                    types_match = sub
                    break

        if types_match is not None:
            place.assigned_subcategory = types_match
            filtered.append(place)
        else:
            removed_count += 1
            logger.debug(
                "Subcategory filter removed: %s (type=%s, assigned=%s, expected=%s)",
                place.display_name,
                place.primary_type,
                assigned,
                requested_subcategories,
            )

    if removed_count > 0:
        logger.info(
            "Subcategory filter: removed %d/%d places for subcategories=%s",
            removed_count,
            len(places),
            requested_subcategories,
        )

    return filtered


def apply_fine_dining_filter(
    places: List[DiscoveryPlaceResult],
) -> List[DiscoveryPlaceResult]:
    _FINE_DINING_PRICES = {"PRICE_LEVEL_EXPENSIVE", "PRICE_LEVEL_VERY_EXPENSIVE"}
    filtered = [
        p for p in places
        if p.price_level in _FINE_DINING_PRICES
        and p.rating is not None
        and p.rating >= 4.0
    ]
    if len(filtered) < len(places):
        logger.info(
            "Fine dining filter: kept %d/%d places (price_level + rating >= 4.0)",
            len(filtered),
            len(places),
        )
    return filtered
