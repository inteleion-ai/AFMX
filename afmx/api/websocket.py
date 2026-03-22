"""
AFMX WebSocket Streaming
Real-time execution event streaming over WebSocket.

Fix: asyncio.Lock() is now created lazily on first use, not in __init__.
     Creating asyncio primitives outside a running event loop raises on Python 3.12+.
"""
from __future__ import annotations
import asyncio
import json
import logging
from typing import Dict, Optional, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from afmx.observability.events import AFMXEvent, EventBus, EventType

logger = logging.getLogger(__name__)

ws_router = APIRouter()


class StreamManager:
    """
    Manages active WebSocket connections and routes EventBus events
    to the appropriate subscribers.

    Each execution_id can have multiple WebSocket subscribers (e.g., multiple
    browser tabs monitoring the same execution).

    asyncio.Lock is created lazily on first use to avoid Python 3.12 deprecation.
    """

    def __init__(self):
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}
        self._lock: Optional[asyncio.Lock] = None  # lazy — created on first use

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def subscribe(self, execution_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        async with self._get_lock():
            if execution_id not in self._subscribers:
                self._subscribers[execution_id] = set()
            self._subscribers[execution_id].add(queue)
        logger.debug(f"[StreamManager] New subscriber for execution '{execution_id}'")
        return queue

    async def unsubscribe(self, execution_id: str, queue: asyncio.Queue) -> None:
        async with self._get_lock():
            if execution_id in self._subscribers:
                self._subscribers[execution_id].discard(queue)
                if not self._subscribers[execution_id]:
                    del self._subscribers[execution_id]

    async def broadcast(self, execution_id: str, event: AFMXEvent) -> None:
        async with self._get_lock():
            queues = set(self._subscribers.get(execution_id, set()))

        if not queues:
            return

        payload = json.dumps({
            "type": event.type.value,
            "execution_id": event.execution_id,
            "matrix_id": event.matrix_id,
            "data": event.data,
            "timestamp": event.timestamp,
        })

        for queue in queues:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning(
                    f"[StreamManager] Queue full for execution '{execution_id}' — dropping event"
                )

    async def broadcast_eof(self, execution_id: str) -> None:
        async with self._get_lock():
            queues = set(self._subscribers.get(execution_id, set()))

        eof = json.dumps({"type": "eof", "execution_id": execution_id})
        for queue in queues:
            try:
                queue.put_nowait(eof)
            except asyncio.QueueFull:
                pass

    def attach_to_event_bus(self, bus: EventBus) -> None:
        bus.subscribe_all(self._on_event)

    async def _on_event(self, event: AFMXEvent) -> None:
        if not event.execution_id:
            return
        await self.broadcast(event.execution_id, event)
        if event.type in (
            EventType.EXECUTION_COMPLETED,
            EventType.EXECUTION_FAILED,
            EventType.EXECUTION_ABORTED,
            EventType.EXECUTION_TIMEOUT,
        ):
            await self.broadcast_eof(event.execution_id)


# Global stream manager — Lock is created lazily on first coroutine call
stream_manager = StreamManager()


@ws_router.websocket("/ws/stream/{execution_id}")
async def execution_stream(websocket: WebSocket, execution_id: str):
    """
    WebSocket endpoint — stream real-time execution events.

    Connect to: ws://localhost:8100/afmx/ws/stream/{execution_id}

    Server pushes JSON events until execution completes, then sends {"type":"eof"}.
    """
    await websocket.accept()
    logger.info(f"[WS] Client connected for execution '{execution_id}'")

    queue = await stream_manager.subscribe(execution_id)

    try:
        await websocket.send_text(json.dumps({
            "type": "connected",
            "execution_id": execution_id,
            "message": "Streaming execution events",
        }))

        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_text(message)
                parsed = json.loads(message)
                if parsed.get("type") == "eof":
                    break
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"type": "ping"}))

    except WebSocketDisconnect:
        logger.info(f"[WS] Client disconnected from execution '{execution_id}'")
    except Exception as exc:
        logger.error(f"[WS] Error streaming execution '{execution_id}': {exc}")
    finally:
        await stream_manager.unsubscribe(execution_id, queue)
