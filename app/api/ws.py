import asyncio
import json
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from app.core.security import (
    is_token_revoked_by_password_change,
    load_user_from_token,
    strip_bearer_prefix,
)
from app.core.websocket_manager import ConnectionManager
from app.models.user import User
from app.schemas.websocket import (
    WSChunk,
    WSClientMessage,
    WSError,
    WSStreamEnd,
    WSStreamStart,
)
from app.services.ai_chat_service import AIChatService
from app.services.place_qa_service import PlaceQAService
from app.utils.error_messages import SERVER_ERROR, sanitize_error_message

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])
manager = ConnectionManager()

_WS_RECEIVE_TIMEOUT = 300.0


@router.websocket("/ws/chat")
async def ws_chat_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket connection accepted")

    user: Optional[User] = None
    db: Optional[Session] = None
    openai_client = None
    pinecone_client = None

    try:
        try:
            raw = await asyncio.wait_for(
                websocket.receive_text(), timeout=_WS_RECEIVE_TIMEOUT
            )
        except asyncio.TimeoutError:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": "Authentication timeout. Send auth within 5 minutes.",
                }
            )
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        auth_msg = json.loads(raw)

        if auth_msg.get("type") != "auth" or not auth_msg.get("token"):
            await websocket.send_json(
                {
                    "type": "error",
                    "message": (
                        'First message must be: {"type": "auth", "token": "Bearer <jwt>"}'
                    ),
                }
            )
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        from app.database.connection import SessionLocal

        db = SessionLocal()
        token_str = strip_bearer_prefix(auth_msg["token"])

        user, payload = load_user_from_token(token_str, db)
        if user is None or payload is None:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": "Invalid or expired authentication token",
                }
            )
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            db.close()
            return

        if is_token_revoked_by_password_change(user, payload):
            await websocket.send_json(
                {
                    "type": "error",
                    "message": (
                        "Token has been revoked due to password change. "
                        "Please log in again."
                    ),
                }
            )
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            db.close()
            return

        openai_client = getattr(websocket.app.state, "openai_client", None)
        pinecone_client = getattr(websocket.app.state, "pinecone_client", None)

        if openai_client is None:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": "OpenAI client not initialized. Server may still be starting.",
                }
            )
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
            db.close()
            return

        await manager.connect(user.id, websocket)

        await websocket.send_json(
            {
                "type": "connected",
                "user_id": user.id,
                "message": "Connected to Geo Map streaming server",
            }
        )

        logger.info("WebSocket authenticated — user_id=%s", user.id)

        while True:
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(), timeout=_WS_RECEIVE_TIMEOUT
                )
            except asyncio.TimeoutError:
                logger.info("WebSocket idle timeout — user_id=%s", user.id)
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "Connection timed out due to inactivity",
                    }
                )
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return

            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": f"Invalid JSON received: {exc}",
                    }
                )
                continue

            try:
                msg = WSClientMessage(**data)
            except (ValueError, TypeError, KeyError) as exc:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": f"Invalid message format: {exc}",
                    }
                )
                continue

            try:
                if msg.type == "chat_message":
                    await _handle_chat_message(
                        websocket=websocket,
                        user=user,
                        db=db,
                        openai_client=openai_client,
                        query=msg.query,
                        session_id=msg.session_id,
                    )
                elif msg.type == "place_question":
                    if not msg.place_id:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "message": "place_id is required for place_question",
                            }
                        )
                        continue

                    if pinecone_client is None:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "message": "Pinecone client not initialized",
                            }
                        )
                        continue

                    await _handle_place_question(
                        websocket=websocket,
                        user=user,
                        db=db,
                        openai_client=openai_client,
                        pinecone_client=pinecone_client,
                        place_id=msg.place_id,
                        query=msg.query,
                        session_id=msg.session_id,
                        top_k=msg.top_k,
                    )
                else:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": (
                                f"Unknown message type: {msg.type}. "
                                f"Supported: chat_message, place_question"
                            ),
                        }
                    )

            except (RuntimeError, ValueError, TypeError, KeyError) as exc:
                logger.exception(
                    "WebSocket handler error (user_id=%s, type=%s)",
                    user.id,
                    msg.type,
                )
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": f"Request failed: {str(exc)}",
                    }
                )

    except WebSocketDisconnect:
        logger.info(
            "WebSocket disconnected — user_id=%s", user.id if user else "unknown"
        )
    except json.JSONDecodeError:
        logger.warning("WebSocket received invalid JSON")
        try:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": "Invalid JSON received",
                }
            )
        except (RuntimeError, AttributeError, OSError):
            pass
    except (RuntimeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        logger.exception("WebSocket unexpected error: %s", exc)
    finally:
        if user:
            await manager.disconnect(user.id)
        if db:
            try:
                db.close()
            except (RuntimeError, AttributeError):
                pass


async def _handle_chat_message(
    websocket: WebSocket,
    user: User,
    db: Session,
    openai_client,
    query: str,
    session_id: Optional[str],
) -> None:
    service = AIChatService(db=db, openai_client=openai_client)
    current_session_id: Optional[str] = None

    try:
        async for event_json in service.stream_chat(
            user.id,
            session_id,
            query,
        ):
            event = json.loads(event_json)
            event_type = event.get("type")

            if event_type == "metadata":
                current_session_id = event["session_id"]
                await websocket.send_json(
                    WSStreamStart(
                        session_id=current_session_id,
                        is_new_session=event.get("is_new_session", False),
                    ).model_dump()
                )
            elif event_type == "token":
                await websocket.send_json(
                    WSChunk(
                        session_id=current_session_id or "",
                        token=event["content"],
                    ).model_dump()
                )
            elif event_type == "done":
                await websocket.send_json(
                    WSStreamEnd(
                        session_id=current_session_id or "",
                        title=event.get("title"),
                    ).model_dump()
                )
    except HTTPException as exc:
        safe_msg = sanitize_error_message(
            exc.detail, f"chat user={user.id} session={session_id}"
        )
        await websocket.send_json(
            WSError(
                session_id=current_session_id,
                message=safe_msg,
            ).model_dump()
        )
    except (RuntimeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        logger.error(
            "WebSocket chat_message failed (user=%s, session=%s): %s",
            user.id,
            session_id,
            exc,
            extra={"metric": "ws.chat_message_error", "user_id": user.id},
        )
        await websocket.send_json(
            WSError(
                session_id=current_session_id,
                message="Something went wrong. Please try again.",
            ).model_dump()
        )


async def _handle_place_question(
    websocket: WebSocket,
    user: User,
    db: Session,
    openai_client,
    pinecone_client,
    place_id: str,
    query: str,
    session_id: Optional[str],
    top_k: int,
) -> None:
    service = PlaceQAService(
        db=db,
        openai_client=openai_client,
        pinecone_client=pinecone_client,
    )
    current_session_id: Optional[str] = None

    try:
        async for event_json in service.stream_answer(
            place_id=place_id,
            question=query,
            user_id=user.id,
            session_id=session_id,
            top_k=top_k,
        ):
            event = json.loads(event_json)
            event_type = event.get("type")

            if event_type == "metadata":
                current_session_id = event["session_id"]
                await websocket.send_json(
                    WSStreamStart(
                        session_id=current_session_id,
                        is_new_session=event.get("is_new_session", False),
                    ).model_dump()
                )
            elif event_type == "token":
                await websocket.send_json(
                    WSChunk(session_id=current_session_id or "", token=event["content"],
                    ).model_dump()
                )
            elif event_type == "done":
                await websocket.send_json(
                    WSStreamEnd(
                        session_id=current_session_id or "",
                        title=event.get("title"),
                    ).model_dump()
                )
    except HTTPException as exc:
        safe_msg = sanitize_error_message(
            exc.detail, f"place_qa user={user.id} place={place_id}"
        )
        await websocket.send_json(
            WSError(
                session_id=current_session_id,
                message=safe_msg,
            ).model_dump()
        )
    except (RuntimeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        logger.error(
            "WebSocket place_question failed (user=%s, place=%s): %s",
            user.id,
            place_id,
            exc,
            extra={
                "metric": "ws.place_question_error",
                "user_id": user.id,
                "place_id": place_id,
            },
        )
        await websocket.send_json(
            WSError(
                session_id=current_session_id,
                message="Unable to answer this question. Please try again.",
            ).model_dump()
        )
