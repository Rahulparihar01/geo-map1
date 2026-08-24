import logging
import traceback
from datetime import datetime, timezone
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

crash_logger = logging.getLogger("crash_detector")


async def custom_rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "success": False,
            "message": "Rate limit exceeded. Please slow down and try again.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


async def global_exception_handler(request: Request, exc: Exception):
    crash_logger.error(
        "UNHANDLED EXCEPTION: %s\nPath: %s %s\nUser-Agent: %s\nError: %s\nTraceback: %s",
        type(exc).__name__,
        request.method,
        request.url.path,
        request.headers.get("user-agent", "unknown"),
        str(exc),
        "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "message": "Internal server error occurred. The issue has been logged.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger = logging.getLogger(__name__)
    
    try:
        raw_errors = exc.errors(include_url=False)
    except TypeError:
        raw_errors = exc.errors()

    # Log detailed validation errors for debugging
    logger.warning(
        "Validation error on %s %s: %s",
        request.method,
        request.url.path,
        raw_errors,
    )
    
    # Return generic validation error to user (don't expose field details)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "message": "Invalid request. Please check your input and try again.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


async def exception_group_handler(request: Request, exc: ExceptionGroup):
    crash_logger.error(
        "UNHANDLED EXCEPTION GROUP (%d sub-exceptions)\nPath: %s %s\nUser-Agent: %s\nErrors: %s\nTraceback: %s",
        len(exc.exceptions),
        request.method,
        request.url.path,
        request.headers.get("user-agent", "unknown"),
        [str(e) for e in exc.exceptions],
        "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "message": "Internal server error occurred. The issue has been logged.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
