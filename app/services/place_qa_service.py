import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from app.core.config import settings
from app.exceptions.custom_exceptions import BadRequestError, NotFoundError
from app.exceptions.places import PlaceDetailNotFoundError
from app.integrations.openai_client import OpenAIEmbeddingClient
from app.integrations.pinecone_client import PineconeClient
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.place_qa_repository import PlaceQARepository
from app.schemas.place_qa import (
    AnswerSource,
    GroundingFragment,
    PlaceQuestionRequest,
    PlaceQuestionResponse,
    TechnicalMetadata,
    PlaceInfo,
    PlaceQASessionListItem,
)
from app.schemas.knowledge import SyncStatus
from app.services.place_unlock_service import PlaceUnlockService
from app.utils.tokens import estimate_tokens
from app.utils.error_messages import SESSION_LIMIT_REACHED
from langfuse import observe, propagate_attributes

logger = logging.getLogger(__name__)

_SIMILARITY_THRESHOLD = getattr(settings, "PLACEQA_SIMILARITY_THRESHOLD", 0.30)
_DEFAULT_TOP_K = getattr(settings, "PLACEQA_DEFAULT_TOP_K", 5)


@dataclass
class _CachedPlaceSnapshot:
    place_id: str
    display_name: Optional[str]
    formatted_address: Optional[str]
    primary_type: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    rating: Optional[float]
    user_rating_count: Optional[int]
    business_status: Optional[str]
    open_now: Optional[bool]
    opening_hours: Optional[Dict]
    international_phone_number: Optional[str]
    website_uri: Optional[str]
    google_maps_uri: Optional[str]
    price_level: Optional[str]
    wheelchair_accessible_entrance: Optional[bool]
    editorial_summary: Optional[str]
    extended_data: Optional[Dict]


@dataclass
class _QASessionContext:
    session: Any
    is_new_session: bool
    conversation_history: List[Any] = field(default_factory=list)


def _orm_to_snapshot(place) -> _CachedPlaceSnapshot:
    return _CachedPlaceSnapshot(
        place_id=place.place_id,
        display_name=place.display_name,
        formatted_address=place.formatted_address,
        primary_type=place.primary_type,
        latitude=place.latitude,
        longitude=place.longitude,
        rating=place.rating,
        user_rating_count=place.user_rating_count,
        business_status=place.business_status,
        open_now=place.open_now,
        opening_hours=place.opening_hours,
        international_phone_number=place.international_phone_number,
        website_uri=place.website_uri,
        google_maps_uri=place.google_maps_uri,
        price_level=place.price_level,
        wheelchair_accessible_entrance=place.wheelchair_accessible_entrance,
        editorial_summary=place.editorial_summary,
        extended_data=place.extended_data,
    )


_SYSTEM_PROMPT_TEMPLATE = """You are the GeoMap local place-discovery assistant — an expert guide for places in India and worldwide.

Your job: answer the user's question about this specific place using ONLY the PLACE CONTEXT below. Be accurate, direct, and genuinely helpful to someone visiting or researching this place.
LANGUAGE
- Always reply in the same language the user wrote in (English, Hindi, Hinglish, or any other). Match their style.
- If the user switches language mid-conversation, switch with them.

ANSWER STRUCTURE
- Start with a direct, one-or-two-line answer to their exact question.
- Then add the most useful supporting details from the context.
- Keep answers short and scannable: short paragraphs, and bullet points only when listing multiple items.
- Use **bold** for key facts (hours, rating, phone) so they stand out.
- For follow-up questions, refer back to what was already said in the conversation before answering again.

GROUNDING RULES
- Use only the PLACE CONTEXT. Never invent facts, prices, hours, reviews, or details that are not in it.
- The context has three parts:
  1. "Previous Conversation" — earlier questions and answers with this user.
  2. "Structured Information" — verified place data (name, address, rating, hours, contact, price level, amenities, etc.).
  3. "Knowledge Base (Retrieved Sections)" — retrieved knowledge sections about the place, each labeled with a SECTION name.
- If a detail is in the context, state it directly and confidently.
- If a detail is NOT in the context, say you don't have that information and suggest what you CAN help with (e.g. hours, rating, address, contact, parking).
- If the user asks about something irrelevant to this place, politely redirect to what you can help with.

HELPFULNESS
- Travelers care about: hours, rating, address, phone, website, price range, parking, wheelchair access, services (dine-in, delivery), and how to reach the place.
- If asked "should I visit" or "is it good", answer using the rating, review count, and editorial summary in the context.
- Never recommend a different place or make claims about competitors.

LIMITS
- If you are unsure, say so. Never guess.
- Keep the total answer under roughly 200 words unless the user explicitly asks for detail.

PLACE CONTEXT
{context_block}

Answer the user's question about this place now.
"""

def _build_structured_facts_block(place) -> str:
    sections = []

    basic_info = []
    if place.display_name:
        basic_info.append(f"This is {place.display_name}")
    if place.formatted_address:
        basic_info.append(f"located at {place.formatted_address}")
    if place.primary_type:
        type_label = place.primary_type.replace("_", " ").title()
        basic_info.append(f"It's a {type_label}")
    if basic_info:
        sections.append(". ".join(basic_info) + ".")

    rating_info = []
    if place.rating is not None:
        rating_info.append(f"Rating: {place.rating} out of 5 stars")
    if place.user_rating_count is not None:
        rating_info.append(f"based on {place.user_rating_count} reviews")
    if rating_info:
        sections.append(" ".join(rating_info) + ".")

    if place.business_status:
        status = place.business_status.replace("_", " ").lower()
        if status == "operational":
            sections.append("The business is currently operational.")
        else:
            sections.append(f"Business status: {status}.")

    if place.open_now is not None:
        sections.append(
            "Currently OPEN for customers." if place.open_now else "Currently CLOSED."
        )

    if place.opening_hours and isinstance(place.opening_hours, dict):
        weekdays = place.opening_hours.get("weekday_descriptions") or []
        if weekdays:
            sections.append("Operating hours:")
            for day in weekdays:
                sections.append(f"  • {day}")

    contact_items = []
    if place.international_phone_number:
        contact_items.append(f"Phone: {place.international_phone_number}")
    if place.website_uri:
        contact_items.append(f"Website: {place.website_uri}")
    if place.google_maps_uri:
        contact_items.append(f"Google Maps: {place.google_maps_uri}")
    if contact_items:
        sections.append("Contact information:")
        for item in contact_items:
            sections.append(f"  • {item}")

    if place.price_level:
        price = place.price_level.replace("PRICE_LEVEL_", "").lower()
        price_descriptions = {
            "free": "Free admission or no cost",
            "inexpensive": "Budget-friendly (₹)",
            "moderate": "Moderately priced (₹₹)",
            "expensive": "Upscale pricing (₹₹₹)",
            "very_expensive": "Premium/luxury pricing (₹₹₹₹)",
        }
        sections.append(
            f"Price range: {price_descriptions.get(price, price.capitalize())}"
        )

    if place.wheelchair_accessible_entrance is not None:
        if place.wheelchair_accessible_entrance:
            sections.append("♿ Wheelchair accessible entrance available.")
        else:
            sections.append("Note: No wheelchair accessible entrance.")

    if place.editorial_summary:
        sections.append(f"\nAbout this place: {place.editorial_summary}")

    if place.extended_data and isinstance(place.extended_data, dict):
        ext = place.extended_data

        dining_labels = []
        for flag, label in [
            ("dineIn", "Dine-in"),
            ("takeout", "Takeout"),
            ("delivery", "Delivery"),
            ("curbsidePickup", "Curbside pickup"),
            ("reservable", "Reservations accepted"),
        ]:
            if ext.get(flag) is True:
                dining_labels.append(label)
        if dining_labels:
            sections.append("Services: " + ", ".join(dining_labels) + ".")

        food_labels = []
        for flag, label in [
            ("servesBreakfast", "Breakfast"),
            ("servesLunch", "Lunch"),
            ("servesDinner", "Dinner"),
            ("servesBeer", "Beer"),
            ("servesWine", "Wine"),
            ("servesCocktails", "Cocktails"),
        ]:
            if ext.get(flag) is True:
                food_labels.append(label)
        if food_labels:
            sections.append("Food & drink: Serves " + ", ".join(food_labels) + ".")

        atmos_labels = []
        for flag, label in [
            ("outdoorSeating", "Outdoor seating"),
            ("liveMusic", "Live music"),
            ("goodForChildren", "Good for children"),
            ("goodForGroups", "Good for groups"),
            ("allowsDogs", "Allows dogs"),
            ("restroom", "Restroom available"),
        ]:
            if ext.get(flag) is True:
                atmos_labels.append(label)
        if atmos_labels:
            sections.append("Atmosphere: " + ", ".join(atmos_labels) + ".")

        parking_types = []
        for k, v in ext.items():
            if k.startswith("parking_") and v is True:
                label = k.replace("parking_", "").replace("_", " ").title()
                parking_types.append(label)
        if parking_types:
            sections.append("Parking available: " + ", ".join(parking_types) + ".")

        payment_types = []
        for k, v in ext.items():
            if k.startswith("payment_") and v is True:
                label = k.replace("payment_", "").replace("_", " ").title()
                payment_types.append(label)
        if payment_types:
            sections.append("Payment methods: " + ", ".join(payment_types) + ".")

        if ext.get("ev_charger_options"):
            ev = ext["ev_charger_options"]
            if isinstance(ev, dict):
                count = ev.get("chargerCount", "some")
                sections.append(f"🔌 EV charging available ({count} chargers).")

        wiki_extract = ext.get("wikipedia_extract")
        if wiki_extract:
            sections.append(f"\n📖 From Wikipedia: {wiki_extract[:500]}")

        for key in ("neighborhood", "sublocality", "locality", "state", "country"):
            val = ext.get(key)
            if val:
                display_key = key.replace("_", " ").title()
                sections.append(f"📍 {display_key}: {val}")

    return "\n".join(sections)


def _compute_confidence(scores: List[float]) -> Optional[float]:
    if not scores:
        return None
    return round(sum(scores) / len(scores), 3)


def _build_rate_limit_fallback(place_name: str, structured_block: str) -> str:
    name = place_name or "this place"
    facts = (structured_block or "").strip()[:600]
    if facts:
        return (
            f"I'm sorry — the AI assistant is temporarily unavailable. "
            f"Here's the key information about {name}:\n\n"
            f"{facts}\n\n"
        )
    return "I'm sorry — the AI assistant is temporarily unavailable."


def _validate_qa_answer(answer: str) -> Optional[str]:
    if not answer or not answer.strip():
        return None

    stripped = answer.strip()

    # Answer is too short to be useful
    if len(stripped) < 10:
        return None

    return stripped


class PlaceQAService:
    _PLACE_CACHE_TTL = 300
    _PLACE_CACHE_MAX_SIZE = 200
    _place_cache: Dict[str, tuple] = {}
    _place_cache_order: List[str] = []  # LRU tracking

    def __init__(
        self,
        db: Session,
        openai_client: OpenAIEmbeddingClient,
        pinecone_client: PineconeClient,
    ) -> None:
        self.db = db
        self.openai_client = openai_client
        self.pinecone_client = pinecone_client
        self.knowledge_repo = KnowledgeRepository(db)
        self.qa_repo = PlaceQARepository(db)

    def _get_cached_place(self, place_id: str) -> Optional[_CachedPlaceSnapshot]:
        now = time.time()
        cached = PlaceQAService._place_cache.get(place_id)
        if cached is not None:
            snapshot, cached_at = cached
            if now - cached_at < self._PLACE_CACHE_TTL:
                # Move to end of order list (most recently used)
                if place_id in PlaceQAService._place_cache_order:
                    PlaceQAService._place_cache_order.remove(place_id)
                PlaceQAService._place_cache_order.append(place_id)
                return snapshot

        place = self.knowledge_repo.get_place_detail(place_id)
        if place is None:
            return None

        snapshot = _orm_to_snapshot(place)

        PlaceQAService._place_cache[place_id] = (snapshot, now)
        if place_id in PlaceQAService._place_cache_order:
            PlaceQAService._place_cache_order.remove(place_id)
        PlaceQAService._place_cache_order.append(place_id)

        # Evict least recently used if over capacity
        while len(PlaceQAService._place_cache) > self._PLACE_CACHE_MAX_SIZE:
            oldest_key = PlaceQAService._place_cache_order.pop(0)
            PlaceQAService._place_cache.pop(oldest_key, None)

        return snapshot

    def get_place_info(self, place_id: str) -> Optional["PlaceInfo"]:
        snapshot = self._get_cached_place(place_id)
        if snapshot is None:
            return None
        return PlaceInfo(
            place_id=snapshot.place_id,
            name=snapshot.display_name,
            address=snapshot.formatted_address,
        )

    def _generate_title_from_question(self, question: str) -> str:
        title = question.split("\n")[0][:50]
        if len(question) > 50:
            title += "..."
        return title or "New Q&A"

    def _format_conversation_history(self, messages: List) -> str:
        if not messages:
            return ""
        history_lines = ["--- Previous Conversation ---"]
        for msg in messages:
            role_label = "User" if msg.role == "user" else "Assistant"
            history_lines.append(f"{role_label}: {msg.content}")
        history_lines.append("--- End Previous Conversation ---\n")
        return "\n".join(history_lines)

    def _trim_conversation_history(self, messages: List) -> List:
        max_tokens = settings.OPENAI_MAX_CONTEXT_TOKENS
        history_budget = int(max_tokens * 0.30)

        total = 0
        kept = []
        for msg in reversed(messages):
            msg_tokens = estimate_tokens(msg.content)
            if total + msg_tokens > history_budget:
                break
            total += msg_tokens
            kept.append(msg)
        kept.reverse()
        return kept

    async def list_sessions(
        self,
        user_id: int,
        page: int = 1,
        page_size: int = 10,
        place_id: Optional[str] = None,
        search: Optional[str] = None,
        sort_by: str = "last_message",
    ) -> Tuple[List[PlaceQASessionListItem], int, bool]:
        logger.info(
            "Listing sessions — user_id: %s, page: %s, place_id: %s, search: %r",
            user_id,
            page,
            place_id,
            search,
        )

        offset = (page - 1) * page_size
        sessions, total_count = self.qa_repo.list_sessions(
            user_id=user_id,
            place_id=place_id,
            search=search,
            sort_by=sort_by,
            limit=page_size,
            offset=offset,
        )

        has_next = (offset + page_size) < total_count

        session_items: List[PlaceQASessionListItem] = []
        for session in sessions:
            place_info = None
            if session.place_id:
                place_detail = self._get_cached_place(session.place_id)
                if place_detail:
                    place_info = PlaceInfo(
                        place_id=session.place_id,
                        name=place_detail.display_name,
                        address=place_detail.formatted_address,
                    )

            message_count = self.qa_repo.count_session_messages(session.id)
            last_message = self.qa_repo.get_last_message_preview(session.id)
            if last_message and len(last_message) > 100:
                last_message = last_message[:100] + "..."

            session_items.append(
                PlaceQASessionListItem(
                    session_id=session.id,
                    place=place_info,
                    title=session.title,
                    last_message=last_message,
                    message_count=message_count,
                    last_message_at=session.last_message_at,
                    created_at=session.created_at,
                )
            )

        logger.info(
            "Found %d sessions (total: %d, has_next: %s)",
            len(session_items),
            total_count,
            has_next,
        )

        return session_items, total_count, has_next

    async def get_session_detail(
        self,
        session_id: str,
        user_id: int,
        page: int = 1,
        page_size: int = 10,
    ) -> Tuple[Optional[Any], int, bool]:
        offset = (page - 1) * page_size
        session = self.qa_repo.get_session_with_messages(
            session_id=session_id,
            user_id=user_id,
            limit=page_size,
            offset=offset,
        )

        if not session:
            return None, 0, False

        total_messages = self.qa_repo.count_session_messages(session_id)
        has_next = (offset + page_size) < total_messages
        return session, total_messages, has_next

    async def bulk_delete_sessions(
        self, session_ids: List[str], user_id: int
    ) -> List[str]:
        deleted_ids = self.qa_repo.bulk_delete_sessions(session_ids, user_id)
        self.db.commit()
        logger.info("Bulk deleted %d sessions for user %s", len(deleted_ids), user_id)
        return deleted_ids

    def _persist_audit(
        self,
        *,
        user_id: int,
        place_id: str,
        question_text: str,
        knowledge_available: bool,
        pinecone_matches: int,
        answer_text: str,
        confidence_score: Optional[float],
        answer_source: str,
        grounding_chunks: Optional[List[Dict[str, Any]]],
        context_tokens: Optional[int],
        model_used: str,
        latency_ms: int,
        session_id: Optional[str] = None,
    ) -> None:
        try:
            q_row = self.qa_repo.create_question(
                user_id=user_id,
                place_id=place_id,
                question_text=question_text,
                knowledge_available=knowledge_available,
                pinecone_matches=pinecone_matches,
                session_id=session_id,
            )
            self.qa_repo.create_answer_log(
                question_id=q_row.id,
                user_id=user_id,
                place_id=place_id,
                answer_text=answer_text,
                confidence_score=confidence_score,
                answer_source=answer_source,
                grounding_chunks=grounding_chunks,
                context_tokens=context_tokens,
                model_used=model_used,
                latency_ms=latency_ms,
                session_id=session_id,
            )
            self.db.commit()
        except Exception as exc:
            logger.error(
                "PlaceQA audit persist failed (user=%s place=%s session=%s): %s",
                user_id,
                place_id,
                session_id,
                exc,
                extra={
                    "metric": "placeqa.audit_failure",
                    "user_id": user_id,
                    "place_id": place_id,
                    "session_id": session_id,
                    "error": str(exc),
                },
            )
            self.db.rollback()

    async def _reserve_question_usage(self, user_id: int, place_id: str) -> None:
        await PlaceUnlockService(self.db).record_question_usage(user_id, place_id)

    async def _build_rag_context(
        self,
        *,
        place_id: str,
        question: str,
        user_id: int,
        session_id: Optional[str],
        conversation_history: List,
        place,
        top_k: int,
        stream: bool,
        build_fragments: bool = False,
    ) -> Dict[str, Any]:
        sync_record = self.knowledge_repo.get_sync_record(place_id)
        knowledge_available = (
            sync_record is not None and sync_record.sync_status == SyncStatus.SYNCED
        )

        query_vector: List[float] = []
        pinecone_matches_list: List[Dict[str, Any]] = []

        if knowledge_available:
            try:
                with propagate_attributes(
                    user_id=str(user_id),
                    session_id=session_id,
                    metadata={"place_id": place_id, "stream": stream, "step": "embedding"},
                ):
                    query_vector = await self.openai_client.embed_single(question)
            except Exception as exc:
                from app.integrations.openai_client import EmbeddingRateLimitError

                if isinstance(exc, EmbeddingRateLimitError):
                    logger.warning(
                        "PlaceQA embed rate limited for %s — continuing without embeddings",
                        place_id,
                        extra={
                            "event": "place_qa_embed_rate_limited",
                            "place_id": place_id,
                            "user_id": user_id,
                        },
                    )
                else:
                    logger.warning(
                        "PlaceQA embed failed for %s, falling back: %s", place_id, exc
                    )
                knowledge_available = False

        if knowledge_available and query_vector:
            try:
                pinecone_matches_list = await self.pinecone_client.query_vectors(
                    place_id=place_id,
                    query_vector=query_vector,
                    top_k=top_k,
                    include_metadata=True,
                )
            except Exception as exc:
                logger.warning(
                    "PlaceQA Pinecone query failed for %s, falling back: %s",
                    place_id,
                    exc,
                )
                pinecone_matches_list = []

        accepted_matches = [
            m
            for m in pinecone_matches_list
            if (m.get("score") or 0.0) >= _SIMILARITY_THRESHOLD
        ]
        accepted_matches = sorted(
            accepted_matches, key=lambda m: m.get("score", 0.0), reverse=True
        )

        max_context_tokens = settings.OPENAI_MAX_CONTEXT_TOKENS
        structured_block = _build_structured_facts_block(place)
        structured_tokens = estimate_tokens(structured_block)

        conversation_context = ""
        if conversation_history:
            trimmed_history = self._trim_conversation_history(conversation_history)
            conversation_context = self._format_conversation_history(
                trimmed_history
            )
        conversation_tokens = estimate_tokens(conversation_context)

        available_for_chunks = (
            max_context_tokens - structured_tokens - conversation_tokens - 200
        )

        trimmed_matches = []
        cumulative_tokens = 0
        for match in accepted_matches:
            text = match.get("metadata", {}).get("text", "")
            chunk_tokens = estimate_tokens(text)
            if cumulative_tokens + chunk_tokens <= available_for_chunks:
                trimmed_matches.append(match)
                cumulative_tokens += chunk_tokens
            else:
                break
        accepted_matches = trimmed_matches

        context_parts: List[str] = []
        grounding_chunks_for_log: List[Dict[str, Any]] = []
        grounding_fragments: List[GroundingFragment] = []

        if conversation_context:
            context_parts.append(conversation_context)

        context_parts.append("--- Structured Information ---")
        context_parts.append(structured_block)

        if accepted_matches:
            context_parts.append("\n--- Knowledge Base (Retrieved Sections) ---")
            for match in accepted_matches:
                meta = match.get("metadata", {})
                section = meta.get("section", "unknown")
                text = meta.get("text", "")
                score = round(float(match.get("score", 0.0)), 4)
                if text.strip():
                    context_parts.append(f"\n[{section.upper()}]\n{text}")
                    grounding_chunks_for_log.append(
                        {"section": section, "text": text, "score": score}
                    )
                    if build_fragments:
                        grounding_fragments.append(
                            GroundingFragment(
                                section=section,
                                text=text[:300],
                                similarity_score=score,
                                source_type="pinecone",
                            )
                        )

        if build_fragments:
            grounding_fragments.insert(
                0,
                GroundingFragment(
                    section="structured_db",
                    text=structured_block[:300],
                    similarity_score=1.0,
                    source_type="structured_db",
                ),
            )

        context_block = "\n".join(context_parts)
        context_tokens = estimate_tokens(context_block)
        accepted_scores = [float(m.get("score", 0.0)) for m in accepted_matches]
        confidence_score = _compute_confidence(accepted_scores)

        return {
            "context_block": context_block,
            "context_tokens": context_tokens,
            "accepted_matches": accepted_matches,
            "knowledge_available": knowledge_available,
            "confidence_score": confidence_score,
            "structured_block": structured_block,
            "grounding_chunks_for_log": grounding_chunks_for_log,
            "grounding_fragments": grounding_fragments,
        }

    def _get_or_create_session(
        self,
        *,
        user_id: int,
        place_id: str,
        question: str,
        session_id: Optional[str],
    ) -> _QASessionContext:
        if session_id:
            session = self.qa_repo.get_session(
                session_id=session_id,
                user_id=user_id,
            )
            if session is None:
                raise NotFoundError("Session not found")

            if session.place_id and session.place_id != place_id:
                logger.warning(
                    "Session %s belongs to place %s, cannot use for place %s (user=%s)",
                    session_id,
                    session.place_id,
                    place_id,
                    user_id,
                )
                raise BadRequestError("This session belongs to a different place.")

            logger.info("Continuing existing session %s", session_id)
            return _QASessionContext(
                session=session,
                is_new_session=False,
                conversation_history=self.qa_repo.get_recent_messages(
                    session_id=session.id,
                    limit=10,
                ),
            )

        current_count = self.qa_repo.count_user_sessions(user_id)
        if current_count >= settings.MAX_SESSIONS_PER_USER:
            logger.warning("Session limit reached for user_id=%s (current=%s)", user_id, current_count)
            raise BadRequestError(SESSION_LIMIT_REACHED)

        title = self._generate_title_from_question(question)
        session = self.qa_repo.create_session(
            user_id=user_id,
            place_id=place_id,
            title=title,
        )
        self.db.flush()
        logger.info("Created new session %s - title: %s", session.id, title)

        return _QASessionContext(
            session=session,
            is_new_session=True,
        )

    @observe(name="place-qa")
    async def answer_question(
        self,
        place_id: str,
        request: PlaceQuestionRequest,
        user_id: int,
    ) -> PlaceQuestionResponse:

        start_time = time.monotonic()
        model_used = settings.OPENAI_CHAT_MODEL

        logger.info(
            "PlaceQA — user_id: %s, place_id: %s, question: %r, session_id: %s",
            user_id,
            place_id,
            request.question,
            request.session_id,
        )
        await self._reserve_question_usage(user_id, place_id)

        session_context = self._get_or_create_session(
            user_id=user_id,
            place_id=place_id,
            question=request.question,
            session_id=request.session_id,
        )
        session = session_context.session
        is_new_session = session_context.is_new_session
        conversation_history = session_context.conversation_history

        place = self._get_cached_place(place_id)
        if place is None:
            raise PlaceDetailNotFoundError(place_id)

        rag = await self._build_rag_context(
            place_id=place_id,
            question=request.question,
            user_id=user_id,
            session_id=str(session.id) if session else None,
            conversation_history=conversation_history,
            place=place,
            top_k=_DEFAULT_TOP_K,
            stream=False,
            build_fragments=True,
        )
        context_block = rag["context_block"]
        context_tokens = rag["context_tokens"]
        accepted_matches = rag["accepted_matches"]
        knowledge_available = rag["knowledge_available"]
        confidence_score = rag["confidence_score"]
        structured_block = rag["structured_block"]
        grounding_chunks_for_log = rag["grounding_chunks_for_log"]
        grounding_fragments = rag["grounding_fragments"]

        system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(context_block=context_block)

        fallback_reason: Optional[str] = None
        try:
            with propagate_attributes(
                user_id=str(user_id),
                session_id=str(session.id) if session else None,
                metadata={"place_id": place_id, "stream": False, "step": "answer"},
            ):
                raw_answer = await self.openai_client.chat_completion(
                    system_prompt=system_prompt,
                    user_message=request.question,
                    temperature=0.7,
                    max_tokens=800,
                )
            validated = _validate_qa_answer(raw_answer)
            if validated is None:
                logger.warning(
                    "PlaceQA produced invalid answer for place_id=%s — using fallback",
                    place_id,
                )
                answer = _build_rate_limit_fallback(place.display_name, structured_block)
                fallback_reason = "invalid_response"
            else:
                answer = validated
        except Exception as exc:
            from app.integrations.openai_client import EmbeddingRateLimitError

            if isinstance(exc, EmbeddingRateLimitError):
                logger.error(
                    "PlaceQA chat rate limited for place_id %s (user_id=%s)",
                    place_id,
                    user_id,
                    extra={
                        "event": "place_qa_chat_rate_limited",
                        "place_id": place_id,
                        "user_id": user_id,
                        "session_id": session.id if session else None,
                    },
                )
                answer = _build_rate_limit_fallback(
                    place.display_name, structured_block
                )
                fallback_reason = "rate_limited"
            else:
                logger.error(
                    "PlaceQA chat failed for place_id %s (user_id=%s): %s",
                    place_id, user_id, exc,
                )
                answer = _build_rate_limit_fallback(
                    place.display_name, structured_block
                )
                fallback_reason = "service_error"

        if fallback_reason:
            answer_source = AnswerSource.FALLBACK
        elif not knowledge_available:
            answer_source = AnswerSource.FALLBACK
        elif accepted_matches:
            answer_source = AnswerSource.RAG
        else:
            answer_source = AnswerSource.STRUCTURED_ONLY

        latency_ms = int((time.monotonic() - start_time) * 1000)

        try:
            self.qa_repo.create_message(
                session_id=session.id,
                role="user",
                content=request.question,
                token_count=estimate_tokens(request.question),
            )

            self.qa_repo.create_message(
                session_id=session.id,
                role="assistant",
                content=answer,
                token_count=estimate_tokens(answer),
                metadata_json={
                    "answer_source": answer_source,
                    "confidence_score": confidence_score,
                    "pinecone_matches": len(accepted_matches),
                },
            )

            self.db.flush()
            self.qa_repo.update_session_timestamp(session)

            self.db.commit()
            logger.info(
                "Committed messages for session %s (user %s)",
                session.id,
                user_id,
            )
        except Exception as exc:
            logger.error(
                "Failed to commit messages for session %s: %s", session.id, exc
            )
            self.db.rollback()
            raise

        self._persist_audit(
            user_id=user_id,
            place_id=place_id,
            question_text=request.question,
            knowledge_available=knowledge_available,
            pinecone_matches=len(accepted_matches),
            answer_text=answer,
            confidence_score=confidence_score,
            answer_source=answer_source,
            grounding_chunks=grounding_chunks_for_log or None,
            context_tokens=context_tokens,
            model_used=model_used,
            latency_ms=latency_ms,
            session_id=session.id,
        )

        metadata = TechnicalMetadata(
            answer_source=answer_source,
            confidence_score=confidence_score,
            knowledge_synced=knowledge_available,
            pinecone_matches=len(accepted_matches),
            model_used=model_used,
            context_tokens=context_tokens,
            grounding_fragments=grounding_fragments if grounding_fragments else None,
        )

        response_data: Dict[str, Any] = {
            "success": True,
            "session_id": session.id,
            "answer": answer,
            "is_new_session": is_new_session,
            "fallback": bool(fallback_reason),
            "fallback_reason": fallback_reason,
            "credits_deducted": 0,
            "remaining_credits": 0,
            "metadata": metadata,
        }

        if is_new_session:
            response_data["title"] = session.title

        return PlaceQuestionResponse(**response_data)

    @observe(name="place-qa-stream")
    async def stream_answer(
        self,
        place_id: str,
        question: str,
        user_id: int,
        session_id: Optional[str] = None,
        top_k: int = 5,
    ) -> AsyncGenerator[str, None]:
        start_time = time.monotonic()
        model_used = settings.OPENAI_CHAT_MODEL

        logger.info(
            "PlaceQA stream — user_id: %s, place_id: %s, question: %r, "
            "session_id: %s",
            user_id,
            place_id,
            question,
            session_id,
        )

        await self._reserve_question_usage(user_id, place_id)

        sess = None
        is_new_session = False
        conversation_history = []

        if session_id:
            sess = self.qa_repo.get_session(
                session_id=session_id,
                user_id=user_id,
            )
            if sess:
                if sess.place_id and sess.place_id != place_id:
                    logger.warning(
                        "Session %s belongs to place %s, cannot use for place %s (user=%s)",
                        session_id,
                        sess.place_id,
                        place_id,
                        user_id,
                    )
                    raise BadRequestError("This session belongs to a different place.")
                logger.info("Continuing existing session %s", session_id)
                conversation_history = self.qa_repo.get_recent_messages(
                    session_id=sess.id,
                    limit=10,
                )
            else:
                raise NotFoundError(
                    f"Session {session_id} not found or access denied"
                )

        if not sess:
            current_count = self.qa_repo.count_user_sessions(user_id)
            if current_count >= settings.MAX_SESSIONS_PER_USER:
                logger.warning("Session limit reached for user_id=%s (current=%s)", user_id, current_count)
                raise BadRequestError(SESSION_LIMIT_REACHED)
            title = self._generate_title_from_question(question)
            sess = self.qa_repo.create_session(
                user_id=user_id,
                place_id=place_id,
                title=title,
            )
            self.db.flush()
            is_new_session = True
            logger.info("Created new session %s — title: %s", sess.id, title)

        yield json.dumps(
            {
                "type": "metadata",
                "session_id": sess.id,
                "is_new_session": is_new_session,
                "place_id": place_id,
            }
        )

        place = self._get_cached_place(place_id)
        if place is None:
            logger.warning(
                "PlaceQA stream blocked — place_id %s not in DB",
                place_id,
            )
            raise PlaceDetailNotFoundError(place_id)

        rag = await self._build_rag_context(
            place_id=place_id,
            question=question,
            user_id=user_id,
            session_id=str(sess.id) if sess else None,
            conversation_history=conversation_history,
            place=place,
            top_k=top_k,
            stream=True,
        )
        context_block = rag["context_block"]
        context_tokens = rag["context_tokens"]
        accepted_matches = rag["accepted_matches"]
        knowledge_available = rag["knowledge_available"]
        confidence_score = rag["confidence_score"]
        structured_block = rag["structured_block"]
        grounding_chunks_for_log = rag["grounding_chunks_for_log"]

        system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(context_block=context_block)

        if not knowledge_available:
            answer_source = AnswerSource.FALLBACK
        elif accepted_matches:
            answer_source = AnswerSource.RAG
        else:
            answer_source = AnswerSource.STRUCTURED_ONLY

        full_answer_parts: List[str] = []
        fallback_reason: Optional[str] = None
        try:
            with propagate_attributes(
                user_id=str(user_id),
                session_id=str(sess.id) if sess else None,
                metadata={"place_id": place_id, "stream": True, "step": "answer"},
            ):
                async for token in self.openai_client.stream_chat_completion(
                    system_prompt=system_prompt,
                    user_message=question,
                    temperature=0.7,
                    max_tokens=800,
                ):
                    full_answer_parts.append(token)
                    yield json.dumps({"type": "token", "content": token})
        except Exception as exc:
            from app.integrations.openai_client import EmbeddingRateLimitError

            if isinstance(exc, EmbeddingRateLimitError):
                logger.error(
                    "PlaceQA stream rate limited for place_id %s (user_id=%s)",
                    place_id,
                    user_id,
                    extra={
                        "event": "place_qa_stream_rate_limited",
                        "place_id": place_id,
                        "user_id": user_id,
                        "session_id": sess.id if sess else None,
                    },
                )
                fallback = _build_rate_limit_fallback(
                    place.display_name, structured_block
                )
                full_answer_parts = [fallback]
                answer_source = AnswerSource.FALLBACK
                fallback_reason = "rate_limited"
                yield json.dumps({"type": "token", "content": fallback})
            else:
                logger.error(
                    "PlaceQA stream failed for place_id %s (user_id=%s): %s",
                    place_id, user_id, exc,
                )
                fallback = _build_rate_limit_fallback(
                    place.display_name, structured_block
                )
                full_answer_parts = [fallback]
                answer_source = AnswerSource.FALLBACK
                fallback_reason = "service_error"
                yield json.dumps({"type": "token", "content": fallback})

        answer = "".join(full_answer_parts)
        latency_ms = int((time.monotonic() - start_time) * 1000)

        try:
            self.qa_repo.create_message(
                session_id=sess.id,
                role="user",
                content=question,
                token_count=estimate_tokens(question),
            )
            self.qa_repo.create_message(
                session_id=sess.id,
                role="assistant",
                content=answer,
                token_count=estimate_tokens(answer),
                metadata_json={
                    "answer_source": answer_source,
                    "confidence_score": confidence_score,
                    "pinecone_matches": len(accepted_matches),
                },
            )
            self.db.flush()
            self.qa_repo.update_session_timestamp(sess)

            self.db.commit()
        except Exception as exc:
            logger.error(
                "Failed to commit messages for session %s: %s",
                sess.id,
                exc,
            )
            self.db.rollback()
            raise

        self._persist_audit(
            user_id=user_id,
            place_id=place_id,
            question_text=question,
            knowledge_available=knowledge_available,
            pinecone_matches=len(accepted_matches),
            answer_text=answer,
            confidence_score=confidence_score,
            answer_source=answer_source,
            grounding_chunks=grounding_chunks_for_log or None,
            context_tokens=context_tokens,
            model_used=model_used,
            latency_ms=latency_ms,
            session_id=sess.id,
        )

        yield json.dumps(
            {
                "type": "done",
                "title": sess.title if is_new_session else None,
                "fallback": bool(fallback_reason),
                "fallback_reason": fallback_reason,
                "metadata": {
                    "answer_source": answer_source,
                    "confidence_score": confidence_score,
                    "knowledge_synced": knowledge_available,
                    "pinecone_matches": len(accepted_matches),
                    "context_tokens": context_tokens,
                },
            }
        )
