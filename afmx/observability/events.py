# Copyright 2026 Agentdyne9
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
AFMX Observability — Event Bus
================================
Typed, pluggable async event bus.  Every state transition in the AFMX engine
emits a structured ``AFMXEvent`` so external systems (logging, Prometheus,
webhooks, Agentability, OTEL traces) can react without coupling to internals.

Subscription model
------------------
* ``subscribe(EventType.X, handler)`` — receive only events of type X.
* ``subscribe_all(handler)``           — wildcard, receives every event.
* Errors in handlers are caught and logged; they never propagate to the engine.

Changelog
---------
v1.2.1  Added ``EventType.LAYER_STARTED`` and ``EventType.LAYER_COMPLETED``
        to replace the semantic overloading of ``EXECUTION_STARTED`` that
        was used inside ``_run_diagonal()`` to signal cognitive-layer
        boundaries.  Webhook and Agentability consumers can now distinguish
        a layer boundary from an execution start without inspecting
        ``data["diagonal_layer"]``.

        Before (broken for consumers):
            EventType.EXECUTION_STARTED  + data={"diagonal_layer": "REASON"}
        After (unambiguous):
            EventType.LAYER_STARTED      + data={"layer": "REASON", "batch_size": 3}
            EventType.LAYER_COMPLETED    + data={"layer": "REASON", "success": 3, "failed": 0}
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
    """
    All event types emitted by the AFMX engine and API layer.

    Execution lifecycle
    -------------------
    EXECUTION_STARTED   — matrix run has begun (emitted once per run)
    EXECUTION_COMPLETED — all nodes finished successfully (or CONTINUE mode)
    EXECUTION_FAILED    — a node failed under a hard abort policy
    EXECUTION_ABORTED   — cancelled via API or CCL policy
    EXECUTION_TIMEOUT   — ``global_timeout_seconds`` exceeded

    Cognitive layer boundaries (DIAGONAL mode — v1.2.1)
    ----------------------------------------------------
    LAYER_STARTED   — a CognitiveLayer batch is about to execute in parallel
    LAYER_COMPLETED — all nodes in a CognitiveLayer batch have finished

    Node lifecycle
    --------------
    NODE_STARTED   — a node handler is about to be called
    NODE_COMPLETED — node handler returned successfully
    NODE_FAILED    — node handler raised after all retries exhausted
    NODE_SKIPPED   — node was skipped due to an unsatisfied edge condition
    NODE_RETRYING  — node is being retried after a transient failure
    NODE_FALLBACK  — fallback node activated after primary node failure

    Fault tolerance
    ---------------
    CIRCUIT_BREAKER_OPEN   — circuit breaker tripped for a node
    CIRCUIT_BREAKER_CLOSED — circuit breaker recovered (half-open test passed)

    Custom
    ------
    CUSTOM — user-emitted events via ``EventBus.emit()`` directly
    """

    # ── Execution lifecycle ───────────────────────────────────────────────────
    EXECUTION_STARTED   = "execution.started"
    EXECUTION_COMPLETED = "execution.completed"
    EXECUTION_FAILED    = "execution.failed"
    EXECUTION_ABORTED   = "execution.aborted"
    EXECUTION_TIMEOUT   = "execution.timeout"

    # ── Cognitive layer boundaries (DIAGONAL mode) — v1.2.1 ──────────────────
    LAYER_STARTED   = "layer.started"    # replaces the overloaded EXECUTION_STARTED
    LAYER_COMPLETED = "layer.completed"

    # ── Node lifecycle ────────────────────────────────────────────────────────
    NODE_STARTED   = "node.started"
    NODE_COMPLETED = "node.completed"
    NODE_FAILED    = "node.failed"
    NODE_SKIPPED   = "node.skipped"
    NODE_RETRYING  = "node.retrying"
    NODE_FALLBACK  = "node.fallback"

    # ── Fault tolerance ───────────────────────────────────────────────────────
    CIRCUIT_BREAKER_OPEN   = "circuit_breaker.open"
    CIRCUIT_BREAKER_CLOSED = "circuit_breaker.closed"

    # ── Custom ────────────────────────────────────────────────────────────────
    CUSTOM = "custom"


@dataclass
class AFMXEvent:
    """
    Structured event emitted by the AFMX engine.

    Attributes
    ----------
    type         : EventType enum value.
    execution_id : UUID of the current execution (empty string if not applicable).
    matrix_id    : UUID of the matrix being executed.
    data         : Arbitrary key-value payload — content varies by event type.
    timestamp    : Unix epoch float at emission time.
    trace_id     : Optional distributed trace correlation ID (OTEL / X-Ray).
    """

    type:         EventType
    execution_id: str               = ""
    matrix_id:    str               = ""
    data:         Dict[str, Any]    = field(default_factory=dict)
    timestamp:    float             = field(default_factory=time.time)
    trace_id:     Optional[str]     = None


# Handler type alias: async callable that accepts a single AFMXEvent.
EventHandler = Callable[[AFMXEvent], Coroutine]


class EventBus:
    """
    Lightweight, thread-safe async event bus for AFMX observability.

    All handlers run concurrently via ``asyncio.gather``.  Exceptions in
    individual handlers are caught, logged, and do **not** propagate to the
    engine — the execution is never blocked by an observer.

    Example usage::

        bus = EventBus()

        @bus.subscribe(EventType.NODE_FAILED)
        async def alert_on_failure(event: AFMXEvent) -> None:
            await pagerduty.trigger(event.execution_id, event.data["error"])

        bus.subscribe_all(LoggingEventHandler())
    """

    def __init__(self) -> None:
        self._handlers:  Dict[str, List[EventHandler]] = {}
        self._wildcard:  List[EventHandler]            = []

    # ── Subscription ──────────────────────────────────────────────────────────

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Register *handler* for a specific *event_type*."""
        key = event_type.value
        self._handlers.setdefault(key, []).append(handler)

    def subscribe_all(self, handler: EventHandler) -> None:
        """Register *handler* as a wildcard — it receives every event type."""
        self._wildcard.append(handler)

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Remove a previously registered *handler* for *event_type*."""
        key = event_type.value
        if key in self._handlers:
            self._handlers[key] = [
                h for h in self._handlers[key] if h is not handler
            ]

    # ── Emission ──────────────────────────────────────────────────────────────

    async def emit(self, event: AFMXEvent) -> None:
        """
        Emit *event* to all matching subscribers.

        All handlers are called concurrently.  A handler that raises will
        have its exception logged at ERROR level; it will **not** affect
        other handlers or the calling engine code.
        """
        handlers: List[EventHandler] = list(self._wildcard)
        handlers += self._handlers.get(event.type.value, [])

        if not handlers:
            return

        async def _safe(h: EventHandler) -> None:
            try:
                await h(event)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "[EventBus] Handler error for '%s': %s",
                    event.type.value,
                    exc,
                    exc_info=True,
                )

        await asyncio.gather(*[_safe(h) for h in handlers])


class LoggingEventHandler:
    """
    Default event handler that emits structured log lines for every event.

    Attach this in development and production for immediate observability::

        bus.subscribe_all(LoggingEventHandler())
        bus.subscribe_all(LoggingEventHandler(level=logging.DEBUG))
    """

    def __init__(self, level: int = logging.INFO) -> None:
        self.level = level

    async def __call__(self, event: AFMXEvent) -> None:
        logger.log(
            self.level,
            "[AFMX] %s | exec=%s | matrix=%s | %s",
            event.type.value,
            event.execution_id[:8] if event.execution_id else "-",
            event.matrix_id[:8]    if event.matrix_id    else "-",
            event.data,
        )
