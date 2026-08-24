from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ComparisonType(str, Enum):
    BASIC = "basic"
    RECOMMENDATION = "recommendation"


class ComparePlacesRequest(BaseModel):
    place_ids: List[str] = Field(..., min_length=2, max_length=10)
    comparison_type: ComparisonType


class PlaceUserContext(BaseModel):
    is_saved: bool = False
    saved_id: Optional[int] = None
    saved_at: Optional[datetime] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = None

    has_visited: bool = False
    visited_at: Optional[datetime] = None
    your_rating: Optional[float] = None
    your_review: Optional[str] = None
    visit_mood: Optional[str] = None
    visited_with: Optional[str] = None


class AttributeValue(BaseModel):

    place_id: str
    value: Any = None
    label: Optional[str] = None


class AttributeColumn(BaseModel):

    key: str
    label: str
    values: List[AttributeValue]


class ReviewSummary(BaseModel):

    author_name: Optional[str] = None
    rating: Optional[float] = None
    text: Optional[str] = None
    relative_time: Optional[str] = None


class PhotoReference(BaseModel):

    name: Optional[str] = None
    width_px: Optional[int] = None
    height_px: Optional[int] = None


class EnhancedComparisonResult(BaseModel):

    place_id: str
    display_name: Optional[str] = None
    formatted_address: Optional[str] = None
    primary_type: Optional[str] = None
    types: Optional[List[str]] = None

    latitude: Optional[float] = None
    longitude: Optional[float] = None
    distance_from_you_km: Optional[float] = None

    rating: Optional[float] = None
    user_rating_count: Optional[int] = None
    price_level: Optional[str] = None

    business_status: Optional[str] = None
    open_now: Optional[bool] = None
    opening_hours_summary: Optional[str] = None

    wheelchair_accessible: Optional[bool] = None

    website_uri: Optional[str] = None
    phone_number: Optional[str] = None
    google_maps_uri: Optional[str] = None

    editorial_summary: Optional[str] = None

    photo_references: Optional[List[PhotoReference]] = None
    top_reviews: Optional[List[ReviewSummary]] = None

    dine_in: Optional[bool] = None
    takeout: Optional[bool] = None
    delivery: Optional[bool] = None
    curbside_pickup: Optional[bool] = None
    serves_breakfast: Optional[bool] = None
    serves_lunch: Optional[bool] = None
    serves_dinner: Optional[bool] = None
    serves_brunch: Optional[bool] = None
    serves_beer: Optional[bool] = None
    serves_wine: Optional[bool] = None
    serves_cocktails: Optional[bool] = None
    serves_vegetarian_food: Optional[bool] = None
    outdoor_seating: Optional[bool] = None
    restroom: Optional[bool] = None
    good_for_children: Optional[bool] = None
    good_for_groups: Optional[bool] = None
    live_music: Optional[bool] = None
    reservable: Optional[bool] = None
    allows_dogs: Optional[bool] = None
    parking_free: Optional[bool] = None
    parking_paid: Optional[bool] = None
    parking_valet: Optional[bool] = None
    ev_charging: Optional[bool] = None
    payment_cash: Optional[bool] = None
    payment_credit_cards: Optional[bool] = None
    payment_contactless: Optional[bool] = None
    payment_nfc: Optional[bool] = None

    wikipedia_extract: Optional[str] = None
    neighborhood: Optional[str] = None

    your_context: Optional[PlaceUserContext] = None

    is_visit: bool = False

    model_config = {"from_attributes": True}


class CompareBasicResponse(BaseModel):

    success: bool = True
    message: str
    places: List[EnhancedComparisonResult]
    attribute_table: List[AttributeColumn]
    highlights: Optional[Dict[str, Any]] = Field(None)
    total_places: int
    user_location_used: bool = False
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ScoreBreakdown(BaseModel):

    rating: float = 0.0
    popularity: float = 0.0
    price_fit: float = 0.0
    amenities: float = 0.0
    proximity: float = 0.0
    user_affinity: float = 0.0


class RecommendationResult(BaseModel):

    rank: int
    place_id: str
    display_name: Optional[str] = None
    primary_type: Optional[str] = None
    formatted_address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    rating: Optional[float] = None
    price_level: Optional[str] = None
    photo_references: Optional[List[PhotoReference]] = None
    overall_score: float
    score_breakdown: ScoreBreakdown
    strengths: List[str] = []
    your_context: Optional[PlaceUserContext] = None
    ai_summary: Optional[str] = None
    is_visit: bool = False


class CompareRecommendResponse(BaseModel):

    success: bool = True
    message: str
    recommendations: List[RecommendationResult]
    overall_ai_summary: Optional[str] = None
    total_places_compared: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


