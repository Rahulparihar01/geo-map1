import asyncio
import logging
from typing import AsyncGenerator, List
from fastapi import HTTPException, status
from langfuse.openai import AsyncOpenAI
from openai import APIError, APITimeoutError, RateLimitError
from app.core.config import settings
from app.core.retry_utils import (
    _is_non_retryable_rate_limit,
    retry_with_exponential_backoff,
)

logger = logging.getLogger(__name__)

_BATCH_LIMIT = 100


class EmbeddingError(HTTPException):
    def __init__(self, detail: str = "Embedding generation failed"):
        super().__init__(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail,
        )


class EmbeddingRateLimitError(HTTPException):
    def __init__(self, detail: str = "OpenAI rate limit exceeded. Try again shortly."):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
        )


def _raise_rate_limit_error(exc: RateLimitError) -> None:
    if _is_non_retryable_rate_limit(exc):
        logger.error(
            "OpenAI quota/billing error (insufficient_quota) — not retrying: %s", exc
        )
        raise EmbeddingRateLimitError(detail="Rate limit exceeded. Please try again later.")
    raise EmbeddingRateLimitError(detail="Rate limit exceeded. Please try again later.")


class ChatCompletionError(HTTPException):
    def __init__(self, detail: str = "Chat completion failed"):
        super().__init__(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail,
        )


class OpenAIEmbeddingClient:
    def __init__(self) -> None:
        self.model = settings.OPENAI_EMBEDDING_MODEL
        self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    @retry_with_exponential_backoff(
        max_retries=5,
        initial_delay=1.0,
        exponential_base=2,
        jitter=True,
        exceptions=(RateLimitError, APITimeoutError, APIError),
    )
    async def _embed_batch_with_retry(self, batch: List[str]) -> List[List[float]]:
        response = await self._client.embeddings.create(
            input=batch,
            model=self.model,
            name="openai-embedding",
        )
        batch_vectors = [item.embedding for item in response.data]
        return batch_vectors

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        filtered_texts = [t for t in texts if t and t.strip()]

        if not filtered_texts:
            return [[0.0] * 1536 for _ in texts]

        all_embeddings: List[List[float]] = []

        for batch_start in range(0, len(filtered_texts), _BATCH_LIMIT):
            batch = filtered_texts[batch_start : batch_start + _BATCH_LIMIT]
            logger.info(
                "OpenAI embed — model: %s, batch: %d texts (offset %d)",
                self.model,
                len(batch),
                batch_start,
            )

            try:
                batch_vectors = await self._embed_batch_with_retry(batch)
                all_embeddings.extend(batch_vectors)
                logger.info(
                    "OpenAI embed — received %d vectors (dim=%d)",
                    len(batch_vectors),
                    len(batch_vectors[0]) if batch_vectors else 0,
                )
            except RateLimitError as exc:
                logger.error("OpenAI rate limit persisted after all retries")
                _raise_rate_limit_error(exc)
            except (APITimeoutError, APIError) as exc:
                logger.error("OpenAI API error after all retries: %s", exc)
                raise EmbeddingError(detail="Embedding generation failed. Please try again.")
            except (ValueError, TypeError, RuntimeError) as exc:
                logger.error("Unexpected error during embedding: %s", exc)
                raise EmbeddingError(detail="Embedding generation failed. Please try again.")

        return all_embeddings

    async def embed_single(self, text: str) -> List[float]:
        results = await self.embed_texts([text])
        return results[0]

    async def chat_completion(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        return await self.get_chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    @retry_with_exponential_backoff(
        max_retries=5,
        initial_delay=1.0,
        exponential_base=2,
        jitter=True,
        exceptions=(RateLimitError, APITimeoutError, APIError),
    )
    async def _get_chat_completion_raw(
        self,
        messages: List[dict],
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> str:
        response = await self._client.chat.completions.create(
            model=settings.OPENAI_CHAT_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            name="openai-chat-with-history",
        )
        return response.choices[0].message.content or ""

    async def get_chat_completion(
        self,
        messages: List[dict],
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> str:
        model = settings.OPENAI_CHAT_MODEL
        logger.info(
            "OpenAI chat with history — model: %s, messages: %d, max_tokens: %d",
            model,
            len(messages),
            max_tokens,
        )

        try:
            answer = await self._get_chat_completion_raw(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            logger.info(
                "OpenAI chat with history — received %d chars",
                len(answer),
            )
            return answer.strip()

        except RateLimitError as exc:
            logger.error("OpenAI rate limit persisted after all retries")
            _raise_rate_limit_error(exc)
        except (APITimeoutError, APIError) as exc:
            logger.error("OpenAI chat with history error after retries: %s", exc)
            raise ChatCompletionError(detail="Unable to answer this question. Please try again.")
        except (ValueError, TypeError, RuntimeError) as exc:
            logger.error("Unexpected error during chat with history: %s", exc)
            raise ChatCompletionError(detail="Unable to answer this question. Please try again.")

    async def _stream_chat_with_retry(
        self,
        messages: List[dict],
        temperature: float,
        max_tokens: int,
        log_label: str,
    ) -> AsyncGenerator[str, None]:
        model = settings.OPENAI_CHAT_MODEL
        logger.info(
            "OpenAI %s — model: %s, messages: %d, max_tokens: %d",
            log_label,
            model,
            len(messages),
            max_tokens,
        )

        max_retries = 5
        initial_delay = 1.0
        emitted = False

        for attempt in range(max_retries + 1):
            try:
                stream = await self._client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                    name="openai-stream-chat",
                )

                async for chunk in stream:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and delta.content:
                        emitted = True
                        yield delta.content

                return

            except RateLimitError as e:
                if _is_non_retryable_rate_limit(e):
                    logger.error(
                        "OpenAI %s quota/billing error (429 insufficient_quota) — not retrying",
                        log_label,
                    )
                    _raise_rate_limit_error(e)

                if emitted:
                    # Never retry after tokens were already sent — a fresh
                    # stream would duplicate content the client already has.
                    logger.error(
                        "OpenAI %s failed mid-stream after emitting tokens — not retrying",
                        log_label,
                    )
                    raise EmbeddingRateLimitError()

                if attempt >= max_retries:
                    logger.error(
                        "OpenAI %s rate limit persisted after all retries", log_label
                    )
                    raise EmbeddingRateLimitError()

                delay = 10.0 * (2**attempt)
                delay = min(delay, 60.0)

                logger.warning(
                    f"OpenAI {log_label} rate limited. Retrying in {delay:.1f}s "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                await asyncio.sleep(delay)

            except (APITimeoutError, APIError) as exc:
                if emitted:
                    # Same as above: no retry after partial output.
                    logger.error(
                        "OpenAI %s failed mid-stream after emitting tokens — not retrying",
                        log_label,
                    )
                    raise ChatCompletionError(detail="Unable to answer this question. Please try again.")

                if attempt >= max_retries:
                    logger.error(
                        "OpenAI %s failed after retries: %s", log_label, exc
                    )
                    raise ChatCompletionError(detail="Unable to answer this question. Please try again.")

                delay = initial_delay * (2**attempt)
                delay = min(delay, 30.0)

                logger.warning(
                    f"OpenAI {log_label} attempt {attempt + 1}/{max_retries} failed, "
                    f"retrying in {delay:.1f}s: {exc}"
                )
                await asyncio.sleep(delay)

            except (ValueError, TypeError, RuntimeError) as exc:
                logger.error("Unexpected error during %s: %s", log_label, exc)
                raise ChatCompletionError(detail="Unable to answer this question. Please try again.")

    async def stream_chat_completion(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> AsyncGenerator[str, None]:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        async for token in self._stream_chat_with_retry(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            log_label="stream chat",
        ):
            yield token

    async def stream_chat_with_history(
        self,
        messages: List[dict],
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> AsyncGenerator[str, None]:
        async for token in self._stream_chat_with_retry(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            log_label="stream chat with history",
        ):
            yield token
