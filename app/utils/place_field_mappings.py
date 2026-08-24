DINING_FLAGS = {
    "dineIn": "Dine-in available",
    "takeout": "Takeout available",
    "delivery": "Delivery available",
    "curbsidePickup": "Curbside pickup available",
    "reservable": "Reservations accepted",
}

FOOD_FLAGS = {
    "servesBreakfast": "Serves breakfast",
    "servesLunch": "Serves lunch",
    "servesDinner": "Serves dinner",
    "servesBeer": "Serves beer",
    "servesWine": "Serves wine",
    "servesCocktails": "Serves cocktails",
}

ATMOSPHERE_FLAGS = {
    "outdoorSeating": "Has outdoor seating",
    "liveMusic": "Has live music",
    "goodForChildren": "Good for children",
    "goodForGroups": "Good for groups",
    "allowsDogs": "Allows dogs",
    "restroom": "Has restroom",
}

PREFIX_MAPPINGS = {
    "parking_": "Parking available: {label}",
    "payment_": "Payment accepted: {label}",
}

LOCATION_CONTEXT_FIELDS = [
    "neighborhood",
    "sublocality",
    "locality",
    "state",
    "country",
]


def extract_summary(place) -> str:
    parts = []
    if place.display_name:
        parts.append(f"Place: {place.display_name}")
    if place.formatted_address:
        parts.append(f"Address: {place.formatted_address}")
    if place.latitude and place.longitude:
        parts.append(f"Coordinates: {place.latitude:.6f}, {place.longitude:.6f}")
    if place.editorial_summary:
        parts.append(f"About: {place.editorial_summary}")
    return "\n".join(parts)


def extract_category(place) -> str:
    parts = []
    if place.primary_type:
        parts.append(f"Primary category: {place.primary_type}")
    if place.types and isinstance(place.types, list):
        parts.append(f"All categories: {', '.join(place.types)}")
    return "\n".join(parts)


def extract_hours(place) -> str:
    parts = []
    if place.open_now is not None:
        parts.append(f"Currently open: {'Yes' if place.open_now else 'No'}")
    if place.opening_hours and isinstance(place.opening_hours, dict):
        weekdays = place.opening_hours.get("weekday_descriptions")
        if weekdays and isinstance(weekdays, list):
            parts.append("Opening hours:")
            parts.extend(f"  {line}" for line in weekdays)
    return "\n".join(parts)


def extract_contact(place) -> str:
    parts = []
    if place.international_phone_number:
        parts.append(f"International phone: {place.international_phone_number}")
    if place.national_phone_number:
        parts.append(f"National phone: {place.national_phone_number}")
    if place.website_uri:
        parts.append(f"Website: {place.website_uri}")
    if place.google_maps_uri:
        parts.append(f"Google Maps: {place.google_maps_uri}")
    return "\n".join(parts)


def extract_ratings(place) -> str:
    parts = []
    if place.rating is not None:
        parts.append(f"Rating: {place.rating} / 5.0")
    if place.user_rating_count is not None:
        parts.append(f"Number of reviews: {place.user_rating_count}")
    if place.price_level:
        label = place.price_level.replace("PRICE_LEVEL_", "").capitalize()
        parts.append(f"Price level: {label}")
    if place.business_status:
        status_label = place.business_status.replace("_", " ").capitalize()
        parts.append(f"Business status: {status_label}")
    return "\n".join(parts)


def extract_accessibility(place) -> str:
    if place.wheelchair_accessible_entrance is not None:
        accessible = place.wheelchair_accessible_entrance
        return f"Wheelchair accessible entrance: {'Yes' if accessible else 'No'}"
    return ""


def extract_amenities(place) -> str:
    parts = []
    extended_data = place.extended_data or {}
    
    if not isinstance(extended_data, dict):
        return ""

    for flag_dict in [DINING_FLAGS, FOOD_FLAGS, ATMOSPHERE_FLAGS]:
        for key, label in flag_dict.items():
            if extended_data.get(key) is True:
                parts.append(label)
            elif extended_data.get(key) is False:
                parts.append(f"No {label.lower()}")

    for key, val in extended_data.items():
        for prefix, template in PREFIX_MAPPINGS.items():
            if key.startswith(prefix) and val is True:
                label = key.replace(prefix, "").replace("_", " ").title()
                parts.append(template.format(label=label))
            elif key.startswith(prefix) and val is False:
                label = key.replace(prefix, "").replace("_", " ").title()
                parts.append(f"No {template.lower().format(label=label)}")

    if extended_data.get("ev_charger_options"):
        ev = extended_data["ev_charger_options"]
        if isinstance(ev, dict):
            count = ev.get("chargerCount", "some")
            parts.append(f"EV charging available ({count} chargers)")

    wiki_extract = extended_data.get("wikipedia_extract")
    if wiki_extract:
        parts.append(f"\nFrom Wikipedia:\n{wiki_extract[:1000]}")

    for field in LOCATION_CONTEXT_FIELDS:
        val = extended_data.get(field)
        if val:
            parts.append(f"Location context: {field.replace('_', ' ').title()}: {val}")

    return "\n".join(parts)


def extract_reviews(place) -> str:
    parts = []
    reviews = place.reviews or []
    
    if isinstance(reviews, list):
        for i, review in enumerate(reviews[:5], start=1):
            if not isinstance(review, dict):
                continue
            text = review.get("text") or ""
            author = review.get("author_name") or "Anonymous"
            rating = review.get("rating")
            if text.strip():
                stars = f" ({rating}/5)" if rating is not None else ""
                snippet = text.strip()[:500]
                parts.append(f"Review {i} by {author}{stars}:\n  {snippet}")
    
    return "\n\n".join(parts)


SECTION_EXTRACTORS = {
    "summary": extract_summary,
    "category": extract_category,
    "hours": extract_hours,
    "contact": extract_contact,
    "ratings": extract_ratings,
    "accessibility": extract_accessibility,
    "amenities": extract_amenities,
    "reviews": extract_reviews,
}
