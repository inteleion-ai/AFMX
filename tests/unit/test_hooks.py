"""
Unit tests for HookRegistry
"""
import asyncio
import pytest
from afmx.core.hooks import HookRegistry, HookPayload, HookType
from afmx.models.node import Node, NodeType, NodeResult, NodeStatus


def make_node(name="test") -> Node:
    return Node(id=name, name=name, type=NodeType.FUNCTION, handler="h")


def make_payload(hook_type: HookType, node=None, node_input=None, node_result=None) -> HookPayload:
    return HookPayload(
        hook_type=hook_type,
        execution_id="exec-1",
        matrix_id="mat-1",
        matrix_name="test",
        node=node,
        node_input=node_input or {},
        node_result=node_result,
    )


class TestHookRegistry:

    @pytest.mark.asyncio
    async def test_pre_node_hook_runs(self):
        registry = HookRegistry()
        called = []

        @registry.pre_node("test_hook")
        async def hook(payload: HookPayload) -> HookPayload:
            called.append("ran")
            return payload

        payload = make_payload(HookType.PRE_NODE)
        await registry.run(payload)
        assert called == ["ran"]

    @pytest.mark.asyncio
    async def test_post_node_hook_runs(self):
        registry = HookRegistry()
        captured = []

        @registry.post_node("capture_hook")
        async def hook(payload: HookPayload) -> HookPayload:
            captured.append(payload.node_result)
            return payload

        result = NodeResult(node_id="n1", node_name="n1", status=NodeStatus.SUCCESS)
        payload = make_payload(HookType.POST_NODE, node_result=result)
        await registry.run(payload)
        assert len(captured) == 1
        assert captured[0].status == NodeStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_hook_can_mutate_node_input(self):
        registry = HookRegistry()

        @registry.pre_node("enrich")
        async def enrich(payload: HookPayload) -> HookPayload:
            payload.node_input["injected"] = "added_by_hook"
            return payload

        node_input = {"params": {}}
        payload = make_payload(HookType.PRE_NODE, node_input=node_input)
        result_payload = await registry.run(payload)
        assert result_payload.node_input["injected"] == "added_by_hook"

    @pytest.mark.asyncio
    async def test_priority_order(self):
        registry = HookRegistry()
        order = []

        @registry.pre_node("second", priority=20)
        async def second(p): order.append(2); return p

        @registry.pre_node("first", priority=10)
        async def first(p): order.append(1); return p

        @registry.pre_node("third", priority=30)
        async def third(p): order.append(3); return p

        await registry.run(make_payload(HookType.PRE_NODE))
        assert order == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_hook_error_does_not_kill_execution(self):
        registry = HookRegistry()
        ran_after = []

        @registry.pre_node("bad_hook", priority=10)
        async def bad_hook(p):
            raise RuntimeError("intentional error")

        @registry.pre_node("good_hook", priority=20)
        async def good_hook(p):
            ran_after.append(True)
            return p

        await registry.run(make_payload(HookType.PRE_NODE))
        assert ran_after == [True]   # second hook still ran

    @pytest.mark.asyncio
    async def test_node_filter_specific_node(self):
        registry = HookRegistry()
        called_for = []

        @registry.pre_node("specific", node_filter="target-node")
        async def hook(p):
            called_for.append(p.node.name if p.node else None)
            return p

        target = make_node("target-node")
        other  = make_node("other-node")

        await registry.run(make_payload(HookType.PRE_NODE, node=target))
        await registry.run(make_payload(HookType.PRE_NODE, node=other))

        assert called_for == ["target-node"]   # only ran for target

    @pytest.mark.asyncio
    async def test_hook_wrong_type_not_called(self):
        registry = HookRegistry()
        called = []

        @registry.post_node("post_only")
        async def hook(p): called.append(True); return p

        # Fire PRE_NODE — should NOT trigger post_only
        await registry.run(make_payload(HookType.PRE_NODE))
        assert called == []

        # Fire POST_NODE — SHOULD trigger
        await registry.run(make_payload(HookType.POST_NODE))
        assert called == [True]

    @pytest.mark.asyncio
    async def test_disable_enable_hook(self):
        registry = HookRegistry()
        called = []

        @registry.pre_node("toggle_hook")
        async def hook(p): called.append(True); return p

        registry.disable("toggle_hook")
        await registry.run(make_payload(HookType.PRE_NODE))
        assert called == []

        registry.enable("toggle_hook")
        await registry.run(make_payload(HookType.PRE_NODE))
        assert called == [True]

    def test_list_hooks(self):
        registry = HookRegistry()

        @registry.pre_node("h1", priority=5)
        async def h1(p): return p

        @registry.post_node("h2", priority=10)
        async def h2(p): return p

        listed = registry.list_hooks()
        assert len(listed) == 2
        names = [h["name"] for h in listed]
        assert "h1" in names
        assert "h2" in names
