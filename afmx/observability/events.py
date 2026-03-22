"""
AFMX Observability — Event Bus
Structured event emission for every state transition in AFMX.
Pluggable: log, push to Redis pub/sub, Prometheus, Webhook, etc.
"""
from __future__ import annotations
import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    # Execution lifecycle
    EXECUTION_STARTED = "execution.started"
    EXECUTION_COMPLETED = "execution.completed"
    EXECUTION_FAILED = "execution.failed"
    EXECUTION_ABORTED = "execution.aborted"
    EXECUTION_TIMEOUT = "execution.timeout"

    # Node lifecycle
    NODE_STARTED = "node.started"
    NODE_COMPLETED = "node.completed"
    NODE_FAILED = "node.failed"
    NODE_SKIPPED = "node.skipped"
    NODE_RETRYING = "node.retrying"
    NODE_FALLBACK = "node.fallback"

    # Engine internal
    CIRCUIT_BREAKER_OPEN = "circuit_breaker.open"
    CIRCUIT_BREAKER_CLOSED = "circuit_breaker.closed"

    # Custom user events
    CUSTOM = "custom"


@dataclass
class AFMXEvent:
    type: EventType
    execution_id: str = ""
    matrix_id: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    trace_id: Optional[str] = None


# Handler type: async function that accepts AFMXEvent
EventHandler = Callable[[AFMXEvent], Coroutine]


class EventBus:
    """
    Lightweight async event bus for AFMX observability.

    - Subscribe handlers per event type
    - Emit events to all matching handlers
    - Handlers run concurrently, errors are logged but don't block execution
    - Optional wildcard subscription (all events)
    """

    def __init__(self):
        self._handlers: Dict[str, List[EventHandler]] = {}
        self._wildcard: List[EventHandler] = []

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        key = event_type.value
        if key not in self._handlers:
            self._handlers[key] = []
        self._handlers[key].append(handler)

    def subscribe_all(self, handler: EventHandler) -> None:
        """Subscribe to ALL event types (wildcard)."""
        self._wildcard.append(handler)

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        key = event_type.value
        if key in self._handlers:
            self._handlers[key] = [h for h in self._handlers[key] if h != handler]

    async def emit(self, event: AFMXEvent) -> None:
        """
        Emit event to all subscribers.
        Errors in handlers are caught and logged — never bubble up to engine.
        """
        handlers = list(self._wildcard)
        handlers += self._handlers.get(event.type.value, [])

        if not handlers:
            return

        async def safe_call(h: EventHandler) -> None:
            try:
                await h(event)
            except Exception as exc:
                logger.error(
                    f"[EventBus] Handler error for '{event.type}': {exc}",
                    exc_info=True,
                )

        await asyncio.gather(*[safe_call(h) for h in handlers])


class LoggingEventHandler:
    """
    Default event handler that logs all AFMX events.
    Attach this for structured log output in development/production.
    """

    def __init__(self, level: int = logging.INFO):
        self.level = level

    async def __call__(self, event: AFMXEvent) -> None:
        logger.log(
            self.level,
            f"[AFMX] {event.type.value} | "
            f"exec={event.execution_id[:8] if event.execution_id else '-'} | "
            f"matrix={event.matrix_id[:8] if event.matrix_id else '-'} | "
            f"data={event.data}",
        )
