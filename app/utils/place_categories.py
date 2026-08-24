from typing import List, Optional

CATEGORY_TO_GOOGLE_TYPES = {
    "tourist": ["tourist_attraction"],
    "restaurant": ["restaurant", "cafe", "bakery"],
    "shopping": ["shopping_mall", "store", "supermarket", "department_store"],
    "parking": ["parking"],
}

CATEGORY_MAPPING = {
    "tourist_attraction": "tourist_attraction",
    "museum": "tourist_attraction",
    "historical_landmark": "tourist_attraction",
    "monument": "tourist_attraction",
    "hindu_temple": "tourist_attraction",
    "church": "tourist_attraction",
    "mosque": "tourist_attraction",
    "synagogue": "tourist_attraction",
    "buddhist_temple": "tourist_attraction",
    "park": "tourist_attraction",
    "national_park": "tourist_attraction",
    "amusement_park": "tourist_attraction",
    "zoo": "tourist_attraction",
    "aquarium": "tourist_attraction",
    "art_gallery": "tourist_attraction",
    "performing_arts_theater": "tourist_attraction",
    "casino": "tourist_attraction",
    "cultural_center": "tourist_attraction",
    "visitor_center": "tourist_attraction",
    "planetarium": "tourist_attraction",
    "stadium": "tourist_attraction",
    "event_venue": "tourist_attraction",

    "restaurant": "restaurant",
    "cafe": "restaurant",
    "bar": "restaurant",
    "bakery": "restaurant",
    "meal_takeaway": "restaurant",
    "meal_delivery": "restaurant",
    "fast_food_restaurant": "restaurant",
    "american_restaurant": "restaurant",
    "chinese_restaurant": "restaurant",
    "indian_restaurant": "restaurant",
    "italian_restaurant": "restaurant",
    "japanese_restaurant": "restaurant",
    "korean_restaurant": "restaurant",
    "mexican_restaurant": "restaurant",
    "thai_restaurant": "restaurant",
    "french_restaurant": "restaurant",
    "greek_restaurant": "restaurant",
    "pizza_restaurant": "restaurant",
    "seafood_restaurant": "restaurant",
    "steak_house": "restaurant",
    "sushi_restaurant": "restaurant",
    "vegetarian_restaurant": "restaurant",
    "vegan_restaurant": "restaurant",
    "brunch_restaurant": "restaurant",
    "breakfast_restaurant": "restaurant",
    "ice_cream_shop": "restaurant",
    "coffee_shop": "restaurant",
    "sandwich_shop": "restaurant",
    "hamburger_restaurant": "restaurant",
    "ramen_restaurant": "restaurant",

    "shopping_mall": "shopping_mall",
    "department_store": "shopping_mall",
    "supermarket": "shopping_mall",
    "convenience_store": "shopping_mall",
    "clothing_store": "shopping_mall",
    "electronics_store": "shopping_mall",
    "book_store": "shopping_mall",
    "jewelry_store": "shopping_mall",
    "shoe_store": "shopping_mall",
    "furniture_store": "shopping_mall",
    "home_goods_store": "shopping_mall",
    "sporting_goods_store": "shopping_mall",
    "toy_store": "shopping_mall",
    "gift_shop": "shopping_mall",
    "pet_store": "shopping_mall",
    "florist": "shopping_mall",
    "hardware_store": "shopping_mall",
    "market": "shopping_mall",
    "store": "shopping_mall",
    "lodging": "tourist_attraction",

    "parking": "parking",
    "parking_garage": "parking",
    "parking_lot": "parking",
    "parking_structure": "parking",
    "motorcycle_parking": "parking",
    "bicycle_parking": "parking",
    "ev_charging_station": "parking",
    "truck_stop": "parking",
    "rest_stop": "parking",
}

PARKING_PLACE_TYPES = ["parking"]

SUBCATEGORIES = {
    "explore": [
        "nature_scenic", "hidden_gems", "historic_cultural",
        "arts_museums", "entertainment_activities",
    ],
    "tourist": [
        "landmarks_attractions", "historic_sites", "cultural_attractions",
        "parks_nature", "tours_experiences",
    ],
    "restaurant": [
        "restaurants", "cafes_coffee", "street_food",
        "fast_food", "fine_dining",
    ],
    "shopping": [
        "shopping_malls", "local_markets", "supermarkets",
        "fashion_clothing", "electronics_specialty",
    ],
    "parking": [
        "public_parking", "parking_garages", "ev_parking",
    ],
}

SUBCATEGORY_TO_GOOGLE_TYPES = {
    # EXPLORE
    "nature_scenic": ["park", "national_park", "botanical_garden"],
    "hidden_gems": [],
    "historic_cultural": ["historical_landmark", "monument", "cultural_center"],
    "arts_museums": ["museum", "art_gallery", "performing_arts_theater"],
    "entertainment_activities": [
        "amusement_park", "zoo", "aquarium", "casino", "stadium",
    ],
    # TOURIST
    "landmarks_attractions": ["tourist_attraction", "monument", "observation_deck"],
    "historic_sites": ["historical_landmark", "castle", "fort"],
    "cultural_attractions": ["museum", "cultural_center", "art_gallery"],
    "parks_nature": ["park", "national_park", "botanical_garden"],
    "tours_experiences": ["tourist_attraction", "visitor_center"],
    # RESTAURANT
    "restaurants": ["restaurant"],
    "cafes_coffee": ["cafe", "coffee_shop"],
    "street_food": ["meal_takeaway", "meal_delivery"],
    "fast_food": ["fast_food_restaurant"],
    "fine_dining": ["restaurant"],
    # SHOPPING
    "shopping_malls": ["shopping_mall", "department_store"],
    "local_markets": ["market"],
    "supermarkets": ["supermarket", "grocery_store"],
    "fashion_clothing": ["clothing_store", "shoe_store"],
    "electronics_specialty": ["electronics_store"],
    # PARKING
    "public_parking": ["parking", "parking_lot"],
    "parking_garages": ["parking_garage", "parking_structure"],
    "ev_parking": ["ev_charging_station"],
}

SUBCATEGORY_MAPPING = {
    # EXPLORE
    "park": "nature_scenic",
    "national_park": "nature_scenic",
    "botanical_garden": "nature_scenic",
    "scenic_area": "nature_scenic",
    "historical_landmark": "historic_cultural",
    "monument": "historic_cultural",
    "cultural_center": "historic_cultural",
    "museum": "arts_museums",
    "art_gallery": "arts_museums",
    "performing_arts_theater": "arts_museums",
    "planetarium": "arts_museums",
    "amusement_park": "entertainment_activities",
    "zoo": "entertainment_activities",
    "aquarium": "entertainment_activities",
    "casino": "entertainment_activities",
    "stadium": "entertainment_activities",
    "event_venue": "entertainment_activities",
    # TOURIST
    "tourist_attraction": "landmarks_attractions",
    "observation_deck": "landmarks_attractions",
    "castle": "historic_sites",
    "fort": "historic_sites",
    "visitor_center": "tours_experiences",
    # RESTAURANT
    "restaurant": "restaurants",
    "cafe": "cafes_coffee",
    "coffee_shop": "cafes_coffee",
    "meal_takeaway": "street_food",
    "meal_delivery": "street_food",
    "fast_food_restaurant": "fast_food",
    "bar": "restaurants",
    "bakery": "cafes_coffee",
    "ice_cream_shop": "cafes_coffee",
    # SHOPPING
    "shopping_mall": "shopping_malls",
    "department_store": "shopping_malls",
    "market": "local_markets",
    "supermarket": "supermarkets",
    "grocery_store": "supermarkets",
    "clothing_store": "fashion_clothing",
    "shoe_store": "fashion_clothing",
    "electronics_store": "electronics_specialty",
    "convenience_store": "local_markets",
    "book_store": "shopping_malls",
    "jewelry_store": "shopping_malls",
    "furniture_store": "shopping_malls",
    "home_goods_store": "shopping_malls",
    "sporting_goods_store": "shopping_malls",
    "toy_store": "shopping_malls",
    "gift_shop": "shopping_malls",
    "pet_store": "shopping_malls",
    "florist": "shopping_malls",
    "hardware_store": "shopping_malls",
    "store": "shopping_malls",
    # PARKING
    "parking": "public_parking",
    "parking_lot": "public_parking",
    "parking_garage": "parking_garages",
    "parking_structure": "parking_garages",
    "ev_charging_station": "ev_parking",
    "motorcycle_parking": "public_parking",
    "bicycle_parking": "public_parking",
    "truck_stop": "public_parking",
    "rest_stop": "public_parking",
}

CATEGORY_WEIGHTS = {
    "tourist": {
        "rating": 0.30, "popularity": 0.25, "price_fit": 0.05,
        "amenities": 0.10, "proximity": 0.15, "user_affinity": 0.15,
    },
    "restaurant": {
        "rating": 0.30, "popularity": 0.10, "price_fit": 0.25,
        "amenities": 0.20, "proximity": 0.05, "user_affinity": 0.10,
    },
    "shopping": {
        "rating": 0.20, "popularity": 0.15, "price_fit": 0.15,
        "amenities": 0.25, "proximity": 0.15, "user_affinity": 0.10,
    },
    "parking": {
        "rating": 0.05, "popularity": 0.05, "price_fit": 0.25,
        "amenities": 0.15, "proximity": 0.45, "user_affinity": 0.05,
    },
    "explore": {
        "rating": 0.25, "popularity": 0.15, "price_fit": 0.20,
        "amenities": 0.20, "proximity": 0.10, "user_affinity": 0.10,
    },
}

# Category-specific overrides for types shared between explore and tourist.
# When a Google type maps to different subcategories in different categories,
# this dict takes priority over SUBCATEGORY_MAPPING.
# Key: (category, primary_type) -> subcategory
SUBCATEGORY_OVERRIDES = {
    ("tourist", "museum"): "cultural_attractions",
    ("tourist", "cultural_center"): "cultural_attractions",
    ("tourist", "art_gallery"): "cultural_attractions",
    ("tourist", "park"): "parks_nature",
    ("tourist", "national_park"): "parks_nature",
    ("tourist", "botanical_garden"): "parks_nature",
    ("tourist", "historical_landmark"): "historic_sites",
    ("tourist", "monument"): "landmarks_attractions",
}


def get_place_category(primary_type: Optional[str]) -> Optional[str]:
    if not primary_type:
        return None
    primary_lower = primary_type.lower()
    if primary_lower in CATEGORY_MAPPING:
        return CATEGORY_MAPPING[primary_lower]
    return primary_lower


def get_place_subcategory(primary_type: Optional[str], category: Optional[str] = None) -> Optional[str]:
    if not primary_type:
        return None
    type_lower = primary_lower = primary_type.lower()
    if category:
        override = SUBCATEGORY_OVERRIDES.get((category.lower(), primary_lower))
        if override:
            return override
    return SUBCATEGORY_MAPPING.get(primary_lower)
