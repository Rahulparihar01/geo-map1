import hashlib
from typing import Optional


class CacheKeyBuilder:

    @staticmethod
    def discovery_text_search(
        user_id: int,
        text_query: str,
        bias_lat: Optional[float] = None,
        bias_lon: Optional[float] = None,
    ) -> str:
        key_data = f"{text_query}|{bias_lat}|{bias_lon}"
        h = hashlib.md5(key_data.encode()).hexdigest()
        return f"discovery_text_{user_id}_{h}"

    @staticmethod
    def discovery_nearby_search(
        user_id: int,
        latitude: float,
        longitude: float,
        radius: float,
        included_types: Optional[str] = None,
        excluded_types: Optional[str] = None,
    ) -> str:
        key_data = (
            f"{latitude}|{longitude}|{radius}|{included_types or ''}|"
            f"{excluded_types or ''}"
        )
        h = hashlib.md5(key_data.encode()).hexdigest()
        return f"discovery_nearby_{user_id}_{h}"

    @staticmethod
    def discovery_autocomplete(
        user_id: int,
        input_text: str,
        bias_lat: Optional[float] = None,
        bias_lon: Optional[float] = None,
    ) -> str:
        key_data = f"{input_text}|{bias_lat}|{bias_lon}"
        h = hashlib.md5(key_data.encode()).hexdigest()
        return f"discovery_autocomplete_{user_id}_{h}"

    @staticmethod
    def place_details(place_id: str) -> str:
        return f"place_details:{place_id}"

    @staticmethod
    def routes_direction(
        user_id: int,
        origin_lat: float,
        origin_lon: float,
        destination_lat: float,
        destination_lon: float,
        travel_mode: str,
    ) -> str:
        key_data = f"{origin_lat}|{origin_lon}|{destination_lat}|{destination_lon}|{travel_mode}"
        h = hashlib.md5(key_data.encode()).hexdigest()
        return f"routes_{user_id}_{travel_mode}_{h}"

    @staticmethod
    def routes_matrix(
        user_id: int,
        origin_lat: float,
        origin_lon: float,
        destinations: str,
        travel_mode: str,
    ) -> str:
        key_data = f"{origin_lat}|{origin_lon}|{destinations}|{travel_mode}"
        h = hashlib.md5(key_data.encode()).hexdigest()
        return f"routes_matrix_{user_id}_{travel_mode}_{h}"

    @staticmethod
    def otp_for_email(email: str) -> str:
        return f"otp:{email}"

    @staticmethod
    def token_blacklist(token: str) -> str:
        return f"token_blacklist:{token}"
