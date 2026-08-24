import asyncio
import functools
import logging
import random
from typing import Any, Callable, Optional, Tuple, Type

from openai import APIError, APITimeoutError, RateLimitError

logger = logging.getLogger(__name__)

DEFAULT_MAX_RETRIES = 5
DEFAULT_INITIAL_DELAY = 1.0
DEFAULT_EXPONENTIAL_BASE = 2
DEFAULT_MAX_DELAY = 60.0
DEFAULT_JITTER = True

RATE_LIMIT_INITIAL_DELAY = 10.0
RATE_LIMIT_EXPONENTIAL_BASE = 2
RATE_LIMIT_MAX_DELAY = 60.0


_NON_RETRYABLE_RATE_LIMIT_TYPES = ("insufficient_quota",)
_NON_RETRYABLE_RATE_LIMIT_CODES = (
    "credit_balance_exhausted",
    "billing_not_active",
    "account_deactivated",
)


def _is_quota_error(error: Any) -> bool:
    return isinstance(error, dict) and (
        error.get("type") in _NON_RETRYABLE_RATE_LIMIT_TYPES
        or error.get("code") in _NON_RETRYABLE_RATE_LIMIT_CODES
    )


def _is_non_retryable_rate_limit(exception: RateLimitError) -> bool:
    body = getattr(exception, "body", None)
    if isinstance(body, dict) and _is_quota_error(body.get("error")):
        return True

    try:
        response = getattr(exception, "response", None)
        if response is not None:
            data = response.json()
            if isinstance(data, dict) and _is_quota_error(data.get("error")):
                return True
    except Exception:
        pass

    return False


def _calculate_delay(
    attempt: int,
    initial_delay: float,
    exponential_base: float,
    max_delay: float,
    jitter: bool,
) -> float:
    delay = initial_delay * (exponential_base**attempt)

    delay = min(delay, max_delay)

    if jitter:
        jitter_amount = random.uniform(0, 1)
        delay += jitter_amount

    return delay


def _extract_retry_after(exception: RateLimitError) -> Optional[float]:
    try:
        if hasattr(exception, "response") and exception.response:
            headers = getattr(exception.response, "headers", {})
            retry_after = headers.get("Retry-After") or headers.get("retry-after")

            if retry_after:
                try:
                    return float(retry_after)
                except (ValueError, TypeError):
                    pass

        if hasattr(exception, "message") and exception.message:
            msg = str(exception.message).lower()
            if "try again in" in msg:
                import re

                match = re.search(r"try again in (\d+)s", msg)
                if match:
                    return float(match.group(1))
    except Exception as e:
        logger.debug(f"Failed to extract Retry-After: {e}")

    return None


def retry_with_exponential_backoff(
    max_retries: int = DEFAULT_MAX_RETRIES,
    initial_delay: float = DEFAULT_INITIAL_DELAY,
    exponential_base: float = DEFAULT_EXPONENTIAL_BASE,
    max_delay: float = DEFAULT_MAX_DELAY,
    jitter: bool = DEFAULT_JITTER,
    exceptions: Tuple[Type[Exception], ...] = (
        RateLimitError,
        APITimeoutError,
        APIError,
    ),
    on_retry: Optional[Callable[[Exception, int, float], None]] = None,
):
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            last_exception: Optional[Exception] = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)

                except exceptions as e:
                    last_exception = e

                    if isinstance(e, RateLimitError) and _is_non_retryable_rate_limit(
                        e
                    ):
                        logger.error(
                            f"{func.__name__} failed with non-retryable OpenAI "
                            f"quota/billing error (429 insufficient_quota) — not retrying: {e}",
                            extra={
                                "function": func.__name__,
                                "exception_type": type(e).__name__,
                                "exception_message": str(e),
                                "non_retryable": "insufficient_quota",
                            },
                        )
                        raise

                    if attempt >= max_retries:
                        logger.error(
                            f"{func.__name__} failed after {max_retries} retries: {e}",
                            extra={
                                "function": func.__name__,
                                "max_retries": max_retries,
                                "exception_type": type(e).__name__,
                                "exception_message": str(e),
                            },
                        )
                        raise

                    is_rate_limit = isinstance(e, RateLimitError)

                    if is_rate_limit:
                        retry_after = _extract_retry_after(e)

                        if retry_after:
                            delay = min(retry_after, RATE_LIMIT_MAX_DELAY)
                            logger.warning(
                                f"{func.__name__} rate limited. Using Retry-After: {delay:.1f}s "
                                f"(attempt {attempt + 1}/{max_retries})",
                                extra={
                                    "function": func.__name__,
                                    "attempt": attempt + 1,
                                    "max_retries": max_retries,
                                    "delay_seconds": delay,
                                    "retry_after_header": True,
                                },
                            )
                        else:
                            delay = _calculate_delay(
                                attempt=attempt,
                                initial_delay=RATE_LIMIT_INITIAL_DELAY,
                                exponential_base=RATE_LIMIT_EXPONENTIAL_BASE,
                                max_delay=RATE_LIMIT_MAX_DELAY,
                                jitter=jitter,
                            )
                            logger.warning(
                                f"{func.__name__} rate limited. Retrying in {delay:.1f}s "
                                f"(attempt {attempt + 1}/{max_retries})",
                                extra={
                                    "function": func.__name__,
                                    "attempt": attempt + 1,
                                    "max_retries": max_retries,
                                    "delay_seconds": delay,
                                    "exception_type": "RateLimitError",
                                },
                            )
                    else:
                        delay = _calculate_delay(
                            attempt=attempt,
                            initial_delay=initial_delay,
                            exponential_base=exponential_base,
                            max_delay=max_delay,
                            jitter=jitter,
                        )
                        logger.warning(
                            f"{func.__name__} failed with {type(e).__name__}. "
                            f"Retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries}): {e}",
                            extra={
                                "function": func.__name__,
                                "attempt": attempt + 1,
                                "max_retries": max_retries,
                                "delay_seconds": delay,
                                "exception_type": type(e).__name__,
                                "exception_message": str(e),
                            },
                        )

                    if on_retry:
                        try:
                            on_retry(e, attempt + 1, delay)
                        except Exception as callback_error:
                            logger.error(f"on_retry callback failed: {callback_error}")

                    await asyncio.sleep(delay)

                except Exception as e:
                    logger.error(
                        f"{func.__name__} failed with non-retryable exception: {e}",
                        extra={
                            "function": func.__name__,
                            "exception_type": type(e).__name__,
                            "exception_message": str(e),
                        },
                    )
                    raise

            if last_exception:
                raise last_exception

        if not asyncio.iscoroutinefunction(func):
            raise TypeError(
                "retry_with_exponential_backoff supports async functions only"
            )
        return async_wrapper

    return decorator
