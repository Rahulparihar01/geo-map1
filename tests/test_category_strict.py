"""
Comprehensive test: simulate Google returning places for each category/subcategory combo.
Verifies that ONLY valid places pass through the filtering pipeline.
"""
import sys
sys.path.insert(0, ".")

from app.schemas.discovery import DiscoveryCategory, DiscoveryPlaceResult
from app.services.category_validator import (
    assign_categories,
    filter_places_by_category,
    filter_places_by_subcategory,
    apply_fine_dining_filter,
    filter_hidden_gems,
)
from app.utils.place_categories import (
    SUBCATEGORIES,
    SUBCATEGORY_TO_GOOGLE_TYPES,
    CATEGORY_TO_GOOGLE_TYPES,
    get_place_category,
)

PASS = 0
FAIL = 0


def make_place(place_id, name, primary_type, types=None, rating=None, user_rating_count=None, price_level=None):
    return DiscoveryPlaceResult(
        place_id=place_id,
        display_name=name,
        primary_type=primary_type,
        types=types or [primary_type],
        rating=rating,
        user_rating_count=user_rating_count,
        price_level=price_level,
    )


def simulate_nearby(category_value, subcategories, google_places):
    """
    Simulates the full nearby_search filtering pipeline:
    Google API -> dedup -> assign_categories -> filter_by_category -> filter_by_subcategory -> special filters
    """
    cat = DiscoveryCategory(category_value)
    
    # Build type filter to check skip_subcategory_filter logic
    merged_types = set()
    has_empty = False
    if subcategories:
        for sub in subcategories:
            sub_types = SUBCATEGORY_TO_GOOGLE_TYPES.get(sub, None)
            if sub_types is not None:
                if sub_types:
                    merged_types.update(sub_types)
                else:
                    has_empty = True
    
    skip_subcategory = False
    if subcategories:
        if not merged_types and has_empty:
            skip_subcategory = True
    
    places = [make_place(**p) for p in google_places]
    places = assign_categories(places, cat)
    places = filter_places_by_category(places, cat)
    if not skip_subcategory:
        places = filter_places_by_subcategory(places, subcategories, category=cat)
    if subcategories and "fine_dining" in subcategories:
        places = apply_fine_dining_filter(places)
    if subcategories and "hidden_gems" in subcategories:
        places = filter_hidden_gems(places)
    
    return places


def test(name, category, subcategories, google_places, expected_ids, forbidden_ids=None):
    global PASS, FAIL
    results = simulate_nearby(category, subcategories, google_places)
    result_ids = [r.place_id for r in results]
    result_names = [r.display_name for r in results]
    
    ok = True
    reasons = []
    
    for eid in expected_ids:
        if eid not in result_ids:
            ok = False
            reasons.append(f"MISSING expected: {eid}")
    
    if forbidden_ids:
        for fid in forbidden_ids:
            if fid in result_ids:
                ok = False
                reasons.append(f"LEAKED forbidden: {fid}")
    
    if ok:
        PASS += 1
        print(f"  PASS {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}")
        for r in reasons:
            print(f"     {r}")
        print(f"     Got: {result_names}")


# ============================================================
# TOURIST tests
# ============================================================
print("\n=== TOURIST CATEGORY ===")

# tourist, no subcategory — should keep tourist types only
test(
    "tourist (no sub): museum + fort kept, oppo/school rejected",
    "tourist", None,
    [
        {"place_id": "m1", "name": "Museum", "primary_type": "museum"},
        {"place_id": "f1", "name": "Red Fort", "primary_type": "historical_landmark"},
        {"place_id": "o1", "name": "Oppo Service", "primary_type": "electronics_store"},
        {"place_id": "s1", "name": "School", "primary_type": "school"},
        {"place_id": "c1", "name": "Cosmetics", "primary_type": "cosmetics_store"},
        {"place_id": "r1", "name": "Restaurant", "primary_type": "restaurant"},
    ],
    expected_ids=["m1", "f1"],
    forbidden_ids=["o1", "s1", "c1", "r1"],
)

# tourist + cultural_attractions — only museum, cultural_center, art_gallery
test(
    "tourist + cultural_attractions: only museum kept",
    "tourist", ["cultural_attractions"],
    [
        {"place_id": "m1", "name": "Museum", "primary_type": "museum"},
        {"place_id": "f1", "name": "Red Fort", "primary_type": "historical_landmark"},
        {"place_id": "o1", "name": "Oppo", "primary_type": "electronics_store"},
        {"place_id": "a1", "name": "Art Gallery", "primary_type": "art_gallery"},
    ],
    expected_ids=["m1", "a1"],
    forbidden_ids=["f1", "o1"],
)

# tourist + historic_sites — only historical_landmark, castle, fort
test(
    "tourist + historic_sites: fort kept, museum rejected",
    "tourist", ["historic_sites"],
    [
        {"place_id": "f1", "name": "Red Fort", "primary_type": "historical_landmark"},
        {"place_id": "m1", "name": "Museum", "primary_type": "museum"},
        {"place_id": "c1", "name": "Castle", "primary_type": "castle"},
        {"place_id": "o1", "name": "Oppo", "primary_type": "electronics_store"},
    ],
    expected_ids=["f1", "c1"],
    forbidden_ids=["m1", "o1"],
)

# tourist + landmarks_attractions — only tourist_attraction, monument, observation_deck
test(
    "tourist + landmarks_attractions: monument kept, school rejected",
    "tourist", ["landmarks_attractions"],
    [
        {"place_id": "mn1", "name": "Monument", "primary_type": "monument"},
        {"place_id": "ta1", "name": "Gateway", "primary_type": "tourist_attraction"},
        {"place_id": "s1", "name": "School", "primary_type": "school"},
        {"place_id": "m1", "name": "Museum", "primary_type": "museum"},
    ],
    expected_ids=["mn1", "ta1"],
    forbidden_ids=["s1", "m1"],
)

# tourist + parks_nature — only park, national_park, botanical_garden
test(
    "tourist + parks_nature: park kept, restaurant rejected",
    "tourist", ["parks_nature"],
    [
        {"place_id": "p1", "name": "Park", "primary_type": "park"},
        {"place_id": "np1", "name": "Nat Park", "primary_type": "national_park"},
        {"place_id": "r1", "name": "Restaurant", "primary_type": "restaurant"},
        {"place_id": "m1", "name": "Museum", "primary_type": "museum"},
    ],
    expected_ids=["p1", "np1"],
    forbidden_ids=["r1", "m1"],
)

# tourist + tours_experiences — only tourist_attraction, visitor_center
test(
    "tourist + tours_experiences: visitor_center kept, shop/museum rejected",
    "tourist", ["tours_experiences"],
    [
        {"place_id": "vc1", "name": "Visitor Center", "primary_type": "visitor_center"},
        {"place_id": "ta1", "name": "Landmark", "primary_type": "tourist_attraction"},
        {"place_id": "sh1", "name": "Shop", "primary_type": "store"},
        {"place_id": "m1", "name": "Museum", "primary_type": "museum"},
    ],
    expected_ids=["vc1"],
    forbidden_ids=["ta1", "sh1", "m1"],
)

# tourist + multiple subcategories
test(
    "tourist + [historic_sites, cultural_attractions]: fort + museum kept, oppo rejected",
    "tourist", ["historic_sites", "cultural_attractions"],
    [
        {"place_id": "f1", "name": "Fort", "primary_type": "fort"},
        {"place_id": "m1", "name": "Museum", "primary_type": "museum"},
        {"place_id": "o1", "name": "Oppo", "primary_type": "electronics_store"},
        {"place_id": "s1", "name": "School", "primary_type": "school"},
    ],
    expected_ids=["f1", "m1"],
    forbidden_ids=["o1", "s1"],
)


# ============================================================
# RESTAURANT tests
# ============================================================
print("\n=== RESTAURANT CATEGORY ===")

test(
    "restaurant (no sub): cafe + restaurant kept, museum rejected",
    "restaurant", None,
    [
        {"place_id": "ca1", "name": "Cafe", "primary_type": "cafe"},
        {"place_id": "re1", "name": "Restaurant", "primary_type": "restaurant"},
        {"place_id": "m1", "name": "Museum", "primary_type": "museum"},
        {"place_id": "o1", "name": "Oppo", "primary_type": "electronics_store"},
    ],
    expected_ids=["ca1", "re1"],
    forbidden_ids=["m1", "o1"],
)

test(
    "restaurant + cafes_coffee: only cafe/coffee_shop kept",
    "restaurant", ["cafes_coffee"],
    [
        {"place_id": "ca1", "name": "Cafe", "primary_type": "cafe"},
        {"place_id": "cs1", "name": "Coffee Shop", "primary_type": "coffee_shop"},
        {"place_id": "re1", "name": "Restaurant", "primary_type": "restaurant"},
        {"place_id": "b1", "name": "Bar", "primary_type": "bar"},
    ],
    expected_ids=["ca1", "cs1"],
    forbidden_ids=["re1", "b1"],
)

test(
    "restaurant + fast_food: only fast_food_restaurant kept",
    "restaurant", ["fast_food"],
    [
        {"place_id": "ff1", "name": "McDonalds", "primary_type": "fast_food_restaurant"},
        {"place_id": "re1", "name": "Fine Dining", "primary_type": "restaurant"},
        {"place_id": "ca1", "name": "Cafe", "primary_type": "cafe"},
    ],
    expected_ids=["ff1"],
    forbidden_ids=["re1", "ca1"],
)

test(
    "restaurant + street_food: only meal_takeaway/delivery kept",
    "restaurant", ["street_food"],
    [
        {"place_id": "mt1", "name": "Street Food", "primary_type": "meal_takeaway"},
        {"place_id": "md1", "name": "Delivery", "primary_type": "meal_delivery"},
        {"place_id": "re1", "name": "Restaurant", "primary_type": "restaurant"},
        {"place_id": "m1", "name": "Museum", "primary_type": "museum"},
    ],
    expected_ids=["mt1", "md1"],
    forbidden_ids=["re1", "m1"],
)

test(
    "restaurant + [cafes_coffee, fast_food]: cafe + fast_food kept, bar rejected",
    "restaurant", ["cafes_coffee", "fast_food"],
    [
        {"place_id": "ca1", "name": "Cafe", "primary_type": "cafe"},
        {"place_id": "ff1", "name": "Fast Food", "primary_type": "fast_food_restaurant"},
        {"place_id": "b1", "name": "Bar", "primary_type": "bar"},
        {"place_id": "m1", "name": "Museum", "primary_type": "museum"},
    ],
    expected_ids=["ca1", "ff1"],
    forbidden_ids=["b1", "m1"],
)


# ============================================================
# SHOPPING tests
# ============================================================
print("\n=== SHOPPING CATEGORY ===")

test(
    "shopping (no sub): mall + store kept, museum rejected",
    "shopping", None,
    [
        {"place_id": "sm1", "name": "Mall", "primary_type": "shopping_mall"},
        {"place_id": "st1", "name": "Store", "primary_type": "store"},
        {"place_id": "m1", "name": "Museum", "primary_type": "museum"},
        {"place_id": "r1", "name": "Restaurant", "primary_type": "restaurant"},
    ],
    expected_ids=["sm1", "st1"],
    forbidden_ids=["m1", "r1"],
)

test(
    "shopping + fashion_clothing: only clothing/shoe store kept",
    "shopping", ["fashion_clothing"],
    [
        {"place_id": "cl1", "name": "Clothes", "primary_type": "clothing_store"},
        {"place_id": "sh1", "name": "Shoes", "primary_type": "shoe_store"},
        {"place_id": "el1", "name": "Electronics", "primary_type": "electronics_store"},
        {"place_id": "m1", "name": "Museum", "primary_type": "museum"},
    ],
    expected_ids=["cl1", "sh1"],
    forbidden_ids=["el1", "m1"],
)

test(
    "shopping + electronics_specialty: only electronics_store kept",
    "shopping", ["electronics_specialty"],
    [
        {"place_id": "el1", "name": "Electronics", "primary_type": "electronics_store"},
        {"place_id": "cl1", "name": "Clothes", "primary_type": "clothing_store"},
        {"place_id": "m1", "name": "Museum", "primary_type": "museum"},
    ],
    expected_ids=["el1"],
    forbidden_ids=["cl1", "m1"],
)

test(
    "shopping + local_markets: only market/convenience kept",
    "shopping", ["local_markets"],
    [
        {"place_id": "mk1", "name": "Market", "primary_type": "market"},
        {"place_id": "cv1", "name": "Convenience", "primary_type": "convenience_store"},
        {"place_id": "sm1", "name": "Mall", "primary_type": "shopping_mall"},
        {"place_id": "m1", "name": "Museum", "primary_type": "museum"},
    ],
    expected_ids=["mk1", "cv1"],
    forbidden_ids=["sm1", "m1"],
)

test(
    "shopping + supermarkets: only supermarket/grocery kept",
    "shopping", ["supermarkets"],
    [
        {"place_id": "su1", "name": "Supermarket", "primary_type": "supermarket"},
        {"place_id": "gr1", "name": "Grocery", "primary_type": "grocery_store"},
        {"place_id": "sm1", "name": "Mall", "primary_type": "shopping_mall"},
        {"place_id": "m1", "name": "Museum", "primary_type": "museum"},
    ],
    expected_ids=["su1", "gr1"],
    forbidden_ids=["sm1", "m1"],
)


# ============================================================
# PARKING tests
# ============================================================
print("\n=== PARKING CATEGORY ===")

test(
    "parking (no sub): parking + garage kept, museum rejected",
    "parking", None,
    [
        {"place_id": "pk1", "name": "Parking", "primary_type": "parking"},
        {"place_id": "pg1", "name": "Garage", "primary_type": "parking_garage"},
        {"place_id": "m1", "name": "Museum", "primary_type": "museum"},
        {"place_id": "r1", "name": "Restaurant", "primary_type": "restaurant"},
    ],
    expected_ids=["pk1", "pg1"],
    forbidden_ids=["m1", "r1"],
)

test(
    "parking + ev_parking: only ev_charging kept",
    "parking", ["ev_parking"],
    [
        {"place_id": "ev1", "name": "EV Station", "primary_type": "ev_charging_station"},
        {"place_id": "pk1", "name": "Parking", "primary_type": "parking"},
        {"place_id": "m1", "name": "Museum", "primary_type": "museum"},
    ],
    expected_ids=["ev1"],
    forbidden_ids=["pk1", "m1"],
)

test(
    "parking + parking_garages: only garage/structure kept",
    "parking", ["parking_garages"],
    [
        {"place_id": "pg1", "name": "Garage", "primary_type": "parking_garage"},
        {"place_id": "ps1", "name": "Structure", "primary_type": "parking_structure"},
        {"place_id": "pk1", "name": "Lot", "primary_type": "parking_lot"},
        {"place_id": "m1", "name": "Museum", "primary_type": "museum"},
    ],
    expected_ids=["pg1", "ps1"],
    forbidden_ids=["pk1", "m1"],
)


# ============================================================
# EXPLORE tests
# ============================================================
print("\n=== EXPLORE CATEGORY ===")

test(
    "explore (no sub): all types pass (broad discovery)",
    "explore", None,
    [
        {"place_id": "m1", "name": "Museum", "primary_type": "museum"},
        {"place_id": "r1", "name": "Restaurant", "primary_type": "restaurant"},
        {"place_id": "s1", "name": "Shop", "primary_type": "store"},
        {"place_id": "p1", "name": "Park", "primary_type": "park"},
    ],
    expected_ids=["m1", "r1", "s1", "p1"],
)

test(
    "explore + arts_museums: only museum/art_gallery/theater kept",
    "explore", ["arts_museums"],
    [
        {"place_id": "m1", "name": "Museum", "primary_type": "museum"},
        {"place_id": "a1", "name": "Art Gallery", "primary_type": "art_gallery"},
        {"place_id": "r1", "name": "Restaurant", "primary_type": "restaurant"},
        {"place_id": "o1", "name": "Oppo", "primary_type": "electronics_store"},
    ],
    expected_ids=["m1", "a1"],
    forbidden_ids=["r1", "o1"],
)

test(
    "explore + historic_cultural: only historical_landmark/monument/cultural_center kept",
    "explore", ["historic_cultural"],
    [
        {"place_id": "hl1", "name": "Fort", "primary_type": "historical_landmark"},
        {"place_id": "mn1", "name": "Monument", "primary_type": "monument"},
        {"place_id": "m1", "name": "Museum", "primary_type": "museum"},
        {"place_id": "r1", "name": "Restaurant", "primary_type": "restaurant"},
    ],
    expected_ids=["hl1", "mn1"],
    forbidden_ids=["m1", "r1"],
)

test(
    "explore + nature_scenic: only park/national_park/botanical kept",
    "explore", ["nature_scenic"],
    [
        {"place_id": "p1", "name": "Park", "primary_type": "park"},
        {"place_id": "np1", "name": "Nat Park", "primary_type": "national_park"},
        {"place_id": "r1", "name": "Restaurant", "primary_type": "restaurant"},
        {"place_id": "s1", "name": "Shop", "primary_type": "store"},
    ],
    expected_ids=["p1", "np1"],
    forbidden_ids=["r1", "s1"],
)

test(
    "explore + entertainment_activities: only amusement/zoo/aquarium/casino/stadium kept",
    "explore", ["entertainment_activities"],
    [
        {"place_id": "z1", "name": "Zoo", "primary_type": "zoo"},
        {"place_id": "a1", "name": "Aquarium", "primary_type": "aquarium"},
        {"place_id": "r1", "name": "Restaurant", "primary_type": "restaurant"},
        {"place_id": "m1", "name": "Museum", "primary_type": "museum"},
    ],
    expected_ids=["z1", "a1"],
    forbidden_ids=["r1", "m1"],
)

test(
    "explore + hidden_gems: high-rating low-review kept, high-review rejected",
    "explore", ["hidden_gems"],
    [
        {"place_id": "h1", "name": "Hidden Gem", "primary_type": "park", "rating": 4.5, "user_rating_count": 100},
        {"place_id": "h2", "name": "Secret Spot", "primary_type": "museum", "rating": 4.6, "user_rating_count": 200},
        {"place_id": "p1", "name": "Popular", "primary_type": "tourist_attraction", "rating": 4.0, "user_rating_count": 5000},
        {"place_id": "l1", "name": "Low Rated", "primary_type": "art_gallery", "rating": 3.5, "user_rating_count": 50},
    ],
    expected_ids=["h1", "h2"],
    forbidden_ids=["p1", "l1"],
)

print("\n=== CROSS-CATEGORY NEGATIVES ===")

test(
    "REGRESSION: museum search -> no electronics/school/cosmetics",
    "tourist", ["cultural_attractions"],
    [
        {"place_id": "m1", "name": "Central Museum", "primary_type": "museum"},
        {"place_id": "o1", "name": "Oppo Service Center", "primary_type": "electronics_store"},
        {"place_id": "s1", "name": "ABC School", "primary_type": "school"},
        {"place_id": "c1", "name": "XYZ Cosmetics", "primary_type": "cosmetics_store"},
        {"place_id": "u1", "name": "University", "primary_type": "university"},
    ],
    expected_ids=["m1"],
    forbidden_ids=["o1", "s1", "c1", "u1"],
)

test(
    "REGRESSION: restaurant search -> no museum/park/school",
    "restaurant", ["restaurants"],
    [
        {"place_id": "r1", "name": "Main Restaurant", "primary_type": "restaurant"},
        {"place_id": "m1", "name": "Museum Cafe", "primary_type": "museum"},
        {"place_id": "p1", "name": "Park View", "primary_type": "park"},
        {"place_id": "s1", "name": "School Canteen", "primary_type": "school"},
    ],
    expected_ids=["r1"],
    forbidden_ids=["m1", "p1", "s1"],
)

test(
    "REGRESSION: parking search -> no restaurant/museum/shop",
    "parking", ["public_parking"],
    [
        {"place_id": "pk1", "name": "City Parking", "primary_type": "parking"},
        {"place_id": "r1", "name": "Parking Restaurant", "primary_type": "restaurant"},
        {"place_id": "m1", "name": "Parking Museum", "primary_type": "museum"},
        {"place_id": "s1", "name": "Parking Shop", "primary_type": "store"},
    ],
    expected_ids=["pk1"],
    forbidden_ids=["r1", "m1", "s1"],
)

test(
    "REGRESSION: shopping search -> no museum/restaurant/park",
    "shopping", ["fashion_clothing"],
    [
        {"place_id": "cl1", "name": "Fashion Store", "primary_type": "clothing_store"},
        {"place_id": "m1", "name": "Museum Gift", "primary_type": "museum"},
        {"place_id": "r1", "name": "Mall Restaurant", "primary_type": "restaurant"},
        {"place_id": "p1", "name": "Mall Parking", "primary_type": "parking"},
    ],
    expected_ids=["cl1"],
    forbidden_ids=["m1", "r1", "p1"],
)


print("\n=== SCHEMA VALIDATION ===")
from app.schemas.discovery import NearbyDiscoveryRequest
# Valid subcategory
try:
    req = NearbyDiscoveryRequest(category="tourist", subcategories=["cultural_attractions"])
    print("  PASS Valid subcategory accepted")
    PASS += 1
except Exception as e:
    print(f"  FAIL Valid subcategory rejected: {e}")
    FAIL += 1

# Invalid subcategory
try:
    req = NearbyDiscoveryRequest(category="tourist", subcategories=["parking_garages"])
    print(f"  FAIL Invalid subcategory accepted (should have been rejected)")
    FAIL += 1
except Exception:
    print("  PASS Invalid subcategory rejected")
    PASS += 1

# Cross-category subcategory
try:
    req = NearbyDiscoveryRequest(category="restaurant", subcategories=["fine_dining", "museums"])
    print(f"  FAIL Cross-category subcategory accepted")
    FAIL += 1
except Exception:
    print("  PASS Cross-category subcategory rejected")
    PASS += 1


# ============================================================
# SUMMARY
# ============================================================
print(f"\n{'='*50}")
print(f"RESULTS: {PASS} passed, {FAIL} failed")
print(f"{'='*50}")

if FAIL > 0:
    sys.exit(1)
