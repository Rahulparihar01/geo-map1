from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TravelMode(str, Enum):
    DRIVE = "DRIVE"
    WALK = "WALK"
    BICYCLE = "BICYCLE"
    TWO_WHEELER = "TWO_WHEELER"
    TRANSIT = "TRANSIT"


class RoutingPreference(str, Enum):
    TRAFFIC_AWARE = "TRAFFIC_AWARE"
    TRAFFIC_AWARE_OPTIMAL = "TRAFFIC_AWARE_OPTIMAL"
    TRAFFIC_UNAWARE = "TRAFFIC_UNAWARE"


class ComputeRouteRequest(BaseModel):
    place_id: Optional[str] = Field(default=None)
    destination_latitude: Optional[float] = Field(
        default=None,
        ge=-90.0,
        le=90.0,
    )
    destination_longitude: Optional[float] = Field(
        default=None,
        ge=-180.0,
        le=180.0,
    )

    waypoints: List[Dict[str, Any]] = Field(
        default=[],
        max_length=25,
    )
    optimize_waypoint_order: bool = Field(default=False)

    departure_time: Optional[datetime] = Field(default=None)

    travel_mode: TravelMode = Field(default=TravelMode.DRIVE)
    language_code: str = Field(
        default="en-US",
        max_length=10,
    )
    avoid_tolls: bool = Field(default=False)
    avoid_highways: bool = Field(default=False)
    avoid_ferries: bool = Field(default=False)

    def has_valid_destination(self) -> bool:
        return self.place_id is not None or (
            self.destination_latitude is not None
            and self.destination_longitude is not None
        )


class ComputeRouteMatrixRequest(BaseModel):
    destinations: List[Dict[str, Any]] = Field(
        ...,
        min_length=1,
        max_length=20,
    )
    travel_mode: TravelMode = Field(default=TravelMode.DRIVE)


class NavigationStep(BaseModel):

    distance_meters: int = 0
    duration_seconds: int = 0
    maneuver: Optional[str] = None
    instruction: Optional[str] = None


class RouteResult(BaseModel):
    distance_meters: int
    duration_seconds: int
    static_duration_seconds: int
    traffic_delay_seconds: int = 0
    distance_text: Optional[str] = None
    duration_text: Optional[str] = None
    traffic_delay_text: Optional[str] = None
    encoded_polyline: str
    steps: List[NavigationStep] = []
    optimized_waypoint_order: Optional[List[int]] = None


class RouteMatrixElement(BaseModel):
    origin_index: int
    destination_index: int
    distance_meters: Optional[int] = None
    duration_seconds: Optional[int] = None
    condition: str = "ROUTE_EXISTS"


class RouteResponse(BaseModel):
    success: bool
    message: str
    cached: bool = False
    travel_mode: str
    origin_latitude: Optional[float] = None
    origin_longitude: Optional[float] = None
    data: Optional[RouteResult] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RouteMatrixItem(BaseModel):
    destination_index: int
    place_id: Optional[str] = None
    distance_meters: Optional[int] = None
    duration_seconds: Optional[int] = None
    distance_text: Optional[str] = None
    duration_text: Optional[str] = None
    reachable: bool = True


class RouteMatrixResponse(BaseModel):
    success: bool
    message: str
    cached: bool = False
    travel_mode: str
    origin_latitude: float
    origin_longitude: float
    data: List[RouteMatrixItem]
    total_destinations: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
