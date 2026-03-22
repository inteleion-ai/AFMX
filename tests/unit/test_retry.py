"""
Unit tests for RetryManager and CircuitBreaker.

Added: test_node_retrying_event_emitted — verifies the new NODE_RETRYING
       event is published to the EventBus on each retry attempt.
"""
import asyncio
import pytest
from afmx.core.retry import RetryManager, CircuitBreaker, CircuitState
from afmx.models.node import RetryPolicy, CircuitBreakerPolicy
from afmx.observability.events import EventBus, EventType


@pytest.fixture
def retry_manager():
    return RetryManager()


@pytest.fixture
def default_retry():
    return RetryPolicy(retries=3, backoff_seconds=0.01, backoff_multiplier=1.0, jitter=False)


@pytest.fixture
def no_retry():
    return RetryPolicy(retries=0, backoff_seconds=0.0)


@pytest.fixture
def no_cb():
    return CircuitBreakerPolicy(enabled=False)


@pytest.fixture
def cb_policy():
    return CircuitBreakerPolicy(
        enabled=True, failure_threshold=2, recovery_timeout_seconds=0.1
    )


class TestRetryManager:

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self, retry_manager, default_retry, no_cb):
        async def handler():
            return "ok"

        result, attempts = await retry_manager.execute_with_retry(
            node_id="n1", handler=handler,
            retry_policy=default_retry, circuit_breaker_policy=no_cb,
        )
        assert result == "ok"
        assert attempts == 1

    @pytest.mark.asyncio
    async def test_retries_on_failure_then_succeeds(self, retry_manager, default_retry, no_cb):
        call_count = 0

        async def handler():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("temporary failure")
            return "recovered"

        result, attempts = await retry_manager.execute_with_retry(
            node_id="n2", handler=handler,
            retry_policy=default_retry, circuit_breaker_policy=no_cb,
        )
        assert result == "recovered"
        assert attempts == 3

    @pytest.mark.asyncio
    async def test_exhausts_retries_raises(self, retry_manager, default_retry, no_cb):
        async def handler():
            raise RuntimeError("always fails")

        with pytest.raises(RuntimeError, match="always fails"):
            await retry_manager.execute_with_retry(
                node_id="n3", handler=handler,
                retry_policy=default_retry, circuit_breaker_policy=no_cb,
            )

    @pytest.mark.asyncio
    async def test_no_retry_fails_immediately(self, retry_manager, no_retry, no_cb):
        call_count = 0

        async def handler():
            nonlocal call_count
            call_count += 1
            raise ValueError("fail")

        with pytest.raises(ValueError):
            await retry_manager.execute_with_retry(
                node_id="n4", handler=handler,
                retry_policy=no_retry, circuit_breaker_policy=no_cb,
            )
        assert call_count == 1

    def test_backoff_computation(self):
        policy = RetryPolicy(
            retries=5, backoff_seconds=1.0,
            backoff_multiplier=2.0, jitter=False,
        )
        assert RetryManager._compute_backoff(1, policy) == 1.0
        assert RetryManager._compute_backoff(2, policy) == 2.0
        assert RetryManager._compute_backoff(3, policy) == 4.0

    def test_backoff_capped_at_max(self):
        policy = RetryPolicy(
            backoff_seconds=100.0, backoff_multiplier=2.0,
            max_backoff_seconds=30.0, jitter=False,
        )
        assert RetryManager._compute_backoff(5, policy) <= 30.0

    # ─── NEW: NODE_RETRYING event emission ────────────────────────────────────

    @pytest.mark.asyncio
    async def test_node_retrying_event_emitted(self):
        """
        NODE_RETRYING must be emitted on every retry attempt (not on first failure
        that leads to final exhaustion without retry — but on each re-attempt).

        Setup:
          - RetryManager wired with an EventBus
          - Handler fails on attempts 1 and 2, succeeds on attempt 3
          - Expect exactly 2 NODE_RETRYING events (one per retry, not per failure)
        """
        bus = EventBus()
        rm = RetryManager(event_bus=bus)

        received_events = []

        async def capture(event):
            received_events.append(event)

        bus.subscribe(EventType.NODE_RETRYING, capture)

        call_count = 0

        async def handler():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("transient")
            return "ok"

        policy = RetryPolicy(retries=3, backoff_seconds=0.01, jitter=False)
        no_cb = CircuitBreakerPolicy(enabled=False)

        result, attempts = await rm.execute_with_retry(
            node_id="test-node", handler=handler,
            retry_policy=policy, circuit_breaker_policy=no_cb,
        )

        assert result == "ok"
        assert attempts == 3
        # 2 failures → 2 retrying events (emitted BEFORE each re-attempt sleep)
        assert len(received_events) == 2
        for evt in received_events:
            assert evt.type == EventType.NODE_RETRYING
            assert evt.data["node_id"] == "test-node"
            assert "attempt" in evt.data
            assert "error" in evt.data

    @pytest.mark.asyncio
    async def test_no_retrying_event_on_first_attempt_success(self):
        """No NODE_RETRYING event when handler succeeds on first attempt."""
        bus = EventBus()
        rm = RetryManager(event_bus=bus)
        events = []
        bus.subscribe(EventType.NODE_RETRYING, lambda e: events.append(e))

        async def handler():
            return "immediate"

        policy = RetryPolicy(retries=3, backoff_seconds=0.01, jitter=False)
        no_cb = CircuitBreakerPolicy(enabled=False)

        await rm.execute_with_retry(
            node_id="quick", handler=handler,
            retry_policy=policy, circuit_breaker_policy=no_cb,
        )
        assert events == []

    @pytest.mark.asyncio
    async def test_no_event_bus_does_not_crash(self):
        """RetryManager without event_bus still retries correctly — no crash."""
        rm = RetryManager()   # no event_bus
        count = []

        async def handler():
            count.append(1)
            if len(count) < 2:
                raise RuntimeError("once")
            return "done"

        policy = RetryPolicy(retries=2, backoff_seconds=0.01, jitter=False)
        no_cb = CircuitBreakerPolicy(enabled=False)

        result, attempts = await rm.execute_with_retry(
            node_id="n", handler=handler,
            retry_policy=policy, circuit_breaker_policy=no_cb,
        )
        assert result == "done"
        assert attempts == 2


class TestCircuitBreaker:

    def test_initial_state_closed(self, cb_policy):
        cb = CircuitBreaker("test", cb_policy)
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True

    def test_trips_to_open_after_threshold(self, cb_policy):
        cb = CircuitBreaker("test", cb_policy)
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

    def test_resets_on_success(self, cb_policy):
        cb = CircuitBreaker("test", cb_policy)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    @pytest.mark.asyncio
    async def test_transitions_to_half_open_after_timeout(self, cb_policy):
        import time
        cb = CircuitBreaker("test", cb_policy)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        # Simulate elapsed recovery timeout
        cb.last_failure_time = time.time() - 1.0
        assert cb.can_execute() is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_disabled_cb_always_allows(self):
        policy = CircuitBreakerPolicy(enabled=False, failure_threshold=1)
        cb = CircuitBreaker("test", policy)
        cb.record_failure()
        cb.record_failure()
        assert cb.can_execute() is True

    @pytest.mark.asyncio
    async def test_circuit_breaker_blocks_retry_manager(self, cb_policy):
        """When CB trips during retries, execute_with_retry raises immediately."""
        rm = RetryManager()
        call_count = []

        async def always_fail():
            call_count.append(1)
            raise RuntimeError("fail")

        # Threshold = 2 failures → opens after 2nd attempt
        policy = RetryPolicy(retries=5, backoff_seconds=0.01, jitter=False)

        with pytest.raises(RuntimeError):
            await rm.execute_with_retry(
                node_id="cb-node", handler=always_fail,
                retry_policy=policy, circuit_breaker_policy=cb_policy,
            )

        # CB should have opened — stopped retries early
        assert len(call_count) <= 3   # at most threshold + 1 call
