from fastapi import HTTPException, status


class GooglePlacesAPIError(HTTPException):
    def __init__(
        self,
        detail: str = "We couldn't complete your request. Please try again.",
        provider_status_code: int | None = None,
    ):
        super().__init__(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail,
        )
        self.provider_status_code = provider_status_code


class GooglePlacesRateLimitError(HTTPException):
    def __init__(self, detail: str = "Too many requests. Please try again later."):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
        )


class GooglePlacesTimeoutError(HTTPException):
    def __init__(self, detail: str = "The service took too long to respond. Please try again."):
        super().__init__(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=detail,
        )


class RedisUnavailableError(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable. Please try again later.",
        )


class NearbySearchValidationError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
        )


class UserLocationNotFoundError(HTTPException):
    def __init__(
        self,
        detail: str = "No saved location found. Please share your device location and try again.",
    ):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
        )


class PlaceDetailNotFoundError(HTTPException):
    def __init__(self, place_id: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Place '{place_id}' not found.",
        )
