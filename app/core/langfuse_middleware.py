import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# HTTP paths that trigger AI/LLM calls and get a request-level trace.
_AI_PATH_PREFIXES = ("/api/chat", "/api/compare")
_AI_PATH_SUFFIXES = ("/question", "/knowledge-sync")


def _is_ai_request(path: str) -> bool:
    if path.startswith(_AI_PATH_PREFIXES):
        return True
    if path.startswith("/api/places/"):
        return path.endswith(_AI_PATH_SUFFIXES)
    return False


def _safe_update(span, **kwargs) -> None:
    try:
        span.update(**kwargs)
    except Exception:
        logger.debug("Langfuse span update failed", exc_info=True)


class LangfuseRequestTracingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if (
            request.scope.get("type") != "http"
            or not _is_ai_request(request.url.path)
        ):
            return await call_next(request)

        try:
            from langfuse import get_client

            client = get_client()
            span_ctx = client.start_as_current_observation(
                name=f"{request.method} {request.url.path}",
                as_type="span",
                input={"path": request.url.path, "method": request.method},
            )
        except Exception:
            # Langfuse unavailable/disabled — never break the request.
            logger.debug("Langfuse unavailable, skipping request trace", exc_info=True)
            return await call_next(request)

        # start_as_current_observation returns a sync-style context manager
        # (sets the current-observation context for child spans); the span ends
        # when the block exits, including across awaits.
        try:
            with span_ctx as span:
                try:
                    response = await call_next(request)
                except Exception as exc:
                    _safe_update(
                        span,
                        level="ERROR",
                        status_message=f"{type(exc).__name__}: {exc}",
                    )
                    raise
                _safe_update(span, output={"status_code": response.status_code})
                return response
        except Exception:
            raise
