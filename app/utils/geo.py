import math

_EARTH_RADIUS_METERS = 6_371_000.0

def haversine_distance_meters(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return _EARTH_RADIUS_METERS * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def haversine_distance_km(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    return round(haversine_distance_meters(lat1, lon1, lat2, lon2) / 1000.0, 2)
