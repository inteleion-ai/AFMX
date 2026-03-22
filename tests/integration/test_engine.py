"""
Integration tests for AFMXEngine — full matrix execution flows.

All fixes applied:
  - autouse fixture clears HandlerRegistry before and after each test.
  - Removed broken asyncio.coroutine usage (removed in Python 3.11).
  - Fallback tests use ON_FAILURE edges so fallback nodes aren't executed
    twice as standalone entry nodes.

New coverage added over original:
  - CONTINUE policy → PARTIAL status
  - CRITICAL_ONLY abort policy
  - PRE_MATRIX / POST_MATRIX hooks firing (and firing on failure)
  - PRE_NODE hook receives matrix_id and matrix_name
  - NODE_RETRYING event emission
  - NODE_SKIPPED event emission
  - Fallback node activation (with fallback_used metadata)
  - Fallback not triggered on success
"""
import asyncio
import pytest
from afmx.core.engine import AFMXEngine
from afmx.core.executor import HandlerRegistry, NodeExecutor
from afmx.core.hooks import HookRegistry, HookPayload, HookType
from afmx.core.retry import RetryManager
from afmx.models.node import Node, NodeType, RetryPolicy, TimeoutPolicy
from afmx.models.edge import Edge, EdgeCondition, EdgeConditionType
from afmx.models.matrix import ExecutionMatrix, ExecutionMode, AbortPolicy
from afmx.models.execution import ExecutionContext, ExecutionRecord, ExecutionStatus
from afmx.observability.events import EventBus, EventType


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_node(
    nid: str,
    handler: str,
    priority: int = 5,
    fallback_node_id: str = None,
    retries: int = 0,
    timeout: float = 5.0,
) -> Node:
    return Node(
        id=nid, name=nid, type=NodeType.FUNCTION, handler=handler,
        priority=priority, fallback_node_id=fallback_node_id,
        retry_policy=RetryPolicy(retries=retries, backoff_seconds=0.01, jitter=False),
        timeout_policy=TimeoutPolicy(timeout_seconds=timeout),
    )


def make_edge(from_id: str, to_id: str, **condition_kwargs) -> Edge:
    if condition_kwargs:
        return Edge(**{"from": from_id, "to": to_id,
                       "condition": EdgeCondition(**condition_kwargs)})
    return Edge(**{"from": from_id, "to": to_id})


def make_engine(hook_registry=None, event_bus=None) -> AFMXEngine:
    bus = event_bus or EventBus()
    rm = RetryManager(event_bus=bus)
    executor = NodeExecutor(retry_manager=rm, hook_registry=hook_registry)
    return AFMXEngine(event_bus=bus, node_executor=executor)


def make_record(matrix: ExecutionMatrix) -> ExecutionRecord:
    return ExecutionRecord(matrix_id=matrix.id, matrix_name=matrix.name)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def register_handlers():
    """Clear and re-register test handlers before each test."""
    HandlerRegistry.clear()

    async def echo(inp, ctx, node):
        return {"echo": inp.get("input")}

    async def double(inp, ctx, node):
        val = inp.get("input", 0)
        return {"value": (val or 0) * 2}

    async def always_fail(inp, ctx, node):
        raise RuntimeError("intentional failure")

    async def slow(inp, ctx, node):
        await asyncio.sleep(5)
        return "done"

    async def write_memory(inp, ctx, node):
        ctx.set_memory("written", True)
        return {"wrote": True}

    async def read_memory(inp, ctx, node):
        return {"found": ctx.get_memory("written", False)}

    async def emit_status(inp, ctx, node):
        return {"status": "active"}

    async def fallback_handler(inp, ctx, node):
        return {"fallback": True, "recovered": True}

    async def flaky_handler(inp, ctx, node):
        """Fails on attempts 1 and 2 (via context memory counter), succeeds on 3rd."""
        count = ctx.get_memory("_flaky_count", 0)
        count += 1
        ctx.set_memory("_flaky_count", count)
        if count < 3:
            raise ConnectionError("transient error")
        return {"recovered_at": count}

    HandlerRegistry.register("echo", echo)
    HandlerRegistry.register("double", double)
    HandlerRegistry.register("always_fail", always_fail)
    HandlerRegistry.register("slow", slow)
    HandlerRegistry.register("write_memory", write_memory)
    HandlerRegistry.register("read_memory", read_memory)
    HandlerRegistry.register("emit_status", emit_status)
    HandlerRegistry.register("fallback_handler", fallback_handler)
    HandlerRegistry.register("flaky_handler", flaky_handler)

    yield

    HandlerRegistry.clear()


# ─── Sequential ───────────────────────────────────────────────────────────────

class TestSequentialExecution:

    @pytest.mark.asyncio
    async def test_single_node_success(self):
        n = make_node("n1", "echo")
        matrix = ExecutionMatrix(nodes=[n], mode=ExecutionMode.SEQUENTIAL)
        result = await make_engine().execute(
            matrix, ExecutionContext(input="hello"), make_record(matrix)
        )
        assert result.status == ExecutionStatus.COMPLETED
        assert result.completed_nodes == 1
        assert result.failed_nodes == 0

    @pytest.mark.asyncio
    async def test_linear_chain_three_nodes(self):
        n1, n2, n3 = (
            make_node("n1", "echo"),
            make_node("n2", "echo"),
            make_node("n3", "echo"),
        )
        matrix = ExecutionMatrix(
            nodes=[n1, n2, n3],
            edges=[make_edge("n1", "n2"), make_edge("n2", "n3")],
            mode=ExecutionMode.SEQUENTIAL,
        )
        result = await make_engine().execute(
            matrix, ExecutionContext(input="test"), make_record(matrix)
        )
        assert result.status == ExecutionStatus.COMPLETED
        assert result.completed_nodes == 3

    @pytest.mark.asyncio
    async def test_fail_fast_aborts_on_failure(self):
        n1 = make_node("n1", "always_fail")
        n2 = make_node("n2", "echo")
        matrix = ExecutionMatrix(
            nodes=[n1, n2], edges=[make_edge("n1", "n2")],
            mode=ExecutionMode.SEQUENTIAL, abort_policy=AbortPolicy.FAIL_FAST,
        )
        result = await make_engine().execute(matrix, ExecutionContext(), make_record(matrix))
        assert result.status == ExecutionStatus.FAILED
        assert result.failed_nodes >= 1

    @pytest.mark.asyncio
    async def test_context_passes_between_nodes(self):
        n1 = make_node("n1", "write_memory")
        n2 = make_node("n2", "read_memory")
        matrix = ExecutionMatrix(
            nodes=[n1, n2], edges=[make_edge("n1", "n2")],
            mode=ExecutionMode.SEQUENTIAL,
        )
        ctx = ExecutionContext()
        result = await make_engine().execute(matrix, ctx, make_record(matrix))
        assert result.status == ExecutionStatus.COMPLETED
        assert result.node_results["n2"]["output"]["found"] is True

    @pytest.mark.asyncio
    async def test_conditional_edge_skips_node(self):
        n1 = make_node("n1", "emit_status")
        n2 = make_node("n2", "echo")
        matrix = ExecutionMatrix(
            nodes=[n1, n2],
            edges=[make_edge(
                "n1", "n2",
                type=EdgeConditionType.ON_OUTPUT,
                output_key="status",
                output_value="inactive",   # n1 returns "active" → mismatch → skip
            )],
            mode=ExecutionMode.SEQUENTIAL,
        )
        result = await make_engine().execute(matrix, ExecutionContext(), make_record(matrix))
        assert result.status == ExecutionStatus.COMPLETED
        assert result.skipped_nodes == 1

    @pytest.mark.asyncio
    async def test_continue_policy_produces_partial_status(self):
        """With CONTINUE policy, failed nodes don't abort. Final status = PARTIAL."""
        n1 = make_node("n1", "echo")
        n2 = make_node("n2", "always_fail")
        n3 = make_node("n3", "echo")
        # No edges — all 3 are independent entry nodes
        matrix = ExecutionMatrix(
            nodes=[n1, n2, n3], edges=[],
            mode=ExecutionMode.SEQUENTIAL, abort_policy=AbortPolicy.CONTINUE,
        )
        result = await make_engine().execute(
            matrix, ExecutionContext(input="x"), make_record(matrix)
        )
        assert result.status == ExecutionStatus.PARTIAL
        assert result.failed_nodes == 1
        assert result.completed_nodes == 2

    @pytest.mark.asyncio
    async def test_critical_only_aborts_on_failure(self):
        """CRITICAL_ONLY aborts the matrix on any terminal node failure."""
        n1 = make_node("n1", "always_fail")
        n2 = make_node("n2", "echo")
        matrix = ExecutionMatrix(
            nodes=[n1, n2], edges=[make_edge("n1", "n2")],
            mode=ExecutionMode.SEQUENTIAL, abort_policy=AbortPolicy.CRITICAL_ONLY,
        )
        result = await make_engine().execute(matrix, ExecutionContext(), make_record(matrix))
        assert result.status == ExecutionStatus.FAILED
        assert result.failed_nodes >= 1


# ─── Parallel ─────────────────────────────────────────────────────────────────

class TestParallelExecution:

    @pytest.mark.asyncio
    async def test_parallel_all_nodes(self):
        nodes = [make_node(f"n{i}", "echo") for i in range(5)]
        matrix = ExecutionMatrix(nodes=nodes, mode=ExecutionMode.PARALLEL)
        result = await make_engine().execute(
            matrix, ExecutionContext(input="parallel"), make_record(matrix)
        )
        assert result.status == ExecutionStatus.COMPLETED
        assert result.completed_nodes == 5


# ─── Hybrid ───────────────────────────────────────────────────────────────────

class TestHybridExecution:

    @pytest.mark.asyncio
    async def test_hybrid_batched_execution(self):
        root = make_node("root", "echo")
        left = make_node("left", "echo")
        right = make_node("right", "echo")
        final = make_node("final", "echo")
        matrix = ExecutionMatrix(
            nodes=[root, left, right, final],
            edges=[
                make_edge("root", "left"),
                make_edge("root", "right"),
                make_edge("left", "final"),
                make_edge("right", "final"),
            ],
            mode=ExecutionMode.HYBRID,
        )
        result = await make_engine().execute(
            matrix, ExecutionContext(input="hybrid"), make_record(matrix)
        )
        assert result.status == ExecutionStatus.COMPLETED
        assert result.completed_nodes == 4


# ─── Hooks ────────────────────────────────────────────────────────────────────

class TestEngineHooks:

    @pytest.mark.asyncio
    async def test_pre_post_matrix_hooks_fire(self):
        """PRE_MATRIX fires before any node; POST_MATRIX fires after execution."""
        fired = []
        hooks = HookRegistry()

        @hooks.pre_matrix("before_matrix")
        async def pre(payload: HookPayload) -> HookPayload:
            fired.append(("pre_matrix", payload.matrix_name))
            return payload

        @hooks.post_matrix("after_matrix")
        async def post(payload: HookPayload) -> HookPayload:
            fired.append(("post_matrix", payload.matrix_name))
            return payload

        engine = make_engine(hook_registry=hooks)
        n = make_node("n1", "echo")
        matrix = ExecutionMatrix(nodes=[n], name="hook-matrix")
        result = await engine.execute(matrix, ExecutionContext(input="x"), make_record(matrix))

        assert result.status == ExecutionStatus.COMPLETED
        assert ("pre_matrix", "hook-matrix") in fired
        assert ("post_matrix", "hook-matrix") in fired

        pre_idx = next(i for i, f in enumerate(fired) if f[0] == "pre_matrix")
        post_idx = next(i for i, f in enumerate(fired) if f[0] == "post_matrix")
        assert pre_idx < post_idx

    @pytest.mark.asyncio
    async def test_post_matrix_hook_fires_on_failure(self):
        """POST_MATRIX must fire even when the matrix fails."""
        fired = []
        hooks = HookRegistry()

        @hooks.post_matrix("cleanup")
        async def post(payload: HookPayload) -> HookPayload:
            fired.append(payload.record.status if payload.record else None)
            return payload

        engine = make_engine(hook_registry=hooks)
        n = make_node("n1", "always_fail")
        matrix = ExecutionMatrix(
            nodes=[n], abort_policy=AbortPolicy.FAIL_FAST, name="fail-matrix"
        )
        result = await engine.execute(matrix, ExecutionContext(), make_record(matrix))
        assert result.status == ExecutionStatus.FAILED
        assert len(fired) == 1

    @pytest.mark.asyncio
    async def test_pre_node_hook_receives_matrix_context(self):
        """
        Executor PRE_NODE hooks must receive the correct matrix_id and matrix_name
        (injected into context.metadata by the engine before dispatch).
        """
        received = []
        hooks = HookRegistry()

        @hooks.pre_node("check_matrix_ctx")
        async def check(payload: HookPayload) -> HookPayload:
            received.append({
                "matrix_id": payload.matrix_id,
                "matrix_name": payload.matrix_name,
            })
            return payload

        engine = make_engine(hook_registry=hooks)
        n = make_node("n1", "echo")
        matrix = ExecutionMatrix(nodes=[n], name="ctx-matrix")
        await engine.execute(matrix, ExecutionContext(input="x"), make_record(matrix))

        assert len(received) == 1
        assert received[0]["matrix_id"] == matrix.id
        assert received[0]["matrix_name"] == "ctx-matrix"


# ─── Events ───────────────────────────────────────────────────────────────────

class TestEngineEvents:

    @pytest.mark.asyncio
    async def test_execution_lifecycle_events_emitted(self):
        """Core lifecycle events must be emitted."""
        bus = EventBus()
        captured_types = []

        async def capture(event):
            captured_types.append(event.type)

        bus.subscribe_all(capture)
        engine = make_engine(event_bus=bus)

        n = make_node("n1", "echo")
        matrix = ExecutionMatrix(nodes=[n])
        await engine.execute(matrix, ExecutionContext(input="x"), make_record(matrix))

        assert EventType.EXECUTION_STARTED in captured_types
        assert EventType.EXECUTION_COMPLETED in captured_types
        assert EventType.NODE_STARTED in captured_types
        assert EventType.NODE_COMPLETED in captured_types

    @pytest.mark.asyncio
    async def test_node_retrying_event_emitted(self):
        """
        NODE_RETRYING must be emitted on each retry attempt.
        flaky_handler fails on attempts 1 and 2, succeeds on 3rd.
        Expect exactly 2 NODE_RETRYING events.
        """
        bus = EventBus()
        retrying_events = []

        async def capture_retrying(event):
            retrying_events.append(event)

        bus.subscribe(EventType.NODE_RETRYING, capture_retrying)
        engine = make_engine(event_bus=bus)

        n = make_node("flaky", "flaky_handler", retries=3)
        matrix = ExecutionMatrix(nodes=[n], mode=ExecutionMode.SEQUENTIAL)
        ctx = ExecutionContext()
        result = await engine.execute(matrix, ctx, make_record(matrix))

        assert result.status == ExecutionStatus.COMPLETED
        assert len(retrying_events) == 2
        for evt in retrying_events:
            assert evt.type == EventType.NODE_RETRYING
            assert "node_id" in evt.data

    @pytest.mark.asyncio
    async def test_node_skipped_event_emitted(self):
        """NODE_SKIPPED event must be emitted for each skipped node."""
        bus = EventBus()
        skipped_events = []

        async def capture(event):
            skipped_events.append(event)

        bus.subscribe(EventType.NODE_SKIPPED, capture)
        engine = make_engine(event_bus=bus)

        n1 = make_node("n1", "emit_status")
        n2 = make_node("n2", "echo")
        matrix = ExecutionMatrix(
            nodes=[n1, n2],
            edges=[make_edge(
                "n1", "n2",
                type=EdgeConditionType.ON_OUTPUT,
                output_key="status",
                output_value="inactive",
            )],
            mode=ExecutionMode.SEQUENTIAL,
        )
        await engine.execute(matrix, ExecutionContext(), make_record(matrix))
        assert len(skipped_events) == 1
        assert skipped_events[0].data["node_id"] == "n2"


# ─── Fallback ─────────────────────────────────────────────────────────────────

class TestFallbackExecution:

    @pytest.mark.asyncio
    async def test_fallback_node_activates_on_failure(self):
        """
        When a node fails and has fallback_node_id set, the fallback runs.
        The primary node's result should be SUCCESS (via fallback).
        metadata["fallback_used"] must be True.

        The ON_FAILURE edge from n1 to n1_fb ensures n1_fb is only
        reachable via the fallback mechanism OR when n1 fails normally —
        but with the "already in node_results" check in the engine,
        n1_fb won't run twice.
        """
        engine = make_engine()

        n1 = make_node("n1", "always_fail", fallback_node_id="n1_fb")
        n1_fb = make_node("n1_fb", "fallback_handler")

        matrix = ExecutionMatrix(
            nodes=[n1, n1_fb],
            edges=[
                # ON_FAILURE edge: n1_fb is only reachable when n1 fails
                make_edge("n1", "n1_fb", type=EdgeConditionType.ON_FAILURE)
            ],
            mode=ExecutionMode.SEQUENTIAL,
        )
        ctx = ExecutionContext(input="test")
        result = await engine.execute(matrix, ctx, make_record(matrix))

        assert result.status == ExecutionStatus.COMPLETED

        n1_result = result.node_results.get("n1")
        assert n1_result is not None
        assert n1_result["status"] == "SUCCESS"
        assert n1_result["metadata"].get("fallback_used") is True
        assert n1_result["output"]["fallback"] is True

    @pytest.mark.asyncio
    async def test_fallback_not_triggered_on_success(self):
        """
        Fallback must NOT run when the primary node succeeds.
        ON_FAILURE edge from n1 → n1_fb ensures n1_fb is skipped when n1 succeeds.
        """
        fallback_called = []

        async def track_fallback(inp, ctx, node):
            fallback_called.append(True)
            return {"unexpected": True}

        HandlerRegistry.register("track_fb", track_fallback)

        engine = make_engine()
        n1 = make_node("n1", "echo", fallback_node_id="n1_fb")
        n1_fb = make_node("n1_fb", "track_fb")

        matrix = ExecutionMatrix(
            nodes=[n1, n1_fb],
            edges=[
                # n1_fb is ONLY reachable when n1 fails
                make_edge("n1", "n1_fb", type=EdgeConditionType.ON_FAILURE)
            ],
            mode=ExecutionMode.SEQUENTIAL,
        )
        result = await engine.execute(
            matrix, ExecutionContext(input="x"), make_record(matrix)
        )
        assert result.status == ExecutionStatus.COMPLETED
        assert fallback_called == []
