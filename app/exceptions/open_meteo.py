from fastapi import HTTPException, status


class OpenMeteoError(HTTPException):
    def __init__(self, detail: str = "Weather service is temporarily unavailable. Please try again later."):
        super().__init__(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)


class OpenMeteoAPIError(OpenMeteoError):
    def __init__(self, detail: str = "Weather service is temporarily unavailable. Please try again later."):
        super().__init__(detail=detail)


class OpenMeteoTimeoutError(OpenMeteoError):
    def __init__(self, detail: str = "The weather service took too long to respond. Please try again."):
        super().__init__(detail=detail)
        self.status_code = status.HTTP_504_GATEWAY_TIMEOUT


class OpenMeteoRateLimitError(OpenMeteoError):
    def __init__(self, detail: str = "Too many requests. Please try again later."):
        super().__init__(detail=detail)
        self.status_code = status.HTTP_429_TOO_MANY_REQUESTS
