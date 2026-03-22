"""
AFMX Retry Manager

Fixes applied in this version:
  - Emits EventType.NODE_RETRYING on each retry attempt (Prometheus, WS, audit)
  - Emits EventType.CIRCUIT_BREAKER_OPEN when a breaker trips CLOSED → OPEN
  - Emits EventType.CIRCUIT_BREAKER_CLOSED when a breaker recovers → CLOSED
    (previously these events existed in Prometheus subscriber but were never fired)
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from enum import Enum
from typing import Any, Callable, Dict, Optional

from afmx.models.node import CircuitBreakerPolicy, RetryPolicy

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """Per-node circuit breaker — CLOSED / OPEN / HALF_OPEN state machine."""

    def __init__(self, node_id: str, policy: CircuitBreakerPolicy):
        self.node_id = node_id
        self.policy = policy
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.half_open_calls = 0

    def record_success(self) -> bool:
        """Record a success. Returns True if state transitioned from non-CLOSED → CLOSED."""
        was_open = self.state in (CircuitState.OPEN, CircuitState.HALF_OPEN)
        self.failure_count = 0
        self.state = CircuitState.CLOSED
        self.half_open_calls = 0
        logger.debug(f"[CB:{self.node_id}] Reset → CLOSED")
        return was_open

    def record_failure(self) -> bool:
        """Record a failure. Returns True if state transitioned to OPEN."""
        prev = self.state
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            logger.warning(f"[CB:{self.node_id}] HALF_OPEN → OPEN (probe failed)")
            return True  # newly opened

        if self.failure_count >= self.policy.failure_threshold:
            if prev != CircuitState.OPEN:
                self.state = CircuitState.OPEN
                logger.warning(
                    f"[CB:{self.node_id}] CLOSED → OPEN "
                    f"(failures={self.failure_count})"
                )
                return True  # newly opened

        return False  # no state change to OPEN

    def can_execute(self) -> bool:
        if not self.policy.enabled:
            return True

        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            elapsed = time.time() - (self.last_failure_time or 0)
            if elapsed >= self.policy.recovery_timeout_seconds:
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                logger.info(f"[CB:{self.node_id}] OPEN → HALF_OPEN (probing)")
                return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_calls < self.policy.half_open_max_calls:
                self.half_open_calls += 1
                return True
            return False

        return True


class RetryManager:
    """
    Manages retry logic:
    - Exponential backoff with optional jitter
    - Circuit breaker per node
    - NODE_RETRYING event emission on each retry
    - CIRCUIT_BREAKER_OPEN / CIRCUIT_BREAKER_CLOSED event emission on state changes
    """

    def __init__(self, event_bus=None):
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._event_bus = event_bus

    def set_event_bus(self, event_bus) -> None:
        self._event_bus = event_bus

    def get_circuit_breaker(self, node_id: str, policy: CircuitBreakerPolicy) -> CircuitBreaker:
        if node_id not in self._circuit_breakers:
            self._circuit_breakers[node_id] = CircuitBreaker(node_id, policy)
        return self._circuit_breakers[node_id]

    def reset_circuit_breaker(self, node_id: str) -> None:
        self._circuit_breakers.pop(node_id, None)

    async def execute_with_retry(
        self,
        node_id: str,
        handler: Callable,
        retry_policy: RetryPolicy,
        circuit_breaker_policy: CircuitBreakerPolicy,
        *args: Any,
        **kwargs: Any,
    ) -> tuple[Any, int]:
        """
        Execute handler with retry + circuit breaker.
        Returns (result, attempt_count). Raises last exception on exhaustion.
        """
        cb = self.get_circuit_breaker(node_id, circuit_breaker_policy)

        if not cb.can_execute():
            raise RuntimeError(
                f"Circuit breaker OPEN for node '{node_id}' — execution blocked"
            )

        last_exception: Optional[Exception] = None
        max_attempts = retry_policy.retries + 1

        for attempt in range(1, max_attempts + 1):
            try:
                logger.debug(f"[RetryManager] '{node_id}' attempt {attempt}/{max_attempts}")
                result = await handler(*args, **kwargs)

                # Success — detect recovery transition
                recovered = cb.record_success()
                if recovered:
                    await self._emit_circuit_closed(node_id)

                return result, attempt

            except Exception as exc:
                last_exception = exc

                # Detect CLOSED → OPEN transition
                newly_opened = cb.record_failure()
                if newly_opened:
                    await self._emit_circuit_open(node_id)

                if attempt == max_attempts:
                    logger.error(
                        f"[RetryManager] '{node_id}' exhausted {max_attempts} attempts. "
                        f"Error: {exc}"
                    )
                    break

                if not cb.can_execute():
                    logger.warning(
                        f"[RetryManager] '{node_id}' circuit breaker opened — stopping retries"
                    )
                    break

                delay = self._compute_backoff(attempt, retry_policy)
                logger.warning(
                    f"[RetryManager] '{node_id}' attempt {attempt} failed: {exc}. "
                    f"Retrying in {delay:.2f}s"
                )

                await self._emit_retrying(node_id, attempt, str(exc), delay)
                await asyncio.sleep(delay)

        raise last_exception

    # ─── Event emission ───────────────────────────────────────────────────────

    async def _emit_retrying(
        self, node_id: str, attempt: int, error: str, delay: float,
    ) -> None:
        if self._event_bus is None:
            return
        try:
            from afmx.observability.events import AFMXEvent, EventType
            await self._event_bus.emit(AFMXEvent(
                type=EventType.NODE_RETRYING,
                data={
                    "node_id": node_id,
                    "node_name": node_id,
                    "attempt": attempt,
                    "error": error,
                    "retry_delay_seconds": delay,
                },
            ))
        except Exception:
            pass

    async def _emit_circuit_open(self, node_id: str) -> None:
        """Emit CIRCUIT_BREAKER_OPEN — now actually called when breaker trips."""
        if self._event_bus is None:
            return
        try:
            from afmx.observability.events import AFMXEvent, EventType
            await self._event_bus.emit(AFMXEvent(
                type=EventType.CIRCUIT_BREAKER_OPEN,
                data={"node_id": node_id, "node_name": node_id},
            ))
            logger.warning(f"[RetryManager] 🔴 Circuit breaker OPENED for '{node_id}'")
        except Exception:
            pass

    async def _emit_circuit_closed(self, node_id: str) -> None:
        """Emit CIRCUIT_BREAKER_CLOSED — breaker recovered."""
        if self._event_bus is None:
            return
        try:
            from afmx.observability.events import AFMXEvent, EventType
            await self._event_bus.emit(AFMXEvent(
                type=EventType.CIRCUIT_BREAKER_CLOSED,
                data={"node_id": node_id, "node_name": node_id},
            ))
            logger.info(f"[RetryManager] 🟢 Circuit breaker CLOSED for '{node_id}'")
        except Exception:
            pass

    @staticmethod
    def _compute_backoff(attempt: int, policy: RetryPolicy) -> float:
        delay = min(
            policy.backoff_seconds * (policy.backoff_multiplier ** (attempt - 1)),
            policy.max_backoff_seconds,
        )
        if policy.jitter:
            delay *= (0.5 + random.random() * 0.5)
        return delay
