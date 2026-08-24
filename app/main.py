import logging
import os
import sys
import httpx
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.integrations.pinecone_client import PineconeClient
from app.integrations.openai_client import OpenAIEmbeddingClient
from app.integrations.pinecone_client import shutdown_executor
from .api import api_router
from .core.redis import close_redis, initialise_redis
from .exceptions import (
    custom_rate_limit_handler,
    global_exception_handler,
    validation_exception_handler,
    exception_group_handler,
)

from app.core.config import settings
from app.core.langfuse_middleware import LangfuseRequestTracingMiddleware
from app.core.rate_limiter import shared_limiter
from app.utils.error_messages import SERVER_ERROR, sanitize_error_message

_ALLOWED_ORIGINS = [
    o.strip() for o in (settings.CORS_ORIGINS.split(",")) if o.strip()
]

os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/app.log", mode="a", encoding="utf-8"),
    ],
)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting geo-map-backend...")

    # Langfuse reads credentials from environment variables. pydantic-settings
    # loads .env into `settings` but does not export it to os.environ, so mirror
    # the values here (without overriding real environment variables).
    if settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY:
        os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.LANGFUSE_PUBLIC_KEY)
        os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.LANGFUSE_SECRET_KEY)
        os.environ.setdefault("LANGFUSE_BASE_URL", settings.LANGFUSE_BASE_URL)

    # Validate required configuration at startup
    if not settings.SECRET_KEY or len(settings.SECRET_KEY) < 32:
        raise ValueError(
            "SECRET_KEY must be set and at least 32 characters. "
            "Set SECRET_KEY in .env file."
        )
    
    if not settings.GOOGLE_PLACES_API_KEY:
        raise ValueError(
            "GOOGLE_PLACES_API_KEY is required. "
            "Set GOOGLE_PLACES_API_KEY in .env file."
        )
    
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        logger.warning(
            "RAZORPAY_KEY_ID or RAZORPAY_KEY_SECRET not set — "
            "payment endpoints will fail at runtime. "
            "Set these in .env file if payments are required."
        )
    
    logger.info("Configuration validation passed")

    app.state.limiter = shared_limiter
    logger.info("Rate limiter initialized (shared instance)")
    await initialise_redis()

    pinecone_client = PineconeClient()
    if settings.PINECONE_API_KEY:
        try:
            await pinecone_client.initialise()
        except Exception as exc:
            logger.warning(
                "Pinecone initialisation failed at startup — "
                "knowledge sync and Q&A will fail until resolved: %s",
                exc,
            )
    else:
        logger.warning(
            "PINECONE_API_KEY not set — Pinecone client inactive. "
            "Knowledge sync and Q&A endpoints will return errors."
        )
    app.state.pinecone_client = pinecone_client

    openai_client = OpenAIEmbeddingClient()
    app.state.openai_client = openai_client
    logger.info("OpenAI client initialized — model: %s", settings.OPENAI_EMBEDDING_MODEL)

    google_timeout = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)
    limits = httpx.Limits(max_connections=50, max_keepalive_connections=20)

    app.state.http_nearby = httpx.AsyncClient(timeout=google_timeout, limits=limits)
    app.state.http_text_search = httpx.AsyncClient(timeout=google_timeout, limits=limits)
    app.state.http_place_details = httpx.AsyncClient(timeout=google_timeout, limits=limits)
    app.state.http_autocomplete = httpx.AsyncClient(timeout=google_timeout, limits=limits)

    routes_timeout = httpx.Timeout(connect=5.0, read=20.0, write=5.0, pool=5.0)
    app.state.http_routes = httpx.AsyncClient(timeout=routes_timeout, limits=limits)

    app.state.http_open_meteo = httpx.AsyncClient(timeout=google_timeout, limits=limits)
    app.state.http_geocoding = httpx.AsyncClient(timeout=google_timeout, limits=limits)

    logger.info("geo-map-backend ready.")
    yield

    logger.info("Shutting down geo-map-backend...")
    await app.state.http_nearby.aclose()
    await app.state.http_text_search.aclose()
    await app.state.http_place_details.aclose()
    await app.state.http_autocomplete.aclose()
    await app.state.http_routes.aclose()
    await app.state.http_open_meteo.aclose()
    await app.state.http_geocoding.aclose()
    logger.info("httpx clients closed.")
    try:
        shutdown_executor()
    except Exception as exc:
        logger.warning("Pinecone executor shutdown encountered an issue: %s", exc)

    await close_redis()
    try:
        from langfuse import get_client

        get_client().flush()
        logger.info("Langfuse traces flushed.")
    except Exception as exc:
        logger.warning("Langfuse flush failed: %s", exc)
    logger.info("geo-map-backend shutdown complete.")


app = FastAPI(
    title="Geo Map Backend",
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=(_ALLOWED_ORIGINS != ["*"]),
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Type", "Authorization", "X-Chat-Session-Id"],
    max_age=3600,
)


async def http_exception_handler(request: Request, exc: HTTPException):
    message = sanitize_error_message(exc.detail, f"{request.method} {request.url.path}")

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": str(message),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RateLimitExceeded, custom_rate_limit_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(Exception, global_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(ExceptionGroup, exception_group_handler)
app.add_middleware(LangfuseRequestTracingMiddleware)

app.include_router(api_router)

@app.get("/", tags=["Health"])
def health_check():
    return {
        "status": "ok",
        "service": "geo-map-backend",
        "version": "3.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    schema.setdefault("components", {})
    schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Enter the JWT token from POST /api/auth/login",
        }
    }

    for path_data in schema.get("paths", {}).values():
        for operation in path_data.values():
            if isinstance(operation, dict) and "security" in operation:
                operation["security"] = [{"BearerAuth": []}]

    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi
