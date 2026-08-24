import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.exceptions.custom_exceptions import BadRequestError, NotFoundError
from app.integrations.openai_client import EmbeddingRateLimitError, OpenAIEmbeddingClient
from app.models.user import User
from app.repositories.ai_chat_repository import AIChatRepository
from app.schemas.ai_chat import AIChatResponse
from app.services.credit_service import CreditService
from app.models.user_location import UserLocation
from app.repositories.location_repository import LocationRepository
from app.utils.tokens import estimate_tokens
from app.utils.error_messages import SESSION_LIMIT_REACHED, SERVER_ERROR
from langfuse import observe, propagate_attributes

logger = logging.getLogger(__name__)


def _validate_answer(answer: str, query: str) -> Optional[str]:
    if not answer or not answer.strip():
        return None

    stripped = answer.strip()

    # Answer is too short to be useful
    if len(stripped) < 10:
        return None

    # Answer looks like an error echo or system prompt leak
    lower = stripped.lower()
    bad_signals = [
        "i cannot",
        "i can't",
        "i am unable",
        "as an ai",
        "i don't have access",
        "i do not have access",
        "error:",
        "traceback",
    ]
    if any(signal in lower for signal in bad_signals):
        if len(stripped) < 80:
            return None

    return stripped


async def _get_user_context(db: Session, user_id: int) -> str:
    try:

        loc = LocationRepository(db).get_current_location(user_id)
        if loc is None:
            return ""

        parts = [f"Current location: ({loc.latitude:.4f}, {loc.longitude:.4f})"]
        if loc.address:
            parts.append(f"Address: {loc.address}")
        return " | ".join(parts)
    except Exception:
        logger.debug("Could not build user context for user_id=%s", user_id)
        return ""

_CHAT_FALLBACK = (
    "Please try again in a moment."
)

_SYSTEM_PROMPT_GENERIC = """You are GeoMap's travel assistant.

Goal: Help users plan trips, discover places, compare options, and answer travel questions accurately.

Language & Tone
- Reply in the language the user writes in (English, Hindi, Hinglish, or any other). Match their style.
- Be direct, structured, and useful. Keep continuity with conversation history.
- Use short paragraphs and bullet lists; only use headers for long answers.
- No filler, hype, or unnecessary commentary.

Rules
- Never hallucinate or invent facts (prices, schedules, opening hours, visa rules, weather, transport times).
- If uncertain, say so. Separate verified info from assumptions.
- For ambiguous requests, ask one clarifying question before answering.
- When current or location-specific info matters, ask for details or verify first.

Travel Planning
- Understand user's goal, budget, dates, origin, destination, group size, pace, preferences.
- Recommend options that fit constraints. Consider practicality, travel time, season, safety, cost.
- For India trips, factor in weather seasons, festivals, crowds, and booking lead times.
- Give specific, realistic recommendations (3-5 options max for suggestions).

Response Structure (when helpful)
- Direct answer
- Key details
- Options or recommendations
- Trade-offs or caveats
- Next step

Special Cases
- Itineraries: Organize by day, include pace/transit, flag items needing confirmation.
- Comparisons: Compare by cost, convenience, travel time, fit, risk. End with clear recommendation.
- Destination suggestions: Match to budget, season, interests, trip length.
- Live/recent info: State that it needs verification before booking. Don't present stale data as current.

Never: Hallucinate, pretend to check live data, invent personal experience, give vague advice when a precise answer is possible."""

class AIChatService:
    CHAT_COST = 5
    
    def __init__(
        self,
        db: Session,
        openai_client: OpenAIEmbeddingClient,
    ) -> None:
        self.db = db
        self.openai_client = openai_client
        self.repo = AIChatRepository(db)

    async def _persist_conversation(self, session_id: str, session: Any,
                                   user_query: str, answer: str, 
                                   model_used: str) -> None:
        
        user_msg = self.repo.add_message(
            session_id=session_id,
            role="user",
            content=user_query,
            token_count=estimate_tokens(user_query),
            model_used=model_used,
        )
        
        assistant_msg = self.repo.add_message(
            session_id=session_id,
            role="assistant",
            content=answer,
            token_count=estimate_tokens(answer),
            model_used=model_used,
        )
        
        # Use assistant message's actual timestamp (no aggregation query needed!)
        self.repo.update_session_timestamp_direct(
            session=session, 
            timestamp=assistant_msg.created_at
        )
        self.db.commit()
        
        logger.debug(
            "Persisted conversation for session %s (user:%d tokens + assistant:%d tokens)",
            session_id,
            user_msg.token_count or 0,
            assistant_msg.token_count or 0,
        )

    def _build_openai_messages(
        self, history_messages: List, user_query: str, system_prompt: str
    ) -> List[dict]:
        messages: List[dict] = [{"role": "system", "content": system_prompt}]
        for m in history_messages:
            messages.append({"role": m.role, "content": m.content})
        messages.append({"role": "user", "content": user_query})
        return messages

    def _find_duplicate_answer(
        self, history: List, query: str, window_seconds: int = 60
    ) -> Optional[str]:

        now = datetime.now(timezone.utc)
        for i, m in enumerate(history):
            if (
                m.role == "user"
                and m.content == query
                and m.created_at is not None
            ):
                age = (now - m.created_at).total_seconds()
                if 0 <= age <= window_seconds:
                    for following in history[i + 1 :]:
                        if following.role == "assistant":
                            return following.content
        return None

    def _resolve_session(
        self, user_id: int, session_id: Optional[str], title: str
    ):
        session = None

        if session_id is not None:
            session = self.repo.get_session(session_id=session_id, user_id=user_id)

        if session_id is not None and session is None:
            raise NotFoundError("Chat session not found")

        if session is None:
            current_count = self.repo.count_user_sessions(user_id=user_id)
            if current_count >= settings.MAX_SESSIONS_PER_USER:
                logger.warning("Session limit reached for user_id=%s (current=%s)", user_id, current_count)
                raise BadRequestError(SESSION_LIMIT_REACHED)
            session = self.repo.create_session(user_id=user_id, title=title)
            self.db.flush()
            return session, True

        return session, False

    def _trim_history(
        self, history: List, user_query: str, system_prompt: str
    ) -> tuple:
        max_tokens = settings.OPENAI_MAX_CONTEXT_TOKENS
        system_tokens = estimate_tokens(system_prompt)
        query_tokens = estimate_tokens(user_query)
        history_tokens = [estimate_tokens(m.content) for m in history]
        total_tokens = system_tokens + sum(history_tokens) + query_tokens
        
        trimmed_count = 0
        while total_tokens > max_tokens and history_tokens:
            removed = history_tokens.pop(0)
            total_tokens -= removed
            history = history[1:]
            trimmed_count += 1

        messages = self._build_openai_messages(history, user_query=user_query, system_prompt=system_prompt)
        
        original_history = len(history) + trimmed_count
        if original_history > 0:
            retention_rate = (len(history) / original_history) * 100
            logger.debug(
                "History trim: %d/%d messages retained (%.1f%%), tokens: %d/%d used",
                len(history), original_history, retention_rate,
                total_tokens, max_tokens
            )
        
        return history, messages

    @observe(name="chat")
    async def chat(
        self,
        user_id: int,
        session_id: Optional[str],
        query: str,
    ) -> AIChatResponse:
        start = time.monotonic()
        model_used = settings.OPENAI_CHAT_MODEL

        await CreditService.check_balance(self.db, user_id, self.CHAT_COST)

        session, is_new_session = self._resolve_session(
            user_id,
            session_id,
            query.split("\n")[0][:60] or "New Chat",
        )

        try:
            history = self.repo.get_recent_messages(session_id=session.id, limit=10)
        except Exception:
            logger.exception(
                "Failed to fetch chat history (user_id=%s session_id=%s). "
                "Continuing without history. Response may lack conversation context.",
                user_id,
                session.id,
            )
            history = []

        user_context = await _get_user_context(self.db, user_id)
        system_prompt = _SYSTEM_PROMPT_GENERIC
        if user_context:
            system_prompt += f"\n\nUser context: {user_context}"
        _, messages = self._trim_history(history, query, system_prompt)

        error_type = None
        duplicate_answer = self._find_duplicate_answer(history, query)
        if duplicate_answer is not None:
            logger.info(
                "Duplicate chat query — reusing stored answer (user_id=%s session_id=%s)",
                user_id,
                session.id,
            )
            answer = duplicate_answer
        else:
            try:
                with propagate_attributes(
                    user_id=str(user_id),
                    session_id=str(session.id),
                    metadata={"stream": False},
                ):
                    raw_answer = await self.openai_client.get_chat_completion(
                        messages=messages,
                        temperature=0.7,
                        max_tokens=800,
                    )
                validated = _validate_answer(raw_answer, query)
                if validated is None:
                    logger.warning(
                        "AI Chat produced invalid answer for user_id=%s — using fallback",
                        user_id,
                    )
                    answer = _CHAT_FALLBACK
                    error_type = "invalid_response"
                else:
                    answer = validated
            except EmbeddingRateLimitError:
                logger.error(
                    "AI Chat rate limit exceeded after retries (user_id=%s session_id=%s)",
                    user_id,
                    session.id,
                    extra={
                        "event": "ai_chat_rate_limit_exceeded",
                        "user_id": user_id,
                        "session_id": session.id,
                    },
                )
                answer = "Please try again in a few moments."
                error_type = "rate_limited"
            except Exception:
                logger.exception("OpenAI API error during chat (user_id=%s)", user_id)
                answer = _CHAT_FALLBACK
                error_type = "service_error"

        if error_type is not None:
            # Do NOT persist the fallback message or deduct on errors.
            # Commit the session so the returned session_id stays valid for retry.
            self.db.commit()
            return AIChatResponse(
                success=True,
                session_id=session.id,
                answer=answer,
                is_new_session=is_new_session,
                title=session.title if is_new_session else None,
                timestamp=datetime.now(timezone.utc),
                error_type=error_type,
            )

        try:
            if duplicate_answer is not None:
                # Answer already stored — do not re-persist or re-deduct.
                self.db.commit()
            else:
                # Deduct BEFORE persisting so a deduction failure never leaves
                # messages committed without a charge (and vice versa) — the single
                # commit inside _persist_conversation persists both atomically.
                await CreditService.deduct(self.db, user_id, self.CHAT_COST)

                await self._persist_conversation(
                    session_id=session.id,
                    session=session,
                    user_query=query,
                    answer=answer,
                    model_used=model_used,
                )

            user = self.db.query(User).filter_by(id=user_id).first()
            credits_remaining = user.credits if user else None

        except Exception:
            logger.exception(
                "Failed to persist chat messages (user_id=%s session_id=%s).",
                user_id,
                session.id,
            )
            self.db.rollback()
            raise

        latency_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "AIChat complete — user=%s session=%s new=%s error=%s latency=%dms credits_left=%s",
            user_id,
            session.id,
            is_new_session,
            error_type,
            latency_ms,
            credits_remaining,
        )

        return AIChatResponse(
            success=True,
            session_id=session.id,
            answer=answer,
            is_new_session=is_new_session,
            title=session.title if is_new_session else None,
            timestamp=datetime.now(timezone.utc),
            error_type=error_type,
            credits_remaining=credits_remaining,
        )
    
    @observe(name="chat-stream")
    async def stream_chat(
        self,
        user_id: int,
        session_id: Optional[str],
        query: str,
    ) -> AsyncGenerator[str, None]:
        model_used = settings.OPENAI_CHAT_MODEL
        await CreditService.check_balance(self.db, user_id, self.CHAT_COST)
        title = query.split("\n")[0][:60] or "New Chat"
        session, is_new_session = self._resolve_session(
            user_id,
            session_id,
            title,
        )

        yield json.dumps(
            {
                "type": "metadata",
                "session_id": session.id,
                "is_new_session": is_new_session,
            }
        )

        try:
            history = self.repo.get_recent_messages(session_id=session.id, limit=10)
        except Exception:
            logger.exception(
                "Failed to fetch chat history (user_id=%s session_id=%s). "
                "Continuing without history.",
                user_id,
                session.id,
            )
            history = []

        user_context = await _get_user_context(self.db, user_id)
        system_prompt = _SYSTEM_PROMPT_GENERIC
        if user_context:
            system_prompt += f"\n\nUser context: {user_context}"
        _, messages = self._trim_history(history, query, system_prompt)

        full_answer_parts: List[str] = []
        error_type = None
        stream_start = time.monotonic()
        token_count = 0

        duplicate_answer = self._find_duplicate_answer(history, query)

        if duplicate_answer is not None:
            logger.info(
                "Duplicate chat stream query — replaying stored answer "
                "(user_id=%s session_id=%s)",
                user_id,
                session.id,
            )
            yield json.dumps({"type": "token", "content": duplicate_answer})
            full_answer_parts = [duplicate_answer]
        else:
            try:
                with propagate_attributes(
                    user_id=str(user_id),
                    session_id=str(session.id),
                    metadata={"stream": True},
                ):
                    async for content in self.openai_client.stream_chat_with_history(
                        messages=messages,
                        temperature=0.7,
                        max_tokens=800,
                    ):
                        full_answer_parts.append(content)
                        token_count += len(content.split())
                        yield json.dumps({"type": "token", "content": content})
            except EmbeddingRateLimitError:
                logger.error(
                    "AI Chat stream rate limit exceeded (user_id=%s session_id=%s)",
                    user_id,
                    session.id,
                    extra={
                        "event": "ai_chat_stream_rate_limit_exceeded",
                        "user_id": user_id,
                        "session_id": session.id,
                    },
                )
                error_msg = "Please try again in a few moments."
                yield json.dumps({"type": "error", "content": error_msg})
                error_type = "rate_limited"
            except Exception:
                logger.exception("OpenAI streaming failed during chat (user_id=%s)", user_id)
                error_msg = _CHAT_FALLBACK
                yield json.dumps({"type": "error", "content": error_msg})
                error_type = "service_error"

        answer = "".join(full_answer_parts)

        if error_type is not None:
            # Do NOT persist the fallback message or deduct on errors.
            # Commit the session so the returned session_id stays valid for retry.
            self.db.commit()
            yield json.dumps(
                {
                    "type": "done",
                    "title": session.title if is_new_session else None,
                    "error_type": error_type,
                }
            )
            return

        try:
            if duplicate_answer is not None:
                # Answer already stored — do not re-persist or re-deduct.
                self.db.commit()
            else:
                # Deduct BEFORE persisting — the single commit inside
                # _persist_conversation persists both atomically.
                await CreditService.deduct(self.db, user_id, self.CHAT_COST)

                await self._persist_conversation(
                    session_id=session.id,
                    session=session,
                    user_query=query,
                    answer=answer,
                    model_used=model_used,
                )

            user = self.db.query(User).filter_by(id=user_id).first()
            credits_remaining = user.credits if user else None
            
            stream_latency = int((time.monotonic() - stream_start) * 1000)
            logger.info(
                "Stream complete — user=%s session=%s error=%s tokens=%d latency=%dms credits=%s",
                user_id, session.id, error_type, token_count, stream_latency, credits_remaining
            )
                
        except Exception:
            logger.exception(
                "Failed to persist chat messages (user_id=%s session_id=%s).",
                user_id,
                session.id,
            )
            self.db.rollback()
            raise

        yield json.dumps(
            {
                "type": "done",
                "title": session.title if is_new_session else None,
                "error_type": error_type,
                "credits_remaining": credits_remaining,
            }
        )