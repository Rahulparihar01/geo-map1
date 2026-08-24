import asyncio
import logging
from typing import Any, Dict, Optional
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    _HEARTBEAT_INTERVAL = 30.0
    def __init__(self) -> None:
        self._connections: Dict[int, WebSocket] = {}
        self._lock: asyncio.Lock = asyncio.Lock()
        self._heartbeat_task: Optional[asyncio.Task] = None

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            old = self._connections.get(user_id)
            if old is not None:
                try:
                    await old.close(code=1000, reason="Replaced by new connection")
                except (RuntimeError, AttributeError, OSError, WebSocketDisconnect):
                    pass
            self._connections[user_id] = websocket
            logger.info(
                "WebSocket connected — user_id=%s",
                user_id,
                extra={"metric": "ws.connect", "user_id": user_id},
            )
        if self._heartbeat_task is None:
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def disconnect(self, user_id: int) -> None:
        async with self._lock:
            self._connections.pop(user_id, None)
            logger.info(
                "WebSocket disconnected — user_id=%s",
                user_id,
                extra={"metric": "ws.disconnect", "user_id": user_id},
            )
            if not self._connections and self._heartbeat_task is not None:
                self._heartbeat_task.cancel()
                self._heartbeat_task = None

    async def is_connected(self, user_id: int) -> bool:
        async with self._lock:
            return user_id in self._connections

    async def active_count(self) -> int:
        async with self._lock:
            return len(self._connections)

    async def send_json(self, user_id: int, data: Dict[str, Any]) -> bool:
        async with self._lock:
            ws = self._connections.get(user_id)
            if ws is None:
                return False
            try:
                await ws.send_json(data)
                return True
            except (RuntimeError, AttributeError, OSError, WebSocketDisconnect) as exc:
                logger.warning(
                    "WebSocket send failed for user_id=%s: %s",
                    user_id,
                    exc,
                    extra={"metric": "ws.send_failure", "user_id": user_id},
                )
                self._connections.pop(user_id, None)
                return False

    async def broadcast(self, data: Dict[str, Any]) -> None:
        async with self._lock:
            snapshot = list(self._connections.items())
        disconnected: list[int] = []
        for user_id, ws in snapshot:
            try:
                await ws.send_json(data)
            except (RuntimeError, AttributeError, OSError, WebSocketDisconnect):
                disconnected.append(user_id)
        if disconnected:
            async with self._lock:
                for uid in disconnected:
                    self._connections.pop(uid, None)
                    logger.info(
                        "Removed stale connection — user_id=%s",
                        uid,
                        extra={"metric": "ws.stale_removed", "user_id": uid},
                    )

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(self._HEARTBEAT_INTERVAL)
            async with self._lock:
                snapshot = list(self._connections.items())
            stale: list[int] = []
            for user_id, ws in snapshot:
                try:
                    await ws.send_json({"type": "ping"})
                except (RuntimeError, AttributeError, OSError, WebSocketDisconnect):
                    stale.append(user_id)
            if stale:
                async with self._lock:
                    for uid in stale:
                        self._connections.pop(uid, None)
                        logger.info(
                            "Heartbeat removed stale connection — user_id=%s",
                            uid,
                            extra={"metric": "ws.heartbeat_removed", "user_id": uid},
                        )
            async with self._lock:
                if not self._connections:
                    break
        self._heartbeat_task = None
