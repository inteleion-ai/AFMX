"""
Unit tests for NodeExecutor.

All executor tests use RetryManager() without event_bus — that is valid
since event_bus is an Optional parameter. The tests verify execution
correctness, not event emission (that is covered in test_retry.py and
test_engine.py).
"""
import asyncio
import pytest
from afmx.core.executor import NodeExecutor, HandlerRegistry
from afmx.core.retry import RetryManager
from afmx.core.hooks import HookRegistry, HookPayload, HookType
from afmx.core.variable_resolver import VariableResolver
from afmx.models.node import (
    Node, NodeType, NodeStatus, RetryPolicy, TimeoutPolicy, NodeConfig,
)
from afmx.models.execution import ExecutionContext


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_registry():
    """Clear HandlerRegistry before and after each test."""
    HandlerRegistry.clear()
    yield
    HandlerRegistry.clear()


def make_node(
    name: str = "test_node",
    handler: str = "test_handler",
    ntype: NodeType = NodeType.FUNCTION,
    retries: int = 0,
    timeout: float = 5.0,
    params: dict = None,
) -> Node:
    return Node(
        id=name,
        name=name,
        type=ntype,
        handler=handler,
        config=NodeConfig(params=params or {}),
        retry_policy=RetryPolicy(retries=retries, backoff_seconds=0.01, jitter=False),
        timeout_policy=TimeoutPolicy(timeout_seconds=timeout),
    )


def make_executor(hooks=None, resolver=None) -> NodeExecutor:
    # RetryManager without event_bus is valid — event_bus is Optional
    return NodeExecutor(
        retry_manager=RetryManager(),
        hook_registry=hooks,
        variable_resolver=resolver,
    )


def make_context(**kwargs) -> ExecutionContext:
    return ExecutionContext(**kwargs)


# ─── Success paths ────────────────────────────────────────────────────────────

class TestNodeExecutorSuccess:

    @pytest.mark.asyncio
    async def test_async_handler_success(self):
        async def handler(inp, ctx, node):
            return {"ok": True}

        HandlerRegistry.register("h", handler)
        result = await make_executor().execute(make_node(handler="h"), make_context())
        assert result.status == NodeStatus.SUCCESS
        assert result.output == {"ok": True}
        assert result.attempt == 1
        assert result.duration_ms is not None

    @pytest.mark.asyncio
    async def test_sync_handler_runs_in_executor(self):
        def sync_handler(inp, ctx, node):
            return "sync_result"

        HandlerRegistry.register("sync_h", sync_handler)
        result = await make_executor().execute(make_node(handler="sync_h"), make_context())
        assert result.status == NodeStatus.SUCCESS
        assert result.output == "sync_result"

    @pytest.mark.asyncio
    async def test_none_output_stored(self):
        async def handler(inp, ctx, node):
            return None

        HandlerRegistry.register("none_h", handler)
        result = await make_executor().execute(make_node(handler="none_h"), make_context())
        assert result.status == NodeStatus.SUCCESS
        assert result.output is None

    @pytest.mark.asyncio
    async def test_context_input_passed_to_handler(self):
        received = []

        async def handler(inp, ctx, node):
            received.append(inp["input"])
            return True

        HandlerRegistry.register("ctx_h", handler)
        ctx = make_context(input={"query": "hello"})
        await make_executor().execute(make_node(handler="ctx_h"), ctx)
        assert received[0] == {"query": "hello"}

    @pytest.mark.asyncio
    async def test_node_metadata_merged_into_input(self):
        received = {}

        async def handler(inp, ctx, node):
            received.update(inp["metadata"])
            return "ok"

        HandlerRegistry.register("meta_h", handler)
        node = make_node(handler="meta_h")
        node.metadata["custom_key"] = "custom_value"
        await make_executor().execute(node, make_context())
        assert received.get("custom_key") == "custom_value"


# ─── Failure paths ────────────────────────────────────────────────────────────

class TestNodeExecutorFailures:

    @pytest.mark.asyncio
    async def test_generic_exception_returns_failed(self):
        async def handler(inp, ctx, node):
            raise ValueError("bad input")

        HandlerRegistry.register("fail_h", handler)
        result = await make_executor().execute(make_node(handler="fail_h"), make_context())
        assert result.status == NodeStatus.FAILED
        assert "bad input" in result.error
        assert result.error_type == "ValueError"

    @pytest.mark.asyncio
    async def test_import_error_returns_failed(self):
        result = await make_executor().execute(
            make_node(handler="nonexistent.module.handler"),
            make_context(),
        )
        assert result.status == NodeStatus.FAILED
        assert result.error_type == "ImportError"

    @pytest.mark.asyncio
    async def test_timeout_returns_failed(self):
        async def slow(inp, ctx, node):
            await asyncio.sleep(10.0)
            return "done"

        HandlerRegistry.register("slow_h", slow)
        node = make_node(handler="slow_h", timeout=0.05)
        result = await make_executor().execute(node, make_context())
        assert result.status == NodeStatus.FAILED
        assert result.error_type == "TimeoutError"
        assert "timed out" in result.error

    @pytest.mark.asyncio
    async def test_runtime_error_returns_aborted(self):
        async def handler(inp, ctx, node):
            raise RuntimeError("circuit open")

        HandlerRegistry.register("abort_h", handler)
        result = await make_executor().execute(make_node(handler="abort_h"), make_context())
        assert result.status == NodeStatus.ABORTED

    @pytest.mark.asyncio
    async def test_retry_eventually_succeeds(self):
        attempts = []

        async def flaky(inp, ctx, node):
            attempts.append(1)
            if len(attempts) < 3:
                raise ConnectionError("temporary")
            return "recovered"

        HandlerRegistry.register("flaky_h", flaky)
        node = make_node(handler="flaky_h", retries=3)
        result = await make_executor().execute(node, make_context())
        assert result.status == NodeStatus.SUCCESS
        assert result.attempt == 3

    @pytest.mark.asyncio
    async def test_retry_exhaustion_returns_failed_or_aborted(self):
        async def always_fail(inp, ctx, node):
            raise RuntimeError("permanent")

        HandlerRegistry.register("perm_h", always_fail)
        node = make_node(handler="perm_h", retries=2)
        result = await make_executor().execute(node, make_context())
        assert result.status in (NodeStatus.FAILED, NodeStatus.ABORTED)

    @pytest.mark.asyncio
    async def test_result_always_has_timestamps(self):
        """duration_ms, started_at, finished_at must always be set — even on failure."""
        async def handler(inp, ctx, node):
            raise ValueError("fail")

        HandlerRegistry.register("ts_h", handler)
        result = await make_executor().execute(make_node(handler="ts_h"), make_context())
        assert result.started_at is not None
        assert result.finished_at is not None
        assert result.duration_ms is not None
        assert result.duration_ms >= 0


# ─── Variable resolver integration ────────────────────────────────────────────

class TestNodeExecutorVariableResolution:

    @pytest.mark.asyncio
    async def test_params_resolved_before_handler_call(self):
        received_params = {}

        async def handler(inp, ctx, node):
            received_params.update(inp["params"])
            return "ok"

        HandlerRegistry.register("var_h", handler)
        resolver = VariableResolver()
        executor = make_executor(resolver=resolver)
        ctx = make_context(input={"city": "Hyderabad"}, variables={"limit": 5})
        node = make_node(
            handler="var_h",
            params={"location": "{{input.city}}", "max": "{{variables.limit}}"},
        )
        result = await executor.execute(node, ctx)
        assert result.status == NodeStatus.SUCCESS
        assert received_params["location"] == "Hyderabad"
        assert received_params["max"] == 5

    @pytest.mark.asyncio
    async def test_unresolvable_template_stays_as_none(self):
        received = {}

        async def handler(inp, ctx, node):
            received.update(inp["params"])
            return "ok"

        HandlerRegistry.register("unres_h", handler)
        resolver = VariableResolver()
        executor = make_executor(resolver=resolver)
        node = make_node(
            handler="unres_h",
            params={"val": "{{node.nonexistent.output.field}}"},
        )
        result = await executor.execute(node, make_context())
        assert result.status == NodeStatus.SUCCESS
        assert received["val"] is None


# ─── Hook integration ─────────────────────────────────────────────────────────

class TestNodeExecutorHooks:

    @pytest.mark.asyncio
    async def test_pre_node_hook_enriches_input(self):
        received = {}

        async def handler(inp, ctx, node):
            received.update(inp["params"])
            return "ok"

        HandlerRegistry.register("hook_h", handler)
        hooks = HookRegistry()

        @hooks.pre_node("inject_key")
        async def inject(payload: HookPayload) -> HookPayload:
            payload.node_input["params"]["injected"] = "from_hook"
            return payload

        result = await make_executor(hooks=hooks).execute(
            make_node(handler="hook_h"), make_context()
        )
        assert result.status == NodeStatus.SUCCESS
        assert received.get("injected") == "from_hook"

    @pytest.mark.asyncio
    async def test_post_node_hook_receives_result(self):
        results_seen = []

        async def handler(inp, ctx, node):
            return {"val": 42}

        HandlerRegistry.register("post_h", handler)
        hooks = HookRegistry()

        @hooks.post_node("capture_result")
        async def capture(payload: HookPayload) -> HookPayload:
            results_seen.append(payload.node_result)
            return payload

        await make_executor(hooks=hooks).execute(
            make_node(handler="post_h"), make_context()
        )
        assert len(results_seen) == 1
        assert results_seen[0].status == NodeStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_post_hook_runs_even_on_failure(self):
        post_ran = []

        async def handler(inp, ctx, node):
            raise ValueError("fail")

        HandlerRegistry.register("fail_post_h", handler)
        hooks = HookRegistry()

        @hooks.post_node("always_post")
        async def post(payload: HookPayload) -> HookPayload:
            post_ran.append(
                payload.node_result.status if payload.node_result else None
            )
            return payload

        result = await make_executor(hooks=hooks).execute(
            make_node(handler="fail_post_h"), make_context()
        )
        assert result.status == NodeStatus.FAILED
        assert post_ran == [NodeStatus.FAILED]

    @pytest.mark.asyncio
    async def test_hook_error_does_not_kill_execution(self):
        """A hook that raises must be isolated — execution continues normally."""
        async def handler(inp, ctx, node):
            return "survived"

        HandlerRegistry.register("safe_h", handler)
        hooks = HookRegistry()

        @hooks.pre_node("broken_hook")
        async def broken(payload: HookPayload) -> HookPayload:
            raise RuntimeError("hook exploded")

        result = await make_executor(hooks=hooks).execute(
            make_node(handler="safe_h"), make_context()
        )
        assert result.status == NodeStatus.SUCCESS
        assert result.output == "survived"

    @pytest.mark.asyncio
    async def test_injected_handler_bypasses_registry(self):
        """Injected handler is used directly — registry is not consulted."""
        async def injected(inp, ctx, node):
            return "injected_output"

        node = make_node(handler="not_in_registry")
        result = await make_executor().execute(
            node, make_context(), injected_handler=injected
        )
        assert result.status == NodeStatus.SUCCESS
        assert result.output == "injected_output"
